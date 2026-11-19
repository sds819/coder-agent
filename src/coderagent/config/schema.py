"""Configuration schema. See `docs/design/coding-agent-architecture.md` section 7."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from coderagent.core.os_sandbox import MODES
from coderagent.core.session import PERSISTENCES
from coderagent.core.shell_env import INHERITS
from coderagent.models.call import check_reserved
from coderagent.models.reasoning import EFFORTS
from coderagent.models.verbosity import VERBOSITIES

DEFAULT_SYSTEM_PROMPT = (
    "You are a coding agent working in a code repository. "
    "Prefer the dedicated tools over shell commands: `read` to look at a file, `glob`/`grep`/`ls` to find code, "
    "`edit`/`multi_edit`/`apply_patch` to change files, and `bash` for builds, tests and pipelines. "
    "Call every tool with the argument names of its schema, exactly as they are written there (`path`), "
    "never a translated or renamed variant. "
    "Complete the task the user describes and summarize what you changed."
)

BUILTIN_TOOL_NAMES = [
    "read",
    "write",
    "edit",
    "multi_edit",
    "apply_patch",
    "glob",
    "grep",
    "ls",
    "bash",
    "bash_output",
    "bash_kill",
    "todo_write",
    "task",
    "skill",
]


class RoutingRuleConfig(BaseModel):
    when: str
    """A condition on the state of the session, like `tokens > 50000`."""
    purpose: str
    """The purpose the model is picked for when the condition holds."""


class ModelConfig(BaseModel):
    model_name: str = ""
    """Model name. Falls back to $MSWEA_MODEL_NAME and then to a built-in default."""
    model_kwargs: dict = Field(default_factory=dict)
    api_key: str = ""
    """The key of the provider of the model. It belongs to the user."""
    api_base: str = ""
    """The address of the provider of the model."""
    max_retries: int = 3
    litellm_config: str = ""
    """A litellm config file with the model list. Its aliases name the models."""
    routing: dict[str, str] = Field(default_factory=dict)
    """The model of a purpose: `main`, `cheap`, `summarize`, `reflect`, `strong`."""
    routing_rules: list[RoutingRuleConfig] = Field(default_factory=list)
    set_cache_control: str | None = None
    reasoning_effort: str = ""
    """How much the model thinks: minimal, low, medium, high. Empty is the default of the model."""
    verbosity: str = ""
    """How much the model says: low, medium, high. Empty is the habit of the model."""
    review_model: str = ""
    """The model that reviews the changes. Empty means: the model of the session."""

    @field_validator("reasoning_effort")
    @classmethod
    def _known_effort(cls, value: str) -> str:
        if value and value not in EFFORTS:
            raise ValueError(f"unknown reasoning effort '{value}'. Use one of: {', '.join(EFFORTS)}.")
        return value

    @field_validator("model_kwargs")
    @classmethod
    def _no_reserved_parameters(cls, value: dict) -> dict:
        check_reserved(value)
        """The parameters of the call belong to the agent: a user may not set them."""
        return value

    @field_validator("verbosity")
    @classmethod
    def _known_verbosity(cls, value: str) -> str:
        if value and value not in VERBOSITIES:
            raise ValueError(f"unknown verbosity '{value}'. Use one of: {', '.join(VERBOSITIES)}.")
        return value


class AgentConfig(BaseModel):
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_turns: int = 50
    """Maximum number of model calls per user turn. 0 means no limit."""
    cost_limit: float = 0.0
    """Stop after exceeding this cost. 0 means no limit."""
    token_limit: int = 0
    """Stop after exceeding this many tokens. 0 means no limit.

    It is the budget of a model that has no price, where the money never moves.
    """
    subagent_max_turns: int = 0
    """The ceiling of the turns of every sub agent. 0 means no ceiling.

    A sub agent that asks for more turns than this is held down to it.
    """
    subagent_max_parallel: int = 2
    """How many sub agents may run at the same time. 0 means no limit."""


class ToolConfig(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: list(BUILTIN_TOOL_NAMES))
    """Names of the tools the model may call."""
    disabled: list[str] = Field(default_factory=list)
    bash_timeout: int = 120
    max_output_tokens: int = 8000
    schema_budget_tokens: int = 0
    """The tokens the schemas of the tools may take. 0 means a tenth of the context window."""


class ShellEnvironmentConfig(BaseModel):
    inherit: str = "all"
    """One of all, core, none. How much of the environment of the user the agent sees."""
    exclude: list[str] = Field(default_factory=list)
    """Patterns of the names of the variables that never reach the agent."""
    include: list[str] = Field(default_factory=list)
    """Patterns of the names that reach the agent even when they look like a secret."""
    set: dict[str, str] = Field(default_factory=dict)
    """The variables the agent always sees."""

    @field_validator("inherit")
    @classmethod
    def _known_inherit(cls, value: str) -> str:
        if value not in INHERITS:
            raise ValueError(f"unknown inheritance '{value}'. Use one of: {', '.join(INHERITS)}.")
        return value


class PermissionConfig(BaseModel):
    mode: str = "default"
    """One of default, acceptEdits, plan, bypass, readonly."""
    rules: list[dict] = Field(default_factory=list)
    deny_paths: list[str] = Field(default_factory=list)
    include_dirs: list[str] = Field(default_factory=list)
    """Directories outside the working directory that the agent may still touch."""
    network: str = "allow"
    """One of allow, deny. `deny` refuses the commands that reach the network."""


class ContextConfig(BaseModel):
    context_window: int = 200000
    reserved_output: int = 8000
    compact_threshold: float = 0.8
    keep_recent_turns: int = 20
    keep_recent_token_ratio: float = 0.4
    compact_every_turns: int = 40
    auto_compact: bool = True
    summarize_model: str = ""
    """Model used for summarization. Empty means the same model as the agent."""
    summary_chunk_tokens: int = 0
    """How many tokens one summarization prompt may take. Zero means: as much as the window allows."""
    project_doc_max_bytes: int = 32768
    """The bytes one instruction file may take. A longer file is cut short."""


class MemoryConfig(BaseModel):
    project_path: str = ".coderagent/memory"
    user_path: str = "~/.coderagent/CLAUDE.md"
    enabled: bool = True


class CheckpointConfig(BaseModel):
    enabled: bool = True
    keep: int = 50


class MCPServerConfig(BaseModel):
    name: str
    command: str = ""
    """Command that starts the server, for the stdio transport."""
    url: str = ""
    """Address of the server, for the http transport."""
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    enabled_tools: list[str] = Field(default_factory=list)
    """The tools of this server that the agent may call. Empty means: all of them."""
    disabled_tools: list[str] = Field(default_factory=list)
    """The tools of this server that the agent may not call."""
    startup_timeout: int = 0
    """The seconds the server may take to start. Zero means: the timeout of the section."""
    tool_timeout: int = 0
    """The seconds one call of this server may take. Zero means: the timeout of the section."""
    supports_parallel_tool_calls: bool = True
    """Whether two calls of this server may run at the same time."""


class MCPConfig(BaseModel):
    servers: list[MCPServerConfig] = Field(default_factory=list)
    timeout: int = 30


class HookCommand(BaseModel):
    type: str = "command"
    command: str
    timeout: int = 10
    strict: bool = False
    """When the hook fails, block the action instead of letting it through."""


class HookMatcher(BaseModel):
    matcher: str = ""
    """Regular expression of the tool names this hook applies to. Empty means all."""
    hooks: list[HookCommand] = Field(default_factory=list)


class HookConfig(BaseModel):
    events: dict[str, list[HookMatcher]] = Field(default_factory=dict)


class UIConfig(BaseModel):
    approval_timeout: int = 0
    """Seconds to wait for an approval. 0 waits forever."""
    notifications: bool = True
    """Tell the terminal when a turn is over. The terminal may not show it."""
    notify_command: str = ""
    """A program that tells the user that the turn is over. It gets the title and the body."""
    file_opener: str = ""
    """The program that opens a file: vscode, cursor, windsurf, or a command with {file}."""
    markdown: bool = True
    """Render the answer of the agent as Markdown. The text stays plain while it arrives."""


class HistoryConfig(BaseModel):
    persistence: str = "save-all"
    """One of save-all, save-none. Whether the history of the sessions is written to the disk."""
    max_bytes: int = 0
    """The bytes the history of all the sessions may take. 0 means no limit.

    The oldest sessions are deleted when the history grows over it.
    """

    @field_validator("persistence")
    @classmethod
    def _known_persistence(cls, value: str) -> str:
        if value not in PERSISTENCES:
            raise ValueError(f"unknown persistence '{value}'. Use one of: {', '.join(PERSISTENCES)}.")
        return value


class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    """The options of the environment, like `image` for a container."""

    type: str = "local"
    """The kind of environment. `local` or one of the environments of mini-swe-agent."""
    mode: str = "full-access"
    """How much the commands of the agent may do on this machine.

    One of `read-only`, `workspace-write` or `full-access`. The modes are
    enforced by the operating system, so they hold whatever the permission
    layer says.
    """

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        if value not in MODES:
            raise ValueError(f"unknown sandbox mode '{value}'. Use one of: {', '.join(MODES)}.")
        return value


class VerifyConfig(BaseModel):
    commands: list[str] = Field(default_factory=list)
    """The commands that check the work of the agent. Empty means: no verification."""
    max_rounds: int = 3
    """How many times the agent may try to make the commands pass."""
    timeout: int = 300
    """The seconds one command may take."""


class TelemetryConfig(BaseModel):
    otel_endpoint: str = ""
    """Where the trace of a session goes. Empty means: it stays in the local event log."""
    otel_headers: dict[str, str] = Field(default_factory=dict)
    """The headers that address wants, like the key it asks for."""
    otel_timeout: float = 5.0
    """The seconds one push may take."""


class Config(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    """The values that went wrong are not shown: a key may be among them."""

    model: ModelConfig = Field(default_factory=ModelConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    permissions: PermissionConfig = Field(default_factory=PermissionConfig)
    shell_environment: ShellEnvironmentConfig = Field(default_factory=ShellEnvironmentConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    hooks: HookConfig = Field(default_factory=HookConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    verify: VerifyConfig = Field(default_factory=VerifyConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    profiles: dict[str, dict] = Field(default_factory=dict)
    """Named presets of the configuration. `--profile` picks one of them."""
    profile: str = ""
    """The name of the profile that is in effect."""
    cwd: Path = Field(default_factory=Path.cwd)
