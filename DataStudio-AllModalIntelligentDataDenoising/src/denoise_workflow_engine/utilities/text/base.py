from __future__ import annotations

import base64
import html
import json
import os
import regex as re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.utilities.network import validate_http_endpoint

MOJIBAKE_MARKERS = ("�", "Ã", "Â", "â", "è", "æ", "å", "¤", "½", "¼")  # Common mojibake marker characters used by `mojibake_score`.

class TextOperator(BaseOperator):
    def should_skip(self, item: dict) -> bool:
        """Return whether the current sample should skip text processing.

        Business logic:
            1. Read the sample modality and payload fields.
            2. Check whether the sample belongs to text processing.
            3. Return `True` when the sample has no text payload to process.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            bool: Whether the sample should be skipped.

        Examples:
            >>> should_skip
            should_skip
        """
        return item.get("modality") != "text" and "text" not in item.get("payload", {})

    def get_text(self, item: dict) -> str:
        """Read the text payload from a sample.

        Business logic:
            1. Read the payload field from the sample dictionary.
            2. Normalize missing values to an empty string.
            3. Return the text content as a string.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            str: Extracted text content.

        Examples:
            >>> get_text
            get_text
        """
        return str(item.get("payload", {}).get("text", "") or "")

    def set_text(self, item: dict, text: str) -> None:
        """Write normalized text back into the sample payload.

        Business logic:
            1. Ensure the payload dictionary exists.
            2. Replace the text field with the provided content.
            3. Keep the update in place for downstream operators.

        Args:
                item (dict): Current sample dictionary.
                text (str): Text content to write back.

        Returns:
            None: The method mutates `item` in place.

        Examples:
            >>> set_text
            set_text
        """
        item.setdefault("payload", {})["text"] = text

def count_chinese_chars(text: str) -> int:
    """Count Chinese characters in a text string.

    Business logic:
        1. Read the input text string.
        2. Match Chinese code points with a regex.
        3. Return the number of matches.

    Args:
            text (str): Input text content.

    Returns:
        int: Number of Chinese characters.

    Examples:
        >>> count_chinese_chars
        count_chinese_chars
    """
    return len(re.findall(r"[\u4e00-\u9fff]", text))

def mojibake_score(text: str) -> int:
    """Compute a heuristic mojibake score for a text string.

    Business logic:
        1. Read the input text string.
        2. Count known mojibake markers and control characters.
        3. Return the combined heuristic score.

    Args:
            text (str): Input text content.

    Returns:
        int: Heuristic mojibake score.

    Examples:
        >>> mojibake_score
        mojibake_score
    """
    marker_hits = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    control_hits = len(re.findall(r"[\u0080-\u009f]", text))
    return marker_hits + control_hits

def extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from free-form text.

    Business logic:
        1. Strip the input text and remove Markdown fences when present.
        2. Try parsing the full content as JSON first.
        3. Fall back to the first brace-delimited object when direct parsing fails.

    Args:
            text (str): Input text content.

    Returns:
        dict[str, Any]: Extracted JSON object, or an empty dict on failure.

    Examples:
        >>> extract_json_object
        extract_json_object
    """
    content = text.strip()
    if content.startswith("```"):  # Strip Markdown fences when the model reply is wrapped in a code block.
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*```$", "", content)
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:  # Retry parsing the first brace-delimited JSON object.
            try:
                parsed = json.loads(content[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}

class OpenAICompatibleChatClient:
    def __init__(self, config: dict[str, Any]) -> None:
        """Store OpenAI-compatible chat client configuration.

        Business logic:
            1. Read runtime configuration and environment overrides.
            2. Store reusable API connection settings.
            3. Keep construction side-effect free.

        Args:
                config (dict[str, Any]): Client configuration dictionary.

        Returns:
            None: The constructor initializes the client in place.

        Examples:
            >>> __init__
            __init__
        """
        self.config = config  # Runtime configuration such as thresholds, endpoints, and API parameters.
        self.api_key = os.getenv(config.get("api_key_env", "LLM_API_KEY"), config.get("api_key", ""))  # Authentication token for external model requests.
        self.api_base = os.getenv(config.get("api_base_env", "LLM_API_BASE"), config.get("api_base", ""))  # Base URL used to compose the chat endpoint.
        self.model = os.getenv(config.get("model_env", "LLM_MODEL"), config.get("model", ""))  # Model name used for text quality, safety, or repair tasks.
        self.path = os.getenv(  # OpenAI-compatible chat completions endpoint path.
            config.get("path_env", "LLM_CHAT_COMPLETIONS_PATH"),
            config.get("path", "/v1/chat/completions"),
        )
        self.timeout = float(config.get("timeout", 60))  # Maximum wait time for external API calls, in seconds.
        self.temperature = float(config.get("temperature", 0))  # Sampling temperature; defaults to 0 for deterministic quality and repair calls.
        self.max_tokens = int(config.get("max_tokens", 1024))  # Upper bound on generated output length.

    def is_enabled(self) -> bool:
        """Return whether the external chat client is fully configured.

        Business logic:
            1. Read the required API key, base URL, and model settings.
            2. Check whether all required values are non-empty.
            3. Return the availability flag.

        Args:
                None: This method does not take input parameters.

        Returns:
            bool: Whether the external client can be called.

        Examples:
            >>> is_enabled
            is_enabled
        """
        return bool(self.api_key and self.api_base and self.model)

    def chat_json(self, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any], str]:
        """Call an OpenAI-compatible chat API and parse a JSON response.

        Business logic:
            1. Assemble the outbound model request payload.
            2. Send the request and read the JSON response.
            3. Return the parsed JSON object and any error message.

        Args:
                system_prompt (str): System prompt text.
                user_prompt (str): User prompt text.

        Returns:
            tuple[dict[str, Any], str]: Parsed JSON object and error string.

        Examples:
            >>> chat_json
            chat_json
        """
        endpoint = self._endpoint()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            # `_endpoint` restricts the request target to a validated HTTP(S) URL.
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
                response_data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {}, str(exc)

        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            return {}, f"unexpected_response: {exc}"
        parsed = extract_json_object(str(content))
        if not parsed:  # Trigger local fallback when the model reply is not valid JSON.
            return {}, "invalid_json_response"
        return parsed, ""

    def _endpoint(self) -> str:
        """Build the final chat endpoint URL.

        Business logic:
            1. Read the configured API base URL.
            2. Reuse it directly when it already points at the chat completions endpoint.
            3. Otherwise append the configured path.

        Args:
                None: This method does not take input parameters.

        Returns:
            str: Final endpoint URL.

        Examples:
            >>> _endpoint
            _endpoint
        """
        base = self.api_base.rstrip("/")
        if base.endswith("/chat/completions"):  # Reuse the URL directly when it already targets chat completions.
            endpoint = base
        else:
            endpoint = base + "/" + self.path.lstrip("/")
        return validate_http_endpoint(endpoint, "chat API endpoint")
