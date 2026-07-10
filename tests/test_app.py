from __future__ import annotations

import pytest
from textual.widgets import DataTable, Markdown, Static

from jira_tui.app import JiraTuiApp
from jira_tui.config import DetailTabConfig, JiraConfig, MetadataFieldConfig
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
                IssueSummary(
                    key="DT-2",
                    summary="Subtask result",
                    status="To Do",
                    assignee="Grace",
                    updated="2026-07-08",
                    parent_key="DT-1",
                    parent_summary=f"Result for {jql}",
                    is_subtask=True,
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
            raw_fields={
                "description": "Description",
                "customfield_10010": "Acceptance criteria",
                "customfield_10020": [{"name": "Sprint 1"}, {"name": "Sprint 2"}],
            },
            markdown_fields={
                "description": "Description",
                "customfield_10010": "Acceptance criteria",
            },
            comments=(Comment(author="Ada", body="Existing comment", created="2026-07-08"),),
        )

    async def add_comment(self, key: str, body: str) -> None:
        self.comments.append((key, body))

    async def get_transitions(self, key: str) -> tuple[Transition, ...]:
        return (Transition(id="31", name="Done"),)

    async def transition_issue(self, key: str, transition_id: str) -> None:
        self.transitions.append((key, transition_id))


class NestedSubtaskJiraClient(FakeJiraClient):
    async def search_issues(
        self, jql: str, *, max_results: int = 50, next_page_token: str | None = None
    ) -> IssueSearchResult:
        return IssueSearchResult(
            issues=(
                IssueSummary(
                    key="DT-43",
                    summary="Data Tracking",
                    status="Done",
                    assignee="Ada",
                    updated="2026-07-08",
                    parent_key="DT-453",
                    parent_summary="Study Reports",
                    is_subtask=True,
                ),
                IssueSummary(
                    key="DT-610",
                    summary="Tooltips missing",
                    status="Done",
                    assignee="Grace",
                    updated="2026-07-08",
                    parent_key="DT-43",
                    parent_summary="Data Tracking",
                    is_subtask=True,
                ),
            )
        )


class MultiParentJiraClient(FakeJiraClient):
    async def search_issues(
        self, jql: str, *, max_results: int = 50, next_page_token: str | None = None
    ) -> IssueSearchResult:
        return IssueSearchResult(
            issues=(
                IssueSummary(
                    key="DT-1",
                    summary="First parent",
                    status="To Do",
                    assignee="Ada",
                    updated="2026-07-08",
                ),
                IssueSummary(
                    key="DT-2",
                    summary="Second parent",
                    status="To Do",
                    assignee="Grace",
                    updated="2026-07-08",
                ),
                IssueSummary(
                    key="DT-3",
                    summary="Second parent subtask",
                    status="To Do",
                    assignee="Grace",
                    updated="2026-07-08",
                    parent_key="DT-2",
                    parent_summary="Second parent",
                    is_subtask=True,
                ),
            )
        )


class CountingRefreshJiraClient(FakeJiraClient):
    instances: list[CountingRefreshJiraClient] = []

    def __init__(self, config: JiraConfig) -> None:
        super().__init__(config)
        self.search_count = 0
        self.issue_fetch_count = 0
        self.__class__.instances.append(self)

    async def search_issues(
        self, jql: str, *, max_results: int = 50, next_page_token: str | None = None
    ) -> IssueSearchResult:
        self.search_count += 1
        return await super().search_issues(
            jql, max_results=max_results, next_page_token=next_page_token
        )

    async def get_issue(self, key: str) -> IssueDetail:
        self.issue_fetch_count += 1
        return await super().get_issue(key)


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
        assert table.has_focus
        assert "Loaded 2 issues." in str(app.query_one("#status", Static).content)


@pytest.mark.asyncio
async def test_refresh_updates_issue_list_when_detail_is_open() -> None:
    CountingRefreshJiraClient.instances.clear()
    config = JiraConfig(
        base_url="https://example.atlassian.net",
        email="me@example.com",
        api_token="token",
        default_jql="project = DT",
    )
    app = JiraTuiApp(config=config, client_factory=CountingRefreshJiraClient)

    async with app.run_test() as pilot:
        await pilot.pause()
        client = CountingRefreshJiraClient.instances[0]
        app.open_issue("DT-1")
        await pilot.pause()

        assert client.search_count == 1
        assert client.issue_fetch_count == 1

        app.action_refresh()
        await pilot.pause()

        assert client.search_count == 2
        assert client.issue_fetch_count == 1


