from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403

class TextDupFusionOperator(BaseOperator):
    operator_name = "text_dup_fusion"  # Workflow config: operator name for fusing multiple text duplicate candidate edges.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Fuse text duplicate candidate edges.

        Business logic:
            1. Read source weights for exact, simhash, minhash, embedding, rerank, and similar sources.
            2. Merge context.duplicate_edges by sample pair.
            3. Keep the highest weighted score, all reasons/operators, and the strongest duplicate_type.

        Args:
            items (list[dict[str, Any]]): Text sample list.
            context (dict[str, Any]): Shared workflow context containing duplicate_edges.

        Returns:
            list[dict[str, Any]]: Original sample list.

        Examples:
            >>> context = {"duplicate_edges": [{"left_id": "a", "right_id": "b", "score": 1.0, "reason": "exact_text_hash"}]}
            >>> TextDupFusionOperator({}).process_dataset([], context)
            []
        """
        weights = self.config.get(
            "weights",
            {
                "exact": 1.0,
                "simhash": 0.85,
                "minhash": 0.8,
                "embedding": 0.9,
                "rerank": 0.95,
            },
        )
        fused = {}
        for edge in context.get("duplicate_edges", []):  # Aggregate candidate edges one by one by undirected pair.
            key = tuple(sorted([str(edge["left_id"]), str(edge["right_id"])]))
            reasons = edge.get("reasons", [edge.get("reason", "unknown")])
            weighted_score = float(edge.get("score", 0)) * reason_weight(reasons, weights)
            if key not in fused:  # Create the fused edge immediately when the pair appears for the first time.
                fused[key] = {
                    "left_id": key[0],
                    "right_id": key[1],
                    "score": weighted_score,
                    "duplicate_type": edge.get("duplicate_type", "near_duplicate"),
                    "reasons": list(reasons),
                    "operators": edge.get("operators", [edge.get("operator", self.operator_name)]),
                }
                continue
            fused_edge = fused[key]
            fused_edge["score"] = max(float(fused_edge["score"]), weighted_score)
            for reason in reasons:  # Preserve every deduplication evidence source for the same pair.
                if reason not in fused_edge["reasons"]:  # Do not append reasons that are already present.
                    fused_edge["reasons"].append(reason)
            if edge.get("duplicate_type") == "exact_duplicate":  # Exact duplicates are stronger than semantic or near duplicates.
                fused_edge["duplicate_type"] = "exact_duplicate"
            elif edge.get("duplicate_type") == "semantic_duplicate" and fused_edge["duplicate_type"] != "exact_duplicate":
                fused_edge["duplicate_type"] = "semantic_duplicate"
        context["duplicate_edges"] = list(fused.values())
        return items

def reason_weight(reasons: list[str], weights: dict[str, float]) -> float:
    """Choose a fusion weight from duplicate reasons.

    Business logic:
        1. Map reason keywords to configured weight keys.
        2. Traverse all reasons and find matching sources.
        3. Return the highest matched weight, defaulting to 1.0.

    Args:
        reasons (list[str]): Reason list carried by the duplicate candidate edge.
        weights (dict[str, float]): Fusion-weight config for each source.

    Returns:
        float: Highest weight applied to this candidate edge.

    Examples:
        >>> reason_weight(["simhash_hamming<=3"], {"simhash": 0.8})
        1.0
    """
    mapping = [
        ("exact", "exact"),
        ("simhash", "simhash"),
        ("minhash", "minhash"),
        ("embedding", "embedding"),
        ("rerank", "rerank"),
    ]
    score = 1.0
    for reason in reasons:  # Each reason may correspond to one fusion-weight source.
        lower = reason.lower()
        for keyword, key in mapping:  # Identify sources such as exact, simhash, and embedding via keywords.
            if keyword in lower:  # Use the configured weight after a source match is found.
                score = max(score, float(weights.get(key, 1.0)))
    return score
