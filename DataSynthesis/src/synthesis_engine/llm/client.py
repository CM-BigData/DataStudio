from __future__ import annotations

import os
import time
import base64
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit


_CHAT_COMPLETION_ARGUMENTS = {
    "audio",
    "extra_body",
    "extra_headers",
    "extra_query",
    "frequency_penalty",
    "function_call",
    "functions",
    "logit_bias",
    "logprobs",
    "max_completion_tokens",
    "max_tokens",
    "messages",
    "metadata",
    "modalities",
    "model",
    "n",
    "parallel_tool_calls",
    "prediction",
    "presence_penalty",
    "reasoning_effort",
    "response_format",
    "seed",
    "service_tier",
    "stop",
    "store",
    "stream",
    "stream_options",
    "temperature",
    "timeout",
    "tool_choice",
    "tools",
    "top_logprobs",
    "top_p",
    "user",
    "verbosity",
    "web_search_options",
}

_IMAGE_GENERATION_ARGUMENTS = {
    "background",
    "extra_body",
    "extra_headers",
    "extra_query",
    "model",
    "moderation",
    "n",
    "output_compression",
    "output_format",
    "partial_images",
    "prompt",
    "quality",
    "response_format",
    "size",
    "stream",
    "style",
    "timeout",
    "user",
}


class LLMClientError(RuntimeError):
    """Represent an error raised by the model-calling layer."""


@dataclass
class LLMClientConfig:
    provider: str = "openai"  # Model adapter provider name.
    model: str = ""  # OpenAI-compatible model identifier.
    api_base: str | None = None  # Compatible API service endpoint.
    api_key: str | None = None  # Access key for the model service.
    timeout_seconds: int = 60  # Timeout in seconds for a single model call.
    max_retries: int = 2  # Retry count delegated to the provider layer.
    temperature: float = 0.7  # Randomness parameter for generation.
    max_tokens: int = 1200  # Maximum response token count per call.
    extra: dict[str, Any] = field(default_factory=dict)  # Extra parameters passed through to the compatible API.

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LLMClientConfig":
        """Create client config from model registration config

        Business logic:
            1. Read explicit values and environment-variable references
            2. Validate the provider and model base fields
            3. Preserve unknown fields in extra for future extension

        Args:
            raw (dict[str, Any]): Model registration configuration.

        Returns:
            LLMClientConfig: Normalized LLM client configuration.

        Examples:
            >>> LLMClientConfig.from_dict({'provider': 'openai', 'model': 'test'}).model
            'test'
        """
        provider = str(raw.get("provider", "openai"))
        model = str(raw.get("model", "")).strip()
        if provider != "openai":
            raise LLMClientError(f"Unsupported LLM provider: {provider}")
        if not model:  # An OpenAI-compatible request cannot be built without a model name.
            raise LLMClientError("LLM model is required")

        api_base = _read_config_or_env(raw, "api_base", "api_base_env")
        api_key = _read_config_or_env(raw, "api_key", "api_key_env")
        _validate_credential_transport(api_base, api_key)
        known_keys = {
            "provider",
            "enabled",
            "model",
            "api_base",
            "api_base_env",
            "api_key",
            "api_key_env",
            "timeout_seconds",
            "max_retries",
            "temperature",
            "max_tokens",
        }
        extra = {key: value for key, value in raw.items() if key not in known_keys}
        return cls(
            provider=provider,
            model=model,
            api_base=api_base,
            api_key=api_key,
            timeout_seconds=int(raw.get("timeout_seconds", 60)),
            max_retries=int(raw.get("max_retries", 2)),
            temperature=float(raw.get("temperature", 0.7)),
            max_tokens=int(raw.get("max_tokens", 1200)),
            extra=extra,
        )


@dataclass
class LLMResponse:
    content: str  # Text content returned by the model.
    model: str  # Actual response model name.
    provider: str  # Local provider adapter name.
    request_id: str | None = None  # Request id returned by the provider.
    usage: dict[str, Any] = field(default_factory=dict)  # Token usage information.
    latency_ms: int = 0  # Call latency in milliseconds.


