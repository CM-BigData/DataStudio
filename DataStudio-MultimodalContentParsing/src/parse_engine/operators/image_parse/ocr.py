from __future__ import annotations

from pathlib import Path

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class RapidOcrOperator(BaseOperator):
    operator_name = "rapid_ocr"  # Operator name: registry name for the RapidOCR image text recognition step.
    _engine = None  # OCR engine: cached RapidOCR instance reused across samples.

    def setup(self) -> None:
        """Initialize the shared RapidOCR engine.

        Business logic:
            1. Check whether the class-level OCR engine has already been created.
            2. On first use, import rapidocr_onnxruntime and construct RapidOCR.
            3. Cache the engine in a class variable to avoid reloading the model for each sample.

        Args:
            None.

        Returns:
            None: The OCR engine is stored in the class-level cache.

        Examples:
            >>> RapidOcrOperator({}).operator_name
            'rapid_ocr'"""
        if RapidOcrOperator._engine is None:  # First use: lazy-load the OCR engine and reuse the model instance.
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise RuntimeError("rapidocr-onnxruntime is required for OCR") from exc
            RapidOcrOperator._engine = RapidOCR()

    def process(self, item: DataItem) -> DataItem:
        """Run OCR on an image and generate text-line artifacts.

        Business logic:
            1. Pass non-image samples through unchanged.
            2. Use the shared RapidOCR engine to recognize text lines in the image.
            3. Filter results by the confidence threshold, generate ocr_text artifacts, and record text metrics.

        Args:
            item: Image or non-image data item in the current workflow.

        Returns:
            DataItem: Data item with OCR text artifacts and metrics appended.

        Examples:
            >>> RapidOcrOperator({"min_confidence": 0.3}).config["min_confidence"]
            0.3"""
        if item.modality != "image":  # Cross-modality guard: the OCR operator only handles image samples.
            return item

        path = Path(item.payload["path"])
        result, _ = RapidOcrOperator._engine(str(path))
        result = result or []
        min_confidence = float(self.config.get("min_confidence", 0.3))
        accepted = 0
        text_length = 0
        for index, entry in enumerate(result, start=1):  # OCR line iteration: preserve the original recognition order.
            bbox, text, confidence = entry
            if float(confidence) < min_confidence:  # Low-confidence filter: keep noisy text out of parsing artifacts.
                continue
            accepted += 1
            text_length += len(text)
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_ocr_{accepted}",
                    type="ocr_text",
                    text=text,
                    data={"confidence": round(float(confidence), 4), "line_index": index},
                    source_trace=SourceTrace(
                        file=str(path),
                        bbox=_flatten_bbox(bbox),
                        operator=self.operator_name,
                    ),
                )
            )

        item.metrics["ocr_lines"] = accepted
        item.metrics["ocr_text_length"] = text_length
        if accepted == 0:  # No trusted text: record an empty OCR result for quality reporting.
            item.issues.append({"type": "ocr_empty", "message": "OCR produced no text above threshold"})
        item.action = "parsed"
        return item

def _flatten_bbox(bbox: object) -> list[float] | None:
    """Flatten an OCR four-point box into rectangle coordinates.

    Business logic:
        1. Read all x and y coordinates from the point collection returned by OCR.
        2. Compute the left, top, right, and bottom of the minimum bounding rectangle.
        3. Return None when the coordinate structure cannot be parsed so the entire image process is not interrupted.

    Args:
        bbox: Multi-point coordinate collection returned by the OCR engine.

    Returns:
        list[float] | None: Four-element rectangle coordinates, or None if parsing fails.

    Examples:
        >>> _flatten_bbox([[0, 1], [2, 1], [2, 3], [0, 3]])
        [0.0, 1.0, 2.0, 3.0]"""
    try:
        xs = [float(point[0]) for point in bbox]
        ys = [float(point[1]) for point in bbox]
        return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]
    except Exception:
        return None
