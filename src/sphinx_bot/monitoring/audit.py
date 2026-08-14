"""Append-only, hash-chained JSONL audit records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


class AuditLogger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.previous_hash = "0" * 64
        self.records: list[dict[str, Any]] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.touch(exist_ok=True)
            if self.path.stat().st_size:
                valid, _, error = verify_chain(self.path)
                if not valid:
                    raise ValueError(f"cannot resume invalid audit chain: {error}")
                with self.path.open(encoding="utf-8") as handle:
                    for line in handle:
                        if line.strip():
                            self.previous_hash = json.loads(line)["record_hash"]

    def write(self, record_type: str, payload: Any) -> dict[str, Any]:
        body = {
            "record_type": record_type,
            "payload": json_safe(payload),
            "previous_hash": self.previous_hash,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        record_hash = hashlib.sha256(canonical.encode()).hexdigest()
        record = {**body, "record_hash": record_hash}
        self.previous_hash = record_hash
        self.records.append(record)
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record


def verify_chain(path: str | Path) -> tuple[bool, int, str | None]:
    previous = "0" * 64
    count = 0
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            claimed = record.pop("record_hash", None)
            if record.get("previous_hash") != previous:
                return False, count, f"previous hash mismatch on line {line_number}"
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
            actual = hashlib.sha256(canonical.encode()).hexdigest()
            if actual != claimed:
                return False, count, f"record hash mismatch on line {line_number}"
            previous = actual
            count += 1
    return True, count, None
