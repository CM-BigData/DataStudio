from typing import Any
from denoise_workflow_engine.utilities.text.base import *  # noqa: F403

class EncodingDetectOperator(TextOperator):
    operator_name: str = "encoding_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect text encoding issues and repair common mojibake.

        Business logic:
            1. Prefer decoding raw bytes when the sample provides them.
            2. Try mojibake repair and record encoding-related metrics.
            3. Add issues for low-confidence decoding or suspicious mojibake.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out text processing.
            return item

        payload = item.setdefault("payload", {})
        text = self.get_text(item)
        detected_encoding = "unicode_text"
        confidence = 1.0
        source = "payload.text"

        raw_bytes = self._get_raw_bytes(payload)
        if raw_bytes is not None:  # Prefer encoding detection when raw bytes are available.
            decoded, detected_encoding, confidence = self._decode_bytes(raw_bytes)
            if decoded:  # Write back the decoded text when decoding succeeds.
                text = decoded
                source = "raw_bytes"
                self.set_text(item, text)

        repaired, repair_label = self._repair_mojibake(text)
        if repaired != text:  # Record repair only when the text actually changes.
            self.set_text(item, repaired)
            text = repaired
            detected_encoding = repair_label
            self.add_issue(item, "mojibake_repaired")
        elif mojibake_score(text) >= int(self.config.get("mojibake_score_threshold", 3)):
            self.add_issue(item, "possible_mojibake")

        min_confidence = float(self.config.get("min_confidence", 0.45))
        if confidence < min_confidence:  # Flag low-confidence decoding when confidence is below threshold.
            self.add_issue(item, "encoding_low_confidence")

        self.set_metric(item, "encoding_source", source)
        self.set_metric(item, "detected_encoding", detected_encoding)
        self.set_metric(item, "encoding_confidence", round(confidence, 4))
        self.set_metric(item, "mojibake_score", mojibake_score(text))
        return item

    def _get_raw_bytes(self, payload: dict[str, Any]) -> bytes | None:
        """Read raw-byte input from the payload when available.

        Business logic:
            1. Decode `raw_bytes_base64` when it is present.
            2. Otherwise read bytes from `text_file` when it points to a real file.
            3. Return `None` when no raw-byte source is available.

        Args:
                payload (dict[str, Any]): Sample payload.

        Returns:
            bytes | None: Raw bytes, or `None` when unavailable.

        Examples:
            >>> _get_raw_bytes
            _get_raw_bytes
        """
        raw_b64 = payload.get("raw_bytes_base64")
        if raw_b64:  # Decode payload-provided base64 text bytes first.
            try:
                return base64.b64decode(str(raw_b64), validate=True)
            except ValueError:
                return None
        text_file = payload.get("text_file")
        if text_file:  # Read file bytes when the payload provides a text file path.
            path = Path(str(text_file))
            if path.exists() and path.is_file():  # Read bytes only from real files to avoid treating plain text as a path.
                return path.read_bytes()
        return None

    def _decode_bytes(self, data: bytes) -> tuple[str, str, float]:
        """Select the most credible decoding result for raw bytes.

        Business logic:
            1. Try charset-normalizer first.
            2. Fall back to chardet and then to a fixed list of common encodings.
            3. Return decoded text, encoding label, and confidence score.

        Args:
                data (bytes): Raw bytes to decode.

        Returns:
            tuple[str, str, float]: Decoded text, encoding label, and confidence score.

        Examples:
            >>> _decode_bytes
            _decode_bytes
        """
        decoder_errors = []
        try:
            from charset_normalizer import from_bytes  # type: ignore

            match = from_bytes(data).best()
            if match is not None:  # Use charset-normalizer when it produces a viable match.
                encoding = match.encoding or "unknown"
                chaos = float(getattr(match, "chaos", 0.0) or 0.0)
                coherence = float(getattr(match, "coherence", 0.0) or 0.0)
                confidence = coherence if coherence > 0 else max(0.0, 1.0 - chaos)
                return str(match), encoding, confidence
        except Exception as exc:
            decoder_errors.append(f"charset_normalizer:{type(exc).__name__}")

        try:
            import chardet  # type: ignore

            detected = chardet.detect(data)
            encoding = detected.get("encoding") or "utf-8"
            confidence = float(detected.get("confidence") or 0.0)
            return data.decode(encoding, errors="replace"), encoding, confidence
        except Exception as exc:
            decoder_errors.append(f"chardet:{type(exc).__name__}")

        for encoding in ["utf-8", "gb18030", "gbk", "big5"]:  # Try common encodings in a Chinese-text-friendly order.
            try:
                return data.decode(encoding), encoding, 0.5
            except UnicodeDecodeError:
                continue
        fallback_label = "unknown"
        if decoder_errors:  # Preserve decoder failure types instead of swallowing diagnostics silently.
            fallback_label = f"unknown_after_{'|'.join(decoder_errors)}"
        return data.decode("utf-8", errors="replace"), fallback_label, 0.0

    def _repair_mojibake(self, text: str) -> tuple[str, str]:
        """Repair common mojibake patterns.

        Business logic:
            1. Score the original text sanity.
            2. Try several common re-encoding combinations.
            3. Return the best repaired text and its label.

        Args:
                text (str): Input text content.

        Returns:
            tuple[str, str]: Repaired text and repair label.

        Examples:
            >>> _repair_mojibake
            _repair_mojibake
        """
        if not text:  # Empty text is returned unchanged.
            return text, "unicode_text"
        original_score = self._sanity_score(text)
        best = text
        best_score = original_score
        best_label = "unicode_text"
        candidates = [
            ("latin1", "utf-8", "latin1_as_utf8"),
            ("cp1252", "utf-8", "cp1252_as_utf8"),
            ("latin1", "gb18030", "latin1_as_gb18030"),
        ]
        for source_encoding, target_encoding, label in candidates:  # Try common encoding-confusion pairs to repair mojibake text.
            try:
                candidate = text.encode(source_encoding).decode(target_encoding)
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            score = self._sanity_score(candidate)
            if score > best_score + 0.15:  # Accept the candidate only when it clearly improves sanity score.
                best = candidate
                best_score = score
                best_label = label
        return best, best_label

    def _sanity_score(self, text: str) -> float:
        """Compute a heuristic sanity score for text quality.

        Business logic:
            1. Measure useful-character ratio.
            2. Reward Chinese-character presence and penalize mojibake.
            3. Return a combined heuristic sanity score.

        Args:
                text (str): Input text content.

        Returns:
            float: Heuristic sanity score.

        Examples:
            >>> _sanity_score
            _sanity_score
        """
        useful = len(re.findall(r"[\w\u4e00-\u9fff]", text))
        useful_ratio = useful / max(len(text), 1)
        chinese_bonus = min(count_chinese_chars(text) / max(len(text), 1), 0.6)
        mojibake_penalty = min(mojibake_score(text) / max(len(text), 1), 0.8)
        return useful_ratio + chinese_bonus - mojibake_penalty

