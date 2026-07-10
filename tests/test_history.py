from jira_tui.history import MAX_QUERY_HISTORY, load_query_history, record_query_history


def test_record_query_history_keeps_recent_unique_queries(tmp_path) -> None:
    path = tmp_path / "query_history.json"

    record_query_history("project = ONE", path)
    record_query_history("project = TWO", path)
    record_query_history("project = ONE", path)

    assert load_query_history(path) == ("project = ONE", "project = TWO")


def test_record_query_history_caps_at_100_queries(tmp_path) -> None:
    path = tmp_path / "query_history.json"

    for index in range(MAX_QUERY_HISTORY + 5):
        record_query_history(f"project = {index}", path)

    history = load_query_history(path)
    assert len(history) == MAX_QUERY_HISTORY
    assert history[0] == f"project = {MAX_QUERY_HISTORY + 4}"
