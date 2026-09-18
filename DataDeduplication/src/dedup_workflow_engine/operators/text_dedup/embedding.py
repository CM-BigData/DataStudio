from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403

class TextEmbeddingOperator(BaseOperator):
    operator_name = "text_embedding"  # Workflow config: operator name for generating text embeddings or hashing-based fallback vectors.

    def setup(self) -> None:
        """Read text-embedding operator config.

        Business logic:
            1. Read whether the external embedding API is enabled.
            2. Read the dimensionality of the local hashing-based fallback vector.
            3. Read environment-variable names for API base/key/model and the endpoint path.

        Args:
            None: setup uses self.config.

        Returns:
            None: Config values are written into instance attributes.

        Examples:
            >>> op = TextEmbeddingOperator({"dimensions": 8})
            >>> op.setup()
            >>> op.dimensions
            8
        """
        self.enabled = config_enabled(self.config)  # Workflow config: whether to attempt calling an external embedding API.
        self.dimensions = int(self.config.get("dimensions", 128))  # Workflow config: fallback hashing-vector dimensionality when the API is unavailable.
        self.api_base_env = str(self.config.get("api_base_env", "TEXT_EMBEDDING_API_BASE"))  # Workflow config: env-var name holding the embedding API base URL.
        self.api_key_env = str(self.config.get("api_key_env", "TEXT_EMBEDDING_API_KEY"))  # Workflow config: env-var name holding the embedding API key.
        self.model_env = str(self.config.get("model_env", "TEXT_EMBEDDING_MODEL"))  # Workflow config: env-var name holding the embedding model name.
        self.endpoint_path = str(self.config.get("endpoint_path", "/embeddings"))  # Workflow config: endpoint path for the embedding API.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Write embedding vectors for text samples.

        Business logic:
            1. Check the environment variables required by the external embedding API.
            2. Call the API for each normalized_text or fall back to hashing_vector.
            3. Write the vector into intermediate.text_embedding.

        Args:
            items (list[dict[str, Any]]): Sample list that has already completed text normalization.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with text_embedding.

        Examples:
            >>> item = {"intermediate": {"normalized_text": "hello"}}
            >>> TextEmbeddingOperator({"enabled": False, "dimensions": 4}).process_dataset([item], {})[0]["intermediate"]["text_embedding"]
            [0.0, 0.0, 0.0, 0.0]
        """
        import os

        missing = missing_env_names(
            {"api_base_env": self.api_base_env, "api_key_env": self.api_key_env},
            ["api_base_env", "api_key_env"],
        )
        use_api = self.enabled and not missing
        for item in items:  # Every non-empty normalized_text needs a vector for ANNRecall.
            text = item.get("intermediate", {}).get("normalized_text", "")
            if not text:  # Empty text cannot produce a meaningful embedding.
                continue
            if use_api:  # Prefer the external embedding API when config is enabled and env vars are complete.
                try:
                    response = call_json_api_endpoint(
                        os.environ[self.api_base_env],
                        self.endpoint_path,
                        os.environ[self.api_key_env],
                        {"model": os.environ.get(self.model_env, ""), "input": text},
                    )
                    vector = response.get("embedding") or response.get("data", [{}])[0].get("embedding")
                    if not isinstance(vector, list):  # The API response must provide a vector usable for similarity calculation.
                        raise ValueError("embedding response does not contain a vector")
                except Exception as exc:
                    self.add_issue(item, "text_embedding_api_failed")
                    item.setdefault("meta", {})["text_embedding_error"] = str(exc)
                    vector = hashing_vector(text, dimensions=self.dimensions)
            else:
                if self.enabled and missing:  # Record an observable issue when the user enabled the API but the environment is incomplete.
                    self.add_issue(item, "text_embedding_api_not_configured")
                vector = hashing_vector(text, dimensions=self.dimensions)
            self.set_intermediate(item, "text_embedding", vector)
        return items
