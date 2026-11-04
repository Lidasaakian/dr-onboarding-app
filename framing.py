"""Can a link be shown in the working area of a path page (an <iframe>)? Each site decides through its response
headers: X-Frame-Options, or Content-Security-Policy frame-ancestors, which browsers use instead when it's there.

embed_url(url)                       YouTube and Vimeo links -> their embeddable players (they allow framing).
allows_framing(headers, ours, url)   what a browser would decide for a page with these headers inside our page.
Checker.check(urls, ours)            fetches headers (public addresses only, redirects checked hop by hop) and
                                     remembers each answer for a day.
"""

from __future__ import annotations

import concurrent.futures as cf
import re
import threading
import time
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from sources import public_url

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def embed_url(url: str) -> str:
    """The URL to put in the frame: YouTube and Vimeo players for their video links, otherwise the link itself."""
    try:
        u = urlparse(url)
    except ValueError:
        return url
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = ""
    if host == "youtube.com":
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        elif u.path.startswith(("/shorts/", "/live/", "/embed/")):
            vid = u.path.split("/")[2] if len(u.path.split("/")) > 2 else ""
    elif host == "youtu.be":
        vid = u.path.lstrip("/").split("/")[0]
    if vid and _YT_ID.match(vid):
        start = (parse_qs(u.query).get("t") or parse_qs(u.query).get("start") or [""])[0].rstrip("s")
        return f"https://www.youtube.com/embed/{vid}" + (f"?start={start}" if start.isdigit() else "")
    if host == "vimeo.com":
        m = re.match(r"^/(\d+)", u.path)
        if m:
            return f"https://player.vimeo.com/video/{m.group(1)}"
    return url


def _origin(url: str) -> tuple[str, str, int | None]:
    u = urlparse(url)
    return (u.scheme, (u.hostname or "").lower(), u.port)


def _source_matches(src: str, ours: str, target: str) -> bool:
    src = src.strip().lower()
    o_scheme, o_host, o_port = _origin(ours)
    if src == "*":
        return True
    if src == "'self'":
        return _origin(target) == _origin(ours)
    if src.endswith(":") and "/" not in src:  # a scheme source such as https:
        return o_scheme == src[:-1]
    m = re.match(r"^(?:(https?)://)?(\*\.)?([a-z0-9.-]+)(?::(\d+|\*))?/?", src)
    if not m:
        return False
    scheme, wild, host, port = m.groups()
    if scheme and scheme != o_scheme:
        return False
    if wild:
        if not o_host.endswith("." + host):
            return False
    elif o_host != host:
        return False
    return port in (None, "*") or (o_port and str(o_port) == port)


def allows_framing(headers: dict, ours: str, target: str) -> bool:
    """True when a browser would show `target` (sent with these headers) inside a page from origin `ours`."""
    h = {k.lower(): v for k, v in (headers or {}).items()}
    policies = [p for p in h.get("content-security-policy", "").split(",") if p.strip()]  # several policies are comma-joined
    ancestors = []
    for p in policies:
        for d in p.split(";"):
            parts = d.strip().split()
            if parts and parts[0].lower() == "frame-ancestors":
                ancestors.append(parts[1:])
    if ancestors:  # browsers use frame-ancestors and ignore X-Frame-Options; every policy must allow us
        return all(srcs and "'none'" not in [s.lower() for s in srcs] and any(_source_matches(s, ours, target) for s in srcs)
                   for srcs in ancestors)
    xfo = h.get("x-frame-options", "").strip().lower()
    if not xfo:
        return True
    if xfo == "sameorigin":
        return _origin(target) == _origin(ours)
    return False  # DENY, ALLOW-FROM (no longer supported) or anything unknown


class Checker:
    """Remembers for a day whether each link can be framed."""

    TTL = 24 * 3600
    MAX = 2000

    def __init__(self, session: requests.Session | None = None) -> None:
        self.http = session or requests.Session()
        self.cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self.lock = threading.Lock()

    def _fetch(self, url: str, ours: str) -> bool:
        for _ in range(5):  # follow redirects by hand so every hop is checked
            if not public_url(url):
                return False
            try:
                r = self.http.get(url, timeout=8, allow_redirects=False, stream=True, headers={"User-Agent": "Mozilla/5.0"})
                r.close()
            except requests.RequestException:
                return False
            if r.is_redirect and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            return r.status_code < 400 and allows_framing(dict(r.headers), ours, url)
        return False

    def one(self, url: str, ours: str) -> dict:
        key = (url, ours)
        with self.lock:
            hit = self.cache.get(key)
            if hit and time.time() - hit[0] < self.TTL:
                return hit[1]
        embed = embed_url(url)
        if embed != url:
            ans = {"frame": True, "embed": embed}  # video players are made to be embedded
        else:
            ans = {"frame": self._fetch(url, ours), "embed": url}
        with self.lock:
            if len(self.cache) >= self.MAX:
                for k in sorted(self.cache, key=lambda k: self.cache[k][0])[: self.MAX // 4]:
                    self.cache.pop(k, None)
            self.cache[key] = (time.time(), ans)
        return ans

    def check(self, urls: list[str], ours: str) -> dict[str, dict]:
        urls = list(dict.fromkeys(u for u in urls if isinstance(u, str) and re.match(r"^https?://", u)))
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            return dict(zip(urls, ex.map(lambda u: self.one(u, ours), urls)))
