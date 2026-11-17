"""The memory layers. M2 only reads them, writing is M4.

Working memory lives in the session metadata, session memory in the summary,
project memory in `.coderagent/memory/` and user memory in `~/.coderagent/CLAUDE.md`.
"""

from pathlib import Path

from coderagent.config.schema import MemoryConfig
from coderagent.core.instructions import InstructionBlock, load_instructions, once_per_file, read_block
from coderagent.paths import config_home


def project_memory_files(cwd: Path, config: MemoryConfig) -> list[Path]:
    directory = Path(cwd) / config.project_path
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.md") if path.is_file())


def load_project_memory(cwd: Path, config: MemoryConfig) -> list[InstructionBlock]:
    blocks = []
    for path in project_memory_files(cwd, config):
        block = read_block(path)
        if block:
            blocks.append(block)
    return blocks


def load_user_memory(config: MemoryConfig, user_home: Path | None = None) -> InstructionBlock | None:
    home = Path(user_home) if user_home else config_home()
    return read_block(home / Path(config.user_path).name)


def project_text(cwd: Path, user_home: Path | None, config: MemoryConfig, max_bytes: int = 0) -> str:
    """The instructions and the memory of a directory, as the model sees them.

    The sub agent gets them too: it works in the same project, and the rules of
    the project are the rules of the work.
    """
    blocks = load_instructions(cwd, user_home, max_bytes)
    blocks += load_project_memory(cwd, config)
    user_memory = load_user_memory(config, user_home)
    if user_memory:
        blocks.append(user_memory)
    return "\n\n".join(block.render() for block in once_per_file(blocks))
