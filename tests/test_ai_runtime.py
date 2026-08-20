import sys
import types
import unittest

from ai.groq_compat import install_groq_compat
from ai.runtime import model_candidates, provider_order


class _FakeResponse:
    def __init__(self, content):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]


class AIRuntimeTests(unittest.TestCase):
    def test_groq_primary_is_current_recommended_model(self):
        cfg = {"groq_model": "openai/gpt-oss-120b", "groq_fallback_models": "qwen/qwen3.6-27b,openai/gpt-oss-20b"}
        self.assertEqual(model_candidates(cfg, "groq")[0], "openai/gpt-oss-120b")

    def test_provider_order_keeps_configured_priority(self):
        cfg = {"ai_provider": "groq", "ai_fallback_order": "openrouter,xai,groq"}
        self.assertEqual(provider_order(cfg), ["groq", "openrouter", "xai"])

    def test_legacy_sdk_model_is_redirected_without_changing_callers(self):
        calls = []

        class FakeCompletions:
            def create(self, **kwargs):
                calls.append(kwargs["model"])
                return _FakeResponse("OK")

        class FakeGroq:
            def __init__(self, *args, **kwargs):
                self.chat = types.SimpleNamespace(completions=FakeCompletions())

        fake_module = types.ModuleType("groq")
        fake_module.Groq = FakeGroq
        old = sys.modules.get("groq")
        sys.modules["groq"] = fake_module
        try:
            cfg = {
                "groq_model": "openai/gpt-oss-120b",
                "groq_fallback_models": "qwen/qwen3.6-27b,openai/gpt-oss-20b",
            }
            self.assertTrue(install_groq_compat(cfg))
            client = fake_module.Groq(api_key="test")
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "oi"}],
                max_tokens=10,
            )
            self.assertEqual(response.choices[0].message.content, "OK")
            self.assertEqual(calls, ["openai/gpt-oss-120b"])
        finally:
            if old is None:
                sys.modules.pop("groq", None)
            else:
                sys.modules["groq"] = old


if __name__ == "__main__":
    unittest.main()
