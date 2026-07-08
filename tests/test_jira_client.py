from __future__ import annotations

import base64
import json

import httpx
import pytest

from jira_tui.config import JiraConfig
from jira_tui.jira_client import JiraAuthError, JiraClient, JiraQueryError


def _client(handler: httpx.MockTransport) -> JiraClient:
    async_client = httpx.AsyncClient(
        transport=handler,
        base_url="https://example.atlassian.net",
        auth=("me@example.com", "token"),
    )
    return JiraClient(
        JiraConfig(
            base_url="https://example.atlassian.net",
            email="me@example.com",
            api_token="token",
        ),
        client=async_client,
    )


@pytest.mark.asyncio
async def test_search_issues_posts_jql_and_maps_results() -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "DT-1",
                        "fields": {
                            "summary": "Fix login",
                            "status": {"name": "To Do"},
                            "assignee": {"displayName": "Ada"},
                            "updated": "2026-07-08T12:00:00.000+0000",
                        },
                    }
                ],
                "isLast": True,
            },
        )

    client = _client(httpx.MockTransport(handler))

    result = await client.search_issues("project = DT")

    assert seen_request is not None
    assert seen_request.method == "POST"
    assert seen_request.url.path == "/rest/api/3/search/jql"
    assert json.loads(seen_request.content)["jql"] == "project = DT"
    assert result.issues[0].key == "DT-1"
    assert result.issues[0].assignee == "Ada"


@pytest.mark.asyncio
async def test_add_comment_sends_adf_body() -> None:
    seen_payload: dict[str, object] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        seen_payload = json.loads(request.content)
        return httpx.Response(201, json={})

    client = _client(httpx.MockTransport(handler))

    await client.add_comment("DT-1", "Looks good")

    assert seen_payload == {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Looks good"}],
                }
            ],
        }
    }


@pytest.mark.asyncio
async def test_transition_issue_posts_transition_id() -> None:
    seen_payload: dict[str, object] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        seen_payload = json.loads(request.content)
        return httpx.Response(204)

    client = _client(httpx.MockTransport(handler))

    await client.transition_issue("DT-1", "31")

    assert seen_payload == {"transition": {"id": "31"}}


@pytest.mark.asyncio
async def test_auth_header_uses_email_and_api_token() -> None:
    seen_auth = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_auth
        seen_auth = request.headers["Authorization"]
        return httpx.Response(200, json={"issues": [], "isLast": True})

    client = _client(httpx.MockTransport(handler))

    await client.search_issues("project = DT")

    encoded = base64.b64encode(b"me@example.com:token").decode()
    assert seen_auth == f"Basic {encoded}"


@pytest.mark.asyncio
async def test_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errorMessages": ["Bad JQL"]})

    client = _client(httpx.MockTransport(handler))

    with pytest.raises(JiraQueryError, match="Bad JQL"):
        await client.search_issues("bad")


@pytest.mark.asyncio
async def test_auth_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errorMessages": ["Unauthorized"]})

    client = _client(httpx.MockTransport(handler))

    with pytest.raises(JiraAuthError, match="Unauthorized"):
        await client.search_issues("project = DT")
