"""A small JSON-file backed persistent store for cross-session agent memory.

LangGraph's ``BaseStore`` only requires ``batch``/``abatch`` to be implemented;
the higher-level ``get``/``put``/``search``/``list_namespaces`` helpers delegate
to ``batch``. This implementation persists every record to a JSON file so the
assistant remembers project context between runs.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from langgraph.store.base import BaseStore, GetOp, PutOp, SearchOp, ListNamespacesOp, Item, SearchItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JsonFileStore(BaseStore):
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._records: dict[tuple[str, ...], dict[str, dict]] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []
        for rec in data:
            ns = tuple(rec["namespace"])
            self._records.setdefault(ns, {})[rec["key"]] = rec

    def _save(self) -> None:
        out: list[dict] = []
        for ns, keys in self._records.items():
            out.extend(keys.values())
        os_dir = self._path
        import os

        os.makedirs(os.path.dirname(os_dir) or ".", exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

    def batch(self, ops: list) -> list:
        return self._execute(ops)

    async def abatch(self, ops: list) -> list:
        return self._execute(ops)

    def _execute(self, ops: list) -> list:
        results: list = []
        changed = False
        with self._lock:
            for op in ops:
                if isinstance(op, GetOp):
                    ns = tuple(op.namespace)
                    rec = self._records.get(ns, {}).get(op.key)
                    if rec is None:
                        results.append(None)
                    else:
                        results.append(
                            Item(
                                namespace=tuple(rec["namespace"]),
                                key=rec["key"],
                                value=rec["value"],
                                created_at=datetime.fromisoformat(rec["created_at"]),
                                updated_at=datetime.fromisoformat(rec["updated_at"]),
                            )
                        )
                elif isinstance(op, PutOp):
                    ns = tuple(op.namespace)
                    if op.value is None:
                        self._records.get(ns, {}).pop(op.key, None)
                    else:
                        now = _now().isoformat()
                        existing = self._records.get(ns, {}).get(op.key)
                        created = existing["created_at"] if existing else now
                        self._records.setdefault(ns, {})[op.key] = {
                            "namespace": list(ns),
                            "key": op.key,
                            "value": op.value,
                            "created_at": created,
                            "updated_at": now,
                        }
                    changed = True
                    results.append(None)
                elif isinstance(op, SearchOp):
                    prefix = tuple(op.namespace_prefix)
                    matches: list[SearchItem] = []
                    for ns, keys in self._records.items():
                        if len(ns) < len(prefix):
                            continue
                        if any(ns[i] != prefix[i] for i in range(len(prefix))):
                            continue
                        for rec in keys.values():
                            value = rec["value"] or {}
                            if op.filter and not _matches_filter(value, op.filter):
                                continue
                            matches.append(
                                SearchItem(
                                    namespace=tuple(rec["namespace"]),
                                    key=rec["key"],
                                    value=value,
                                    created_at=datetime.fromisoformat(rec["created_at"]),
                                    updated_at=datetime.fromisoformat(rec["updated_at"]),
                                    score=None,
                                )
                            )
                    if op.limit:
                        matches = matches[: op.limit]
                    results.append(matches)
                elif isinstance(op, ListNamespacesOp):
                    results.append(list(self._records.keys()))
                else:
                    results.append(None)
            if changed:
                self._save()
        return results


def _matches_filter(value: dict, filters: dict) -> bool:
    for k, v in filters.items():
        if value.get(k) != v:
            return False
    return True
