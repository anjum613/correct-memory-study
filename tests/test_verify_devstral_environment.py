from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from cmpilot.model_profiles import load_model_profile


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_devstral_environment.py"


def load_verifier_module():
    spec = importlib.util.spec_from_file_location("verify_devstral_environment", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chat_template_preflight_uses_exact_offline_tokenizer_and_native_bash_tool(monkeypatch) -> None:
    profile = load_model_profile("devstral-small-2507")
    calls: dict[str, object] = {}

    class Record:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

    class FakeMistralTokenizer:
        @classmethod
        def from_hf_hub(cls, model_id, **kwargs):
            calls["model_id"] = model_id
            calls["tokenizer_kwargs"] = kwargs
            return cls()

        def encode_chat_completion(self, request):
            calls["request"] = request
            return SimpleNamespace(tokens=[1, 2, 131072])

    modules = {
        "mistral_common": ModuleType("mistral_common"),
        "mistral_common.protocol": ModuleType("mistral_common.protocol"),
        "mistral_common.protocol.instruct": ModuleType("mistral_common.protocol.instruct"),
        "mistral_common.protocol.instruct.messages": ModuleType("mistral_common.protocol.instruct.messages"),
        "mistral_common.protocol.instruct.request": ModuleType("mistral_common.protocol.instruct.request"),
        "mistral_common.protocol.instruct.tool_calls": ModuleType("mistral_common.protocol.instruct.tool_calls"),
        "mistral_common.tokens": ModuleType("mistral_common.tokens"),
        "mistral_common.tokens.tokenizers": ModuleType("mistral_common.tokens.tokenizers"),
        "mistral_common.tokens.tokenizers.mistral": ModuleType("mistral_common.tokens.tokenizers.mistral"),
    }
    modules["mistral_common.protocol.instruct.messages"].SystemMessage = Record
    modules["mistral_common.protocol.instruct.messages"].UserMessage = Record
    modules["mistral_common.protocol.instruct.request"].ChatCompletionRequest = Record
    modules["mistral_common.protocol.instruct.tool_calls"].Function = Record
    modules["mistral_common.protocol.instruct.tool_calls"].Tool = Record
    modules["mistral_common.tokens.tokenizers.mistral"].MistralTokenizer = FakeMistralTokenizer
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    result = load_verifier_module().render_official_template()

    assert calls["model_id"] == profile.tokenizer_id
    assert calls["tokenizer_kwargs"] == {"revision": profile.tokenizer_revision, "local_files_only": True}
    request = calls["request"]
    assert request.tools[0].function.name == "bash"
    assert request.tools[0].function.parameters["required"] == ["command"]
    assert result["token_count"] == 3
    assert len(result["rendered_token_ids_sha256"]) == 64
