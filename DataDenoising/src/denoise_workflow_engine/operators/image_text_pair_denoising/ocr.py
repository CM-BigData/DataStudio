from typing import Any
from denoise_workflow_engine.utilities.image_text_pair.base import *  # noqa: F403

class ImageOCRExtractOperator(BaseOperator):
    operator_name: str = "image_ocr_extract"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for OCR extraction.

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
        """Extract OCR text from one image-text-pair sample.

        Business logic:
            1. Skip non-pair modalities.
            2. Prefer provided OCR text when available or call the OCR model when configured.
            3. Record OCR output, extraction mode, and fallback reasons.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if item.get("modality") != "image_text_pair":  # Run this operator only for image-text-pair samples.
            return item

        payload = item.get("payload", {})
        meta = item.get("meta", {})
        provided = self._provided_ocr(payload, meta)
        image_path = Path(str(payload.get("image_path", "") or ""))
        ocr_text = ""
        mode = "not_configured"
        confidence: Any = None

        if self.client.is_enabled() and image_path.exists():  # Call external OCR only when the model is configured and the image exists.
            result, error = self._call_ocr(image_path)
            if error:  # Record fallback reasons when OCR fails.
                self.add_issue(item, "ocr_api_fallback")
                self.set_metric(item, "ocr_error", error)
                ocr_text = provided
                mode = "provided_fallback" if provided else "api_failed_no_text"
            else:
                ocr_text = str(result.get("ocr_text", result.get("text", "")) or "")
                confidence = result.get("confidence")
                mode = "api"
        else:
            ocr_text = provided
            if provided:  # Treat provided OCR text as a fallback source.
                mode = "provided_fallback"

        item.setdefault("intermediate", {})["ocr_text"] = ocr_text
        self.set_metric(item, "ocr_mode", mode)
        self.set_metric(item, "ocr_text_length", len(ocr_text.strip()))
        if confidence is not None:  # Record confidence when the OCR model returns it.
            self.set_metric(item, "ocr_confidence", round(bounded_float(confidence), 4))
        return item

    def _provided_ocr(self, payload: dict, meta: dict) -> str:
        """Read OCR text already provided with the sample.

        Business logic:
            1. Check payload OCR fields first.
            2. Fall back to OCR hints stored in metadata.
            3. Return an empty string when no OCR text is provided.

        Args:
                payload (dict): Sample payload.
                meta (dict): Sample metadata.

        Returns:
            str: Provided OCR text.

        Examples:
            >>> _provided_ocr
            _provided_ocr
        """
        for key in ["precomputed_ocr_text", "ocr_text"]:  # Check known OCR fields in order.
            if payload.get(key):  # Use payload OCR content directly when present.
                return str(payload[key])
            if meta.get(key):  # Fall back to metadata OCR hints.
                return str(meta[key])
        return ""

    def _call_ocr(self, path: Path) -> tuple[dict[str, Any], str]:
        """Call the vision model to extract OCR text.

        Business logic:
            1. Assemble an OCR prompt for visible text extraction.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                path (Path): File path.

        Returns:
            tuple[dict[str, Any], str]: Structured OCR result and error string.

        Examples:
            >>> _call_ocr
            _call_ocr
        """
        prompt = (
            "Extract visible text from this image for a multimodal denoising pipeline. "
            "Return strict JSON only with keys: ocr_text(string), confidence(0-1), "
            "language(string), key_fields(object). Do not infer text that is not visible."
        )
        return self.client.chat_json(path, prompt)

class OCRTextConsistencyOperator(BaseOperator):
    operator_name: str = "ocr_text_consistency"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Compare OCR text against caption text for one pair sample.

        Business logic:
            1. Skip non-pair modalities.
            2. Compute token overlap between caption text and OCR text.
            3. Record consistency metrics and add mismatch issues when needed.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if item.get("modality") != "image_text_pair":  # Run this operator only for image-text-pair samples.
            return item
        payload = item.get("payload", {})
        caption = str(payload.get("text", "") or "")
        ocr_text = str(
            item.get("intermediate", {}).get("ocr_text", "")
            or payload.get("precomputed_ocr_text", "")
            or payload.get("ocr_text", "")
            or ""
        )
        if not ocr_text.strip():  # Skip consistency checks when OCR text is unavailable.
            self.set_metric(item, "ocr_consistency_score", None)
            self.set_metric(item, "ocr_consistency_source", "insufficient_evidence")
            return item
        score = token_overlap(caption, ocr_text)
        self.set_metric(item, "ocr_consistency_score", round(score, 4))
        self.set_metric(item, "ocr_consistency_source", "rapidfuzz_token_similarity")
        if score < float(self.config.get("min_ocr_consistency", 0.15)):  # Flag OCR mismatch when the consistency score is too low.
            self.add_issue(item, "ocr_text_mismatch")
        return item

class OCRKeyFieldConsistencyOperator(BaseOperator):
    operator_name: str = "ocr_key_field_consistency"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Compare OCR key fields against caption key fields.

        Business logic:
            1. Skip non-pair modalities.
            2. Extract numbers, dates, and codes from caption and OCR text.
            3. Record conflicts and add key-field inconsistency issues when needed.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if item.get("modality") != "image_text_pair":  # Run this operator only for image-text-pair samples.
            return item
        payload = item.get("payload", {})
        caption = str(payload.get("text", "") or "")
        ocr_text = str(item.get("intermediate", {}).get("ocr_text", "") or payload.get("ocr_text", "") or "")
        if not ocr_text.strip():  # Skip key-field consistency checks when OCR text is unavailable.
            self.set_metric(item, "ocr_key_field_consistency_score", None)
            return item

        caption_fields = extract_key_fields(caption)
        ocr_fields = extract_key_fields(ocr_text)
        compared = 0
        conflicts: dict[str, dict[str, list[str]]] = {}
        for field_type in ["numbers", "dates", "codes"]:  # Compare numeric, date, and code fields separately to avoid cross-type false positives.
            caption_values = caption_fields.get(field_type, set())
            ocr_values = ocr_fields.get(field_type, set())
            if not caption_values or not ocr_values:  # Skip conflict checks when one side lacks key fields.
                continue
            compared += 1
            if caption_values.isdisjoint(ocr_values):  # Record conflicts when caption and OCR key fields share no overlap.
                conflicts[field_type] = {
                    "caption": sorted(caption_values),
                    "ocr": sorted(ocr_values),
                }

        score = None if compared == 0 else max(0.0, 1.0 - len(conflicts) / compared)
        self.set_metric(item, "ocr_key_field_consistency_score", None if score is None else round(score, 4))
        self.set_metric(
            item,
            "ocr_key_fields",
            {
                "caption": {key: sorted(value) for key, value in caption_fields.items()},
                "ocr": {key: sorted(value) for key, value in ocr_fields.items()},
            },
        )
        if conflicts:  # Add an OCR key-field conflict issue when any key-field category conflicts.
            self.add_issue(item, "ocr_key_field_conflict")
            self.set_metric(item, "ocr_key_field_conflicts", conflicts)
        if score is None:  # Record that the comparison lacked enough key-field evidence.
            self.set_metric(item, "ocr_key_field_consistency_source", "insufficient_key_fields")
        return item
