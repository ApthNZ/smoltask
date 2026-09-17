"""Configuration: the environment contract, and the documents the house
standard requires every repo to carry."""

import os
import re

from conftest import ROOT


def test_db_path_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SMOLTASK_DB", "/tmp/somewhere-else.db")
    import importlib

    import db as db_module

    importlib.reload(db_module)
    assert db_module.DB_PATH == "/tmp/somewhere-else.db"
    monkeypatch.delenv("SMOLTASK_DB")
    importlib.reload(db_module)
    assert db_module.DB_PATH.endswith("smoltask.db")


def test_env_example_documents_every_setting():
    text = (ROOT / ".env.example").read_text()
    for name in ("SMOLTASK_DB", "SMOLTASK_PORT"):
        assert name in text, f".env.example does not mention {name}"


def test_env_example_holds_no_real_values():
    """It is a template. A token in here would be a token in the public repo."""
    text = (ROOT / ".env.example").read_text()
    assert not re.search(r"=\s*['\"]?[A-Za-z0-9+/]{24,}", text)


def test_required_documents_exist():
    for name in ("README.md", "SECURITY.md", "SECURITY_STATUS.md", "DESIGN.md",
                 ".gitignore", ".env.example", "requirements.txt", "Dockerfile"):
        assert (ROOT / name).exists(), f"missing {name}"


def test_dependencies_are_pinned():
    for name in ("requirements.txt", "requirements-dev.txt"):
        for line in (ROOT / name).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r")):
                continue
            assert "==" in line, f"{name}: {line} is not pinned"


def test_compose_takes_the_port_from_the_environment():
    """A hardcoded port in the published compose file is a deployment detail."""
    text = (ROOT / "docker-compose.yml").read_text()
    assert "${SMOLTASK_PORT:-8108}:8000" in text


def test_the_container_does_not_run_as_root():
    assert "USER smoltask" in (ROOT / "Dockerfile").read_text()
