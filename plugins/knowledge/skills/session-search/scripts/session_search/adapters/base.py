from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..turns import bounded_lines

HOME = Path.home()


def ro_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def iter_jsonl(path: Path) -> Iterator[dict]:
    for _, line in bounded_lines(path):
        line = line.decode('utf-8', errors='ignore').strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


class Adapter:
    name = ""

    def crawl(self) -> Iterator[SessionRecord]:
        raise NotImplementedError
