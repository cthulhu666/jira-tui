from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from markdownify import markdownify


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
    parent_key: str | None = None
    parent_summary: str | None = None
    is_subtask: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> IssueSummary:
        fields = payload.get("fields") or {}
        status = fields.get("status") or {}
        parent = fields.get("parent") or {}
        parent_fields = parent.get("fields") or {}
        issue_type = fields.get("issuetype") or {}
        return cls(
            key=str(payload.get("key") or ""),
            summary=str(fields.get("summary") or ""),
            status=str(status.get("name") or ""),
            assignee=JiraUser.from_payload(fields.get("assignee")).display_name,
            updated=format_jira_datetime(fields.get("updated")),
            parent_key=str(parent.get("key") or "") or None,
            parent_summary=str(parent_fields.get("summary") or "") or None,
            is_subtask=bool(issue_type.get("subtask")) or bool(parent),
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
    raw_fields: dict[str, Any] = field(default_factory=dict)
    detail_fields: dict[str, str] = field(default_factory=dict)
    markdown_fields: dict[str, str] = field(default_factory=dict)
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
            raw_fields=fields,
            detail_fields={key: extract_adf_text(value) for key, value in fields.items()},
            markdown_fields={key: render_field_markdown(value) for key, value in fields.items()},
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


def format_jira_datetime(value: Any) -> str:
    if not value:
        return ""
    raw_value = str(value)
    try:
        parsed = datetime.strptime(raw_value, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        return raw_value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


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


def extract_field_path_text(fields: dict[str, Any], source: str) -> str:
    field_key, *path_parts = source.split(".")
    expand_root = field_key.endswith("[]")
    field_key = field_key.removesuffix("[]")
    value: Any = fields.get(field_key)
    values = list(value) if expand_root and isinstance(value, list) else [value]
    if not path_parts:
        return ", ".join(text for value in values if (text := extract_value_text(value)))
    for part in path_parts:
        next_values: list[Any] = []
        expand_list = part.endswith("[]")
        key = part.removesuffix("[]")
        for item in values:
            if expand_list:
                if isinstance(item, list):
                    next_values.extend(_path_value(child, key) for child in item)
                else:
                    next_values.append(_path_value(item, key))
            else:
                next_values.append(_path_value(item, key))
        values = next_values
    return ", ".join(text for value in values if (text := extract_value_text(value)))


def render_field_markdown(value: Any) -> str:
    if isinstance(value, str) and _looks_like_html(value):
        return markdownify(value).strip()
    if isinstance(value, dict) and value.get("type") == "doc":
        return _adf_to_markdown(value).strip()
    return extract_value_text(value)


def extract_value_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(text for item in value if (text := extract_value_text(item)))
    if isinstance(value, dict):
        if "content" in value:
            return extract_adf_text(value)
        if "name" in value:
            return str(value["name"])
        if "value" in value:
            return str(value["value"])
        return ""
    return extract_adf_text(value)


def _path_value(value: Any, key: str) -> Any:
    if key == "":
        return value
    if isinstance(value, dict):
        return value.get(key)
    return None


def _looks_like_html(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("<") and ">" in stripped


def _adf_to_markdown(node: Any) -> str:
    if isinstance(node, list):
        return "".join(_adf_to_markdown(item) for item in node)
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    content = node.get("content") or []
    if node_type == "doc":
        return "\n\n".join(
            block for child in content if (block := _adf_to_markdown(child).strip())
        )
    if node_type == "paragraph":
        return _adf_to_markdown(content)
    if node_type == "heading":
        level = int((node.get("attrs") or {}).get("level") or 2)
        return f"{'#' * max(1, min(level, 6))} {_adf_to_markdown(content).strip()}"
    if node_type == "bulletList":
        return "\n".join(_adf_list_item(child, "-") for child in content)
    if node_type == "orderedList":
        return "\n".join(
            _adf_list_item(child, f"{index}.") for index, child in enumerate(content, 1)
        )
    if node_type == "listItem":
        return _adf_to_markdown(content)
    if node_type == "text":
        return _adf_text_node_to_markdown(node)
    if node_type == "hardBreak":
        return "\n"
    return _adf_to_markdown(content)


def _adf_list_item(node: dict[str, Any], marker: str) -> str:
    text = _adf_to_markdown(node).strip().replace("\n", "\n  ")
    return f"{marker} {text}"


def _adf_text_node_to_markdown(node: dict[str, Any]) -> str:
    text = str(node.get("text") or "")
    for mark in node.get("marks") or []:
        mark_type = mark.get("type")
        if mark_type == "strong":
            text = f"**{text}**"
        elif mark_type == "em":
            text = f"*{text}*"
        elif mark_type == "code":
            text = f"`{text}`"
        elif mark_type == "link":
            href = (mark.get("attrs") or {}).get("href")
            if href:
                text = f"[{text}]({href})"
    return text
