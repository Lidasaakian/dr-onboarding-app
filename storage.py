"""Where the app keeps its data.

- progress/<learner key>.json  one record per learner (all paths)
- docs/<name>.json             reports inbox, uploaded content, users and roles, custom paths, bookkeeping
- blobs/<name>                 files attached to problem reports (kept when they couldn't go to Jira)

Both live in the DataRobot Files catalog item PROGRESS_FILES_ID, written with the app owner's credentials.
Without DataRobot credentials (local runs) they live in ./data.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

log = logging.getLogger("onboarding.storage")
FLUSH_SECONDS = 5


class LocalStorage:
    """Local disk. Not persistent inside a DataRobot app container."""

    mode = "local-disk"

    def __init__(self, root: Path) -> None:
        self.root = root
        (self.root / "_docs").mkdir(parents=True, exist_ok=True)

    def write(self, key: str, record: dict) -> None:
        (self.root / f"{key}.json").write_text(json.dumps(record), encoding="utf-8")

    def read_all(self) -> dict[str, dict]:
        out = {}
        for p in self.root.glob("*.json"):
            try:
                out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                log.warning("Skipping unreadable progress file %s", p)
        return out

    def read_doc(self, name: str):
        p = self.root / "_docs" / f"{name}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def write_doc(self, name: str, obj) -> None:
        p = self.root / "_docs" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding="utf-8")

    def list_docs(self, prefix: str) -> list[str]:
        return sorted(p.stem for p in (self.root / "_docs").glob(f"{prefix}*.json"))

    def write_blob(self, name: str, data: bytes) -> None:
        p = self.root / "_blobs" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def read_blob(self, name: str) -> bytes | None:
        p = self.root / "_blobs" / name
        return p.read_bytes() if p.exists() else None


class DataRobotFilesStorage:
    """A DataRobot Files catalog item."""

    mode = "datarobot-files"

    def __init__(self, files_id: str, token: str, endpoint: str) -> None:
        import datarobot as dr
        from datarobot.fs import DataRobotFileSystem

        dr.Client(token=token, endpoint=endpoint)
        self.fs = DataRobotFileSystem()
        self.created_new = not files_id
        if not files_id:
            files_id = self.fs.create_catalog_item_dir()
            log.warning("PROGRESS_FILES_ID is not set. Created Files catalog item %s; set the runtime parameter to keep progress.", files_id)
        self.files_id = files_id

    def write(self, key: str, record: dict) -> None:
        with self.fs.open(f"dr://{self.files_id}/progress/{key}.json", "w") as f:
            f.write(json.dumps(record))

    def read_all(self) -> dict[str, dict]:
        out = {}
        try:
            paths = self.fs.glob(f"dr://{self.files_id}/progress/*.json")
        except FileNotFoundError:
            return out
        for p in paths:
            key = p.rsplit("/", 1)[-1].removesuffix(".json")
            try:
                with self.fs.open(p if p.startswith("dr://") else f"dr://{p}", "r") as f:
                    out[key] = json.loads(f.read())
            except Exception:  # one bad file shouldn't hide everyone else
                log.exception("Skipping unreadable progress file %s", p)
        return out

    def read_doc(self, name: str):
        try:
            with self.fs.open(f"dr://{self.files_id}/docs/{name}.json", "r") as f:
                return json.loads(f.read())
        except FileNotFoundError:
            return None

    def write_doc(self, name: str, obj) -> None:
        with self.fs.open(f"dr://{self.files_id}/docs/{name}.json", "w") as f:
            f.write(json.dumps(obj))

    def list_docs(self, prefix: str) -> list[str]:
        try:
            paths = self.fs.glob(f"dr://{self.files_id}/docs/{prefix}*.json")
        except FileNotFoundError:
            return []
        return sorted(p.rsplit("/", 1)[-1].removesuffix(".json") for p in paths)

    def write_blob(self, name: str, data: bytes) -> None:
        with self.fs.open(f"dr://{self.files_id}/blobs/{name}", "wb") as f:
            f.write(data)

    def read_blob(self, name: str) -> bytes | None:
        try:
            with self.fs.open(f"dr://{self.files_id}/blobs/{name}", "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None


def make_storage(endpoint: str, token: str, files_id: str, local_dir: Path):
    problems = []
    if endpoint and token:
        try:
            return DataRobotFilesStorage(files_id, token, endpoint), problems
        except Exception as e:  # missing fsspec, Files not enabled, permissions...
            log.exception("DataRobot Files storage unavailable; falling back to local disk")
            problems.append(f"DataRobot Files storage unavailable ({type(e).__name__}: {e}). Data is kept on local disk and lost on restart.")
    else:
        problems.append("No DATAROBOT_ENDPOINT / DATAROBOT_API_TOKEN: running locally with ./data storage.")
    return LocalStorage(local_dir), problems


class ProgressStore:
    """In-memory copy of everyone's records, written through to storage in the background."""

    def __init__(self, backend) -> None:
        self.backend = backend
        self.lock = threading.Lock()
        self.records: dict[str, dict] = {}
        self.loaded = False
        self.dirty: set[str] = set()
        threading.Thread(target=self._flusher, daemon=True).start()

    def _ensure_loaded(self) -> None:
        if self.loaded:
            return
        try:
            data = self.backend.read_all()
        except Exception:
            log.exception("Could not read saved progress")
            data = {}
        with self.lock:
            for k, v in data.items():
                self.records.setdefault(k, v)
            self.loaded = True

    def resolve_key(self, uid_key: str, email_key: str, email: str) -> str:
        """Existing records win, so a learner keeps one record whether they come in with their DataRobot login
        (keyed by user id) or through the external-share link (only their email is known)."""
        self._ensure_loaded()
        with self.lock:
            if uid_key and uid_key in self.records:
                return uid_key
            if email_key and email_key in self.records:
                return email_key
            if email:
                for k, v in self.records.items():
                    if (v.get("email") or "").lower() == email.lower():
                        return k
        return uid_key or email_key

    def get(self, key: str) -> dict | None:
        self._ensure_loaded()
        with self.lock:
            rec = self.records.get(key)
            return json.loads(json.dumps(rec)) if rec else None

    def update(self, key: str, fn) -> dict:
        """Apply fn(record) under the lock and schedule a write. Returns a copy of the new record."""
        self._ensure_loaded()
        with self.lock:
            rec = self.records.get(key) or {}
            fn(rec)
            rec["savedAt"] = time.time()
            self.records[key] = rec
            self.dirty.add(key)
            return json.loads(json.dumps(rec))

    def exists(self, key: str) -> bool:
        self._ensure_loaded()
        with self.lock:
            return key in self.records

    def all(self) -> dict[str, dict]:
        self._ensure_loaded()
        with self.lock:
            return json.loads(json.dumps(self.records))

    def _flusher(self) -> None:
        while True:
            time.sleep(FLUSH_SECONDS)
            with self.lock:
                pending = {k: json.loads(json.dumps(self.records[k])) for k in self.dirty}
                self.dirty.clear()
            for k, rec in pending.items():
                try:
                    self.backend.write(k, rec)
                except Exception:
                    log.exception("Saving progress for %s failed; will retry", k)
                    with self.lock:
                        self.dirty.add(k)


