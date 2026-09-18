from dedup_workflow_engine.utilities.audio.shared import *  # noqa: F403

class AudioEmbeddingOperator(BaseOperator):
    operator_name = "audio_embedding"  # Workflow config: operator name for generating audio embeddings and optionally recalling semantic duplicate edges directly.

    def setup(self) -> None:
        """Read audio-embedding operator config.

        Business logic:
            1. Read whether the external audio-embedding API is enabled.
            2. Read the dimensionality of local acoustic/bytes fallback vectors.
            3. Read API environment-variable names, endpoint, and input-field name.

        Args:
            None: setup uses self.config.

        Returns:
            None: Config values are written into instance attributes.

        Examples:
            >>> op = AudioEmbeddingOperator({"dimensions": 8})
            >>> op.setup()
            >>> op.dimensions
            8
        """
        self.enabled = config_enabled(self.config)  # Workflow config: whether to attempt calling an external audio-embedding API.
        self.dimensions = int(self.config.get("dimensions", 128))  # Workflow config: local fallback vector dimensionality or acoustic-bin count.
        self.api_base_env = str(self.config.get("api_base_env", "AUDIO_EMBEDDING_API_BASE"))  # Workflow config: env-var name holding the API base URL.
        self.api_key_env = str(self.config.get("api_key_env", "AUDIO_EMBEDDING_API_KEY"))  # Workflow config: env-var name holding the API key.
        self.model_env = str(self.config.get("model_env", "AUDIO_EMBEDDING_MODEL"))  # Workflow config: env-var name holding the audio-embedding model name.
        self.endpoint_path = str(self.config.get("endpoint_path", "/embeddings"))  # Workflow config: audio-embedding API endpoint path.
        self.input_field = str(self.config.get("input_field", "audio_base64"))  # Workflow config: request-body field name carrying audio base64.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate embeddings for audio samples and optionally recall similar edges.

        Business logic:
            1. Check whether the external API environment variables are complete.
            2. Call the API for each audio file or fall back to acoustic/bytes vectors.
            3. Write audio_embedding and optionally run pairwise recall according to config.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized audio paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with audio_embedding.

        Examples:
            >>> AudioEmbeddingOperator({"recall": False}).process_dataset([], {})
            []
        """
        import base64
        import os

        missing = missing_env_names(
            {"api_base_env": self.api_base_env, "api_key_env": self.api_key_env},
            ["api_base_env", "api_key_env"],
        )
        use_api = self.enabled and not missing
        vectors: list[tuple[str, list[float]]] = []
        threshold = float(self.config.get("similarity_threshold", 0.92))
        for item in items:  # Try generating an embedding for every valid audio path.
            path_value = item.get("intermediate", {}).get("audio_path_abs")
            if not path_value:  # Samples missing a path are already handled by normalize.
                continue
            path = Path(path_value)
            data = path.read_bytes() if path.exists() else b""
            if use_api:  # Prefer model embeddings when the API is available.
                try:
                    response = call_json_api_endpoint(
                        os.environ[self.api_base_env],
                        self.endpoint_path,
                        os.environ[self.api_key_env],
                        {
                            "model": os.environ.get(self.model_env, ""),
                            self.input_field: base64.b64encode(data).decode("ascii"),
                        },
                    )
                    vector = response.get("embedding") or response.get("data", [{}])[0].get("embedding")
                    if not isinstance(vector, list):  # The API response must return a vector before it can participate in similarity calculation.
                        raise ValueError("embedding response does not contain a vector")
                except Exception as exc:
                    self.add_issue(item, "audio_embedding_api_failed")
                    item.setdefault("meta", {})["audio_embedding_error"] = str(exc)
                    vector = wav_acoustic_vector(path, bins=self.dimensions) or bytes_hashing_vector(data, self.dimensions)
            else:
                if self.enabled and missing:  # Record a diagnosable issue when the user enabled the API but required env vars are missing.
                    self.add_issue(item, "audio_embedding_api_not_configured")
                vector = wav_acoustic_vector(path, bins=self.dimensions) or bytes_hashing_vector(data, self.dimensions)
            self.set_intermediate(item, "audio_embedding", vector)
            vectors.append((str(item["id"]), vector))

        if self.config.get("recall", True):  # The audio-embedding operator runs recall by default to reduce extra workflow steps.
            for left_id, right_id, score in pairwise_topk(vectors, threshold=threshold, top_k=int(self.config.get("top_k", 0))):  # Highly similar embedding pairs become semantic duplicate candidates.
                self.add_duplicate_edge(
                    context,
                    left_id,
                    right_id,
                    score,
                    f"audio_embedding_cosine>={threshold}",
                    "semantic_duplicate",
                )
        return items
