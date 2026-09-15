from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request
from collections.abc import Iterable
from itertools import combinations
from typing import Any
from urllib.parse import urlsplit


def config_enabled(config: dict[str, Any]) -> bool:
    """Read the enabled flag from operator config.

    Business logic:
        1. Read the enabled field from config.
        2. Use bool conversion to tolerate missing values.
        3. Return whether external models or enhanced capabilities are enabled.

    Args:
        config (dict[str, Any]): Operator config dictionary.

    Returns:
        bool: Boolean value converted from the enabled field.

    Examples:
        >>> config_enabled({"enabled": True})
        True
    """
    return bool(config.get("enabled", False))


def missing_env_names(config: dict[str, Any], keys: Iterable[str]) -> list[str]:
    """Check whether environment variables referenced by config are missing.

    Business logic:
        1. Read environment-variable names from config using keys.
        2. Filter out empty names.
        3. Return variable names that are absent from os.environ.

    Args:
        config (dict[str, Any]): Config dictionary storing env-var names.
        keys (Iterable[str]): Config keys to inspect.

    Returns:
        list[str]: List of missing environment-variable names.

    Examples:
        >>> missing_env_names({"api_key_env": ""}, ["api_key_env"])
        []
    """
    names = [str(config.get(key, "")).strip() for key in keys]
    return [name for name in names if name and not os.environ.get(name)]


def hashing_vector(text: str, dimensions: int = 128) -> list[float]:
    """Generate a text vector using stable hashing.

    Business logic:
        1. Prefer splitting tokens by whitespace.
        2. Fall back to character bigrams when no tokens exist.
        3. Project tokens into fixed dimensions with blake2b and normalize the vector.

    Args:
        text (str): Text to vectorize.
        dimensions (int, optional): Vector dimensionality. Defaults to 128.

    Returns:
        list[float]: Normalized hash vector.

    Examples:
        >>> len(hashing_vector("hello world", 8))
        8
    """
    vector = [0.0] * dimensions
    tokens = text.split()
    if not tokens:  # Use character bigrams as a fallback for CJK or compact text without whitespace tokens.
        tokens = [text[index : index + 2] for index in range(max(0, len(text) - 1))]
    for token in tokens:  # Each token contributes one signed sparse update to the vector.
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    return normalize_vector(vector)


def bytes_hashing_vector(data: bytes, dimensions: int = 128) -> list[float]:
    """Generate a vector for binary content using stable hashing.

    Business logic:
        1. Return an all-zero vector for empty bytes.
        2. Sample the binary content in at most roughly 256 chunks.
        3. Project each chunk into fixed dimensions and normalize the vector.

    Args:
        data (bytes): Binary content to vectorize.
        dimensions (int, optional): Vector dimensionality. Defaults to 128.

    Returns:
        list[float]: Normalized binary hash vector.

    Examples:
        >>> len(bytes_hashing_vector(b"abc", 4))
        4
    """
    vector = [0.0] * dimensions
    if not data:  # Empty content has no projectable features, so keep the all-zero vector.
        return vector
    step = max(1, len(data) // 256)
    for index in range(0, len(data), step):  # Sample in chunks to avoid byte-by-byte processing for large files.
        chunk = data[index : index + step]
        digest = hashlib.blake2b(chunk, digest_size=16).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        vector[bucket] += 1.0 if digest[4] & 1 else -1.0
    return normalize_vector(vector)


def normalize_vector(vector: list[float]) -> list[float]:
    """Apply L2 normalization to a vector.

    Business logic:
        1. Compute the vector's L2 norm.
        2. Return zero vectors unchanged.
        3. Divide each dimension by the norm for non-zero vectors.

    Args:
        vector (list[float]): Input vector.

    Returns:
        list[float]: L2-normalized vector.

    Examples:
        >>> normalize_vector([3.0, 4.0])
        [0.6, 0.8]
    """
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:  # Zero vectors cannot be normalized, so keep the original values for similarity functions to return 0.
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Business logic:
        1. Return 0 immediately for empty vectors.
        2. Align both vectors by their shortest length when computing norms and dot product.
        3. Clamp the result into the [-1, 1] range.

    Args:
        left (list[float]): Left vector.
        right (list[float]): Right vector.

    Returns:
        float: Cosine-similarity score.

    Examples:
        >>> cosine_similarity([1.0, 0.0], [1.0, 0.0])
        1.0
    """
    if not left or not right:  # Missing either vector means there is no similarity evidence.
        return 0.0
    size = min(len(left), len(right))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm <= 0 or right_norm <= 0:  # A zero vector on either side carries no directional information.
        return 0.0
    score = sum(left[index] * right[index] for index in range(size)) / (left_norm * right_norm)
    return max(-1.0, min(1.0, score))


def pairwise_topk(vectors: list[tuple[str, list[float]]], threshold: float, top_k: int) -> list[tuple[str, str, float]]:
    """Compute pairwise vector similarity and return candidate edges above the threshold.

    Business logic:
        1. Enumerate all vector pairs.
        2. Compute cosine similarity and filter by threshold.
        3. Sort by descending score and truncate by top_k.

    Args:
        vectors (list[tuple[str, list[float]]]): Sample ids paired with vectors.
        threshold (float): Minimum similarity threshold.
        top_k (int): Maximum number of returned candidates; 0 means no truncation.

    Returns:
        list[tuple[str, str, float]]: Candidate edges as left_id, right_id, and score.

    Examples:
        >>> pairwise_topk([("a", [1.0]), ("b", [1.0])], 0.9, 1)
        [('a', 'b', 1.0)]
    """
    scored: list[tuple[str, str, float]] = []
    for (left_id, left_vector), (right_id, right_vector) in combinations(vectors, 2):  # Vector recall must inspect every sample pair.
        score = cosine_similarity(left_vector, right_vector)
        if score >= threshold:  # Keep only candidate duplicate edges that reach the recall threshold.
            scored.append((left_id, right_id, score))
    scored.sort(key=lambda row: row[2], reverse=True)
    if top_k > 0:  # A top_k of 0 means to keep all candidates above the threshold.
        return scored[:top_k]
    return scored


def call_json_api(api_base: str, api_key: str, payload: dict[str, Any], timeout_seconds: float = 30.0) -> dict[str, Any]:
    """Call a JSON API without an extra endpoint path.

    Business logic:
        1. Use api_base as the full endpoint.
        2. Reuse the HTTP POST logic from call_json_api_endpoint.
        3. Return the parsed JSON response.

    Args:
        api_base (str): API base URL or full endpoint.
        api_key (str): Bearer token.
        payload (dict[str, Any]): JSON request body.
        timeout_seconds (float, optional): Request timeout in seconds. Defaults to 30.

    Returns:
        dict[str, Any]: API JSON response.

    Examples:
        >>> call_json_api("http://example", "key", {})  # doctest: +SKIP
        {}
    """
    return call_json_api_endpoint(api_base, "", api_key, payload, timeout_seconds=timeout_seconds)


def validate_http_endpoint(value: str, name: str = "API endpoint") -> str:
    """Require a well-formed HTTP(S) endpoint before making a request."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty HTTP(S) URL")
    if value != value.strip() or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{name} contains whitespace or control characters")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{name} is invalid: {exc}") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"{name} must use http or https")
    if not parsed.netloc or not parsed.hostname:
        raise ValueError(f"{name} must include a host")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{name} contains an invalid port")
    return value


