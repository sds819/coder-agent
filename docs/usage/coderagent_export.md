# The trace of a session

Every session is written to an event log, and that log is the source of truth.
The `export` command turns it into a trace, with the metrics of the session.

```bash
coder export --session 20261106-a1b2c3 --format json --out trace.json
coder export --session 20261106-a1b2c3 --format otel --out trace.otlp
coder export --cwd .                       # the newest session of this directory
```

Without `--out` the trace goes to the standard output.

## The json format

The format is `coder-agent-1.0`, next to the `mini-swe-agent-1.1` of
mini-swe-agent:

```json
{
  "trajectory_format": "coder-agent-1.0",
  "session": {
    "id": "20261106-a1b2c3",
    "cwd": "/home/me/project",
    "created_at": 1762310400.0,
    "updated_at": 1762310900.0,
    "state": "done",
    "model_name": "deepseek/deepseek-flash",
    "permission_mode": "default",
    "turn_count": 3,
    "total_cost": 0.42
  },
  "events": [
    {
      "session_id": "20261106-a1b2c3",
      "type": "user_message",
      "timestamp": 1762310400.0,
      "payload": {"content": "fix the test"}
    }
  ],
  "metrics": {
    "total_cost": 0.42,
    "total_tokens_in": 120433,
    "total_tokens_out": 8421,
    "model_calls": 9,
    "tool_calls": 60,
    "per_tool": {"read": 42, "bash": 13, "edit": 5},
    "per_purpose_cost": {"main": 0.38, "cheap": 0.04},
    "per_model_cost": {"deepseek/deepseek-flash": 0.38},
    "duration_seconds": 412.3,
    "compactions": 3,
    "summary_ratios": [0.06, 0.07, 0.05],
    "errors": 0
  }
}
```

`summary_ratios` holds one number per compaction: how much of the compacted
history the summary kept. It is the gauge of the quality of the summary.

## The otel format

The same session as OTLP/JSON: one span per turn, one per model call, one per
tool call. The calls of a turn are the children of that turn, and the file goes
into Jaeger, Tempo or any other place that reads OTLP.

```json
{
  "resourceSpans": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "coderagent"}},
          {"key": "session.id", "value": {"stringValue": "20261106-a1b2c3"}},
          {"key": "session.cwd", "value": {"stringValue": "/home/me/project"}}
        ]
      },
      "scopeSpans": [
        {
          "scope": {"name": "coderagent"},
          "spans": [
            {
              "name": "turn",
              "traceId": "6f1c…",
              "spanId": "9a02…",
              "startTimeUnixNano": "1762310400000000000",
              "endTimeUnixNano": "1762310412000000000",
              "attributes": [
                {"key": "turn.cost", "value": {"doubleValue": 0.12}},
                {"key": "turn.stop_reason", "value": {"stringValue": "end_turn"}}
              ]
            },
            {
              "name": "model",
              "parentSpanId": "9a02…",
              "attributes": [
                {"key": "model.name", "value": {"stringValue": "deepseek/deepseek-flash"}},
                {"key": "cost", "value": {"doubleValue": 0.05}},
                {"key": "tokens.in", "value": {"intValue": 12000}},
                {"key": "tokens.out", "value": {"intValue": 800}}
              ]
            },
            {
              "name": "tool.read",
              "parentSpanId": "9a02…",
              "attributes": [
                {"key": "tool.name", "value": {"stringValue": "read"}},
                {"key": "tool.call_id", "value": {"stringValue": "call_1"}}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

The spans stand next to each other, not inside each other: that is what OTLP
wants, and a backend that reads it will not complain. A tool that failed gets
a `status` of code 2.

## Sending the trace to a backend

The trace does not have to stay on your machine. Name a collector and the trace
of every turn goes there as the turn ends:

```yaml
telemetry:
  otel_endpoint: "http://localhost:4318/v1/traces"
  otel_headers:
    authorization: "Bearer …"
```

- **The event log stays the source of truth** — the trace is built from it, and
  the log is written whether the backend is there or not;
- **A backend that is down is a warning**: the session does not stop, and the
  trace is sent again with the next turn;
- **Every span is sent once** — the second turn does not send the first one
  again;
- **A project may not send the trace somewhere**: the configuration of a
  project may close the trace (`otel_endpoint: ""`), never point it at an
  address of its own. Where the trace goes is your decision, not the decision
  of the repository you cloned;
- **By hand**: `coder export --format otel --push` sends one session to the
  address of the configuration.

The headers are for the backends that ask for a key. They are yours: the
configuration of a project may not bring headers either.

## Where the money went

The `/cost` command shows the same metrics, with the cost of the session split
by purpose, by model and by tool:

```
model: deepseek/deepseek-flash
calls: 9
tokens in the context: 120433
tokens spent: 128854
cost so far: $0.4200
cost: $0.4200
tokens: 120433 in, 8421 out
model calls: 9
tool calls: 60
duration: 412.3s
by purpose:
  main        $0.3800
  cheap       $0.0400
by model:
  deepseek/deepseek-flash  $0.4200
by tool:
  bash         13
  edit          5
  read         42
```

The `purpose` is the job the model was called for: `main` for the agent itself,
the purpose of the sub agent for a delegated task, `summarize` for the summary
of a compacted context and `reflect` for the memory of the session.
