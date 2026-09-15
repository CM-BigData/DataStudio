from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import openai
import pytest
import yaml

from synthesis_engine.llm import (
    ImageGenerationConfig,
    LLMClientConfig,
    LLMClientError,
    OpenAIClient,
    OpenAIImageClient,
)
from synthesis_engine.llm.client import _load_openai_completion


class _Usage:
    def model_dump(self) -> dict[str, int]:
        return {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}


def test_openai_client_builds_request_and_normalizes_sdk_response() -> None:
    calls: list[dict[str, Any]] = []

    def completion_fn(**request: Any) -> Any:
        calls.append(request)
        return SimpleNamespace(
            id="request-1",
            model="gpt-test-response",
            choices=[SimpleNamespace(message=SimpleNamespace(content="generated"))],
            usage=_Usage(),
        )

    config = LLMClientConfig(
        model="gpt-test",
        temperature=0.3,
        max_tokens=128,
        extra={"top_p": 0.9, "vendor_option": "configured"},
    )
    response = OpenAIClient(config, completion_fn=completion_fn).complete(
        [{"role": "user", "content": "hello"}],
        {"response_format": {"type": "json_object"}, "vendor_option": "per-call"},
    )

    assert calls == [
        {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.3,
            "max_tokens": 128,
            "top_p": 0.9,
            "response_format": {"type": "json_object"},
            "extra_body": {"vendor_option": "per-call"},
        }
    ]
    assert response.content == "generated"
    assert response.model == "gpt-test-response"
    assert response.provider == "openai"
    assert response.request_id == "request-1"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}


def test_openai_client_uses_sdk_level_endpoint_retry_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    completion_fn = lambda **request: request
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion_fn)))

    def openai_factory(**options: Any) -> Any:
        captured.update(options)
        return fake_client

    monkeypatch.setattr(openai, "OpenAI", openai_factory)
    config = LLMClientConfig(
        model="gpt-test",
        api_base="https://models.example.test/v1",
        api_key="secret",
        timeout_seconds=45,
        max_retries=3,
    )

    loaded = _load_openai_completion(config)

    assert loaded is completion_fn
    assert captured == {
        "base_url": "https://models.example.test/v1",
        "api_key": "secret",
        "timeout": 45,
        "max_retries": 3,
    }


@pytest.mark.parametrize("config_type", [LLMClientConfig, ImageGenerationConfig])
def test_model_config_rejects_api_key_over_remote_http(config_type: type[Any]) -> None:
    with pytest.raises(LLMClientError, match="must use HTTPS"):
        config_type.from_dict(
            {
                "model": "test-model",
                "api_base": "http://models.example.test/v1",
                "api_key": "secret",
            }
        )


@pytest.mark.parametrize(
    "api_base",
    [
        "https://models.example.test/v1",
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://[::1]:11434/v1",
    ],
)
def test_model_config_accepts_secure_remote_or_loopback_endpoint(api_base: str) -> None:
    config = LLMClientConfig.from_dict(
        {"model": "test-model", "api_base": api_base, "api_key": "secret"}
    )

    assert config.api_base == api_base


def test_openai_client_checks_implicit_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    config = LLMClientConfig(model="gpt-test", api_base="http://models.example.test/v1")

    with pytest.raises(LLMClientError, match="must use HTTPS"):
        _load_openai_completion(config)


@pytest.mark.parametrize(
    ("workflow_name", "stage_name"),
    [
        ("image_synthesis.yaml", "image_card_synthesis"),
        ("text_question_augmentation.yaml", "question_augmentation_synthesis"),
    ],
)
def test_model_workflow_reads_endpoint_from_environment(workflow_name: str, stage_name: str) -> None:
    workflow_path = Path(__file__).parents[1] / "workflows" / workflow_name
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    model_config = workflow["steps"][0]["params"]["stages"][stage_name]["model_config"]

    assert model_config["api_base_env"] == "LLM_API_BASE"
    assert model_config["api_key_env"] == "OPENAI_API_KEY"
    assert "api_base" not in model_config


def test_openai_image_client_sends_compatible_extensions_in_extra_body() -> None:
    calls: list[dict[str, Any]] = []

    def image_generation_fn(**request: Any) -> dict[str, Any]:
        calls.append(request)
        return {"data": [{"b64_json": base64.b64encode(b"image-bytes").decode("ascii")}]}

    response = OpenAIImageClient(
        ImageGenerationConfig(model="gpt-image-test", response_format="b64_json"),
        image_generation_fn=image_generation_fn,
    ).generate("draw a test", {"negative_prompt": "blur", "quality": "high"})

    assert calls == [
        {
            "model": "gpt-image-test",
            "prompt": "draw a test",
            "size": "1024x1024",
            "response_format": "b64_json",
            "quality": "high",
            "extra_body": {"negative_prompt": "blur"},
        }
    ]
    assert response.image_bytes == b"image-bytes"
    assert response.provider == "openai"


def test_litellm_provider_is_no_longer_accepted() -> None:
    with pytest.raises(LLMClientError, match="Unsupported LLM provider"):
        LLMClientConfig.from_dict({"provider": "litellm", "model": "test"})
