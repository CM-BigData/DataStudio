from typing import Any
from denoise_workflow_engine.utilities.text.base import *  # noqa: F403

class LLMSemanticQualityOperator(TextOperator):
    operator_name: str = "llm_semantic_quality"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for semantic-quality evaluation.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable chat client for processing.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleChatClient(self.config.get("llm", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Evaluate semantic quality for one text sample.

        Business logic:
            1. Use the API path when the LLM client is enabled, otherwise fall back locally.
            2. Record semantic-quality metrics from the chosen evaluation path.
            3. Add review or repairability issues according to configured thresholds.

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
        stage = str(self.config.get("stage", "semantic"))
        if self.client.is_enabled():  # Use the API path when the external model is fully configured.
            result, error = self._call_llm(text)
            if error:  # Record fallback reasons when the API path fails.
                self.add_issue(item, "llm_api_fallback")
                self.set_metric(item, f"{stage}_llm_error", error)
                result = self._local_semantic_quality(text)
                mode = "local_fallback"
            else:
                mode = "api"
        else:
            result = self._local_semantic_quality(text)
            mode = "local_fallback"

        score = self._bounded_float(result.get("semantic_quality_score", 1.0))
        coherence = self._bounded_float(result.get("coherence_score", score))
        completeness = self._bounded_float(result.get("completeness_score", score))
        repairable = bool(result.get("repairable", False))
        noise_types = result.get("noise_types", [])
        if not isinstance(noise_types, list):  # Normalize unexpected response shapes into a list.
            noise_types = [str(noise_types)]

        self.set_metric(item, f"{stage}_llm_mode", mode)
        self.set_metric(item, f"{stage}_semantic_quality_score", round(score, 4))
        self.set_metric(item, f"{stage}_coherence_score", round(coherence, 4))
        self.set_metric(item, f"{stage}_completeness_score", round(completeness, 4))
        self.set_metric(item, f"{stage}_repairable", repairable)
        self.set_metric(item, f"{stage}_semantic_noise_types", noise_types)
        self.set_metric(item, "semantic_quality_score", round(score, 4))

        if repairable and self.config.get("mark_repairable", True):  # Add a repairable issue when configured and the text is recoverable.
            self.add_issue(item, "semantic_repairable")

        if self.config.get("add_quality_issues", True):  # Write semantic quality labels into issues when enabled.
            min_score = float(self.config.get("min_semantic_score", 0.55))
            review_score = float(self.config.get("review_semantic_score", 0.72))
            if score < min_score:  # Add a low-quality issue below the minimum threshold.
                self.add_issue(item, "semantic_low_quality")
            elif score < review_score:
                self.add_issue(item, "semantic_needs_review")
        return item

    def _call_llm(self, text: str) -> tuple[dict[str, Any], str]:
        """Call the text LLM for semantic-quality evaluation.

        Business logic:
            1. Assemble the model prompts and request parameters.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                text (str): Input text content.

        Returns:
            tuple[dict[str, Any], str]: Structured result and error string.

        Examples:
            >>> _call_llm
            _call_llm
        """
        system_prompt = (
            "You are a text data quality evaluator. Return strict JSON only. "
            "Do not repair the text in this step."
        )
        user_prompt = (
            "Evaluate this text for denoising. Score semantic quality, coherence, completeness, "
            "and whether it is repairable without adding facts. Return JSON with keys: "
            "semantic_quality_score, coherence_score, completeness_score, noise_types, "
            "repairable, action_hint, reason.\n\nTEXT:\n"
            + text[: int(self.config.get("max_input_chars", 4000))]
        )
        return self.client.chat_json(system_prompt, user_prompt)

    def _local_semantic_quality(self, text: str) -> dict[str, Any]:
        """Estimate semantic quality locally without an external model.

        Business logic:
            1. Extract simple statistical cues from the text.
            2. Derive coherence, completeness, and repairability heuristics.
            3. Return a structured local quality estimate.

        Args:
                text (str): Input text content.

        Returns:
            dict[str, Any]: Local semantic-quality estimate.

        Examples:
            >>> _local_semantic_quality
            _local_semantic_quality
        """
        if not text.strip():  # Treat empty text as the lowest-quality case.
            return {
                "semantic_quality_score": 0.0,
                "coherence_score": 0.0,
                "completeness_score": 0.0,
                "noise_types": ["empty"],
                "repairable": False,
            }
        length = len(text)
        punctuation_count = len(re.findall(r"[。.!！?？;；]", text))
        useful = len(re.findall(r"[\w\u4e00-\u9fff]", text))
        useful_ratio = useful / max(length, 1)
        replacement_penalty = min(mojibake_score(text) * 0.08, 0.5)
        repetition_penalty = min(self._short_token_repetition(text) * 0.6, 0.6)
        symbol_penalty = 0.25 if useful_ratio < 0.45 else 0.0
        completeness = 0.9 if punctuation_count > 0 or length < 80 else 0.72
        coherence = max(0.0, 1.0 - replacement_penalty - repetition_penalty - symbol_penalty)
        score = max(0.0, min(1.0, (coherence * 0.65 + completeness * 0.35)))
        noise_types = []
        if replacement_penalty:  # Lower semantic quality when mojibake markers are present.
            noise_types.append("mojibake")
        if repetition_penalty:  # Lower semantic quality when short-token repetition is strong.
            noise_types.append("repetition")
        if symbol_penalty:  # Lower semantic quality when symbols dominate the content.
            noise_types.append("low_information")
        return {
            "semantic_quality_score": round(score, 4),
            "coherence_score": round(coherence, 4),
            "completeness_score": round(completeness, 4),
            "noise_types": noise_types,
            "repairable": bool(noise_types and score >= 0.45),
        }

    def _short_token_repetition(self, text: str) -> float:
        """Compute repetition among short text tokens.

        Business logic:
            1. Tokenize the text into short word-like units.
            2. Compare unique-token count against total-token count.
            3. Return the resulting repetition ratio.

        Args:
                text (str): Input text content.

        Returns:
            float: Short-token repetition ratio.

        Examples:
            >>> _short_token_repetition
            _short_token_repetition
        """
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        if len(tokens) < 4:  # Very short token sequences are treated as non-repetitive.
            return 0.0
        unique = len(set(tokens))
        return 1.0 - unique / max(len(tokens), 1)

    def _bounded_float(self, value: Any) -> float:
        """Clamp a model score into the range [0, 1].

        Business logic:
            1. Try converting the input into a float.
            2. Clamp the parsed value into the valid score range.
            3. Return 0.0 when conversion fails.

        Args:
                value (Any): Value to normalize.

        Returns:
            float: Normalized score.

        Examples:
            >>> _bounded_float
            _bounded_float
        """
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

class LLMTextRepairOperator(TextOperator):
    operator_name: str = "llm_text_repair"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for text repair.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable chat client for repair calls.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleChatClient(self.config.get("llm", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Repair noisy text in one sample with an LLM or local fallback.

        Business logic:
            1. Skip repair for hard-fail or non-triggering samples.
            2. Prefer the LLM path when configured, otherwise use deterministic local repair.
            3. Apply the repair only when confidence and fidelity checks pass.

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
        issues = set(item.get("issues", []))
        skip_issues = set(self.config.get("skip_issues", ["empty_text", "too_short", "sensitive_risk"]))
        if issues & skip_issues:  # Skip repair when hard-fail issues are present.
            self.set_metric(item, "repair_applied", False)
            self.set_metric(item, "repair_skip_reason", sorted(issues & skip_issues))
            return item

        text = self.get_text(item)
        if not self._should_repair(item):  # Preserve original text when no repair trigger is present.
            self.set_metric(item, "repair_applied", False)
            return item

        if self.client.is_enabled():  # Use the API path when the external model is fully configured.
            result, error = self._call_llm(text)
            if error:  # Record fallback reasons when the API path fails.
                self.add_issue(item, "llm_api_fallback")
                self.set_metric(item, "repair_llm_error", error)
                repaired, confidence, reason, mode = self._local_repair(text)
            else:
                repaired = str(result.get("repaired_text", text) or text)
                confidence = self._bounded_float(result.get("confidence", 0.0))
                reason = str(result.get("reason", ""))
                mode = "api"
        else:
            repaired, confidence, reason, mode = self._local_repair(text)

        min_confidence = float(self.config.get("min_confidence", 0.45))
        if repaired != text and confidence >= min_confidence and self._valid_repair(text, repaired):  # Accept the repair only when confidence and fidelity checks pass.
            item.setdefault("intermediate", {})["text_before_llm_repair"] = text
            self.set_text(item, repaired)
            self.add_issue(item, "text_repaired")
            self.set_metric(item, "repair_applied", True)
            self.set_metric(item, "repair_mode", mode)
            self.set_metric(item, "repair_confidence", round(confidence, 4))
            self.set_metric(item, "repair_reason", reason)
        else:
            self.set_metric(item, "repair_applied", False)
            self.set_metric(item, "repair_mode", mode)
            self.set_metric(item, "repair_confidence", round(confidence, 4))
        return item

    def _should_repair(self, item: dict) -> bool:
        """Return whether a sample should enter the text-repair step.

        Business logic:
            1. Respect the `repair_all` override when it is enabled.
            2. Otherwise compare sample issues against the configured repair-trigger set.
            3. Return whether any repair trigger is present.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            bool: Whether the sample should be repaired.

        Examples:
            >>> _should_repair
            _should_repair
        """
        if self.config.get("repair_all", False):  # Ignore issue-based filtering when full repair is requested.
            return True
        repair_issues = set(
            self.config.get(
                "repair_issues",
                [
                    "mojibake_repaired",
                    "possible_mojibake",
                    "unicode_repaired",
                    "chinese_normalized",
                    "markdown_noise_removed",
                    "semantic_repairable",
                ],
            )
        )
        return bool(set(item.get("issues", [])) & repair_issues)

    def _call_llm(self, text: str) -> tuple[dict[str, Any], str]:
        """Call the text LLM for repair.

        Business logic:
            1. Assemble prompts and request parameters for repair.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                text (str): Input text content.

        Returns:
            tuple[dict[str, Any], str]: Structured result and error string.

        Examples:
            >>> _call_llm
            _call_llm
        """
        system_prompt = (
            "You are a conservative Chinese text denoising repair engine. Return strict JSON only. "
            "Repair OCR mistakes, broken punctuation, abnormal spacing, encoding artifacts, and line breaks. "
            "Do not add facts, do not summarize, and do not change the original meaning."
        )
        user_prompt = (
            "Repair the following noisy text. If it cannot be safely repaired, return the original text "
            "with changed=false. Return JSON keys: repaired_text, changed, confidence, reason.\n\nTEXT:\n"
            + text[: int(self.config.get("max_input_chars", 4000))]
        )
        return self.client.chat_json(system_prompt, user_prompt)

    def _local_repair(self, text: str) -> tuple[str, float, str, str]:
        """Run deterministic local text repair.

        Business logic:
            1. Collapse repeated punctuation and abnormal intra-Chinese spacing.
            2. Apply configured OCR replacements.
            3. Return repaired text, confidence, reason, and mode.

        Args:
                text (str): Input text content.

        Returns:
            tuple[str, float, str, str]: Repaired text, confidence, reason, and repair mode.

        Examples:
            >>> _local_repair
            _local_repair
        """
        repaired = text
        repaired = re.sub(r"([!！]){2,}", r"\1", repaired)
        repaired = re.sub(r"([?？]){2,}", r"\1", repaired)
        repaired = re.sub(r"([。]){2,}", r"\1", repaired)
        repaired = re.sub(r"([,，]){2,}", r"\1", repaired)
        repaired = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", repaired)
        repaired = re.sub(r"\s+", " ", repaired).strip()
        replacements = self.config.get("ocr_replacements", {})
        if isinstance(replacements, dict):  # Apply configured OCR replacements only when the mapping is valid.
            for source, target in replacements.items():  # Replace common OCR mistakes with deterministic local rules.
                repaired = repaired.replace(str(source), str(target))
        confidence = 0.75 if repaired != text else 0.0
        return repaired, confidence, "local deterministic repair", "local_fallback"

    def _valid_repair(self, original: str, repaired: str) -> bool:
        """Validate that a repair stays faithful to the original text.

        Business logic:
            1. Reject empty repaired text.
            2. Enforce a maximum length-growth constraint.
            3. Return whether the repair is acceptable.

        Args:
                original (str): Original text.
                repaired (str): Repaired text.

        Returns:
            bool: Whether the repair passes fidelity checks.

        Examples:
            >>> _valid_repair
            _valid_repair
        """
        if not repaired.strip():  # Reject repairs that erase all content.
            return False
        max_growth = float(self.config.get("max_length_growth", 1.25))
        if len(repaired) > max(len(original) * max_growth, len(original) + 30):  # Reject repairs that grow beyond the configured length allowance.
            return False
        return True

    def _bounded_float(self, value: Any) -> float:
        """Clamp a model score into the range [0, 1].

        Business logic:
            1. Try converting the input into a float.
            2. Clamp the parsed value into the valid score range.
            3. Return 0.0 when conversion fails.

        Args:
                value (Any): Value to normalize.

        Returns:
            float: Normalized score.

        Examples:
            >>> _bounded_float
            _bounded_float
        """
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
