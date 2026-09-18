from typing import Any
from denoise_workflow_engine.utilities.video.base import *  # noqa: F403

class SubtitleOCROperator(VideoOperator):
    operator_name: str = "subtitle_ocr"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for subtitle OCR.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable vision client for OCR calls.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleVisionClient(self.config.get("ocr", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Extract subtitle-like text from video keyframes.

        Business logic:
            1. Prefer provided subtitle text when available.
            2. Otherwise run OCR over a limited set of keyframes through the configured vision client.
            3. Record subtitle availability, extraction mode, and fallback reasons.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out video processing.
            return item
        payload = item.get("payload", {})
        provided = str(payload.get("precomputed_subtitle_text", "") or payload.get("subtitle_text", "") or "")
        subtitle_text = provided
        mode = "provided_fallback" if provided else "not_configured"
        if self.client.is_enabled():  # Use the API path when the external model is fully configured.
            extracted = []
            errors = []
            for frame_path in item.get("intermediate", {}).get("keyframe_paths", [])[: int(self.config.get("max_ocr_frames", 4))]:  # Aggregate OCR output across a limited set of keyframes.
                result, error = self._call_ocr(Path(frame_path))
                if error:  # Record fallback reasons when frame OCR fails.
                    errors.append(error)
                    continue
                text = str(result.get("subtitle_text", result.get("ocr_text", result.get("text", ""))) or "")
                if text.strip():  # Keep only non-empty OCR text fragments.
                    extracted.append(text.strip())
            if extracted:  # Write results only when at least one subtitle fragment was extracted.
                subtitle_text = "\n".join(dict.fromkeys(extracted))
                mode = "api"
            elif errors:
                self.add_issue(item, "subtitle_ocr_api_fallback")
                self.set_metric(item, "subtitle_ocr_error", errors[0])
        self.set_metric(item, "subtitle_text_available", bool(subtitle_text.strip()))
        self.set_metric(item, "subtitle_ocr_mode", mode)
        self.set_metric(item, "subtitle_text_length", len(subtitle_text.strip()))
        if subtitle_text:  # Persist subtitle text when any subtitle content is available.
            item.setdefault("intermediate", {})["subtitle_text"] = subtitle_text
        return item

    def _call_ocr(self, frame_path: Path) -> tuple[dict[str, Any], str]:
        """Call the vision model to extract OCR text from a frame.

        Business logic:
            1. Assemble an OCR prompt focused on subtitle-like overlay text.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                frame_path (Path): Frame path.

        Returns:
            tuple[dict[str, Any], str]: Structured OCR result and error string.

        Examples:
            >>> _call_ocr
            _call_ocr
        """
        prompt = (
            "Extract visible subtitle or overlay text from this video frame. Return strict JSON only with keys: "
            "subtitle_text(string), confidence(0-1), language(string). If there is no readable text, use empty string."
        )
        return self.client.chat_json(frame_path, prompt)

class VideoASROperator(VideoOperator):
    operator_name: str = "video_asr"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for video ASR.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable audio client for ASR calls.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleAudioClient(self.config.get("asr", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Extract ASR text for one video sample.

        Business logic:
            1. Prefer provided ASR text when available.
            2. Otherwise run ASR over the extracted audio track when the client is enabled.
            3. Record ASR availability, mode, language, confidence, and fallback reasons.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out video processing.
            return item
        payload = item.get("payload", {})
        asr_text = str(payload.get("precomputed_asr_text", "") or payload.get("asr_text", "") or "")
        mode = "provided_fallback" if asr_text else "not_configured"
        audio_path_value = item.get("intermediate", {}).get("audio_path")
        if self.client.is_enabled() and audio_path_value:  # Use the API path when the external model is fully configured and audio is available.
            result, error = self.client.transcribe_json(
                Path(str(audio_path_value)),
                "Transcribe speech for a video denoising pipeline. Return JSON if supported.",
            )
            if error:  # Record fallback reasons when the ASR path fails.
                self.add_issue(item, "asr_api_fallback")
                self.set_metric(item, "asr_error", error)
            else:
                asr_text = str(result.get("asr_text", result.get("text", "")) or "")
                mode = "api"
                if result.get("language"):  # Record language when the transcription model returns it.
                    self.set_metric(item, "asr_language", str(result["language"]))
                if result.get("confidence") is not None:  # Record confidence when the transcription model returns it.
                    self.set_metric(item, "asr_confidence", round(bounded_float(result["confidence"]), 4))
        self.set_metric(item, "asr_text_available", bool(asr_text.strip()))
        self.set_metric(item, "asr_mode", mode)
        self.set_metric(item, "asr_text_length", len(asr_text.strip()))
        if asr_text:  # Persist non-empty ASR text for later semantic checks.
            item.setdefault("intermediate", {})["asr_text"] = asr_text
        return item
