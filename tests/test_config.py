from pathlib import Path

import pytest

from jira_tui.config import DEFAULT_JQL, ConfigError, load_config


def test_load_config_from_environment() -> None:
    config = load_config(
        Path("/missing.ini"),
        {
            "JIRA_BASE_URL": "https://example.atlassian.net/",
            "JIRA_EMAIL": "me@example.com",
            "JIRA_API_TOKEN": "token",
        },
    )

    assert config.normalized_base_url == "https://example.atlassian.net"
    assert config.email == "me@example.com"
    assert config.api_token == "token"
    assert config.default_jql == DEFAULT_JQL


def test_environment_overrides_config_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        "\n".join(
            [
                "[jira]",
                "base_url = https://file.atlassian.net",
                "email = file@example.com",
                "api_token = file-token",
                "default_jql = project = FILE",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(
        config_file,
        {
            "JIRA_BASE_URL": "https://env.atlassian.net",
            "JIRA_EMAIL": "env@example.com",
            "JIRA_API_TOKEN": "env-token",
        },
    )

    assert config.base_url == "https://env.atlassian.net"
    assert config.email == "env@example.com"
    assert config.api_token == "env-token"
    assert config.default_jql == "project = FILE"


def test_missing_required_config_raises() -> None:
    with pytest.raises(ConfigError, match="JIRA_BASE_URL"):
        load_config(Path("/missing.ini"), {})
