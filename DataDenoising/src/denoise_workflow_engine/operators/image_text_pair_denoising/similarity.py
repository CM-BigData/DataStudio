from typing import Any
from denoise_workflow_engine.utilities.image_text_pair.base import *  # noqa: F403

class ImageTextKeywordSimilarityOperator(BaseOperator):
    operator_name: str = "image_text_keyword_similarity"  # Operator identifier used by workflow configs and the registry.

    STOPWORDS: set[str] = {  # Stopword set ignored during image-text keyword similarity scoring.
        "image",
        "img",
        "jpg",
        "jpeg",
        "png",
        "real",
        "mean",
        "photo",
        "picture",
        "图片",
        "图像",
        "照片",
        "一张",
        "一个",
        "场景",
        "画面",
    }

    def process(self, item: dict) -> dict:
        """Compute keyword-based similarity for one image-text-pair sample.

        Business logic:
            1. Collect image-side and caption-side tokens.
            2. Expand both token sets through the configured synonym map.
            3. Record overlap metrics and add a mismatch issue when similarity is too low.

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
        caption = str(payload.get("text", "") or "")
        image_tokens = self._image_tokens(payload, meta)
        caption_tokens = normalize_tokens(caption)
        usable_image_tokens = image_tokens - self.STOPWORDS
        usable_caption_tokens = caption_tokens - self.STOPWORDS
        if not usable_image_tokens:  # Avoid inflated similarity when the image side has no usable tokens.
            self.set_metric(item, "image_text_similarity_score", None)
            self.set_metric(item, "image_text_similarity_source", "insufficient_image_keywords")
            return item

        synonyms = load_synonyms(self.config.get("synonyms"))
        expanded_image = expand_synonyms(usable_image_tokens, synonyms)
        expanded_caption = expand_synonyms(usable_caption_tokens, synonyms)
        matched = expanded_image & expanded_caption
        score = len(matched) / max(len(expanded_image), 1)
        self.set_metric(item, "image_text_similarity_score", round(score, 4))
        self.set_metric(item, "image_text_similarity_source", "keyword_rapidfuzz_token_rules")
        self.set_metric(item, "image_keywords", sorted(usable_image_tokens))
        self.set_metric(item, "caption_keywords", sorted(usable_caption_tokens))
        self.set_metric(item, "matched_keywords", sorted(matched))
        if score < float(self.config.get("min_keyword_similarity", 0.2)):  # Flag a mismatch when keyword similarity is too low.
            self.add_issue(item, "image_text_mismatch")
        return item

    def _image_tokens(self, payload: dict, meta: dict) -> set[str]:
        """Collect image-side keywords from payload and metadata.

        Business logic:
            1. Read known visual-keyword fields from payload and metadata.
            2. Normalize list or string values into token sets.
            3. Optionally fall back to filename hints when configured.

        Args:
                payload (dict): Sample payload.
                meta (dict): Sample metadata.

        Returns:
            set[str]: Image-side keyword tokens.

        Examples:
            >>> _image_tokens
            _image_tokens
        """
        tokens: set[str] = set()
        for key in ["image_keywords", "objects", "labels"]:  # Read candidate visual-keyword fields from payload and metadata.
            value = payload.get(key, meta.get(key))
            if isinstance(value, list):  # Normalize list-shaped visual keywords entry by entry.
                for entry in value:  # Convert each visual-keyword entry into normalized tokens.
                    tokens |= normalize_tokens(str(entry))
            elif isinstance(value, str):
                tokens |= normalize_tokens(value)
        if tokens:  # Return immediately when image-side tokens are available.
            return tokens
        if bool(self.config.get("allow_filename_hints", False)):  # Use filename hints only when explicitly enabled.
            image_path = str(payload.get("image_path", "") or "")
            if image_path:  # Use the image filename stem as a weak fallback hint.
                tokens |= normalize_tokens(Path(image_path).stem)
            for key in ["scene", "category", "filename_hint"]:  # Read metadata-only weak hints when configured.
                if meta.get(key):  # Add metadata hints to image-side tokens when present.
                    tokens |= normalize_tokens(str(meta[key]))
        return tokens

class CLIPImageTextSimilarityOperator(BaseOperator):
    operator_name: str = "clip_image_text_similarity"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for CLIP-style similarity estimation.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable vision client for similarity requests.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleVisionClient(self.config.get("clip", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Estimate image-text similarity with CLIP-like scoring or local fallback.

        Business logic:
            1. Prefer provided scores when they exist.
            2. Otherwise use the external model when configured, or fall back to local token similarity.
            3. Record similarity metrics and add mismatch issues when needed.

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
        provided = payload.get("clip_similarity_score", meta.get("clip_similarity_score"))
        source = "local_fallback"
        score: float | None

        if provided is not None:  # Reuse provided offline scores when available.
            score = bounded_float(provided, 0.0)
            source = "provided_score"
        elif self.client.is_enabled() and payload.get("image_path"):
            image_path = Path(str(payload.get("image_path")))
            result, error = self._call_clip(image_path, str(payload.get("text", "") or ""))
            if error:  # Record fallback reasons when the API path fails.
                self.add_issue(item, "clip_api_fallback")
                self.set_metric(item, "clip_error", error)
                score = self._local_similarity(item)
            else:
                score = bounded_float(result.get("clip_similarity_score", result.get("similarity_score", 0.0)), 0.0)
                source = "api"
                if result.get("reason"):  # Preserve model explanations for auditing when provided.
                    self.set_metric(item, "clip_reason", str(result.get("reason"))[:300])
        else:
            score = self._local_similarity(item)

        self.set_metric(item, "clip_similarity_source", source)
        self.set_metric(item, "clip_similarity_score", None if score is None else round(score, 4))
        if score is not None and score < float(self.config.get("min_clip_similarity", 0.28)):  # Flag a mismatch when CLIP similarity is too low.
            self.add_issue(item, "clip_mismatch")
        return item

    def _call_clip(self, image_path: Path, caption: str) -> tuple[dict[str, Any], str]:
        """Call the image-text similarity model.

        Business logic:
            1. Assemble the outbound similarity prompt.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                image_path (Path): Image path.
                caption (str): Caption text.

        Returns:
            tuple[dict[str, Any], str]: Structured similarity result and error string.

        Examples:
            >>> _call_clip
            _call_clip
        """
        prompt = (
            "Estimate image-text semantic similarity for data denoising. "
            "Return strict JSON only with keys: clip_similarity_score(0-1), matched_concepts(list), "
            "missing_concepts(list), contradiction(boolean), reason(string). Caption:\n"
            + caption[:1000]
        )
        return self.client.chat_json(image_path, prompt)

    def _local_similarity(self, item: dict) -> float | None:
        """Estimate image-text similarity locally.

        Business logic:
            1. Collect normalized image and caption token sets.
            2. Expand both token sets with synonyms.
            3. Return a blended recall/precision similarity estimate.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            float | None: Local similarity estimate.

        Examples:
            >>> _local_similarity
            _local_similarity
        """
        payload = item.get("payload", {})
        meta = item.get("meta", {})
        image_tokens = ImageTextKeywordSimilarityOperator({})._image_tokens(payload, meta)
        caption_tokens = normalize_tokens(str(payload.get("text", "") or ""))
        synonyms = load_synonyms(self.config.get("synonyms"))
        image_tokens = expand_synonyms(image_tokens - ImageTextKeywordSimilarityOperator.STOPWORDS, synonyms)
        caption_tokens = expand_synonyms(caption_tokens - ImageTextKeywordSimilarityOperator.STOPWORDS, synonyms)
        if not image_tokens:  # Return no estimate when the image side has no tokens.
            return None
        if not caption_tokens:  # Return zero similarity when the caption has no tokens.
            return 0.0
        overlap = image_tokens & caption_tokens
        recall = len(overlap) / max(len(image_tokens), 1)
        precision = len(overlap) / max(len(caption_tokens), 1)
        return max(0.0, min(1.0, recall * 0.75 + precision * 0.25))

class VLMConsistencyOperator(BaseOperator):
    operator_name: str = "vlm_consistency"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for VLM-based consistency checks.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable vision client for consistency checks.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleVisionClient(self.config.get("vlm", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Check image-text consistency with a VLM or local fallback.

        Business logic:
            1. Prefer provided scores when available.
            2. Otherwise use the VLM when configured, or fall back locally.
            3. Record consistency metrics and add inconsistency issues when needed.

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
        provided = payload.get("vlm_consistency_score", meta.get("vlm_consistency_score"))
        contradiction = False
        reason = ""

        if provided is not None:  # Reuse provided offline scores when available.
            score = bounded_float(provided, 0.0)
            source = "provided_score"
        elif self.client.is_enabled() and payload.get("image_path"):
            image_path = Path(str(payload.get("image_path")))
            result, error = self._call_vlm(image_path, str(payload.get("text", "") or ""))
            if error:  # Record fallback reasons when the API path fails.
                self.add_issue(item, "vlm_api_fallback")
                self.set_metric(item, "vlm_consistency_error", error)
                score, source = self._fallback_score(item)
            else:
                score = bounded_float(result.get("vlm_consistency_score", result.get("consistency_score", 0.0)), 0.0)
                contradiction = bool(result.get("contradiction", False))
                reason = str(result.get("reason", "") or "")
                source = "api"
        else:
            score, source = self._fallback_score(item)

        self.set_metric(item, "vlm_consistency_source", source)
        self.set_metric(item, "vlm_consistency_score", None if score is None else round(score, 4))
        self.set_metric(item, "vlm_contradiction", contradiction)
        if reason:  # Preserve model explanations for auditing when available.
            self.set_metric(item, "vlm_consistency_reason", reason[:300])
        if contradiction:  # Add a contradiction issue when the model explicitly reports inconsistency.
            self.add_issue(item, "vlm_contradiction")
        if score is not None and score < float(self.config.get("min_vlm_consistency", 0.2)):  # Flag inconsistency when the VLM score is too low.
            self.add_issue(item, "vlm_inconsistent")
        return item

    def _call_vlm(self, image_path: Path, caption: str) -> tuple[dict[str, Any], str]:
        """Call the vision model for image-text consistency evaluation.

        Business logic:
            1. Assemble the outbound consistency prompt.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                image_path (Path): Image path.
                caption (str): Caption text.

        Returns:
            tuple[dict[str, Any], str]: Structured consistency result and error string.

        Examples:
            >>> _call_vlm
            _call_vlm
        """
        prompt = (
            "Check whether the caption is consistent with this image. Return strict JSON only with keys: "
            "vlm_consistency_score(0-1), contradiction(boolean), matched_facts(list), "
            "conflicting_facts(list), reason(string). Caption:\n"
            + caption[:1000]
        )
        return self.client.chat_json(image_path, prompt)

    def _fallback_score(self, item: dict) -> tuple[float | None, str]:
        """Estimate image-text consistency from available local metrics.

        Business logic:
            1. Prefer CLIP similarity when it is already available.
            2. Otherwise fall back to keyword-based similarity when available.
            3. Return `insufficient_evidence` when neither metric exists.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            tuple[float | None, str]: Fallback consistency score and source label.

        Examples:
            >>> _fallback_score
            _fallback_score
        """
        metrics = item.get("metrics", {})
        if metrics.get("clip_similarity_score") is not None:  # Prefer CLIP similarity as the first local fallback.
            return metric_or_default(metrics, "clip_similarity_score", 0.0), "clip_fallback_low_confidence"
        if metrics.get("image_text_similarity_score") is not None:  # Fall back to keyword similarity when CLIP is unavailable.
            return metric_or_default(metrics, "image_text_similarity_score", 0.0), "keyword_fallback_low_confidence"
        return None, "insufficient_evidence"
