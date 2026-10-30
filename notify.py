"""Slack notifications.

Channel messages go through an incoming webhook (runtime parameter SLACK_WEBHOOK_URL):
- a message for every problem reported (learning path, DataRobot bug with its Jira key, or to the system admins)
- a weekly summary on Mondays from 09:00 Europe/Dublin: inactive learners, open reports, new completions

Direct messages go through a Slack bot token (runtime parameter SLACK_BOT_TOKEN, a credential; the bot needs the
chat:write, users:read and users:read.email scopes):
- a DM to someone given the Admin or Author role, with the same text as the welcome banner in the app
"""

from __future__ import annotations

import logging
import os
import threading
import time

import requests

log = logging.getLogger("onboarding.slack")


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link(url: str, text: str) -> str:
    return f"<{url}|{_esc(text)}>" if url else _esc(text)


class Slack:
    def __init__(self, webhook: str, app_url: str) -> None:
        self.webhook = webhook.strip()
        self.app_url = app_url.rstrip("/")
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return self.webhook.startswith(("https://", "http://"))

    def url(self, path: str = "") -> str:
        return f"{self.app_url}/{path.lstrip('/')}" if self.app_url else ""

    def post(self, text: str, background: bool = True) -> bool:
        if not self.enabled:
            return False

        def send() -> bool:
            try:
                r = requests.post(self.webhook, json={"text": text, "unfurl_links": False}, timeout=10)
                if not r.ok:
                    self.last_error = f"Slack returned {r.status_code}: {r.text[:200]}"
                    log.warning(self.last_error)
                    return False
                self.last_error = ""
                return True
            except requests.RequestException as e:
                self.last_error = f"Couldn't reach Slack: {e}"
                log.warning(self.last_error)
                return False

        if background:
            threading.Thread(target=send, daemon=True).start()
            return True
        return send()

    def report(self, r: dict) -> None:
        kind = r.get("kind") or "path"
        where = link(self.url(f"{r['path']}/#{r.get('anchor') or ''}"), f"{r['pathTitle']} · {r['itemLabel'] or 'general'}")
        title = {"bug": ":beetle: *DataRobot bug reported*", "system": ":rotating_light: *Problem reported to the system admins*"}.get(kind, ":triangular_flag_on_post: *Problem reported*")
        jira = r.get("jira") or {}
        extra = ""
        if jira.get("key"):
            extra = f"\nJira: {link(jira.get('url', ''), jira['key'])} ({_esc(jira.get('project', ''))})"
        elif kind == "bug" and jira.get("error"):
            extra = f"\nNot sent to Jira: {_esc(jira['error'][:200])}"
        self.post(
            f"{title} by {_esc(r['name'])} ({_esc(r['email'])})\n"
            f"{where}\n>{_esc(r['message']).replace(chr(10), chr(10) + '>')}{extra}\n"
            f"{link(self.url('admin/#reports'), 'Open Problem reports')}"
        )

    def weekly(self, inactive: list[dict], open_reports: int, completed: list[dict]) -> bool:
        lines = [":calendar: *Onboarding weekly summary*"]
        if inactive:
            lines.append(f"*No progress for 7+ days ({len(inactive)}):*")
            for x in inactive[:25]:
                lines.append(f"• {_esc(x['name'])} — {_esc(x['path'])}, {x['days']} days, {_esc(x['pace'])}")
            if len(inactive) > 25:
                lines.append(f"…and {len(inactive) - 25} more")
        else:
            lines.append("Everyone who has started is active. :white_check_mark:")
        if completed:
            lines.append(f"*Completed last week ({len(completed)}):* " + ", ".join(f"{_esc(c['name'])} ({_esc(c['path'])})" for c in completed))
        lines.append(f"Open problem reports: *{open_reports}*")
        if self.app_url:
            lines.append(link(self.url(""), "Open the onboarding hub"))
        return self.post("\n".join(lines), background=False)


# --------------------------------------------------------------------------- welcome (banner in the app + Slack DM)

def welcome_text(roles: list[str], by: str) -> dict:
    """Title, text and main action for someone who was just given roles. The same words go in the banner and the DM."""
    admin, author = "admin" in roles, "author" in roles
    by = by or "An admin"
    if admin and author:
        return {"title": "You're now an admin and an author",
                "text": f"{by} gave you the Admin and Author roles. You can manage every learning path, see team progress and problem reports, "
                        "invite people, and create learning paths: by hand, or from Jira, Confluence, GitHub and files with the LLM.",
                "action": {"label": "Open Admin", "path": "admin/"}}
    if admin:
        return {"title": "You're now an admin",
                "text": f"{by} gave you the Admin role. You can manage every learning path, see team progress and problem reports, and invite people.",
                "action": {"label": "Open Admin", "path": "admin/"}}
    return {"title": "You're now an author",
            "text": f"{by} gave you the Author role. You can create learning paths: by hand, or from Jira, Confluence, GitHub and files with the LLM. "
                    "You own the paths you create and see their progress and problem reports.",
            "action": {"label": "Create a learning path", "path": "admin/#create"}}


