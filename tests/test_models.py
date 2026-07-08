from jira_tui.models import (
    IssueDetail,
    IssueSummary,
    adf_from_text,
    extract_adf_text,
    extract_field_path_text,
)


def test_adf_round_trip_text() -> None:
    body = adf_from_text("Hello\nWorld")

    assert extract_adf_text(body) == "Hello\nWorld"


def test_issue_detail_maps_comments() -> None:
    detail = IssueDetail.from_payload(
        {
            "key": "DT-1",
            "fields": {
                "summary": "Fix login",
                "status": {"name": "In Progress"},
                "assignee": None,
                "reporter": {"displayName": "Reporter"},
                "priority": {"name": "High"},
                "labels": ["bug"],
                "description": adf_from_text("Description"),
            },
        },
        {
            "comments": [
                {
                    "author": {"displayName": "Ada"},
                    "created": "2026-07-08",
                    "body": adf_from_text("Comment"),
                }
            ]
        },
    )

    assert detail.key == "DT-1"
    assert detail.assignee == "Unassigned"
    assert detail.description == "Description"
    assert detail.comments[0].body == "Comment"


def test_issue_summary_maps_subtask_parent() -> None:
    issue = IssueSummary.from_payload(
        {
            "key": "DT-2",
            "fields": {
                "summary": "Subtask",
                "status": {"name": "To Do"},
                "assignee": {"displayName": "Ada"},
                "updated": "2026-07-08",
                "issuetype": {"subtask": True},
                "parent": {
                    "key": "DT-1",
                    "fields": {
                        "summary": "Parent task",
                    },
                },
            },
        }
    )

    assert issue.is_subtask is True
    assert issue.parent_key == "DT-1"
    assert issue.parent_summary == "Parent task"


def test_extract_field_path_text_maps_array_property() -> None:
    fields = {
        "customfield_10020": [
            {"id": 1, "name": "Sprint 1"},
            {"id": 2, "name": "Sprint 2"},
        ]
    }

    assert extract_field_path_text(fields, "customfield_10020[].name") == "Sprint 1, Sprint 2"
