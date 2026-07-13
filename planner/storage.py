from __future__ import annotations

import json
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

_ModelT = TypeVar("_ModelT", bound=BaseModel)

MADS_HOME = Path.home() / ".mads"


def projects_root() -> Path:
    return MADS_HOME / "projects"


def project_dir(slug: str) -> Path:
    return projects_root() / slug


class JsonRecordStore(Generic[_ModelT]):
    """A single JSON file holding one Pydantic model instance.

    Used for anything that's a single record per scope — a project's
    project.json, for example. Not for collections; see JsonListStore.
    """

    def __init__(self, path: Path, model: type[_ModelT]) -> None:
        self._path = path
        self._model = model

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def read(self) -> _ModelT | None:
        if not self._path.exists():
            return None
        return self._model.model_validate_json(self._path.read_text(encoding="utf-8"))

    def write(self, record: _ModelT) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(record.model_dump_json(indent=2), encoding="utf-8")


class JsonListStore(Generic[_ModelT]):
    """A single JSON file holding a list of Pydantic model instances.

    Used for collections scoped to one file — a project's tasks.json.
    Not safe for concurrent writers; Mads is single-process/single-user,
    so read-modify-write is sufficient without file locking.
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
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
