from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class JiraUser:
    display_name: str = "Unassigned"

    @classmethod
    def from_payload(
        cls, payload: dict[str, Any] | None, default: str = "Unassigned"
    ) -> JiraUser:
        if not payload:
            return cls(default)
        return cls(str(payload.get("displayName") or default))


@dataclass(frozen=True)
class IssueSummary:
    key: str
    summary: str
    status: str
    assignee: str
    updated: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> IssueSummary:
        fields = payload.get("fields") or {}
        status = fields.get("status") or {}
        return cls(
            key=str(payload.get("key") or ""),
            summary=str(fields.get("summary") or ""),
            status=str(status.get("name") or ""),
            assignee=JiraUser.from_payload(fields.get("assignee")).display_name,
            updated=str(fields.get("updated") or ""),
        )


@dataclass(frozen=True)
class Comment:
    author: str
    body: str
    created: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Comment:
        return cls(
            author=JiraUser.from_payload(payload.get("author"), default="Unknown").display_name,
            body=extract_adf_text(payload.get("body")),
            created=str(payload.get("created") or ""),
        )


@dataclass(frozen=True)
class IssueDetail:
    key: str
    summary: str
    status: str
    assignee: str
    reporter: str
    priority: str
    labels: tuple[str, ...]
    description: str
    comments: tuple[Comment, ...] = field(default_factory=tuple)

    @classmethod
    def from_payload(
        cls, issue_payload: dict[str, Any], comment_payload: dict[str, Any] | None = None
    ) -> IssueDetail:
        fields = issue_payload.get("fields") or {}
        status = fields.get("status") or {}
        priority = fields.get("priority") or {}
        comments = tuple(
            Comment.from_payload(comment) for comment in (comment_payload or {}).get("comments", [])
        )
        return cls(
            key=str(issue_payload.get("key") or ""),
            summary=str(fields.get("summary") or ""),
            status=str(status.get("name") or ""),
            assignee=JiraUser.from_payload(fields.get("assignee")).display_name,
            reporter=JiraUser.from_payload(fields.get("reporter"), default="Unknown").display_name,
            priority=str(priority.get("name") or "None"),
            labels=tuple(str(label) for label in fields.get("labels") or []),
            description=extract_adf_text(fields.get("description")),
            comments=comments,
        )


@dataclass(frozen=True)
class Transition:
    id: str
    name: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Transition:
        return cls(id=str(payload.get("id") or ""), name=str(payload.get("name") or ""))


def adf_from_text(text: str) -> dict[str, Any]:
    lines = text.splitlines() or [""]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}] if line else [],
            }
            for line in lines
        ],
    }


def extract_adf_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value)

    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and node.get("text"):
                parts.append(str(node["text"]))
            elif node.get("type") in {"paragraph", "heading"} and parts and parts[-1] != "\n":
                parts.append("\n")
            for child in node.get("content") or []:
                walk(child)
            if node.get("type") in {"paragraph", "heading"}:
                parts.append("\n")
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return "\n".join(line.strip() for line in "".join(parts).splitlines() if line.strip())
