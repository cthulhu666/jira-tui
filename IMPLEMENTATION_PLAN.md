# Jira TUI MVP Implementation Plan

## Summary

Build a Python/Textual Jira Cloud TUI in the `jira-tui` repo. The MVP uses `uv`, Jira Cloud REST API v3, and API-token auth. It supports issue search, issue browsing, issue detail viewing, comments, and basic light edits: adding comments and transitioning issue status.

## Key Changes

- Create a `uv` Python app with `pyproject.toml`, package source under `src/jira_tui/`, tests under `tests/`, and console entrypoint `jira-tui`.
- Use runtime dependencies: `textual`, `httpx`, and `platformdirs`.
- Use dev dependencies: `pytest`, `pytest-asyncio`, `pytest-httpx`, and `ruff`.
- Read `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN` from environment first.
- Optionally read a local config file from the user config directory for non-secret defaults like base URL and default JQL.
- Never persist API tokens in repo files.
- Implement a small async `JiraClient` around `httpx.AsyncClient`.
- Support Jira Cloud REST calls for search, issue detail, comments, transitions, add comment, and transition issue.
- Normalize Jira errors into app-level exceptions with user-facing messages.

## Textual UI

- Main screen: JQL input, issue `DataTable`, detail panel, comments panel, status line, and footer key bindings.
- Comment modal: multiline input with submit/cancel.
- Transition modal: list available Jira transitions for the current issue.
- Confirmation modal for write actions before sending comment or transition requests.
- Key bindings:
  - `/`: focus JQL search
  - `enter`: search from input or open selected issue
  - `r`: refresh current search or issue
  - `c`: add comment
  - `t`: transition issue
  - `escape`: back/cancel
  - `q`: quit
- Run all Jira network calls in async Textual workers so the UI remains responsive.

## MVP Behavior

- On startup, validate config and show a clear setup error if required Jira credentials are missing.
- Default query: `assignee = currentUser() ORDER BY updated DESC`.
- Search returns a first page of issues with columns: key, status, summary, assignee, updated.
- Opening an issue fetches full details and comments.
- Adding a comment refreshes the current issue detail after success.
- Transitioning an issue shows only transitions returned by Jira for that issue, then refreshes the issue after success.

## Test Plan

- Unit-test config loading precedence and missing required config.
- Unit-test Jira client request construction, response parsing, and error mapping with mocked HTTP.
- Unit-test Jira ADF text conversion for comments and descriptions.
- Textual app tests with `App.run_test()` and fake Jira client:
  - Startup renders search results.
  - Opening an issue renders details and comments.
- Run:
  - `ruff check .`
  - `pytest`
  - `python -m compileall src tests`

## Assumptions

- Target Jira Cloud, not Jira Data Center/Server.
- MVP auth is API-token basic auth, not OAuth.
- MVP includes light edits: add comment and transition issue status only.
- No board/sprint dashboard, attachment download, issue creation, field editing, saved filters, or multi-account support in MVP.
- Existing `.envrc` is unrelated and should remain untouched unless explicitly requested.
