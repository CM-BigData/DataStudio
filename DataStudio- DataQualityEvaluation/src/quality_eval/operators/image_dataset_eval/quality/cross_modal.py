from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_eval.utilities.image.shared import *  # noqa: F403


class ImageTextConsistencyEvalOperator(BaseOperator):
    operator_name: str = "image_text_consistency_eval"  # Registered operator name used to evaluate text-image consistency with ChineseCLIP.

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the text-image consistency operator.

        Business logic:
            1. Read the model name and threshold from workflow rules.
            2. Prepare a lazy model state so validation does not require model downloads.
            3. Defer actual model loading until the first real sample needs inference.

        Args:
            config (dict[str, Any]): Workflow-injected operator config.

        Returns:
            None: Stores configuration and lazy model state on the instance.

        Examples:
            >>> ImageTextConsistencyEvalOperator({"rules": {}}).operator_name
            'image_text_consistency_eval'
        """
        super().__init__(config)
        self.threshold = float(self.rules.get("image_text_consistency_threshold", 0.24))
        self.model_name = str(self.rules.get("image_text_consistency_model_name", "OFA-Sys/chinese-clip-vit-huge-patch14"))
        revision_value = self.rules.get("image_text_consistency_model_revision")
        self.model_revision = str(revision_value).strip() if revision_value else None
        self._model = None
        self._processor = None
        self._device = None

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Evaluate whether one text-image pair is semantically consistent.

        Business logic:
            1. Read `payload.text` and `payload.image_path` and return empty metrics when either is missing.
            2. Load the ChineseCLIP model lazily on the first real sample.
            3. Compute the normalized cosine similarity between text and image embeddings.
            4. Append `image_text_inconsistent` when the similarity is below the threshold.

        Args:
            item (dict[str, Any]): Image sample that may also carry `payload.text`.

        Returns:
            dict[str, Any]: Sample updated with consistency metrics and issues.

        Examples:
            >>> sample = {"payload": {}, "metrics": {}, "issues": []}
            >>> ImageTextConsistencyEvalOperator({"rules": {}}).process(sample)["metrics"]["image_text_consistency_score"] is None
            True
        """
        payload = item.get("payload", {})
        text = str(payload.get("text", "")).strip()
        image_path = str(payload.get("image_path", "")).strip()

        if not text:
            self.metric(item, "image_text_consistency_score", None)
            self.metric(item, "image_text_consistency_ok", False)
            self.metric(item, "image_text_consistency_reason", "missing_text")
            return item

        if not image_path:
            self.metric(item, "image_text_consistency_score", None)
            self.metric(item, "image_text_consistency_ok", False)
            self.metric(item, "image_text_consistency_reason", "missing_image_path")
            return item

        path = Path(image_path)
        if not path.exists():
            self.metric(item, "image_text_consistency_score", None)
            self.metric(item, "image_text_consistency_ok", False)
            self.metric(item, "image_text_consistency_reason", "image_not_found")
            return item

        try:
            model, processor, device = self._load_model()
            with Image.open(path) as image:
                inputs = processor(text=[text], images=image.convert("RGB"), return_tensors="pt", padding=True)
            inputs = {key: value.to(device) for key, value in inputs.items()}

            import torch

            with torch.no_grad():
                outputs = model(**inputs)

            image_embeddings = outputs.image_embeds
            text_embeddings = outputs.text_embeds
            image_embeddings = image_embeddings / image_embeddings.norm(p=2, dim=-1, keepdim=True)
            text_embeddings = text_embeddings / text_embeddings.norm(p=2, dim=-1, keepdim=True)
            similarity = float((image_embeddings * text_embeddings).sum(dim=-1).cpu().item())
            score = round(max(0.0, min(1.0, similarity)), 6)
            consistent = score >= self.threshold

            self.metric(item, "image_text_consistency_score", score)
            self.metric(item, "image_text_consistency_ok", consistent)
            self.metric(item, "image_text_consistency_reason", f"similarity={score:.6f},threshold={self.threshold:.6f}")
            if not consistent:  # Low CLIP similarity means the text-image pair is likely semantically inconsistent.
                self.add_issue(item, "image_text_inconsistent")
            return item
        except Exception as exc:
            self.metric(item, "image_text_consistency_score", None)
            self.metric(item, "image_text_consistency_ok", False)
            self.metric(item, "image_text_consistency_reason", f"consistency_check_failed:{exc}")
            return item

    def _load_model(self) -> tuple[Any, Any, Any]:
        """Load the ChineseCLIP model lazily.

        Business logic:
            1. Return the cached model when it is already loaded.
            2. Import torch and transformers only when real inference is needed.
            3. Load the processor and model, then place the model onto the best available device.

        Args:
            None.

        Returns:
            tuple[Any, Any, Any]: Model, processor, and torch device.

        Examples:
            >>> callable(ImageTextConsistencyEvalOperator._load_model)
            True
        """
        if self._model is not None and self._processor is not None and self._device is not None:
            return self._model, self._processor, self._device

        if not Path(self.model_name).expanduser().exists() and self.model_revision is None:
            raise RuntimeError("remote image-text consistency models require an immutable model revision")
        import torch
        from transformers import AutoModel, AutoProcessor

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        processor = AutoProcessor.from_pretrained(
            self.model_name,
            revision=self.model_revision,
            trust_remote_code=False,
        )
        model = AutoModel.from_pretrained(
            self.model_name,
            revision=self.model_revision,
            trust_remote_code=False,
        )
        model.to(device)
        model.eval()

        self._model = model
        self._processor = processor
        self._device = device
        return self._model, self._processor, self._device
