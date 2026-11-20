"""The web interface of the coding agent: FastAPI, SSE and a browser UI.

Nothing here imports FastAPI or uvicorn at module level: `coderagent.web` is
importable on its own, and the server is only pulled in by `coder web`.
"""
