from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403
from dedup_workflow_engine.operators.text_dedup.minhash import lexical_similarity

class CrossEncoderRerankOperator(BaseOperator):
    operator_name = "cross_encoder_rerank"  # Workflow config: operator name for running cross-encoder or lexical rerank over text candidate edges.

    def setup(self) -> None:
        """Read text-rerank operator config.

        Business logic:
            1. Read whether the external rerank API is enabled.
            2. Read the API environment-variable names, mode, and timeout.
            3. Read the maximum text length sent to rerank.

        Args:
            None: setup uses self.config.

        Returns:
            None: Config values are written into instance attributes.

        Examples:
            >>> op = CrossEncoderRerankOperator({"max_text_chars": 10})
            >>> op.setup()
            >>> op.max_text_chars
            10
        """
        self.enabled = config_enabled(self.config)  # Workflow config: whether to attempt calling an external rerank API.
        self.api_base_env = str(self.config.get("api_base_env", "TEXT_RERANK_API_BASE"))  # Workflow config: env-var name holding the rerank API base URL.
        self.api_key_env = str(self.config.get("api_key_env", "TEXT_RERANK_API_KEY"))  # Workflow config: env-var name holding the rerank API key.
        self.model_env = str(self.config.get("model_env", "TEXT_RERANK_MODEL"))  # Workflow config: env-var name holding the rerank model name.
        self.api_mode = str(self.config.get("api_mode", "openai_chat"))  # Workflow config: protocol mode used to call the rerank API.
        self.max_text_chars = int(self.config.get("max_text_chars", 2000))  # Workflow config: maximum character length for one text segment sent to rerank.
        self.api_timeout_seconds = float(self.config.get("api_timeout_seconds", 60.0))  # Workflow config: rerank API request timeout in seconds.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Rerank text duplicate candidate edges and filter low-confidence edges.

        Business logic:
            1. Deduplicate duplicate_edges by sample pair.
            2. Call the rerank API when available, otherwise fall back to lexical_similarity.
            3. Keep only candidate edges whose rerank score or original score reaches the threshold.

        Args:
            items (list[dict[str, Any]]): Text sample list that already contains normalized_text.
            context (dict[str, Any]): Shared workflow context containing duplicate_edges.

        Returns:
            list[dict[str, Any]]: Original sample list; context.duplicate_edges is replaced by the reranked result.

        Examples:
            >>> CrossEncoderRerankOperator({"enabled": False}).process_dataset([], {"duplicate_edges": []})
            []
        """
        import os

        threshold = float(self.config.get("threshold", 0.85))
        by_id = {str(item["id"]): item for item in items}
        missing = missing_env_names(
            {"api_base_env": self.api_base_env, "api_key_env": self.api_key_env},
            ["api_base_env", "api_key_env"],
        )
        use_api = self.enabled and not missing
        reranked_edges = []
        for edge in _unique_edges_by_pair(context.get("duplicate_edges", [])):  # Each sample pair needs reranking only once.
            left = by_id.get(str(edge["left_id"]))
            right = by_id.get(str(edge["right_id"]))
            if not left or not right:  # Rerank input cannot be built when the candidate edge references missing samples.
                continue
            left_text = _clip_text(left.get("intermediate", {}).get("normalized_text", ""), self.max_text_chars)
            right_text = _clip_text(right.get("intermediate", {}).get("normalized_text", ""), self.max_text_chars)
            if use_api:  # Prefer model-based judgment when an external rerank service is available.
                try:
                    if self.api_mode == "openai_chat":  # OpenAI-compatible chat mode expects the model to return JSON content.
                        content = call_openai_chat(
                            os.environ[self.api_base_env],
                            os.environ[self.api_key_env],
                            os.environ.get(self.model_env, ""),
                            [
                                {
                                    "role": "system",
                                    "content": "You judge whether two Chinese text samples are duplicates. Return JSON only.",
                                },
                                {
                                    "role": "user",
                                    "content": (
                                        "Return a JSON object with keys score and duplicate. "
                                        "score must be a number from 0 to 1.\n"
                                        f"text_a: {left_text}\ntext_b: {right_text}"
                                    ),
                                },
                            ],
                            timeout_seconds=self.api_timeout_seconds,
                        )
                        import json

                        response = json.loads(content)
                        score = float(response.get("score", edge.get("score", 0)))
                    else:
                        response = call_json_api_endpoint(
                            os.environ[self.api_base_env],
                            str(self.config.get("endpoint_path", "")),
                            os.environ[self.api_key_env],
                            {
                                "model": os.environ.get(self.model_env, ""),
                                "query": left_text,
                                "document": right_text,
                            },
                            timeout_seconds=self.api_timeout_seconds,
                        )
                        score = float(response.get("score", response.get("similarity", edge.get("score", 0))))
                except Exception as exc:
                    left.setdefault("meta", {})["text_rerank_error"] = str(exc)
                    score = lexical_similarity(left_text, right_text)
            else:
                if self.enabled and missing:  # Record an issue and use lexical fallback when config is enabled but the environment is incomplete.
                    left.setdefault("issues", []).append("text_rerank_api_not_configured")
                score = max(float(edge.get("score", 0)), lexical_similarity(left_text, right_text))
            if score >= threshold or float(edge.get("score", 0)) >= threshold:  # Keep the edge when either the rerank score or the upstream score meets the threshold.
                edge = dict(edge)
                edge["score"] = max(float(edge.get("score", 0)), score)
                edge.setdefault("reasons", [edge.get("reason", "unknown")])
                if "cross_encoder_rerank" not in edge["reasons"]:  # Mark that the candidate edge has been reviewed by rerank or fallback logic.
                    edge["reasons"].append("cross_encoder_rerank" if use_api else "lexical_rerank_fallback")
                reranked_edges.append(edge)
        context["duplicate_edges"] = reranked_edges
        return items

def _unique_edges_by_pair(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge rerank-input candidate edges by sample pair.

    Business logic:
        1. Use sorted left/right ids as the undirected pair key.
        2. Normalize the edge on first appearance.
        3. Merge the highest score, reasons, and operators for repeated pairs.

    Args:
        edges (list[dict[str, Any]]): Duplicate candidate edges produced by upstream operators.

    Returns:
        list[dict[str, Any]]: One normalized candidate edge per sample pair.

    Examples:
        >>> _unique_edges_by_pair([{"left_id": "a", "right_id": "b", "score": 0.5}])[0]["left_id"]
        'a'
    """
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in edges:  # Merge every upstream candidate edge into an undirected sample pair.
        key = tuple(sorted([str(edge["left_id"]), str(edge["right_id"])]))
        if key not in unique:  # A new pair needs a standardized rerank edge first.
            unique[key] = _normalize_edge_for_rerank(edge, key)
            continue

        current = unique[key]
        if float(edge.get("score", 0)) > float(current.get("score", 0)):  # Keep the highest upstream score for the same pair.
            current["score"] = edge.get("score", current.get("score", 0))
            current["duplicate_type"] = edge.get("duplicate_type", current.get("duplicate_type", "near_duplicate"))

        for reason in edge.get("reasons", [edge.get("reason", "unknown")]):  # Merge all upstream judgment reasons.
            if reason not in current["reasons"]:  # Do not append reasons already recorded.
                current["reasons"].append(reason)
        for operator in edge.get("operators", [edge.get("operator", "unknown")]):  # Merge all operator names that contributed this edge.
            if operator not in current["operators"]:  # Do not append operator names already recorded.
                current["operators"].append(operator)
    return list(unique.values())

