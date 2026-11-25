"""Configuration schema. See `docs/design/coding-agent-architecture.md` section 7."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from coderagent.core.capabilities import MODALITIES
from coderagent.core.os_sandbox import MODES
from coderagent.core.session import PERSISTENCES
from coderagent.core.shell_env import INHERITS
from coderagent.models.call import check_reserved
from coderagent.models.reasoning import EFFORTS
from coderagent.models.verbosity import VERBOSITIES
from coderagent.tools.permissions import NETWORK_POLICIES, PermissionMode, check_rule

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

ENVIRONMENT_TYPES = (
    "local",
    "docker",
    "singularity",
    "swerex_docker",
    "swerex_modal",
    "bubblewrap",
    "contree",
)
"""The kinds of environment the commands of the agent may run in."""

HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
    "SessionStart",
    "SessionEnd",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
)
"""The moments of a session a hook may hang on."""

PURPOSES = ("main", "cheap", "strong", "summarize", "reflect", "review")
"""The jobs a model may be picked for."""

COMPARISONS = {
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
}
"""The operators a condition of the routing may use."""


def parse_condition(when: str) -> tuple[str, str, float] | None:
    """The parts of a condition: a key, an operator and a number.

    Nothing when the condition is not one: a condition that cannot be read is
    a condition that never holds, and the user should hear about it.
    """
    parts = when.split()
    if len(parts) != 3:
        return None
    key, operator, value = parts
    if operator not in COMPARISONS:
        return None
    try:
        return key, operator, float(value)
    except ValueError:
        return None


def check_routing_rule(rule: dict) -> None:
    """Whether a routing rule is one the router can read. It raises when it is not.

    The rule is checked without the model, so that the message is the one of
    the rule and not a nest of field names.
    """
    when = rule.get("when")
    if not isinstance(when, str) or parse_condition(when) is None:
        raise ValueError(f"'{when}' is not a condition. A condition is a key, an operator and a number.")
    purpose = rule.get("purpose")
    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose '{purpose}'. Use one of: {', '.join(PURPOSES)}.")


class RoutingRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    when: str
    """A condition on the state of the session, like `tokens > 50000`."""
    purpose: str
    """The purpose the model is picked for when the condition holds."""

    @field_validator("when")
    @classmethod
    def _known_condition(cls, value: str) -> str:
        if parse_condition(value) is None:
            raise ValueError(f"'{value}' is not a condition. A condition is a key, an operator and a number.")
        return value

    @field_validator("purpose")
    @classmethod
    def _known_purpose(cls, value: str) -> str:
        if value not in PURPOSES:
            raise ValueError(f"unknown purpose '{value}'. Use one of: {', '.join(PURPOSES)}.")
        return value


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = ""
    """Model name. Falls back to $MSWEA_MODEL_NAME and then to a built-in default."""
    model_kwargs: dict = Field(default_factory=dict)
    api_key: str = ""
    """The key of the provider of the model. It belongs to the user."""
    api_base: str = ""
    """The address of the provider of the model."""
    max_retries: int = Field(default=3, ge=0)
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
    capabilities: dict[str, dict[str, bool]] = Field(default_factory=dict)
    """What the models take: the name of a model and the kinds of content it takes.

    The user says it for the models litellm does not know: `{"my/model": {"image": true}}`.
    """

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

    @field_validator("routing")
    @classmethod
    def _known_purposes(cls, value: dict) -> dict:
        for purpose in value:
            if purpose not in PURPOSES:
                raise ValueError(f"unknown purpose '{purpose}'. Use one of: {', '.join(PURPOSES)}.")
        return value

    @field_validator("capabilities")
    @classmethod
    def _known_capabilities(cls, value: dict) -> dict:
        for model, takes in value.items():
            for modality, supported in takes.items():
                if modality not in MODALITIES:
                    raise ValueError(
                        f"unknown kind of content '{modality}' for the model '{model}'. "
                        f"Use one of: {', '.join(MODALITIES)}."
                    )
                if not isinstance(supported, bool):
                    raise ValueError(f"what the model '{model}' takes for {modality} is not true or false.")
        return value


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_turns: int = Field(default=100, ge=0)
    """Maximum number of model calls per user turn. 0 means no limit."""
    cost_limit: float = Field(default=0.0, ge=0)
    """Stop after exceeding this cost. 0 means no limit."""
    token_limit: int = Field(default=0, ge=0)
    """Stop after exceeding this many tokens. 0 means no limit.

    It is the budget of a model that has no price, where the money never moves.
    """
    subagent_max_turns: int = Field(default=0, ge=0)
    """The ceiling of the turns of every sub agent. 0 means no ceiling.

    A sub agent that asks for more turns than this is held down to it.
    """
    subagent_max_parallel: int = Field(default=2, ge=0)
    """How many sub agents may run at the same time. 0 means no limit."""


class ToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: list[str] = Field(default_factory=lambda: list(BUILTIN_TOOL_NAMES))
    """Names of the tools the model may call."""
    disabled: list[str] = Field(default_factory=list)
    bash_timeout: int = Field(default=120, ge=0)
    max_output_tokens: int = Field(default=8000, ge=0)
    schema_budget_tokens: int = Field(default=0, ge=0)
    """The tokens the schemas of the tools may take. 0 means a tenth of the context window."""

    @field_validator("enabled", "disabled")
    @classmethod
    def _known_tools(cls, value: list[str]) -> list[str]:
        for name in value:
            if name not in BUILTIN_TOOL_NAMES:
                raise ValueError(f"unknown tool '{name}'. Use one of: {', '.join(BUILTIN_TOOL_NAMES)}.")
        return value


class ShellEnvironmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    mode: str = "default"
    """One of default, acceptEdits, plan, bypass, readonly."""
    rules: list[dict] = Field(default_factory=list)
    deny_paths: list[str] = Field(default_factory=list)
    include_dirs: list[str] = Field(default_factory=list)
    """Directories outside the working directory that the agent may still touch."""
    network: str = "allow"
    """One of allow, deny. `deny` refuses the commands that reach the network."""

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        if value not in {mode.value for mode in PermissionMode}:
            raise ValueError(
                f"unknown permission mode '{value}'. Use one of: {', '.join(m.value for m in PermissionMode)}."
            )
        return value

    @field_validator("network")
    @classmethod
    def _known_network(cls, value: str) -> str:
        if value not in NETWORK_POLICIES:
            raise ValueError(f"unknown network policy '{value}'. Use one of: {', '.join(NETWORK_POLICIES)}.")
        return value

    @field_validator("rules")
    @classmethod
    def _known_rules(cls, value: list[dict]) -> list[dict]:
        for number, rule in enumerate(value, start=1):
            try:
                check_rule(rule)
            except ValueError as error:
                raise ValueError(f"rule {number}: {error}") from None
            """A rule that says something the policy does not know is a rule
            that may not deny: it is refused at the start instead."""
        return value


class ContextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_window: int = Field(default=200000, gt=0)
    reserved_output: int = Field(default=8000, ge=0)
    compact_threshold: float = Field(default=0.8, gt=0, le=1)
    keep_recent_turns: int = Field(default=20, ge=0)
    keep_recent_token_ratio: float = Field(default=0.4, ge=0, le=1)
    compact_every_turns: int = Field(default=40, ge=0)
    auto_compact: bool = True
    summarize_model: str = ""
    """Model used for summarization. Empty means the same model as the agent."""
    summary_chunk_tokens: int = Field(default=0, ge=0)
    """How many tokens one summarization prompt may take. Zero means: as much as the window allows."""
    project_doc_max_bytes: int = Field(default=32768, ge=0)
    """The bytes one instruction file may take. A longer file is cut short."""


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_path: str = ".coderagent/memory"
    user_path: str = "~/.coderagent/CLAUDE.md"
    enabled: bool = True


class CheckpointConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    keep: int = Field(default=50, ge=0)


class MCPServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    startup_timeout: int = Field(default=0, ge=0)
    """The seconds the server may take to start. Zero means: the timeout of the section."""
    tool_timeout: int = Field(default=0, ge=0)
    """The seconds one call of this server may take. Zero means: the timeout of the section."""
    supports_parallel_tool_calls: bool = True
    """Whether two calls of this server may run at the same time."""


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servers: list[MCPServerConfig] = Field(default_factory=list)
    timeout: int = Field(default=30, ge=0)


class HookCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "command"
    command: str
    timeout: int = Field(default=10, ge=0)
    strict: bool = False
    """When the hook fails, block the action instead of letting it through."""


class HookMatcher(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matcher: str = ""
    """Regular expression of the tool names this hook applies to. Empty means all."""
    hooks: list[HookCommand] = Field(default_factory=list)


class HookConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: dict[str, list[HookMatcher]] = Field(default_factory=dict)

    @field_validator("events")
    @classmethod
    def _known_events(cls, value: dict) -> dict:
        for event in value:
            if event not in HOOK_EVENTS:
                raise ValueError(f"unknown hook event '{event}'. Use one of: {', '.join(HOOK_EVENTS)}.")
        return value


class UIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_timeout: int = Field(default=0, ge=0)
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
    model_config = ConfigDict(extra="forbid")

    persistence: str = "save-all"
    """One of save-all, save-none. Whether the history of the sessions is written to the disk."""
    max_bytes: int = Field(default=0, ge=0)
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

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in ENVIRONMENT_TYPES and "." not in value:
            """A path to a class of mini-swe-agent is a kind of environment too."""
            raise ValueError(f"unknown environment '{value}'. Use one of: {', '.join(ENVIRONMENT_TYPES)}.")
        return value


class VerifyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commands: list[str] = Field(default_factory=list)
    """The commands that check the work of the agent. Empty means: no verification."""
    max_rounds: int = Field(default=3, ge=0)
    """How many times the agent may try to make the commands pass."""
    timeout: int = Field(default=300, ge=0)
    """The seconds one command may take."""


class TelemetryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    otel_endpoint: str = ""
    """Where the trace of a session goes. Empty means: it stays in the local event log."""
    otel_headers: dict[str, str] = Field(default_factory=dict)
    """The headers that address wants, like the key it asks for."""
    otel_timeout: float = Field(default=5.0, ge=0)
    """The seconds one push may take."""


class SkillsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    """Whether skills may be downloaded and installed."""
    max_bytes: int = Field(default=8 * 1024 * 1024, ge=0)
    """How many bytes a download may take."""
    max_file_bytes: int = Field(default=1024 * 1024, ge=0)
    """How many bytes one file of a skill may have."""
    max_files: int = Field(default=2000, ge=0)
    """How many files a skill may have."""
    max_depth: int = Field(default=16, ge=0)
    """How deep the directories of a skill may go."""
    timeout: int = Field(default=30, ge=0)
    """The seconds a download may take."""
    registries: list[str] = Field(default_factory=list)
    """The registries that are offered in the page of the skills."""
    github_token: str = ""
    """The token of GitHub. It only goes into the headers of a request."""
    allow_insecure: bool = False
    """Whether `http://` may be fetched. `https://` is the rule."""
    allowed_hosts: list[str] = Field(default_factory=list)
    """The hosts that may point inside the network. The others may not."""


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    """The values that went wrong are not shown: a key may be among them.

    A section that is not known is refused: a name that is written wrong would
    otherwise be a setting that does nothing.
    """

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
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    profiles: dict[str, dict] = Field(default_factory=dict)
    """Named presets of the configuration. `--profile` picks one of them."""
    profile: str = ""
    """The name of the profile that is in effect."""
