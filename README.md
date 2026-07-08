# Jira TUI

A Textual-based terminal browser for Jira Cloud issues.

## Setup

Install project tools with `mise`, then install dependencies with `uv`:

```sh
mise install
```

```sh
uv sync
```

Configure Jira Cloud API-token auth with environment variables:

```sh
export JIRA_BASE_URL="https://your-site.atlassian.net"
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="your-api-token"
```

Optional detail tabs can be configured in the user config file:

```ini
[jira]
base_url = https://your-site.atlassian.net
email = you@example.com
api_token = your-api-token

[detail_tabs]
Description = description
Acceptance Criteria = customfield_10010
Out of Scope = customfield_10011
Technical Details = customfield_10012
Comments = comments
```

Use Jira field keys, such as `customfield_10010`, for custom fields. The special source
`comments` renders the issue comments tab.

Run the app:

```sh
uv run jira-tui
```

The default query is:

```jql
assignee = currentUser() ORDER BY updated DESC
```

## MVP Controls

- `/`: focus JQL search
- `enter`: search from the input or open the selected issue
- `r`: refresh current search or issue
- `space`: expand or collapse subtasks for the selected parent issue
- `c`: add a comment to the open issue
- `t`: transition the open issue
- `escape`: go back or cancel
- `q`: quit
