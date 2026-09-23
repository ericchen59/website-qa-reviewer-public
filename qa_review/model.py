"""Model access through the local `claude` CLI, one narrow question at a time.

The isolation flags mirror fixtures/naive-run.py: no tools, no setting sources, no MCP
servers, no slash commands, no session persistence, and a scratch working directory, so
the model sees only the prompt. The verdict shape is forced with --json-schema.
Calls are strictly sequential.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

MODEL = os.environ.get("QA_REVIEW_MODEL", "claude-sonnet-5")
ATTEMPTS = 2
TIMEOUT = int(os.environ.get("QA_REVIEW_MODEL_TIMEOUT", "180"))


class ModelCallError(RuntimeError):
    """A model call failed after its retry. The runner aborts the run (no partial report)."""


def validate(value, schema: dict, path: str = "answer") -> None:
    """Minimal JSON-schema check: type, properties, required, enum, items."""
    t = schema.get("type")
    checks = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if t in checks and not isinstance(value, checks[t]):
        raise ValueError(f"{path}: expected {t}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: {value!r} not in {schema['enum']}")
    if t == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}: missing {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate(value[key], sub, f"{path}.{key}")
    if t == "array" and "items" in schema:
        for i, v in enumerate(value):
            validate(v, schema["items"], f"{path}[{i}]")


class ModelClient:
    def ask(self, prompt: str, schema: dict, label: str) -> dict:
        raise NotImplementedError


class StubModel(ModelClient):
    """Canned answers for tests, keyed by the call label. A value may be a callable."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls: list[str] = []

    def ask(self, prompt: str, schema: dict, label: str) -> dict:
        self.calls.append(label)
        a = self.answers[label]
        return a(prompt) if callable(a) else a


class ClaudeCLIModel(ModelClient):
    def __init__(self, model: str = MODEL, runner=subprocess.run, timeout: int = TIMEOUT):
        self.model = model
        self.runner = runner
        self.timeout = timeout

    def command(self, schema: dict) -> list[str]:
        return [
            "claude", "-p", "--model", self.model, "--tools", "", "--setting-sources", "",
            "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
            "--output-format", "json", "--json-schema", json.dumps(schema),
        ]

    def ask(self, prompt: str, schema: dict, label: str) -> dict:
        last = "no attempt made"
        for _ in range(ATTEMPTS):
            with tempfile.TemporaryDirectory() as scratch:
                try:
                    res = self.runner(self.command(schema), input=prompt, capture_output=True,
                                      text=True, cwd=scratch, timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    last = f"timed out after {self.timeout}s"
                    continue
                except FileNotFoundError as e:
                    raise ModelCallError(f"the claude CLI is not on PATH ({e})") from e
            if res.returncode != 0:
                last = f"exit {res.returncode}: {(res.stderr or '').strip()[:200]}"
                continue
            try:
                env = json.loads(res.stdout)
                if env.get("is_error"):
                    last = "the CLI reported an error"
                    continue
                answer = env["structured_output"]
                validate(answer, schema)
                return answer
            except (ValueError, KeyError, TypeError) as e:
                last = f"unusable output: {e}"
        raise ModelCallError(f"model call for {label} failed after {ATTEMPTS} attempts ({last})")
