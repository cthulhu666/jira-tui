from __future__ import annotations

import json
from pathlib import Path

from jira_tui.config import default_config_path

MAX_QUERY_HISTORY = 100


def default_history_path() -> Path:
    return default_config_path().with_name("query_history.json")


def load_query_history(path: Path | None = None) -> tuple[str, ...]:
    history_path = path or default_history_path()
    if not history_path.exists():
        return ()
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(item for item in payload if isinstance(item, str) and item.strip())[
        :MAX_QUERY_HISTORY
    ]


def record_query_history(query: str, path: Path | None = None) -> tuple[str, ...]:
    normalized_query = query.strip()
    if not normalized_query:
        return load_query_history(path)
    history = [
        normalized_query,
        *[item for item in load_query_history(path) if item != normalized_query],
    ][:MAX_QUERY_HISTORY]
    history_path = path or default_history_path()
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return tuple(history)
    return tuple(history)
