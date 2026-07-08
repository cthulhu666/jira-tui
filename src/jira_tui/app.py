from __future__ import annotations

from collections.abc import Callable

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from jira_tui.config import (
    DEFAULT_DETAIL_TABS,
    DEFAULT_METADATA_FIELDS,
    ConfigError,
    DetailTabConfig,
    JiraConfig,
    MetadataFieldConfig,
    load_config,
)
from jira_tui.jira_client import JiraClient, JiraClientError
from jira_tui.models import IssueDetail, IssueSummary, Transition, extract_field_path_text

ClientFactory = Callable[[JiraConfig], JiraClient]


class CommentScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    CommentScreen {
        align: center middle;
    }

    #comment-dialog {
        width: 70%;
        height: 45%;
        border: round $accent;
        background: $surface;
        padding: 1;
    }

    #comment-body {
        height: 1fr;
        margin: 1 0;
    }

    #comment-actions {
        height: auto;
        align-horizontal: right;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "submit", "Submit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="comment-dialog"):
            yield Label("Add comment")
            yield TextArea(id="comment-body")
            with Horizontal(id="comment-actions"):
                yield Button("Cancel", id="cancel-comment")
                yield Button("Submit", id="submit-comment", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-comment":
            self.action_cancel()
        elif event.button.id == "submit-comment":
            self.action_submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        body = self.query_one("#comment-body", TextArea).text.strip()
        self.dismiss(body or None)


class TransitionScreen(ModalScreen[Transition | None]):
    DEFAULT_CSS = """
    TransitionScreen {
        align: center middle;
    }

    #transition-dialog {
        width: 60%;
        height: 50%;
        border: round $accent;
        background: $surface;
        padding: 1;
    }

    #transition-list {
        height: 1fr;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "choose", "Choose"),
    ]

    def __init__(self, transitions: tuple[Transition, ...]) -> None:
        super().__init__()
        self.transitions = transitions

    def compose(self) -> ComposeResult:
        with Vertical(id="transition-dialog"):
            yield Label("Choose transition")
            yield ListView(
                *[
                    ListItem(Label(transition.name), id=f"transition-{transition.id}")
                    for transition in self.transitions
                ],
                id="transition-list",
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(self._transition_for_item(event.item))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_choose(self) -> None:
        view = self.query_one("#transition-list", ListView)
        if view.highlighted_child is not None:
            self.dismiss(self._transition_for_item(view.highlighted_child))

    def _transition_for_item(self, item: ListItem) -> Transition | None:
        item_id = item.id or ""
        transition_id = item_id.removeprefix("transition-")
        return next(
            (transition for transition in self.transitions if transition.id == transition_id),
            None,
        )


class ConfirmScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }

    #confirm-dialog {
        width: 50%;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1;
    }

    #confirm-message {
        margin-bottom: 1;
    }

    #confirm-actions {
        height: auto;
        align-horizontal: right;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm", "Confirm"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self.message, id="confirm-message")
            with Horizontal(id="confirm-actions"):
                yield Button("Cancel", id="cancel-confirm")
                yield Button("Confirm", id="submit-confirm", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-confirm":
            self.action_cancel()
        elif event.button.id == "submit-confirm":
            self.action_confirm()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)


class JiraTuiApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "Jira TUI"

    BINDINGS = [
        ("/", "focus_search", "Search"),
        ("r", "refresh", "Refresh"),
        ("space", "toggle_subtasks", "Subtasks"),
        ("c", "comment", "Comment"),
        ("t", "transition", "Transition"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        config: JiraConfig | None = None,
        client_factory: ClientFactory = JiraClient,
    ) -> None:
        super().__init__()
        self._provided_config = config
        self._client_factory = client_factory
        self.config_error: str | None = None
        self.jira_config = self._load_initial_config()
        self.client: JiraClient | None = None
        self.current_jql = ""
        self.current_issue_key: str | None = None
        self.current_issues: tuple[IssueSummary, ...] = ()
        self.expanded_parent_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="app-body"):
            yield Input(placeholder="JQL", id="jql-input")
            with Horizontal(id="content"):
                yield DataTable(id="issue-table", cursor_type="row")
                with Vertical(id="detail-pane"):
                    yield Static("No issue selected.", id="issue-metadata")
                    with TabbedContent(id="detail-tabs"):
                        for index, tab in enumerate(self._detail_tabs()):
                            with TabPane(tab.label, id=self._tab_pane_id(index)):
                                yield Markdown("", id=self._tab_content_id(index))
            yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#issue-table", DataTable)
        table.add_columns("Key", "Status", "Summary", "Assignee", "Updated")
        table.zebra_stripes = True

        if self.config_error:
            self._set_status(self.config_error, error=True)
            return

        if self.jira_config is None:
            self._set_status("Missing Jira configuration.", error=True)
            return

        self.client = self._client_factory(self.jira_config)
        self.current_jql = self.jira_config.default_jql
        self.query_one("#jql-input", Input).value = self.current_jql
        self.search(self.current_jql)

    async def on_unmount(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "jql-input":
            self.current_jql = event.value.strip() or self.current_jql
            self.search(self.current_jql)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value)
        if key:
            self.open_issue(key)

    def action_focus_search(self) -> None:
        self.query_one("#jql-input", Input).focus()

    def action_refresh(self) -> None:
        if self.current_issue_key:
            self.open_issue(self.current_issue_key)
        elif self.current_jql:
            self.search(self.current_jql)

    def action_toggle_subtasks(self) -> None:
        table = self.query_one("#issue-table", DataTable)
        if table.cursor_row is None or not table.row_count:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        key = str(row_key.value)
        parent_key = key.removeprefix("parent:")
        if not self._subtasks_for_parent(parent_key):
            self._set_status(f"{parent_key} has no subtasks in the current result.")
            return
        if parent_key in self.expanded_parent_keys:
            self.expanded_parent_keys.remove(parent_key)
            self._set_status(f"Collapsed subtasks for {parent_key}.")
        else:
            self.expanded_parent_keys.add(parent_key)
            self._set_status(f"Expanded subtasks for {parent_key}.")
        self._render_issue_table(cursor_key=parent_key)

    def action_comment(self) -> None:
        if not self.current_issue_key:
            self._set_status("Open an issue before adding a comment.", error=True)
            return
        self.push_screen(CommentScreen(), self._handle_comment)

    def action_transition(self) -> None:
        if not self.current_issue_key:
            self._set_status("Open an issue before transitioning it.", error=True)
            return
        self.load_transitions(self.current_issue_key)

    @work(exclusive=True)
    async def search(self, jql: str) -> None:
        if self.client is None:
            return
        self._set_status("Searching Jira...")
        try:
            result = await self.client.search_issues(jql)
        except JiraClientError as error:
            self._set_status(str(error), error=True)
            return

        self.current_issues = result.issues
        self.expanded_parent_keys.clear()
        self._render_issue_table()
        suffix = "" if result.is_last else " (more results available)"
        self._set_status(f"Loaded {len(result.issues)} issues{suffix}.")

    @work(exclusive=True)
    async def open_issue(self, key: str) -> None:
        if self.client is None:
            return
        self._set_status(f"Loading {key}...")
        try:
            issue = await self.client.get_issue(key)
        except JiraClientError as error:
            self._set_status(str(error), error=True)
            return
        self.current_issue_key = key
        self._render_issue(issue)
        self._set_status(f"Loaded {key}.")

    @work(exclusive=True)
    async def add_comment(self, key: str, body: str) -> None:
        if self.client is None:
            return
        self._set_status(f"Adding comment to {key}...")
        try:
            await self.client.add_comment(key, body)
        except JiraClientError as error:
            self._set_status(str(error), error=True)
            return
        self._set_status(f"Comment added to {key}.")
        self.open_issue(key)

    @work(exclusive=True)
    async def load_transitions(self, key: str) -> None:
        if self.client is None:
            return
        self._set_status(f"Loading transitions for {key}...")
        try:
            transitions = await self.client.get_transitions(key)
        except JiraClientError as error:
            self._set_status(str(error), error=True)
            return
        if not transitions:
            self._set_status(f"No transitions available for {key}.")
            return
        self.push_screen(TransitionScreen(transitions), self._handle_transition)

    @work(exclusive=True)
    async def transition_issue(self, key: str, transition: Transition) -> None:
        if self.client is None:
            return
        self._set_status(f"Transitioning {key} to {transition.name}...")
        try:
            await self.client.transition_issue(key, transition.id)
        except JiraClientError as error:
            self._set_status(str(error), error=True)
            return
        self._set_status(f"Transitioned {key} to {transition.name}.")
        self.open_issue(key)

    def _handle_comment(self, body: str | None) -> None:
        if body and self.current_issue_key:
            key = self.current_issue_key
            self.push_screen(
                ConfirmScreen(f"Add comment to {key}?"),
                lambda confirmed: self.add_comment(key, body) if confirmed else None,
            )

    def _handle_transition(self, transition: Transition | None) -> None:
        if transition and self.current_issue_key:
            key = self.current_issue_key
            self.push_screen(
                ConfirmScreen(f"Transition {key} to {transition.name}?"),
                lambda confirmed: self.transition_issue(key, transition) if confirmed else None,
            )

    def _render_issue(self, issue: IssueDetail) -> None:
        self.query_one("#issue-metadata", Static).update(
            "\n".join(
                [f"{issue.key}: {issue.summary}"]
                + [
                    f"{field.label}: {self._content_for_metadata_field(issue, field)}"
                    for field in self._metadata_fields()
                ]
            )
        )
        for index, tab in enumerate(self._detail_tabs()):
            self.query_one(f"#{self._tab_content_id(index)}", Markdown).update(
                self._content_for_detail_tab(issue, tab)
            )

    def _content_for_metadata_field(self, issue: IssueDetail, field: MetadataFieldConfig) -> str:
        if field.source == "status":
            return issue.status
        if field.source == "assignee":
            return issue.assignee
        if field.source == "reporter":
            return issue.reporter
        if field.source == "priority":
            return issue.priority
        if field.source == "labels":
            return ", ".join(issue.labels) if issue.labels else "None"
        return extract_field_path_text(issue.raw_fields, field.source) or "None"

    def _content_for_detail_tab(self, issue: IssueDetail, tab: DetailTabConfig) -> str:
        if tab.source == "comments":
            return self._format_comments(issue)
        if "." in tab.source:
            return extract_field_path_text(issue.raw_fields, tab.source) or "No content."
        return issue.markdown_fields.get(tab.source) or "No content."

    def _format_comments(self, issue: IssueDetail) -> str:
        if issue.comments:
            return "\n\n".join(
                f"{comment.author} ({comment.created}):\n{comment.body}"
                for comment in issue.comments[-5:]
            )
        return "No comments."

    def _render_issue_table(self, cursor_key: str | None = None) -> None:
        table = self.query_one("#issue-table", DataTable)
        table.clear()
        rendered_order: list[str] = []
        children_by_parent = self._children_by_parent()
        issues_by_key = self._issues_by_key_with_synthetic_parents()
        rendered_keys: set[str] = set()

        def render_issue(issue: IssueSummary, depth: int) -> None:
            if issue.key in rendered_keys:
                return
            rendered_keys.add(issue.key)
            rendered_order.append(issue.key)

            children = children_by_parent.get(issue.key, ())
            marker = ""
            if children:
                marker = "▼ " if issue.key in self.expanded_parent_keys else "▶ "
            indentation = "  " * depth
            table.add_row(
                f"{indentation}{marker}{issue.key}",
                issue.status,
                _trim_table_text(issue.summary, 50),
                issue.assignee,
                issue.updated,
                key=issue.key,
            )
            if issue.key in self.expanded_parent_keys:
                for child in children:
                    render_issue(child, depth + 1)

        for issue in self.current_issues:
            root = self._root_issue_for(issue, issues_by_key)
            render_issue(root, 0)
        if cursor_key in rendered_order:
            table.move_cursor(row=rendered_order.index(cursor_key))

    def _subtasks_for_parent(self, parent_key: str) -> tuple[IssueSummary, ...]:
        return self._children_by_parent().get(parent_key, ())

    def _children_by_parent(self) -> dict[str, tuple[IssueSummary, ...]]:
        children: dict[str, list[IssueSummary]] = {}
        for issue in self.current_issues:
            if issue.is_subtask and issue.parent_key:
                children.setdefault(issue.parent_key, []).append(issue)
        return {parent_key: tuple(items) for parent_key, items in children.items()}

    def _issues_by_key_with_synthetic_parents(self) -> dict[str, IssueSummary]:
        issues_by_key = {issue.key: issue for issue in self.current_issues}
        for issue in self.current_issues:
            if issue.is_subtask and issue.parent_key and issue.parent_key not in issues_by_key:
                issues_by_key[issue.parent_key] = IssueSummary(
                    key=issue.parent_key,
                    summary=issue.parent_summary or "Parent issue",
                    status="",
                    assignee="",
                    updated="",
                )
        return issues_by_key

    def _root_issue_for(
        self, issue: IssueSummary, issues_by_key: dict[str, IssueSummary]
    ) -> IssueSummary:
        root = issue
        seen_keys = {issue.key}
        while root.parent_key and root.parent_key in issues_by_key:
            if root.parent_key in seen_keys:
                break
            root = issues_by_key[root.parent_key]
            seen_keys.add(root.key)
        return root

    def _set_status(self, message: str, *, error: bool = False) -> None:
        status = self.query_one("#status", Static)
        status.update(message)
        status.set_class(error, "error")

    def _load_initial_config(self) -> JiraConfig | None:
        if self._provided_config is not None:
            return self._provided_config
        try:
            return load_config()
        except ConfigError as error:
            self.config_error = str(error)
            return None

    def _detail_tabs(self) -> tuple[DetailTabConfig, ...]:
        return self.jira_config.detail_tabs if self.jira_config else DEFAULT_DETAIL_TABS

    def _metadata_fields(self) -> tuple[MetadataFieldConfig, ...]:
        return self.jira_config.metadata_fields if self.jira_config else DEFAULT_METADATA_FIELDS

    def _tab_pane_id(self, index: int) -> str:
        return f"detail-tab-{index}"

    def _tab_content_id(self, index: int) -> str:
        return f"detail-tab-content-{index}"


def _trim_table_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1] + "…"
