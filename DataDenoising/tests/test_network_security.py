from __future__ import annotations

import pytest

from denoise_workflow_engine.utilities.image.base import OpenAICompatibleVisionClient
from denoise_workflow_engine.utilities.text.base import OpenAICompatibleChatClient
from denoise_workflow_engine.utilities.video.base import OpenAICompatibleAudioClient


@pytest.mark.parametrize(
    ("client_type", "path"),
    [
        (OpenAICompatibleChatClient, "/v1/chat/completions"),
        (OpenAICompatibleVisionClient, "/v1/chat/completions"),
        (OpenAICompatibleAudioClient, "/v1/audio/transcriptions"),
    ],
)
@pytest.mark.parametrize(
    "api_base",
    [
        "file:///tmp/model-api",
        "ftp://example.com/model-api",
        "https:///missing-host",
        " https://example.com",
        "https://example.com\n",
        "https://example.com:70000",
    ],
)
def test_external_clients_reject_unsafe_api_endpoints(client_type: type, path: str, api_base: str) -> None:
    client = client_type({"api_base": api_base, "path": path})

    with pytest.raises(ValueError):
        client._endpoint()


@pytest.mark.parametrize(
    ("client_type", "api_base", "path", "expected"),
    [
        (OpenAICompatibleChatClient, "http://localhost:8000", "/v1/chat/completions", "http://localhost:8000/v1/chat/completions"),
        (OpenAICompatibleVisionClient, "https://models.example.com/v1", "/chat/completions", "https://models.example.com/v1/chat/completions"),
        (OpenAICompatibleAudioClient, "https://audio.example.com/v1/audio/transcriptions", "/ignored", "https://audio.example.com/v1/audio/transcriptions"),
    ],
)
def test_external_clients_accept_http_and_https_endpoints(
    client_type: type,
    api_base: str,
    path: str,
    expected: str,
) -> None:
    client = client_type({"api_base": api_base, "path": path})

    assert client._endpoint() == expected