class DocStore:
    """Small JSON documents (reports, uploaded content, bookkeeping), cached in memory and written straight away."""

    def __init__(self, backend) -> None:
        self.backend = backend
        self.lock = threading.Lock()
        self.cache: dict[str, object] = {}

    def get(self, name: str, default=None):
        with self.lock:
            if name not in self.cache:
                try:
                    self.cache[name] = self.backend.read_doc(name)
                except Exception:
                    log.exception("Could not read %s", name)
                    return default
            v = self.cache[name]
            return default if v is None else json.loads(json.dumps(v))

    def names(self, prefix: str) -> list[str]:
        """Names of the stored documents that start with prefix (for example every custom path). Deleted
        documents (written as null) are left out."""
        try:
            stored = set(self.backend.list_docs(prefix))
        except Exception:
            log.exception("Could not list %s*", prefix)
            stored = set()
        with self.lock:
            stored |= {k for k in self.cache if k.startswith(prefix)}
        return sorted(k for k in stored if self.get(k) is not None)

    def delete(self, name: str) -> None:
        """Documents can't be removed from a Files item reliably, so a deleted one is written as null."""
        with self.lock:
            self.backend.write_doc(name, None)
            self.cache[name] = None

    def put(self, name: str, obj) -> None:
        with self.lock:
            self.backend.write_doc(name, obj)
            self.cache[name] = json.loads(json.dumps(obj))

    def mutate(self, name: str, default, fn):
        """Read-modify-write under one lock (so two reports at once don't overwrite each other)."""
        with self.lock:
            if name not in self.cache:
                self.cache[name] = self.backend.read_doc(name)
            cur = self.cache[name]
            cur = json.loads(json.dumps(cur)) if cur is not None else default
            result = fn(cur)
            self.backend.write_doc(name, cur)
            self.cache[name] = cur
            return result