def _normalize_edge_for_rerank(edge: dict[str, Any], key: tuple[str, str]) -> dict[str, Any]:
    """Normalize an upstream candidate edge into the standard rerank structure.

    Business logic:
        1. Fix left_id and right_id using the undirected pair key.
        2. Preserve score and duplicate_type.
        3. Normalize single-value reason/operator fields into reasons/operators lists.

    Args:
        edge (dict[str, Any]): Upstream candidate edge.
        key (tuple[str, str]): Sorted sample-pair key.

    Returns:
        dict[str, Any]: Standardized rerank edge.

    Examples:
        >>> _normalize_edge_for_rerank({"score": 1}, ("a", "b"))["right_id"]
        'b'
    """
    return {
        "left_id": key[0],
        "right_id": key[1],
        "score": edge.get("score", 0),
        "duplicate_type": edge.get("duplicate_type", "near_duplicate"),
        "reasons": list(edge.get("reasons", [edge.get("reason", "unknown")])),
        "operators": list(edge.get("operators", [edge.get("operator", "unknown")])),
    }

def _clip_text(text: str, max_chars: int) -> str:
    """Truncate text before sending it to rerank.

    Business logic:
        1. Do not truncate when max_chars is less than or equal to 0.
        2. Return the original text when it stays within the limit.
        3. Keep only the first max_chars characters when the limit is exceeded.

    Args:
        text (str): Text to send to rerank.
        max_chars (int): Maximum character count.

    Returns:
        str: Truncated text.

    Examples:
        >>> _clip_text("abcdef", 3)
        'abc'
    """
    if max_chars <= 0 or len(text) <= max_chars:  # Non-positive limits or short text do not need truncation.
        return text
    return text[:max_chars]
