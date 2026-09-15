from dedup_workflow_engine.utilities.image.shared import *  # noqa: F403

class ImageEmbeddingOperator(BaseOperator):
    operator_name = "image_embedding"  # Workflow config: operator name for generating image embeddings or local fallback vectors.

    def setup(self) -> None:
        """Read image-embedding operator config.

        Business logic:
            1. Read whether the external image-embedding API is enabled.
            2. Read the dimensionality of the local fallback vector.
            3. Read API environment-variable names, endpoint, and input-field name.

        Args:
            None: setup uses self.config.

        Returns:
            None: Config values are written into instance attributes.

        Examples:
            >>> op = ImageEmbeddingOperator({"dimensions": 8})
            >>> op.setup()
            >>> op.dimensions
            8
        """
        self.enabled = config_enabled(self.config)  # Workflow config: whether to attempt calling an external image-embedding API.
        self.dimensions = int(self.config.get("dimensions", 128))  # Workflow config: local fallback vector dimensionality when the API is unavailable.
        self.api_base_env = str(self.config.get("api_base_env", "IMAGE_EMBEDDING_API_BASE"))  # Workflow config: env-var name holding the API base URL.
        self.api_key_env = str(self.config.get("api_key_env", "IMAGE_EMBEDDING_API_KEY"))  # Workflow config: env-var name holding the API key.
        self.model_env = str(self.config.get("model_env", "IMAGE_EMBEDDING_MODEL"))  # Workflow config: env-var name holding the model name.
        self.endpoint_path = str(self.config.get("endpoint_path", "/embeddings"))  # Workflow config: image-embedding API endpoint path.
        self.input_field = str(self.config.get("input_field", "image_base64"))  # Workflow config: request-body field name that carries image base64.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate embedding vectors for image samples.

        Business logic:
            1. Check whether image-embedding API environment variables are complete.
            2. Call the API for each existing image_path_abs or fall back to local vectors.
            3. Write vectors into intermediate.image_embedding.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized image paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with image_embedding.

        Examples:
            >>> ImageEmbeddingOperator({"enabled": False}).process_dataset([], {})
            []
        """
        import base64
        import os

        missing = missing_env_names(
            {"api_base_env": self.api_base_env, "api_key_env": self.api_key_env},
            ["api_base_env", "api_key_env"],
        )
        use_api = self.enabled and not missing
        for item in items:  # Try generating a recall-ready vector for every valid image path.
            path_value = item.get("intermediate", {}).get("image_path_abs")
            if not path_value:  # Samples missing a path are already handled by the normalize operator.
                continue
            path = Path(path_value)
            if not path.exists():  # Missing files cannot provide bytes or local image features.
                continue
            data = path.read_bytes()
            if use_api:  # Prefer model embeddings when an external API is available.
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
                    if not isinstance(vector, list):  # The API response must return a vector before the sample can enter ANN recall.
                        raise ValueError("embedding response does not contain a vector")
                except Exception as exc:
                    self.add_issue(item, "image_embedding_api_failed")
                    item.setdefault("meta", {})["image_embedding_error"] = str(exc)
                    vector = bytes_hashing_vector(data, dimensions=self.dimensions)
            else:
                if self.enabled and missing:  # Preserve a diagnosable issue when the user enabled the API but required env vars are missing.
                    self.add_issue(item, "image_embedding_api_not_configured")
                vector = image_local_embedding(path, dimensions=self.dimensions)
            self.set_intermediate(item, "image_embedding", vector)
        return items