def call_json_api_endpoint(
    api_base: str,
    endpoint_path: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Call a JSON POST API with an endpoint path.

    Business logic:
        1. Join api_base and endpoint_path.
        2. Serialize payload into UTF-8 JSON.
        3. Send a Bearer-authenticated POST request and parse the JSON response.

    Args:
        api_base (str): API base URL.
        endpoint_path (str): Relative or absolute endpoint path.
        api_key (str): Bearer token.
        payload (dict[str, Any]): JSON request body.
        timeout_seconds (float, optional): Request timeout in seconds. Defaults to 30.

    Returns:
        dict[str, Any]: API JSON response.

    Examples:
        >>> call_json_api_endpoint("http://example", "/v1", "key", {})  # doctest: +SKIP
        {}
    """
    endpoint = join_api_endpoint(api_base, endpoint_path)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    # join_api_endpoint restricts the request target to a validated HTTP(S) URL.
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def join_api_endpoint(api_base: str, endpoint_path: str) -> str:
    """Join an API base URL and an endpoint path.

    Business logic:
        1. Strip the trailing slash from api_base.
        2. Return the base when endpoint_path is empty.
        3. Return absolute URLs directly; otherwise join the relative path.

    Args:
        api_base (str): API base URL.
        endpoint_path (str): Relative endpoint path or absolute URL.

    Returns:
        str: Full requestable endpoint URL.

    Examples:
        >>> join_api_endpoint("http://a/", "/b")
        'http://a/b'
    """
    base = api_base.rstrip("/")
    path = endpoint_path.strip()
    if not path:  # An empty path means api_base is already the full endpoint.
        endpoint = base
    elif urlsplit(path).scheme:  # Absolute endpoints override api_base and receive the same validation.
        endpoint = path
    else:
        endpoint = f"{base}/{path.lstrip('/')}"
    return validate_http_endpoint(endpoint)


def call_openai_chat(api_base: str, api_key: str, model: str, messages: list[dict[str, str]], timeout_seconds: float = 60.0) -> str:
    """Call an OpenAI-compatible chat completions API and return content.

    Business logic:
        1. Ensure the endpoint ends with /chat/completions.
        2. Build a chat payload with JSON-object response_format.
        3. Send the POST request and read choices[0].message.content.

    Args:
        api_base (str): OpenAI-compatible API base or chat-completions endpoint.
        api_key (str): Bearer token.
        model (str): Model name.
        messages (list[dict[str, str]]): Chat messages.
        timeout_seconds (float, optional): Request timeout in seconds. Defaults to 60.

    Returns:
        str: message content returned by the model.

    Examples:
        >>> call_openai_chat("http://example/v1", "key", "model", [])  # doctest: +SKIP
        '{}'
    """
    endpoint = api_base.rstrip("/")
    if not endpoint.endswith("/chat/completions"):  # Allow either a base URL or a fully qualified chat endpoint in config.
        endpoint = f"{endpoint}/chat/completions"
    endpoint = validate_http_endpoint(endpoint, "chat API endpoint")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    # validate_http_endpoint restricts the request target to a validated HTTP(S) URL.
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        body = json.loads(response.read().decode("utf-8"))
    return str(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
