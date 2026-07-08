from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_JQL = "assignee = currentUser() ORDER BY updated DESC"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DetailTabConfig:
    label: str
    source: str

    @property
    def pane_id(self) -> str:
        value = "".join(char.lower() if char.isalnum() else "-" for char in self.label)
        return "tab-" + "-".join(part for part in value.split("-") if part)


DEFAULT_DETAIL_TABS = (
    DetailTabConfig("Description", "description"),
    DetailTabConfig("Comments", "comments"),
)


@dataclass(frozen=True)
class MetadataFieldConfig:
    label: str
    source: str


DEFAULT_METADATA_FIELDS = (
    MetadataFieldConfig("Status", "status"),
    MetadataFieldConfig("Assignee", "assignee"),
    MetadataFieldConfig("Reporter", "reporter"),
    MetadataFieldConfig("Priority", "priority"),
    MetadataFieldConfig("Labels", "labels"),
)


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    default_jql: str = DEFAULT_JQL
    metadata_fields: tuple[MetadataFieldConfig, ...] = DEFAULT_METADATA_FIELDS
    detail_tabs: tuple[DetailTabConfig, ...] = DEFAULT_DETAIL_TABS

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


def default_config_path() -> Path:
    return Path.home() / ".config" / "jira-tui" / "config.ini"


def load_config(path: Path | None = None, environ: dict[str, str] | None = None) -> JiraConfig:
    env = environ if environ is not None else os.environ
    file_values = _read_config_file(path or default_config_path())

    base_url = env.get("JIRA_BASE_URL") or file_values.get("base_url") or ""
    email = env.get("JIRA_EMAIL") or file_values.get("email") or ""
    api_token = env.get("JIRA_API_TOKEN") or file_values.get("api_token") or ""
    default_jql = env.get("JIRA_DEFAULT_JQL") or file_values.get("default_jql") or DEFAULT_JQL
    metadata_fields = _read_metadata_fields(path or default_config_path())
    detail_tabs = _read_detail_tabs(path or default_config_path())

    missing = [
        name
        for name, value in {
            "JIRA_BASE_URL": base_url,
            "JIRA_EMAIL": email,
            "JIRA_API_TOKEN": api_token,
        }.items()
        if not value
    ]
    if missing:
        raise ConfigError(
            "Missing Jira configuration: "
            + ", ".join(missing)
            + ". Set environment variables or create "
            + str(path or default_config_path())
            + "."
        )

    return JiraConfig(
        base_url=base_url,
        email=email,
        api_token=api_token,
        default_jql=default_jql,
        metadata_fields=metadata_fields,
        detail_tabs=detail_tabs,
    )


def _read_config_file(path: Path) -> dict[str, str]:
    parser = configparser.ConfigParser()
    if not path.exists():
        return {}
    parser.read(path)
    if not parser.has_section("jira"):
        return {}
    return {key: value for key, value in parser.items("jira")}


def _read_detail_tabs(path: Path) -> tuple[DetailTabConfig, ...]:
    return (
        _read_field_configs(path, section="detail_tabs", config_type=DetailTabConfig)
        or DEFAULT_DETAIL_TABS
    )


def _read_metadata_fields(path: Path) -> tuple[MetadataFieldConfig, ...]:
    return (
        _read_field_configs(path, section="metadata_fields", config_type=MetadataFieldConfig)
        or DEFAULT_METADATA_FIELDS
    )


def _read_field_configs[T](
    path: Path,
    *,
    section: str,
    config_type: type[T],
) -> tuple[T, ...]:
    parser = configparser.ConfigParser()
    parser.optionxform = str
    if not path.exists():
        return ()
    parser.read(path)
    if not parser.has_section(section):
        return ()
    return tuple(
        config_type(label.strip(), source.strip())
        for label, source in parser.items(section)
        if label.strip() and source.strip()
    )
