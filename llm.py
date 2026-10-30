"""DataRobot LLM Gateway (OpenAI-style chat completions), called with the app owner's DataRobot API token.

Two models, each a runtime parameter so they can be switched without a code change:
- LLM_MODEL_GENERATE  building paths from sources, converting documents, editing drafts with the LLM
- LLM_MODEL_REPORTS   turning a learner's bug report into a Jira issue and picking the project

When a parameter is empty, the app picks from the gateway catalog: the strongest Claude model for generating,
a fast one for reports. api/health lists what the catalog offers and which models are in use.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time

import requests

log = logging.getLogger("onboarding.llm")


class LLMError(RuntimeError):
    pass


def _rank(name: str, prefer: list[str]) -> tuple:
    """Sort key: preferred tier first (opus/sonnet/haiku), then the newest version number."""
    n = name.lower()
    tier = next((i for i, p in enumerate(prefer) if p in n), len(prefer))
    tail = re.sub(r"\d{6,}", "", n.split("claude", 1)[-1])
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", tail)[:2]]
    return (tier, [-x for x in nums] + [0, 0])


class Gateway:
    def __init__(self, endpoint: str, token: str, model_generate: str = "", model_reports: str = "", base_url: str = "") -> None:
        self.base = (base_url or (f"{endpoint.rstrip('/')}/genai/llmgw" if endpoint else "")).rstrip("/")
        self.token = token
        self._want = {"generate": model_generate.strip(), "reports": model_reports.strip()}
        self._catalog: list[dict] | None = None
        self._catalog_at = 0.0
        self.last_error = ""
        self.lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.token)

    # ------------------------------------------------------------------ catalog
    def catalog(self) -> list[dict]:
        if not self.enabled:
            return []
        with self.lock:
            if self._catalog is not None and time.time() - self._catalog_at < 3600:
                return self._catalog
        try:
            rows = self._catalog_rows()
            cat = []
            for m in rows or []:
                if not isinstance(m, dict):
                    continue
                name = m.get("model") or m.get("name") or m.get("id")
                if not name or m.get("isActive") is False or m.get("isDeprecated") is True:
                    continue
                cat.append({"model": name, "provider": m.get("provider", ""), "context": m.get("contextSize") or m.get("maxContext") or 0,
                            "vision": bool(m.get("supportsImages") or m.get("vision") or "vision" in json.dumps(m).lower() or "claude" in name.lower() or "gpt-4o" in name.lower())})
            with self.lock:
                self._catalog, self._catalog_at = cat, time.time()
            return cat
        except Exception as e:
            self.last_error = f"Couldn't read the LLM Gateway catalog: {e}"
            log.warning(self.last_error)
            return self._catalog or []

    def _catalog_rows(self) -> list:
        """Every catalog entry, page by page. The gateway caps the page size (a large limit is refused with 422),
        so ask for 100 at a time and follow "next"; if the server refuses paging parameters, ask without them."""
        h = {"Authorization": f"Bearer {self.token}"}
        rows: list = []
        url, params = f"{self.base}/catalog/", {"limit": 100}
        for _ in range(20):
            r = requests.get(url, headers=h, params=params, timeout=20)
            if r.status_code in (400, 422) and params:
                log.info("LLM Gateway catalog refused %s (%s): retrying without paging", params, r.text[:200])
                params = None
                r = requests.get(url, headers=h, timeout=20)
            if not r.ok:
                raise RuntimeError(f"{r.status_code} {r.reason}: {r.text[:300]}")
            data = r.json()
            if isinstance(data, list):
                return rows + data
            rows += data.get("data") or []
            nxt = data.get("next")
            if not nxt:
                break
            url, params = nxt, None
        return rows

    def model_for(self, purpose: str) -> str:
        if self._want.get(purpose):
            return self._want[purpose]
        names = [m["model"] for m in self.catalog()]
        claude = [n for n in names if "claude" in n.lower()]
        if purpose == "generate":
            prefer = ["opus", "sonnet", "haiku"]
        else:
            prefer = ["haiku", "sonnet", "opus"]
        pool = claude or [n for n in names if "gpt" in n.lower()] or names
        if not pool:
            return ""
        return sorted(pool, key=lambda n: _rank(n, prefer))[0]

    # ------------------------------------------------------------------ chat
    def chat(self, purpose: str, system: str, user: str | list, max_tokens: int = 4000, temperature: float = 0.2, timeout: int = 240) -> str:
        if not self.enabled:
            raise LLMError("The LLM Gateway isn't available (the app has no DataRobot endpoint or token).")
        model = self.model_for(purpose)
        if not model:
            raise LLMError("No LLM model is available in the LLM Gateway catalog. Set LLM_MODEL_GENERATE / LLM_MODEL_REPORTS.")
        content = user if isinstance(user, list) else [{"type": "text", "text": user}]
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
                "max_tokens": max_tokens, "temperature": temperature}
        last = None
        for attempt in range(3):
            try:
                r = requests.post(f"{self.base}/chat/completions/", json=body, timeout=timeout,
                                  headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                if r.status_code == 400 and any(isinstance(c, dict) and c.get("type") == "image_url" for c in content):
                    # the model doesn't take images: send the text only
                    body["messages"][1]["content"] = [c for c in content if c.get("type") == "text"]
                    content = body["messages"][1]["content"]
                    continue
                if not r.ok:
                    raise LLMError(f"LLM Gateway returned {r.status_code}: {r.text[:300]}")
                j = r.json()
                msg = (j.get("choices") or [{}])[0].get("message") or {}
                text = msg.get("content")
                if isinstance(text, list):
                    text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
                self.last_error = ""
                return text or ""
            except requests.RequestException as e:
                last = e
                time.sleep(2)
        self.last_error = f"Couldn't reach the LLM Gateway: {last}"
        raise LLMError(self.last_error)

    def chat_json(self, purpose: str, system: str, user: str | list, max_tokens: int = 6000, temperature: float = 0.2):
        """Ask for JSON and parse it; one retry with the parse error when the reply isn't valid JSON."""
        sys2 = system + "\n\nReply with one JSON value only: no prose before or after it, no markdown code fences."
        text = self.chat(purpose, sys2, user, max_tokens=max_tokens, temperature=temperature)
        try:
            return parse_json(text)
        except ValueError as e:
            fix = [{"type": "text", "text": "Your previous reply wasn't valid JSON (" + str(e) + "). Here it is:\n\n" + text[:20000] +
                    "\n\nReturn the same content as one valid JSON value only."}]
            return parse_json(self.chat(purpose, sys2, fix, max_tokens=max_tokens, temperature=0))


def parse_json(text: str):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON found")
    s = min(starts)
    end = max(t.rfind("}"), t.rfind("]"))
    if end <= s:
        raise ValueError("unterminated JSON")
    try:
        return json.loads(t[s:end + 1])
    except ValueError as e:
        raise ValueError(f"invalid JSON: {e}")