@pytest.mark.asyncio
async def test_subtasks_expand_from_collapsed_parent() -> None:
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
        assert table.get_row_at(0)[0] == "▶ DT-1"

        table.focus()
        await pilot.press("space")

        assert table.row_count == 2
        assert table.get_row_at(0)[0] == "▼ DT-1"
        assert table.get_row_at(1)[0] == "  DT-2"


@pytest.mark.asyncio
async def test_expanding_parent_keeps_cursor_on_parent() -> None:
    config = JiraConfig(
        base_url="https://example.atlassian.net",
        email="me@example.com",
        api_token="token",
        default_jql="project = DT",
    )
    app = JiraTuiApp(config=config, client_factory=MultiParentJiraClient)

    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#issue-table", DataTable)

        table.focus()
        table.move_cursor(row=1)
        await pilot.press("space")

        assert table.cursor_row == 1
        assert table.get_row_at(table.cursor_row)[0] == "▼ DT-2"


@pytest.mark.asyncio
async def test_nested_subtasks_do_not_render_duplicate_rows() -> None:
    config = JiraConfig(
        base_url="https://example.atlassian.net",
        email="me@example.com",
        api_token="token",
        default_jql="project = DT",
    )
    app = JiraTuiApp(config=config, client_factory=NestedSubtaskJiraClient)

    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#issue-table", DataTable)

        assert table.row_count == 1
        assert table.get_row_at(0)[0] == "▶ DT-453"

        table.focus()
        await pilot.press("space")

        assert table.row_count == 2
        assert table.get_row_at(0)[0] == "▼ DT-453"
        assert table.get_row_at(1)[0] == "  ▶ DT-43"

        table.move_cursor(row=1)
        await pilot.press("space")

        assert table.row_count == 3
        assert table.get_row_at(1)[0] == "  ▼ DT-43"
        assert table.get_row_at(2)[0] == "    DT-610"


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

        title = str(app.query_one("#issue-title", Static).content)
        assert "DT-1: Fix login" in title
        assert app.query_one("#detail-tab-content-0", Markdown)
        assert app.query_one("#detail-tab-content-1", Markdown)


@pytest.mark.asyncio
async def test_open_issue_renders_configured_metadata_fields() -> None:
    config = JiraConfig(
        base_url="https://example.atlassian.net",
        email="me@example.com",
        api_token="token",
        metadata_fields=(
            MetadataFieldConfig("State", "status"),
            MetadataFieldConfig("Owner", "assignee"),
            MetadataFieldConfig("Sprint", "customfield_10020[].name"),
        ),
    )
    app = JiraTuiApp(config=config, client_factory=FakeJiraClient)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.open_issue("DT-1")
        await pilot.pause()

        title = str(app.query_one("#issue-title", Static).content)
        metadata = str(app.query_one("#issue-metadata", Static).content)
        assert "DT-1: Fix login" in title
        assert "State: To Do" in metadata
        assert "Owner: Ada" in metadata
        assert "Sprint: Sprint 1, Sprint 2" in metadata
        assert "Reporter:" not in metadata


@pytest.mark.asyncio
async def test_open_issue_renders_configured_detail_tabs() -> None:
    config = JiraConfig(
        base_url="https://example.atlassian.net",
        email="me@example.com",
        api_token="token",
        detail_tabs=(
            DetailTabConfig("Description", "description"),
            DetailTabConfig("Acceptance Criteria", "customfield_10010"),
            DetailTabConfig("Comments", "comments"),
        ),
    )
    app = JiraTuiApp(config=config, client_factory=FakeJiraClient)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.open_issue("DT-1")
        await pilot.pause()

        issue = await app.client.get_issue("DT-1")
        assert app._content_for_detail_tab(issue, config.detail_tabs[0]) == "Description"
        assert app._content_for_detail_tab(issue, config.detail_tabs[1]) == "Acceptance criteria"
        assert "Existing comment" in app._content_for_detail_tab(issue, config.detail_tabs[2])
