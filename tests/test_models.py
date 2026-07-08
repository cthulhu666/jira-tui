from jira_tui.models import IssueDetail, adf_from_text, extract_adf_text


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
