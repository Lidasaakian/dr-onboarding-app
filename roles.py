"""Who can do what.

- System admins: the emails in the MANAGER_EMAILS runtime parameter. Always admins; can't lose Admin in the app.
- Admins (in the app): see and manage every path, the dashboard and problem reports, and invite people.
- Authors (in the app): create learning paths and own what they create.
- Owners: everyone listed on a path (its creator plus co-owners). They see that path's progress, problem
  reports and content, whatever their role.

The list of invited users lives in the app's Files item (docs/users.json), so changes apply straight away.
Roles are checked on every request (never cached with the visitor's profile), so a removed admin loses
access on their next click.
"""

from __future__ import annotations

import re
import time

ROLES = ("admin", "author")
DOMAIN = "datarobot.com"
_EMAIL = re.compile(r"^[a-z0-9._%+'-]+@[a-z0-9.-]+\.[a-z]{2,}$")
SEEN_EVERY_MS = 6 * 3600 * 1000  # how often "last seen" is written (each write goes to the Files item)


def now_ms() -> float:
    return time.time() * 1000


def normalize_email(raw: str) -> str:
    """'first.last' or 'First.Last@DataRobot.com' -> 'first.last@datarobot.com'. Raises ValueError otherwise."""
    e = (raw or "").strip().lower()
    if e and "@" not in e:
        e = f"{e}@{DOMAIN}"
    if not _EMAIL.match(e):
        raise ValueError("Enter a valid email address.")
    if not e.endswith("@" + DOMAIN):
        raise ValueError(f"Only @{DOMAIN} emails can be invited.")
    return e


class Users:
    def __init__(self, docs, system_admins: set[str]) -> None:
        self.docs = docs
        self.system = {e.lower() for e in system_admins}
        self._seen: dict[str, float] = {}

    # ------------------------------------------------------------------ reading
    def _doc(self) -> dict:
        d = self.docs.get("users", {}) or {}
        d.setdefault("users", {})
        d.setdefault("log", [])
        return d

    def roles_of(self, email: str) -> set[str]:
        email = (email or "").lower()
        if not email:
            return set()
        roles = set(((self._doc()["users"].get(email) or {}).get("roles")) or [])
        if email in self.system:
            roles.add("admin")
        return roles & set(ROLES)

    def is_system(self, email: str) -> bool:
        return (email or "").lower() in self.system

    def listing(self) -> list[dict]:
        users = self._doc()["users"]
        out = []
        for email in sorted(set(users) | self.system):
            u = users.get(email) or {}
            out.append({
                "email": email,
                "name": u.get("name") or "",
                "roles": sorted(self.roles_of(email), key=ROLES.index),
                "system": email in self.system,
                "addedBy": u.get("addedBy") or "",
                "addedAt": u.get("addedAt"),
                "lastSeen": u.get("lastSeen"),
                "invited": bool(u.get("invited")),
            })
        return out

    # ------------------------------------------------------------------ writing
    def _log(self, d: dict, who: str, what: str) -> None:
        d["log"].append({"at": now_ms(), "by": who, "what": what})
        d["log"] = d["log"][-500:]

    def invite(self, raw_email: str, by: str) -> dict:
        email = normalize_email(raw_email)

        def fn(d):
            d.setdefault("users", {}); d.setdefault("log", [])
            u = d["users"].get(email)
            if u and u.get("invited"):
                return u
            u = {**(u or {}), "invited": True, "roles": (u or {}).get("roles", []), "addedBy": by, "addedAt": now_ms()}
            d["users"][email] = u
            self._log(d, by, f"invited {email}")
            return u
        self.docs.mutate("users", {}, fn)
        return next(x for x in self.listing() if x["email"] == email)

    def set_roles(self, email: str, roles: list[str], by: str) -> dict:
        email = (email or "").lower()
        roles = [r for r in ROLES if r in set(roles or [])]
        if email in self.system and "admin" not in roles:
            raise PermissionError("System admins are set in the app's runtime parameters and keep the Admin role.")

        def fn(d):
            d.setdefault("users", {}); d.setdefault("log", [])
            u = d["users"].get(email)
            if not u and email not in self.system:
                raise KeyError(email)
            u = u or {"invited": True, "addedBy": "Runtime parameters", "addedAt": None}
            before = sorted(u.get("roles") or [])
            u["roles"] = [r for r in roles if not (r == "admin" and email in self.system)]  # system admin role isn't stored
            added = [r for r in u["roles"] if r not in before]
            # the welcome banner: roles given and not acknowledged yet ("Got it"); roles taken away drop out of it
            pending = [r for r in ((u.get("welcome") or {}).get("roles") or []) if r in u["roles"]]
            pending = [r for r in ROLES if r in set(pending) | set(added)]
            if added:
                u["welcome"] = {"roles": pending, "by": by, "at": now_ms()}
            elif pending:
                u["welcome"]["roles"] = pending
            else:
                u.pop("welcome", None)
            d["users"][email] = u
            self._log(d, by, f"roles of {email}: {', '.join(before) or 'none'} -> {', '.join(roles) or 'none'}")
            return added
        added = self.docs.mutate("users", {}, fn)
        return {**next(x for x in self.listing() if x["email"] == email), "added": added}

    def welcome_of(self, email: str) -> dict | None:
        """Roles given to this person that they haven't acknowledged yet: {"roles": [...], "by": name, "at": ms}."""
        w = (self._doc()["users"].get((email or "").lower()) or {}).get("welcome")
        return w if w and w.get("roles") else None

    def dismiss_welcome(self, email: str) -> None:
        email = (email or "").lower()

        def fn(d):
            u = (d.get("users") or {}).get(email)
            if u:
                u.pop("welcome", None)
        if self.welcome_of(email):
            self.docs.mutate("users", {}, fn)

    def remove(self, email: str, by: str) -> None:
        email = (email or "").lower()
        if email in self.system:
            raise PermissionError("System admins are set in the app's runtime parameters and can't be removed here.")

        def fn(d):
            d.setdefault("users", {}); d.setdefault("log", [])
            if email not in d["users"]:
                raise KeyError(email)
            d["users"].pop(email)
            self._log(d, by, f"removed {email}")
        self.docs.mutate("users", {}, fn)

    def seen(self, email: str, name: str) -> None:
        """Record when an invited user (or system admin) last opened the app, at most every few hours."""
        email = (email or "").lower()
        if not email:
            return
        now = now_ms()
        if now - self._seen.get(email, 0) < SEEN_EVERY_MS:
            return
        self._seen[email] = now
        users = self._doc()["users"]
        if email not in users and email not in self.system:
            return

        def fn(d):
            d.setdefault("users", {}); d.setdefault("log", [])
            u = d["users"].setdefault(email, {"invited": False, "roles": [], "addedBy": "Runtime parameters", "addedAt": None})
            u["lastSeen"] = now
            if name:
                u["name"] = name
        try:
            self.docs.mutate("users", {}, fn)
        except Exception:  # last-seen is a nicety; never block a page view on it
            pass
