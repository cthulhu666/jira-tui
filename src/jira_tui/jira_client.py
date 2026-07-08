from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from jira_tui.config import JiraConfig
from jira_tui.models import IssueDetail, IssueSummary, Transition, adf_from_text


class JiraClientError(RuntimeError):
    pass


class JiraAuthError(JiraClientError):
    pass


class JiraPermissionError(JiraClientError):
    pass


class JiraNotFoundError(JiraClientError):
    pass


class JiraQueryError(JiraClientError):
    pass


@dataclass(frozen=True)
class IssueSearchResult:
    issues: tuple[IssueSummary, ...]
    next_page_token: str | None = None
    is_last: bool = True


class JiraClient:
    def __init__(self, config: JiraConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=config.normalized_base_url,
            auth=(config.email, config.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=20.0,
        )

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def search_issues(
        self, jql: str, *, max_results: int = 50, next_page_token: str | None = None
    ) -> IssueSearchResult:
        payload: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "updated", "issuetype", "parent"],
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token
        response = await self._request("POST", "/rest/api/3/search/jql", json=payload)
        data = response.json()
        return IssueSearchResult(
            issues=tuple(IssueSummary.from_payload(issue) for issue in data.get("issues", [])),
            next_page_token=data.get("nextPageToken"),
            is_last=bool(data.get("isLast", True)),
        )

    async def get_issue(self, key: str) -> IssueDetail:
        issue = await self._request(
            "GET",
            f"/rest/api/3/issue/{key}",
            params={
                "fields": "summary,status,assignee,reporter,priority,labels,description",
            },
        )
        comments = await self._request("GET", f"/rest/api/3/issue/{key}/comment")
        return IssueDetail.from_payload(issue.json(), comments.json())

    async def add_comment(self, key: str, body: str) -> None:
        await self._request(
            "POST",
            f"/rest/api/3/issue/{key}/comment",
            json={"body": adf_from_text(body)},
        )

    async def get_transitions(self, key: str) -> tuple[Transition, ...]:
        response = await self._request("GET", f"/rest/api/3/issue/{key}/transitions")
        return tuple(
            Transition.from_payload(transition)
            for transition in response.json().get("transitions", [])
        )

    async def transition_issue(self, key: str, transition_id: str) -> None:
        await self._request(
            "POST",
            f"/rest/api/3/issue/{key}/transitions",
            json={"transition": {"id": transition_id}},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.RequestError as error:
            raise JiraClientError(f"Could not reach Jira: {error}") from error

        if response.status_code < 400:
            return response

        message = _error_message(response)
        if response.status_code == 401:
            raise JiraAuthError(message)
        if response.status_code == 403:
            raise JiraPermissionError(message)
        if response.status_code == 404:
            raise JiraNotFoundError(message)
        if response.status_code == 400:
            raise JiraQueryError(message)
        raise JiraClientError(message)


def _error_message(response: httpx.Response) -> str:
    default = f"Jira request failed with HTTP {response.status_code}."
    try:
        payload = response.json()
    except ValueError:
        return default

    messages: list[str] = []
    for item in payload.get("errorMessages") or []:
        messages.append(str(item))
    errors = payload.get("errors") or {}
    for field, message in errors.items():
        messages.append(f"{field}: {message}")
    return "; ".join(messages) or default
