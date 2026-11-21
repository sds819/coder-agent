"""The tests of the coding agent never touch the data of the user."""

import pytest

from tests.coderagent.gitd import GitDaemon


@pytest.fixture(autouse=True)
def _coder_home(tmp_path, monkeypatch):
    """The user level data goes to a temporary directory, not to the one of the user."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))


@pytest.fixture
def daemon(tmp_path):
    """A repository of skills that is served over the git protocol."""
    server = GitDaemon(tmp_path)
    yield server
    server.close()
