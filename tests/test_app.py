from __future__ import annotations

import pytest
from textual.widgets import DataTable, Static

from jira_tui.app import JiraTuiApp
from jira_tui.config import JiraConfig
from jira_tui.jira_client import IssueSearchResult
from jira_tui.models import Comment, IssueDetail, IssueSummary, Transition


class FakeJiraClient:
    def __init__(self, config: JiraConfig) -> None:
        self.config = config
        self.closed = False
        self.comments: list[tuple[str, str]] = []
        self.transitions: list[tuple[str, str]] = []

    async def aclose(self) -> None:
        self.closed = True

    async def search_issues(
        self, jql: str, *, max_results: int = 50, next_page_token: str | None = None
    ) -> IssueSearchResult:
        return IssueSearchResult(
            issues=(
                IssueSummary(
                    key="DT-1",
                    summary=f"Result for {jql}",
                    status="To Do",
                    assignee="Ada",
                    updated="2026-07-08",
                ),
            )
        )

    async def get_issue(self, key: str) -> IssueDetail:
        return IssueDetail(
            key=key,
            summary="Fix login",
            status="To Do",
            assignee="Ada",
            reporter="Grace",
            priority="High",
            labels=("bug",),
            description="Description",
            comments=(Comment(author="Ada", body="Existing comment", created="2026-07-08"),),
        )

    async def add_comment(self, key: str, body: str) -> None:
        self.comments.append((key, body))

    async def get_transitions(self, key: str) -> tuple[Transition, ...]:
        return (Transition(id="31", name="Done"),)

    async def transition_issue(self, key: str, transition_id: str) -> None:
        self.transitions.append((key, transition_id))


@pytest.mark.asyncio
async def test_app_loads_search_results() -> None:
    config = JiraConfig(
        base_url="https://example.atlassian.net",
        email="me@example.com",
        api_token="token",
        default_jql="project = DT",
    )
    app = JiraTuiApp(config=config, client_factory=FakeJiraClient)

    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#issue-table", DataTable)

        assert table.row_count == 1
        assert "Loaded 1 issues." in str(app.query_one("#status", Static).content)


@pytest.mark.asyncio
async def test_open_issue_renders_details() -> None:
    config = JiraConfig(
        base_url="https://example.atlassian.net",
        email="me@example.com",
        api_token="token",
    )
    app = JiraTuiApp(config=config, client_factory=FakeJiraClient)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.open_issue("DT-1")
        await pilot.pause()

        detail = str(app.query_one("#issue-detail", Static).content)
        comments = str(app.query_one("#comments", Static).content)
        assert "DT-1: Fix login" in detail
        assert "Existing comment" in comments
