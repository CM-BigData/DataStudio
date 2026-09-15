from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from synthesis_engine.accessors import LLMAccessor
from synthesis_engine.llm import LLMClientError
from synthesis_engine.mappers import BaseMapper, MapperInput, MapperResult


class MultimodalSynthesisMapper(BaseMapper):
    mapper_name = "multimodal_synthesis"
    mapper_version = "1.1.0"

    def __init__(self, config: dict[str, Any] | None = None, llm_accessor: Any | None = None) -> None:
        """Initialize the multimodal synthesis mapper

        Business logic:
            1. Store mapper configuration through BaseMapper
            2. Inject or create an LLM accessor for real multimodal requests
            3. Keep model-call settings reusable across map calls

        Args:
            config (dict[str, Any] | None): Mapper configuration.
            llm_accessor (Any | None): Injectable LLM accessor.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> MultimodalSynthesisMapper({}, llm_accessor=object()).mapper_name
            'multimodal_synthesis'
        """
        super().__init__(config)
        self.llm_accessor = llm_accessor or LLMAccessor(model_config=dict(self.config.get("model_config", {})))  # Real multimodal accessor used for image+text synthesis calls.

    def map(self, input: MapperInput) -> MapperResult:
        """Generate multimodal instruction-response items from text and image inputs

        Business logic:
            1. Read text and image inputs and verify that image files exist
            2. Run the image-understanding, instruction-extraction, and response-generation stages
            3. Persist structured items, stage metrics, issues, and lineage for workflow retry and tracing

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: Structured multimodal synthesis result.

        Examples:
            >>> MultimodalSynthesisMapper({}, llm_accessor=object()).mapper_version
            '1.0.0'
        """
        source_text = str(input.payload.get("text", input.content or "")).strip()
        image_paths = _collect_image_paths(input.payload)
        if not source_text:
            return MapperResult(
                items=[],
                metrics={"image_count": len(image_paths), "multimodal_item_count": 0},
                issues=[{"type": "empty_input", "message": "Multimodal text input is empty"}],
                lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version},
                failed=True,
            )
        if not image_paths:
            return MapperResult(
                items=[],
                metrics={"image_count": 0, "multimodal_item_count": 0},
                issues=[{"type": "image_missing", "message": "No image_path or image_paths were provided"}],
                lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version},
                failed=True,
            )

        try:
            image_parts = [_image_part(path) for path in image_paths]
        except FileNotFoundError as exc:
            return MapperResult(
                items=[],
                metrics={"image_count": len(image_paths), "multimodal_item_count": 0},
                issues=[{"type": "image_missing", "message": str(exc)}],
                lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version},
                failed=True,
            )

        stage_history: list[dict[str, Any]] = []

        image_understanding = self._run_stage(
            stage_name="image_understanding",
            messages=[{"role": "user", "content": [{"type": "text", "text": _build_image_understanding_prompt(source_text)}, *image_parts]}],
            stage_history=stage_history,
            image_count=len(image_paths),
        )
        if image_understanding["failed"]:
            return image_understanding["result"]

        instruction_extraction = self._run_stage(
            stage_name="instruction_extraction",
            messages=[
                {
                    "role": "user",
                    "content": _build_instruction_extraction_prompt(
                        source_text=source_text,
                        image_summary=image_understanding["content"],
                    ),
                }
            ],
            stage_history=stage_history,
            image_count=len(image_paths),
        )
        if instruction_extraction["failed"]:
            return instruction_extraction["result"]

        extracted_payload = _parse_instruction_payload(instruction_extraction["content"])
        if extracted_payload is None:
            return _failed_result(
                mapper_name=self.mapper_name,
                mapper_version=self.mapper_version,
                image_count=len(image_paths),
                stage_history=stage_history,
                issue_type="invalid_mapper_output",
                message="Instruction extraction stage did not return valid instruction/input JSON",
                response_meta=instruction_extraction["response_meta"],
            )

        response_generation = self._run_stage(
            stage_name="response_generation",
            messages=[
                {
                    "role": "user",
                    "content": _build_response_generation_prompt(
                        instruction=extracted_payload["instruction"],
                        input_text=extracted_payload["input"],
                        image_summary=image_understanding["content"],
                        source_text=source_text,
                    ),
                }
            ],
            stage_history=stage_history,
            image_count=len(image_paths),
        )
        if response_generation["failed"]:
            return response_generation["result"]

        output_text = response_generation["content"].strip()
        if not output_text:
            return _failed_result(
                mapper_name=self.mapper_name,
                mapper_version=self.mapper_version,
                image_count=len(image_paths),
                stage_history=stage_history,
                issue_type="invalid_mapper_output",
                message="Response generation stage returned empty output",
                response_meta=response_generation["response_meta"],
            )

        item = {
            "instruction": extracted_payload["instruction"],
            "input": extracted_payload["input"],
            "output": output_text,
            "image_refs": image_paths,
            "stage_history": stage_history,
        }
        response_meta = response_generation["response_meta"]
        return MapperResult(
            items=[item],
            metrics={
                "image_count": len(image_paths),
                "multimodal_item_count": 1,
                "output_length": len(output_text),
                "multimodal_stage_count": len(stage_history),
            },
            issues=[],
            lineage={
                "mapper": self.mapper_name,
                "mapper_version": self.mapper_version,
                "model": response_meta.get("model", ""),
                "provider": response_meta.get("provider", ""),
                "stage_history": stage_history,
            },
            failed=False,
        )

    def _run_stage(
        self,
        stage_name: str,
        messages: list[dict[str, Any]],
        stage_history: list[dict[str, Any]],
        image_count: int,
    ) -> dict[str, Any]:
        """Run one multimodal synthesis stage and capture its trace."""
        try:
            response = self.llm_accessor.complete(messages, self._stage_call_options(stage_name))
        except LLMClientError as exc:
            return {
                "failed": True,
                "result": _failed_result(
                    mapper_name=self.mapper_name,
                    mapper_version=self.mapper_version,
                    image_count=image_count,
                    stage_history=stage_history,
                    issue_type="llm_call_failed",
                    message=f"{stage_name} stage failed: {exc}",
                ),
            }

        content = response.content.strip()
        response_meta = {"model": response.model, "provider": response.provider}
        stage_history.append(
            {
                "stage": stage_name,
                "content_preview": _preview_text(content),
                "content_length": len(content),
                "model": response.model,
                "provider": response.provider,
            }
        )
        if not content:
            return {
                "failed": True,
                "result": _failed_result(
                    mapper_name=self.mapper_name,
                    mapper_version=self.mapper_version,
                    image_count=image_count,
                    stage_history=stage_history,
                    issue_type="invalid_mapper_output",
                    message=f"{stage_name} stage returned empty output",
                    response_meta=response_meta,
                ),
            }
        return {"failed": False, "content": content, "response_meta": response_meta}

    def _stage_call_options(self, stage_name: str) -> dict[str, Any]:
        """Resolve stage-specific call options over the shared defaults."""
        options = dict(self.config.get("call_options", {}))
        stage_options = self.config.get("stage_call_options", {})
        if isinstance(stage_options, dict) and isinstance(stage_options.get(stage_name), dict):
            options.update(stage_options[stage_name])
        return options


