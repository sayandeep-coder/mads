from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

_ModelT = TypeVar("_ModelT", bound=BaseModel)

ADAPTIVE_HOME = Path.home() / ".mads" / "adaptive"

PROFILE_PATH = ADAPTIVE_HOME / "profile.json"
PENDING_PATH = ADAPTIVE_HOME / "pending.json"
LEDGER_PATH = ADAPTIVE_HOME / "ledger.json"


class JsonListStore(Generic[_ModelT]):
    """A single JSON file holding a list of Pydantic model instances.

    Same shape as planner.storage.JsonListStore — duplicated rather than
    imported cross-package to keep adaptive/ independently deployable and
    because a cross-package storage dependency isn't warranted for one
    shared generic class.
    """

    def __init__(self, path: Path, model: type[_ModelT]) -> None:
        self._path = path
        self._model = model

    @property
    def path(self) -> Path:
        return self._path

    def read_all(self) -> list[_ModelT]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [self._model.model_validate(item) for item in raw]

    def write_all(self, records: list[_ModelT]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        payload = [json.loads(r.model_dump_json()) for r in records]
        content = json.dumps(payload, indent=2)

        # write_text() truncates-then-writes in place, which is not atomic:
        # concurrent tool calls (Gemini can fire several approve/reject
        # calls in the same turn via asyncio.gather) can interleave two
        # writes and leave a shorter write's tail sitting after a longer
        # prior write, corrupting the JSON ("Extra data" / truncated-empty
        # reads). Write to a sibling temp file and atomically replace —
        # os.replace() is a single atomic filesystem operation, so any
        # concurrent reader/writer either sees the old complete file or the
        # new complete file, never a mix of both.
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            # Adaptive profile/pending files contain learned personal
            # preferences/decisions — same sensitivity as memory.sqlite3,
            # same owner-only restriction. Set on the temp file before the
            # atomic rename so the target is never briefly world-readable.
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