@dataclass
class ImageGenerationConfig:
    provider: str = "openai"  # Image-generation adapter provider name.
    model: str = ""  # Image-generation model identifier.
    api_base: str | None = None  # Compatible API service endpoint.
    api_key: str | None = None  # Access key for the model service.
    timeout_seconds: int = 120  # Timeout in seconds for one image request.
    max_retries: int = 1  # Retry count delegated to the provider layer.
    size: str = "1024x1024"  # Requested image size.
    response_format: str | None = None  # Optional image response format when supported by the provider.
    extra: dict[str, Any] = field(default_factory=dict)  # Extra parameters passed through to the compatible API.

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ImageGenerationConfig":
        """Create image-generation config from workflow config

        Business logic:
            1. Read provider, model, endpoint, and credentials from config
            2. Validate the provider and required model field
            3. Preserve unknown fields in extra for provider-specific options

        Args:
            raw (dict[str, Any]): Raw image model configuration.

        Returns:
            ImageGenerationConfig: Normalized image-generation configuration.

        Examples:
            >>> ImageGenerationConfig.from_dict({'model': 'gpt-image-1'}).model
            'gpt-image-1'
        """
        provider = str(raw.get("provider", "openai"))
        model = str(raw.get("model", "")).strip()
        if provider != "openai":
            raise LLMClientError(f"Unsupported image provider: {provider}")
        if not model:  # A model name is required to call the text-to-image service.
            raise LLMClientError("Image generation model is required")

        api_base = _read_config_or_env(raw, "api_base", "api_base_env")
        api_key = _read_config_or_env(raw, "api_key", "api_key_env")
        _validate_credential_transport(api_base, api_key)
        known_keys = {
            "provider",
            "enabled",
            "model",
            "api_base",
            "api_base_env",
            "api_key",
            "api_key_env",
            "timeout_seconds",
            "max_retries",
            "size",
            "response_format",
        }
        extra = {key: value for key, value in raw.items() if key not in known_keys}
        return cls(
            provider=provider,
            model=model,
            api_base=api_base,
            api_key=api_key,
            timeout_seconds=int(raw.get("timeout_seconds", 120)),
            max_retries=int(raw.get("max_retries", 1)),
            size=str(raw.get("size", "1024x1024")),
            response_format=str(raw["response_format"]) if raw.get("response_format") else None,
            extra=extra,
        )


@dataclass
class ImageGenerationResponse:
    image_bytes: bytes  # Generated image bytes returned by the provider.
    model: str  # Actual response model name.
    provider: str  # Local provider adapter name.
    mime_type: str = "image/png"  # MIME type used when saving the image.
    request_id: str | None = None  # Request id returned by the provider.
    revised_prompt: str | None = None  # Provider-revised prompt when available.
    latency_ms: int = 0  # Call latency in milliseconds.