class UnicodeRepairOperator(TextOperator):
    operator_name: str = "unicode_repair"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Repair invalid Unicode control characters in one text sample.

        Business logic:
            1. Remove replacement characters and disallowed control characters.
            2. Compare repaired length with the original.
            3. Record an issue when the repair changes content length.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out text processing.
            return item
        text = self.get_text(item)
        original_len = len(text)
        text = text.replace("\ufffd", "")
        text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
        if len(text) != original_len:  # Record a repair issue when content length changes.
            self.add_issue(item, "unicode_repaired")
        self.set_text(item, text)
        return item

class WhitespaceNormalizeOperator(TextOperator):
    operator_name: str = "whitespace_normalize"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Normalize whitespace in one text sample.

        Business logic:
            1. Apply NFKC normalization to the current text.
            2. Collapse repeated spaces and excessive blank lines.
            3. Write normalized text back and record changes when they occur.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out text processing.
            return item
        text = self.get_text(item)
        normalized = unicodedata.normalize("NFKC", text)
        normalized = re.sub(r"[ \t\r\f\v]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
        if normalized != text:  # Record normalization only when the text changes.
            self.add_issue(item, "text_normalized")
        self.set_text(item, normalized)
        return item

class ChineseNormalizeOperator(TextOperator):
    operator_name: str = "chinese_normalize"  # Operator identifier used by workflow configs and the registry.

    ZERO_WIDTH_RE: Any = re.compile(r"[\u200b\u200c\u200d\ufeff]")  # Invisible zero-width characters removed during Chinese text cleanup.

    def process(self, item: dict) -> dict:
        """Normalize Chinese-oriented formatting in one text sample.

        Business logic:
            1. Apply NFKC normalization and remove zero-width characters.
            2. Normalize line breaks, spacing, and punctuation adjacency.
            3. Optionally remove inner spaces between Chinese characters and record changes.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out text processing.
            return item
        text = self.get_text(item)
        normalized = unicodedata.normalize("NFKC", text)
        normalized = self.ZERO_WIDTH_RE.sub("", normalized)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t\f\v]+", " ", normalized)
        normalized = re.sub(r"\s*([,，。.!！?？;；:：])\s*", r"\1", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
        if self.config.get("remove_cjk_inner_spaces", True):  # Remove abnormal spaces between Chinese characters when enabled.
            normalized = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", normalized)
        if normalized != text:  # Record normalization only when the text changes.
            self.add_issue(item, "chinese_normalized")
        self.set_text(item, normalized)
        return item
