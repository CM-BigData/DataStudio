from __future__ import annotations
from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator


class ModalityRouterOperator(BaseOperator):
    operator_name: str = "modality_router"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Route a single sample to its inferred modality.

        Business logic:
            1. Read the sample payload and any pre-declared modality.
            2. Infer the effective modality from payload fields when needed.
            3. Write the selected modality and module metadata back to the sample.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        payload = item.get("payload", {})
        provided = str(item.get("modality", "") or "").strip()
        inferred = self._infer(payload)
        modality = provided if provided and provided != "unknown" else inferred
        item["modality"] = modality or "unknown"
        selected_module = self._module_name(item["modality"])
        item.setdefault("meta", {})["selected_module"] = selected_module
        self.set_metric(item, "selected_modality", item["modality"])
        self.set_metric(item, "selected_module", selected_module)
        if item["modality"] == "unknown":  # Record an issue when the payload still cannot determine modality.
            self.add_issue(item, "unknown_modality")
        return item

    def _infer(self, payload: dict) -> str:
        """Infer sample modality from payload fields.

        Business logic:
            1. Check whether the payload contains text, image, or video fields.
            2. Resolve modality by the priority order video, image-text pair, image, then text.
            3. Return `unknown` when no recognizable field is present.

        Args:
                payload (dict): Sample payload.

        Returns:
            str: Inferred modality name.

        Examples:
            >>> _infer
            _infer
        """
        has_text = bool(str(payload.get("text", "") or "").strip())
        has_image = bool(str(payload.get("image_path", "") or "").strip())
        has_video = bool(str(payload.get("video_path", "") or "").strip())
        if has_video:  # Route video payloads to the video operator chain.
            return "video"
        if has_text and has_image:  # Route paired text and image payloads to the multimodal chain.
            return "image_text_pair"
        if has_image:  # Route image-only payloads to the image operator chain.
            return "image"
        if has_text or payload.get("raw_bytes") is not None:  # Route text or raw-byte payloads to the text operator chain.
            return "text"
        return "unknown"

    def _module_name(self, modality: str) -> str:
        """Convert a modality name into the workflow module label.

        Business logic:
            1. Read the resolved modality string.
            2. Map it to the module label used in workflow reporting.
            3. Fall back to `unknown` for unsupported modalities.

        Args:
                modality (str): Sample modality.

        Returns:
            str: Workflow module label.

        Examples:
            >>> _module_name
            _module_name
        """
        return {
            "text": "text_denoise",
            "image": "image_denoise",
            "image_text_pair": "image_text_pair_denoise",
            "video": "video_denoise",
        }.get(modality, "unknown")
