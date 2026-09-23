import json
import subprocess
import types
import unittest

from qa_review.model import ClaudeCLIModel, ModelCallError, StubModel, validate

SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["PASS", "FAIL"]}, "quote": {"type": "string"}},
    "required": ["verdict", "quote"],
}


def envelope(obj, is_error=False):
    return json.dumps({"type": "result", "is_error": is_error, "structured_output": obj})


class FakeRunner:
    """Returns queued (returncode, stdout) results and records the calls."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        rc, out = self.results.pop(0)
        return types.SimpleNamespace(returncode=rc, stdout=out, stderr="boom" if rc else "")


class ValidateTests(unittest.TestCase):
    def test_accepts_valid_and_rejects_bad_enum_and_missing_key(self):
        validate({"verdict": "PASS", "quote": "x"}, SCHEMA)
        with self.assertRaises(ValueError):
            validate({"verdict": "MAYBE", "quote": "x"}, SCHEMA)
        with self.assertRaises(ValueError):
            validate({"verdict": "PASS"}, SCHEMA)


class ClientTests(unittest.TestCase):
    def test_stub_returns_canned_answer_by_label(self):
        m = StubModel({"item-1": {"verdict": "PASS", "quote": "q"}})
        self.assertEqual(m.ask("prompt", SCHEMA, "item-1")["verdict"], "PASS")

    def test_valid_answer_returned(self):
        r = FakeRunner([(0, envelope({"verdict": "FAIL", "quote": "q"}))])
        m = ClaudeCLIModel(runner=r)
        self.assertEqual(m.ask("p", SCHEMA, "item-1"), {"verdict": "FAIL", "quote": "q"})

    def test_command_carries_isolation_flags_and_schema_and_prompt_on_stdin(self):
        r = FakeRunner([(0, envelope({"verdict": "PASS", "quote": "q"}))])
        ClaudeCLIModel(runner=r).ask("the prompt", SCHEMA, "i")
        cmd, kw = r.calls[0]
        for flag in ("-p", "--tools", "--setting-sources", "--strict-mcp-config",
                     "--disable-slash-commands", "--no-session-persistence",
                     "--output-format", "--json-schema", "--model"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertEqual(json.loads(cmd[cmd.index("--json-schema") + 1]), SCHEMA)
        self.assertEqual(kw["input"], "the prompt")
        self.assertNotIn("the prompt", cmd)

    def test_fails_twice_raises_naming_the_item(self):
        r = FakeRunner([(1, ""), (1, "")])
        with self.assertRaises(ModelCallError) as cm:
            ClaudeCLIModel(runner=r).ask("p", SCHEMA, "cta.abc123")
        self.assertIn("cta.abc123", str(cm.exception))
        self.assertEqual(len(r.calls), 2)

    def test_fails_once_then_succeeds(self):
        r = FakeRunner([(1, ""), (0, envelope({"verdict": "PASS", "quote": "q"}))])
        self.assertEqual(ClaudeCLIModel(runner=r).ask("p", SCHEMA, "i")["verdict"], "PASS")

    def test_enum_violation_counts_as_failure_and_retries(self):
        r = FakeRunner([(0, envelope({"verdict": "MAYBE", "quote": "q"})),
                        (0, envelope({"verdict": "PASS", "quote": "q"}))])
        self.assertEqual(ClaudeCLIModel(runner=r).ask("p", SCHEMA, "i")["verdict"], "PASS")

    def test_unparseable_output_twice_raises(self):
        r = FakeRunner([(0, "not json"), (0, "still not json")])
        with self.assertRaises(ModelCallError):
            ClaudeCLIModel(runner=r).ask("p", SCHEMA, "i")

    def test_is_error_envelope_is_a_failure(self):
        r = FakeRunner([(0, envelope(None, is_error=True)), (0, envelope(None, is_error=True))])
        with self.assertRaises(ModelCallError):
            ClaudeCLIModel(runner=r).ask("p", SCHEMA, "i")

    def test_runner_receives_the_configured_timeout(self):
        r = FakeRunner([(0, envelope({"verdict": "PASS", "quote": "q"}))])
        ClaudeCLIModel(runner=r, timeout=42).ask("p", SCHEMA, "i")
        self.assertEqual(r.calls[0][1]["timeout"], 42)

    def test_a_hung_call_times_out_and_retries_instead_of_blocking_forever(self):
        r = TimeoutThenOkRunner()
        self.assertEqual(ClaudeCLIModel(runner=r, timeout=1).ask("p", SCHEMA, "i")["verdict"], "PASS")
        self.assertEqual(len(r.calls), 2)

    def test_two_timeouts_raise_a_model_call_error_naming_the_timeout(self):
        r = AlwaysTimeoutRunner()
        with self.assertRaises(ModelCallError) as cm:
            ClaudeCLIModel(runner=r, timeout=1).ask("p", SCHEMA, "cta.abc123")
        self.assertIn("timed out", str(cm.exception))
        self.assertIn("cta.abc123", str(cm.exception))
        self.assertEqual(r.calls, 2)

    def test_missing_claude_binary_fails_fast_without_retrying(self):
        calls = []

        def missing(cmd, **kw):
            calls.append(cmd)
            raise FileNotFoundError("claude")

        with self.assertRaises(ModelCallError) as cm:
            ClaudeCLIModel(runner=missing).ask("p", SCHEMA, "i")
        self.assertIn("not on PATH", str(cm.exception))
        self.assertEqual(len(calls), 1)


class TimeoutThenOkRunner:
    """Times out once, then succeeds -- a hung `claude` call should not sink the whole run."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if len(self.calls) == 1:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        return types.SimpleNamespace(returncode=0, stdout=envelope({"verdict": "PASS", "quote": "q"}), stderr="")


class AlwaysTimeoutRunner:
    def __init__(self):
        self.calls = 0

    def __call__(self, cmd, **kw):
        self.calls += 1
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))


if __name__ == "__main__":
    unittest.main()