class SlackBot:
    """Slack Web API with a bot token: look people up by email (name, photo) and send them direct messages."""
    API = os.getenv("SLACK_API_URL", "https://slack.com/api/")  # overridable for tests

    def __init__(self, token: str, app_url: str) -> None:
        self.token = (token or "").strip()
        self.app_url = app_url.rstrip("/")
        self.last_error = ""
        self._people: dict[str, tuple[float, dict | None]] = {}
        self._pending: set[str] = set()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.token.startswith("xox")

    def url(self, path: str = "") -> str:
        return f"{self.app_url}/{path.lstrip('/')}" if self.app_url else ""

    def _call(self, method: str, http: str = "GET", **data) -> dict:
        h = {"Authorization": f"Bearer {self.token}"}
        if http == "GET":
            r = requests.get(self.API + method, headers=h, params=data, timeout=10)
        else:
            r = requests.post(self.API + method, headers={**h, "Content-Type": "application/json; charset=utf-8"}, json=data, timeout=10)
        try:
            j = r.json()
        except ValueError:
            j = {"ok": False, "error": f"HTTP {r.status_code}"}
        if not j.get("ok"):
            err = j.get("error") or f"HTTP {r.status_code}"
            if err == "missing_scope":
                err += f" (the bot needs {j.get('needed') or 'chat:write, users:read and users:read.email'})"
            raise RuntimeError(err)
        return j

    def person(self, email: str) -> dict | None:
        """{"id", "name", "firstName", "title", "image"} for a Slack user, kept for 6 hours (2 hours when not found)."""
        email = (email or "").strip().lower()
        if not self.enabled or not email:
            return None
        with self._lock:
            hit = self._people.get(email)
            if hit and time.time() - hit[0] < (6 * 3600 if hit[1] else 2 * 3600):
                return hit[1]
        try:
            u = self._call("users.lookupByEmail", email=email)["user"]
            p = u.get("profile") or {}
            out = {"id": u["id"], "name": p.get("real_name") or u.get("real_name") or "", "firstName": p.get("first_name") or "",
                   "title": (p.get("title") or "").strip(), "image": p.get("image_192") or p.get("image_72") or ""}
            if p.get("is_custom_image") is False and "gravatar.com" in out["image"]:
                out["image"] = ""  # Slack's default avatar: show initials instead
        except RuntimeError as e:
            if str(e) != "users_not_found":
                self.last_error = f"Slack bot: {e}"
                log.warning("Slack lookup for %s failed: %s", email, e)
            out = None
        except requests.RequestException as e:
            self.last_error = f"Couldn't reach Slack: {e}"
            return None
        with self._lock:
            self._people[email] = (time.time(), out)
        return out

    def photo(self, email: str) -> str:
        """The person's Slack photo URL, without waiting: a cache miss is looked up in the background (the page shows
        initials until then)."""
        email = (email or "").strip().lower()
        if not self.enabled or not email:
            return ""
        with self._lock:
            hit = self._people.get(email)
            fresh = hit and time.time() - hit[0] < (6 * 3600 if hit[1] else 2 * 3600)
            pending = email in self._pending
            if not fresh and not pending:
                self._pending.add(email)
        if not fresh and not pending:
            def look():
                try:
                    self.person(email)
                finally:
                    with self._lock:
                        self._pending.discard(email)
            threading.Thread(target=look, daemon=True).start()
        return ((hit or (0, None))[1] or {}).get("image", "") if hit else ""

    def dm(self, email: str, text: str, background: bool = True) -> bool:
        if not self.enabled:
            return False

        def send() -> bool:
            who = self.person(email)
            if not who:
                log.info("No Slack user for %s: welcome DM not sent", email)
                return False
            try:
                self._call("chat.postMessage", "POST", channel=who["id"], text=text, unfurl_links=False, unfurl_media=False)
                self.last_error = ""
                return True
            except RuntimeError as e:
                self.last_error = f"Slack bot couldn't send a DM: {e}"
                log.warning(self.last_error)
                return False
            except requests.RequestException as e:
                self.last_error = f"Couldn't reach Slack: {e}"
                return False

        if background:
            threading.Thread(target=send, daemon=True).start()
            return True
        return send()

    def welcome_message(self, name: str, roles: list[str], by: str) -> str:
        w = welcome_text(roles, by)
        first = (name or "").strip().split(" ")[0]
        links = " · ".join([link(self.url(w["action"]["path"]), w["action"]["label"]), link(self.url(""), "Open the onboarding hub")]) if self.app_url else ""
        return f"*{_esc(w['title'])} in DataRobot Onboarding*\n" + (f"Hi {_esc(first)}, " if first else "") + _esc(w["text"]) + (f"\n{links}" if links else "")

    def welcome(self, email: str, name: str, roles: list[str], by: str, background: bool = True) -> bool:
        """DM someone who was just given roles. Their first name comes from Slack when it has one."""
        if not self.enabled:
            return False

        def send() -> bool:
            who = self.person(email)
            return self.dm(email, self.welcome_message((who or {}).get("firstName") or name, roles, by), background=False)

        if background:
            threading.Thread(target=send, daemon=True).start()
            return True
        return send()