class OpenAIClient:
    def __init__(self, config: LLMClientConfig, completion_fn: Callable[..., Any] | None = None) -> None:
        """Initialize the OpenAI-compatible client

        Business logic:
            1. Store model call configuration
            2. Accept an injectable completion function for tests
            3. Delay importing the OpenAI SDK until a real call is needed

        Args:
            config (LLMClientConfig): Normalized model configuration.
            completion_fn (Callable[..., Any] | None): Optional completion function.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> OpenAIClient(LLMClientConfig(model='test')).config.model
            'test'
        """
        self.config = config  # Normalized model call configuration.
        self._completion_fn = completion_fn  # Test-injected completion function.

    def complete(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> LLMResponse:
        """Call the LLM and return a normalized response

        Business logic:
            1. Merge model config with per-call options
            2. Invoke chat.completions.create or the injected completion function
            3. Convert the third-party response into LLMResponse

        Args:
            messages (list[dict[str, str]]): OpenAI-compatible message list.
            options (dict[str, Any] | None): Per-call override options.

        Returns:
            LLMResponse: Normalized model response.

        Examples:
            >>> callable(OpenAIClient.complete)
            True
        """
        start = time.monotonic()
        completion_fn = self._completion_fn or _load_openai_completion(self.config)
        request = self._build_request(messages, options or {})

        try:
            response = completion_fn(**request)
        except Exception as exc:  # Convert third-party provider exceptions into the local boundary uniformly.
            raise LLMClientError(f"LLM completion failed: {exc}") from exc

        return _normalize_response(response, self.config, int((time.monotonic() - start) * 1000))

    def _build_request(self, messages: list[dict[str, str]], options: dict[str, Any]) -> dict[str, Any]:
        """Build an OpenAI-compatible completion request

        Business logic:
            1. Fill model, messages, temperature, and token settings
            2. Merge standard SDK request options
            3. Move compatible-endpoint extensions into extra_body

        Args:
            messages (list[dict[str, str]]): Prompt messages.
            options (dict[str, Any]): Per-call override options.

        Returns:
            dict[str, Any]: OpenAI SDK completion arguments.

        Examples:
            >>> OpenAIClient(LLMClientConfig(model='test'))._build_request([], {})['model']
            'test'
        """
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        return _merge_request_options(request, self.config.extra, options, _CHAT_COMPLETION_ARGUMENTS)


class OpenAIImageClient:
    def __init__(self, config: ImageGenerationConfig, image_generation_fn: Callable[..., Any] | None = None) -> None:
        """Initialize the OpenAI-compatible image-generation client

        Business logic:
            1. Store image-generation configuration
            2. Accept an injectable image_generation function for tests
            3. Delay importing the OpenAI SDK until a real call is needed

        Args:
            config (ImageGenerationConfig): Normalized image-generation configuration.
            image_generation_fn (Callable[..., Any] | None): Optional injected provider function.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> OpenAIImageClient(ImageGenerationConfig(model='gpt-image-1')).config.model
            'gpt-image-1'
        """
        self.config = config  # Normalized image model call configuration.
        self._image_generation_fn = image_generation_fn  # Test-injected generation function.

    def generate(self, prompt: str, options: dict[str, Any] | None = None) -> ImageGenerationResponse:
        """Call the text-to-image model and normalize the generated image

        Business logic:
            1. Merge image model config with per-call options
            2. Invoke images.generate or the injected function
            3. Convert base64 or URL provider output into image bytes

        Args:
            prompt (str): Text prompt for image generation.
            options (dict[str, Any] | None): Per-call override options.

        Returns:
            ImageGenerationResponse: Normalized generated image response.

        Examples:
            >>> callable(OpenAIImageClient.generate)
            True
        """
        start = time.monotonic()
        image_generation_fn = self._image_generation_fn or _load_openai_image_generation(self.config)
        request = self._build_request(prompt, options or {})

        try:
            response = image_generation_fn(**request)
        except Exception as exc:  # Normalize third-party failures behind the local client boundary.
            raise LLMClientError(f"Image generation failed: {exc}") from exc

        return _normalize_image_response(response, self.config, int((time.monotonic() - start) * 1000))

    def _build_request(self, prompt: str, options: dict[str, Any]) -> dict[str, Any]:
        """Build an OpenAI-compatible image-generation request

        Business logic:
            1. Fill model, prompt, size, and response format
            2. Merge standard SDK request options
            3. Move compatible-endpoint extensions into extra_body

        Args:
            prompt (str): Image prompt.
            options (dict[str, Any]): Per-call override options.

        Returns:
            dict[str, Any]: OpenAI SDK image-generation arguments.

        Examples:
            >>> OpenAIImageClient(ImageGenerationConfig(model='gpt-image-1'))._build_request('x', {})['prompt']
            'x'
        """
        request: dict[str, Any] = {
            "model": self.config.model,
            "prompt": prompt,
            "size": self.config.size,
        }

        if self.config.response_format:  # Some providers support explicit b64_json or URL response formats.
            request["response_format"] = self.config.response_format

        return _merge_request_options(request, self.config.extra, options, _IMAGE_GENERATION_ARGUMENTS)


def _read_config_or_env(raw: dict[str, Any], value_key: str, env_key: str) -> str | None:
    """Read an explicit config value or an environment-backed value

    Business logic:
        1. Prefer the direct configured value
        2. Otherwise read the environment variable named by the config
        3. Return None when neither exists

    Args:
        raw (dict[str, Any]): Raw configuration.
        value_key (str): Direct-value field name.
        env_key (str): Environment-variable-name field name.

    Returns:
        str | None: Resolved config value or None.

    Examples:
        >>> _read_config_or_env({'api_key': 'x'}, 'api_key', 'api_key_env')
        'x'
    """

    if raw.get(value_key):  # Prefer direct values for fixed local compatible-service tokens.
        return str(raw[value_key])

    if raw.get(env_key):  # Secret-like config is preferably injected through environment variables.
        env_name = str(raw[env_key])
        value = os.getenv(env_name)

        if value is None:  # Explicitly require the referenced environment variable to be present.
            raise LLMClientError(f"Required environment variable is missing: {env_name}")

        return value

    return None


def _load_openai_completion(config: LLMClientConfig) -> Callable[..., Any]:
    """Lazily load the OpenAI SDK completion callable

    Business logic:
        1. Build an SDK client with endpoint, credential, timeout, and retry settings
        2. Raise a clear configuration error when client construction fails
        3. Return chat.completions.create

    Args:
        config (LLMClientConfig): Normalized text model configuration.

    Returns:
        Callable[..., Any]: OpenAI SDK completion function.

    Examples:
        >>> callable(_load_openai_completion)
        True
    """
    return _create_openai_client(config).chat.completions.create


def _load_openai_image_generation(config: ImageGenerationConfig) -> Callable[..., Any]:
    """Lazily load the OpenAI SDK image-generation callable

    Business logic:
        1. Build an SDK client with endpoint, credential, timeout, and retry settings
        2. Raise a clear configuration error when client construction fails
        3. Return images.generate

    Args:
        config (ImageGenerationConfig): Normalized image model configuration.

    Returns:
        Callable[..., Any]: OpenAI SDK image-generation function.

    Examples:
        >>> callable(_load_openai_image_generation)
        True
    """
    return _create_openai_client(config).images.generate


def _create_openai_client(config: LLMClientConfig | ImageGenerationConfig) -> Any:
    """Create an OpenAI SDK client for an official or compatible endpoint."""

    effective_api_key = config.api_key or os.getenv("OPENAI_API_KEY")
    _validate_credential_transport(config.api_base, effective_api_key)

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMClientError("openai is required for real model calls. Install project dependencies first.") from exc

    client_options: dict[str, Any] = {
        "timeout": config.timeout_seconds,
        "max_retries": config.max_retries,
    }
    if config.api_base:
        client_options["base_url"] = config.api_base
    if config.api_key:
        client_options["api_key"] = config.api_key

    try:
        return OpenAI(**client_options)
    except Exception as exc:
        raise LLMClientError(f"Failed to configure OpenAI-compatible client: {exc}") from exc


def _validate_credential_transport(api_base: str | None, api_key: str | None) -> None:
    """Require encrypted transport when an API credential leaves the local machine."""
    if not api_base or not api_key:
        return

    try:
        parsed = urlsplit(api_base)
        hostname = parsed.hostname
    except ValueError as exc:
        raise LLMClientError(f"Invalid OpenAI-compatible API base URL: {api_base}") from exc

    if parsed.scheme.lower() == "https":
        return
    if parsed.scheme.lower() == "http" and hostname in {"localhost", "127.0.0.1", "::1"}:
        return

    raise LLMClientError(
        "Credential-bearing OpenAI-compatible endpoints must use HTTPS; "
        "HTTP is allowed only for localhost, 127.0.0.1, or ::1"
    )


def _merge_request_options(
    request: dict[str, Any],
    config_options: dict[str, Any],
    call_options: dict[str, Any],
    supported_arguments: set[str],
) -> dict[str, Any]:
    """Merge SDK arguments and compatible-endpoint extensions."""
    extra_body: dict[str, Any] = {}

    for options in (config_options, call_options):
        for key, value in options.items():
            if key == "extra_body" and isinstance(value, dict):
                extra_body.update(value)
            elif key in supported_arguments:
                request[key] = value
            else:
                extra_body[key] = value

    if extra_body:
        existing_extra_body = request.get("extra_body", {})
        request["extra_body"] = {**existing_extra_body, **extra_body}

    return request


def _normalize_response(response: Any, config: LLMClientConfig, latency_ms: int) -> LLMResponse:
    """Normalize an OpenAI-compatible response

    Business logic:
        1. Read the first message.content from choices
        2. Support both dict-style and attribute-style responses
        3. Extract request id, usage, and model information

    Args:
        response (Any): Raw SDK or compatible-endpoint response.
        config (LLMClientConfig): Client configuration.
        latency_ms (int): Call latency in milliseconds.

    Returns:
        LLMResponse: Normalized response.

    Examples:
        >>> _normalize_response({'choices': [{'message': {'content': 'x'}}]}, LLMClientConfig(model='test'), 1).content
        'x'
    """
    choices = _get_value(response, "choices", [])

    if not choices:  # Missing choices means the provider response is unusable.
        raise LLMClientError("LLM response has no choices")

    first = choices[0]
    message = _get_value(first, "message", {})
    content = _get_value(message, "content", "")

    if content is None:  # Some providers may return an empty message.content.
        content = ""

    usage = _get_value(response, "usage", {}) or {}

    if not isinstance(usage, dict):
        usage = _model_to_dict(usage)

    request_id = _get_value(response, "id", None)
    model = _get_value(response, "model", None) or config.model

    return LLMResponse(
        content=str(content),
        model=str(model),
        provider=config.provider,
        request_id=str(request_id) if request_id else None,
        usage=usage,
        latency_ms=latency_ms,
    )


def _normalize_image_response(response: Any, config: ImageGenerationConfig, latency_ms: int) -> ImageGenerationResponse:
    """Normalize an OpenAI-compatible image-generation response

    Business logic:
        1. Read the first generated image from response.data
        2. Decode b64_json responses or download URL responses
        3. Preserve model, request id, and revised prompt metadata

    Args:
        response (Any): Raw provider response.
        config (ImageGenerationConfig): Image client configuration.
        latency_ms (int): Call latency in milliseconds.

    Returns:
        ImageGenerationResponse: Normalized image response.

    Examples:
        >>> _normalize_image_response({'data': [{'b64_json': 'eA=='}]}, ImageGenerationConfig(model='m'), 1).image_bytes
        b'x'
    """
    data = _get_value(response, "data", [])

    if not data:  # Missing data means the image provider did not return a usable image.
        raise LLMClientError("Image generation response has no data")

    first = data[0]
    b64_json = _get_value(first, "b64_json", None)
    image_url = _get_value(first, "url", None)

    if b64_json:
        try:
            image_bytes = base64.b64decode(str(b64_json))
        except ValueError as exc:
            raise LLMClientError("Image generation response contains invalid base64 data") from exc
    elif image_url:
        image_bytes = _download_image(str(image_url), config.timeout_seconds)
    else:
        raise LLMClientError("Image generation response has neither b64_json nor url")

    request_id = _get_value(response, "id", None)
    model = _get_value(response, "model", None) or config.model
    revised_prompt = _get_value(first, "revised_prompt", None)

    return ImageGenerationResponse(
        image_bytes=image_bytes,
        model=str(model),
        provider=config.provider,
        request_id=str(request_id) if request_id else None,
        revised_prompt=str(revised_prompt) if revised_prompt else None,
        latency_ms=latency_ms,
    )


def _download_image(url: str, timeout_seconds: int) -> bytes:
    """Download image bytes returned by a URL-based provider

    Business logic:
        1. Validate that the provider URL uses HTTP or HTTPS
        2. Download the generated image with a timeout
        3. Raise a normalized client error on request failures

    Args:
        url (str): Provider image URL.
        timeout_seconds (int): Request timeout in seconds.

    Returns:
        bytes: Downloaded image bytes.

    Examples:
        >>> callable(_download_image)
        True
    """

    if not url.startswith(("http://", "https://")):  # Reject local file and unsupported schemes at the network boundary.
        raise LLMClientError("Image URL must use http or https")

    try:
        import httpx

        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

            return response.content
    except Exception as exc:  # Convert httpx and unexpected network errors into the local client error.
        raise LLMClientError(f"Failed to download generated image: {exc}") from exc


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    """Read a value from either a dictionary or an object attribute

    Business logic:
        1. Use get when the source is a dictionary
        2. Use getattr when the source is an object
        3. Return the default value when both fail

    Args:
        source (Any): Dictionary or object source.
        key (str): Field name.
        default (Any): Default value.

    Returns:
        Any: Retrieved field value.

    Examples:
        >>> _get_value({'a': 1}, 'a')
        1
    """

    if isinstance(source, dict):
        return source.get(key, default)

    return getattr(source, key, default)


def _model_to_dict(source: Any) -> dict[str, Any]:
    """Convert SDK model objects to plain dictionaries."""
    if hasattr(source, "model_dump"):
        value = source.model_dump()
        return value if isinstance(value, dict) else {}
    if hasattr(source, "items"):
        return dict(source)
    return {}
