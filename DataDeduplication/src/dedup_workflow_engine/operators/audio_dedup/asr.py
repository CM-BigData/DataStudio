from dedup_workflow_engine.utilities.audio.shared import *  # noqa: F403

class ASRTranscribeOperator(BaseOperator):
    operator_name = "asr_transcribe"  # Workflow config: operator name for generating or reading ASR text for audio samples.

    def setup(self) -> None:
        """Read ASR-transcription operator config.

        Business logic:
            1. Read whether the external ASR API is enabled.
            2. Read environment-variable names for API base/key/model.
            3. Read the endpoint path and audio-input field name.

        Args:
            None: setup uses self.config.

        Returns:
            None: Config values are written into instance attributes.

        Examples:
            >>> op = ASRTranscribeOperator({"enabled": False})
            >>> op.setup()
            >>> op.enabled
            False
        """
        self.enabled = config_enabled(self.config)  # Workflow config: whether to attempt calling an external ASR API.
        self.api_base_env = str(self.config.get("api_base_env", "ASR_API_BASE"))  # Workflow config: env-var name holding the ASR API base URL.
        self.api_key_env = str(self.config.get("api_key_env", "ASR_API_KEY"))  # Workflow config: env-var name holding the ASR API key.
        self.model_env = str(self.config.get("model_env", "ASR_MODEL"))  # Workflow config: env-var name holding the ASR model name.
        self.endpoint_path = str(self.config.get("endpoint_path", ""))  # Workflow config: ASR API endpoint path.
        self.input_field = str(self.config.get("input_field", "audio_base64"))  # Workflow config: request-body field name carrying audio base64.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Write ASR text for audio samples.

        Business logic:
            1. Prefer transcription text already present in payload.asr_text.
            2. Call an external ASR API when enabled and fully configured.
            3. Write transcription text into intermediate.asr_text and record issues on failure.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized audio paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with asr_text.

        Examples:
            >>> item = {"payload": {"asr_text": "hello"}}
            >>> ASRTranscribeOperator({}).process_dataset([item], {})[0]["intermediate"]["asr_text"]
            'hello'
        """
        import base64
        import os

        missing = missing_env_names(
            {"api_base_env": self.api_base_env, "api_key_env": self.api_key_env},
            ["api_base_env", "api_key_env"],
        )
        use_api = self.enabled and not missing
        for item in items:  # Prefer reusing existing ASR text for every audio sample.
            payload_text = item.get("payload", {}).get("asr_text")
            if payload_text:  # No external API call is needed when the dataset already contains a transcript.
                self.set_intermediate(item, "asr_text", str(payload_text))
                continue
            if not use_api:  # Skip online transcription when the API is disabled or incompletely configured.
                if self.enabled and missing:  # Record an issue when the user enabled ASR but required env vars are missing.
                    self.add_issue(item, "asr_api_not_configured")
                continue
            path_value = item.get("intermediate", {}).get("audio_path_abs")
            if not path_value:  # ASR cannot be called when the audio path is missing.
                continue
            try:
                data = Path(path_value).read_bytes()
                response = call_json_api_endpoint(
                    os.environ[self.api_base_env],
                    self.endpoint_path,
                    os.environ[self.api_key_env],
                    {
                        "model": os.environ.get(self.model_env, ""),
                        self.input_field: base64.b64encode(data).decode("ascii"),
                    },
                )
                text = response.get("text") or response.get("transcript")
                if text:  # Write intermediate results when the API returns text or transcript.
                    self.set_intermediate(item, "asr_text", str(text))
            except Exception as exc:
                self.add_issue(item, "asr_api_failed")
                item.setdefault("meta", {})["asr_error"] = str(exc)
        return items

class ASRTextDeduplicator(BaseOperator):
    operator_name = "asr_text_deduplicator"  # Workflow config: semantic audio-duplicate detection operator name based on ASR-text SimHash.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect semantic audio duplicates using ASR text.

        Business logic:
            1. Read intermediate.asr_text from each sample.
            2. Normalize the text and compute SimHash.
            3. Generate semantic_duplicate edges when ASR-text fingerprint distance stays below the threshold.

        Args:
            items (list[dict[str, Any]]): Audio sample list that already contains ASR text.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with asr_normalized_text and asr_simhash.

        Examples:
            >>> ASRTextDeduplicator({}).process_dataset([], {})
            []
        """
        max_hamming_distance = int(self.config.get("max_hamming_distance", 8))
        texts: list[tuple[str, str, int]] = []
        for item in items:  # Generate one text fingerprint for every audio sample that has ASR text.
            text = item.get("intermediate", {}).get("asr_text")
            if not text:  # ASR-text deduplication cannot run when transcription text is missing.
                continue
            normalized = normalize_text(str(text))
            fp = simhash(normalized)
            self.set_intermediate(item, "asr_normalized_text", normalized)
            self.set_intermediate(item, "asr_simhash", fp)
            texts.append((str(item["id"]), normalized, fp))
        for (left_id, _left_text, left_hash), (right_id, _right_text, right_hash) in combinations(texts, 2):  # ASR-text fingerprints require pairwise comparison.
            distance = hamming_distance(left_hash, right_hash)
            if distance <= max_hamming_distance:  # Close text fingerprints suggest the audio semantic content may be duplicate.
                score = 1 - distance / 64
                self.add_duplicate_edge(
                    context,
                    left_id,
                    right_id,
                    score,
                    f"asr_text_simhash<={max_hamming_distance}",
                    "semantic_duplicate",
                )
        return items
