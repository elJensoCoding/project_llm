"""Query-Logger: protokolliert alle LLM-Queries und erlaubt Fehler-Markierung."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _log_path() -> Path:
    from . import config
    return Path(config.get().get("log", {}).get("path", "data/query_log.jsonl"))


def log(
    question: str,
    sql: str,
    error: str | None,
    rows: int,
    retried: bool,
) -> str:
    """Schreibt einen Query-Eintrag. Gibt die ID zurück (für späteres Flaggen)."""
    entry_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    entry = {
        "id":       entry_id,
        "ts":       datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "sql":      sql,
        "error":    error,
        "rows":     rows,
        "retried":  retried,
        "flagged":  False,
    }
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry_id


def flag(entry_id: str) -> None:
    """Markiert einen Eintrag als fehlerhaft (in-place Update der JSONL)."""
    p = _log_path()
    if not p.exists():
        return
    lines = p.read_text(encoding="utf-8").splitlines()
    updated = []
    for line in lines:
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["id"] == entry_id:
            entry["flagged"] = True
        updated.append(json.dumps(entry, ensure_ascii=False))
    p.write_text("\n".join(updated) + "\n", encoding="utf-8")


def read_all(only_flagged: bool = False) -> list[dict]:
    p = _log_path()
    if not p.exists():
        return []
    entries = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if only_flagged:
        return [e for e in entries if e.get("flagged")]
    return entries
