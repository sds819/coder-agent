"""Where the coding agent keeps its configuration and session data."""

import os
from pathlib import Path


def config_home() -> Path:
    """Root of the coder agent's user-level data. Overridable via `MSWEA_CODER_HOME`."""
    home = os.getenv("MSWEA_CODER_HOME")
    return Path(home) if home else Path.home() / ".coderagent"


def global_env_file() -> Path:
    """The file with the keys of the models. The same one mini-swe-agent uses."""
    from platformdirs import user_config_dir

    return Path(os.getenv("MSWEA_GLOBAL_CONFIG_DIR") or user_config_dir("mini-swe-agent")) / ".env"


def load_global_env() -> None:
    """Load the keys of the models into the environment.

    Two files are read: the one of the coding agent and the one that
    mini-swe-agent used. The keys that are already in the environment win, and
    the file of the coding agent wins over the one of mini-swe-agent.
    """
    from dotenv import load_dotenv

    for path in (config_home() / ".env", global_env_file()):
        if path.is_file():
            load_dotenv(dotenv_path=path, override=False)
