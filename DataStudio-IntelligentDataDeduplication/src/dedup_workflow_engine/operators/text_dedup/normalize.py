from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403
from dedup_workflow_engine.utilities.text.normalize import normalize_text

class TextNormalizeForDedupOperator(BaseOperator):
    operator_name = "text_normalize_for_dedup"  # Workflow config: operator name for text normalization inside the text-dedup workflow.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize text samples and write intermediate results.

        Business logic:
            1. Read raw text from payload.text.
            2. Apply case, HTML, whitespace, and punctuation normalization according to config.
            3. Mark empty normalized samples as review, and pass non-empty samples to later dedup operators.

        Args:
            items (list[dict[str, Any]]): Text sample list.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with normalized_text and normalized_length.

        Examples:
            >>> TextNormalizeForDedupOperator({}).process_dataset([{"payload": {"text": "Hello"}}], {})[0]["intermediate"]["normalized_text"]
            'hello'
        """
        for item in items:  # Every text sample must produce normalized_text for downstream shared use.
            text = str(item.get("payload", {}).get("text", ""))
            normalized = normalize_text(
                text,
                lowercase=bool(self.config.get("lowercase", True)),
                remove_html=bool(self.config.get("remove_html", True)),
                normalize_space=bool(self.config.get("normalize_space", True)),
                normalize_punctuation=bool(self.config.get("normalize_punctuation", True)),
            )
            self.set_intermediate(item, "normalized_text", normalized)
            self.set_metric(item, "normalized_length", len(normalized))
            if not normalized:  # Samples that normalize to empty text cannot participate in text-similarity computation.
                self.add_issue(item, "empty_text_after_normalize")
                item["action"] = "review"
        return items