def _collect_image_paths(payload: dict[str, Any]) -> list[str]:
    """Collect image paths from payload."""
    if isinstance(payload.get("image_paths"), list):  # Prefer explicit multi-image input when present.
        return [str(path) for path in payload["image_paths"] if str(path).strip()]
    if payload.get("image_path"):  # Fall back to the single-image field.
        return [str(payload["image_path"])]
    return []


def _image_part(path_str: str) -> dict[str, Any]:
    """Convert a local image path into an OpenAI-compatible image_url part."""
    path = Path(path_str).expanduser()
    if not path.exists():  # Real multimodal calls require an existing local image file.
        raise FileNotFoundError(f"Image file not found: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data_url = "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": data_url}}


def _build_image_understanding_prompt(source_text: str) -> str:
    """Build the first-stage prompt that grounds image understanding."""
    return (
        "Describe the image in a way that supports downstream instruction-data synthesis. "
        "Cover the main subject, scene, attributes, counts, relations, text in the image, and any useful constraints. "
        "Return only plain text.\n"
        f"Request: {source_text}"
    )


def _build_instruction_extraction_prompt(source_text: str, image_summary: str) -> str:
    """Build the second-stage prompt that extracts instruction and input fields."""
    return (
        "You are converting multimodal source material into one instruction-tuning sample. "
        "Use the request and image summary below to produce one JSON object with string fields "
        '"instruction", "input", and "output_seed". '
        "The instruction must be answerable from the image summary. "
        "The input may be empty. The output_seed should describe the expected answer focus, not the full final answer. "
        "Return valid JSON only.\n"
        f"Request: {source_text}\n"
        f"Image summary: {image_summary}"
    )


def _build_response_generation_prompt(instruction: str, input_text: str, image_summary: str, source_text: str) -> str:
    """Build the third-stage prompt that generates the final response."""
    rendered_input = input_text or "(empty)"
    return (
        "Generate the final output field for one multimodal instruction-tuning sample. "
        "Use the instruction, input, original request, and image summary consistently. "
        "Return only the final answer text.\n"
        f"Original request: {source_text}\n"
        f"Instruction: {instruction}\n"
        f"Input: {rendered_input}\n"
        f"Image summary: {image_summary}"
    )


def _parse_instruction_payload(text: str) -> dict[str, str] | None:
    """Parse the instruction-extraction stage JSON payload."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    instruction = str(data.get("instruction", "")).strip()
    input_text = str(data.get("input", "")).strip()
    if not instruction:
        return None
    return {"instruction": instruction, "input": input_text}


def _failed_result(
    mapper_name: str,
    mapper_version: str,
    image_count: int,
    stage_history: list[dict[str, Any]],
    issue_type: str,
    message: str,
    response_meta: dict[str, str] | None = None,
) -> MapperResult:
    """Build a failed mapper result with consistent trace payload."""
    lineage = {
        "mapper": mapper_name,
        "mapper_version": mapper_version,
        "stage_history": stage_history,
    }
    if response_meta:
        lineage.update(response_meta)
    return MapperResult(
        items=[],
        metrics={
            "image_count": image_count,
            "multimodal_item_count": 0,
            "multimodal_stage_count": len(stage_history),
        },
        issues=[{"type": issue_type, "message": message}],
        lineage=lineage,
        failed=True,
    )


def _preview_text(text: str, limit: int = 120) -> str:
    """Create a short preview for stage-history tracing."""
    return text if len(text) <= limit else text[: limit - 3] + "..."
