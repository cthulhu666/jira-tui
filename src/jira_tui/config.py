from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

DEFAULT_JQL = "assignee = currentUser() ORDER BY updated DESC"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    default_jql: str = DEFAULT_JQL

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


def default_config_path() -> Path:
    return Path(user_config_dir("jira-tui", appauthor=False)) / "config.ini"


def load_config(path: Path | None = None, environ: dict[str, str] | None = None) -> JiraConfig:
    env = environ if environ is not None else os.environ
    file_values = _read_config_file(path or default_config_path())

    base_url = env.get("JIRA_BASE_URL") or file_values.get("base_url") or ""
    email = env.get("JIRA_EMAIL") or file_values.get("email") or ""
    api_token = env.get("JIRA_API_TOKEN") or file_values.get("api_token") or ""
    default_jql = env.get("JIRA_DEFAULT_JQL") or file_values.get("default_jql") or DEFAULT_JQL

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
    )


def _read_config_file(path: Path) -> dict[str, str]:
    parser = configparser.ConfigParser()
    if not path.exists():
        return {}
    parser.read(path)
    if not parser.has_section("jira"):
        return {}
    return {key: value for key, value in parser.items("jira")}
