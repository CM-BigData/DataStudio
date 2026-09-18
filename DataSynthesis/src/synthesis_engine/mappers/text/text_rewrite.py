from __future__ import annotations

from typing import Any

from synthesis_engine.accessors import LLMAccessor
from synthesis_engine.llm import LLMClientError
from synthesis_engine.mappers import BaseMapper, MapperInput, MapperResult
from synthesis_engine.prompts import PromptTemplateStore


class TextRewriteMapper(BaseMapper):
    mapper_name = "text_rewrite"  # Mapper name identifying the text rewriting enhancement capability.
    mapper_version = "1.1.0"  # Mapper version used for lineage auditing.

    def __init__(self, config: dict[str, Any] | None = None, llm_accessor: Any | None = None) -> None:
        """Initialize the text rewrite mapper

        Business logic:
            1. Store mapper configuration
            2. Inject or create an LLMAccessor
            3. Prepare follow-up rewrite calls

        Args:
            config (dict[str, Any] | None): Mapper configuration.
            llm_accessor (Any | None): LLM accessor.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> TextRewriteMapper().mapper_name
            'text_rewrite'
        """
        super().__init__(config)
        self.llm_accessor = llm_accessor or LLMAccessor(model_config=dict(self.config.get("model_config", {})))  # LLM accessor used to invoke the rewrite model.
        self.prompt_store = PromptTemplateStore(self.config.get("prompt_dir"))  # Prompt store used to render rewrite messages from template files.

    def map(self, input: MapperInput) -> MapperResult:
        """Rewrite input text

        Business logic:
            1. Validate the input text
            2. Build the rewrite prompt and call the LLM
            3. Enforce minimal rewrite quality gates before returning success

        Args:
            input (MapperInput): Mapper input.

        Returns:
            MapperResult: Rewrite result.

        Examples:
            >>> TextRewriteMapper({'llm_accessor': None}).mapper_name
            'text_rewrite'
        """
        text = input.content.strip()
        if not text:  # Empty text cannot be rewritten.
            return MapperResult(items=[], issues=[{"type": "empty_input", "message": "Input text is empty"}], lineage={"mapper": self.mapper_name}, failed=True)
        messages = self.prompt_store.render(
            str(self.config.get("prompt_template", "text_rewrite")),
            _build_rewrite_prompt_variables(text, str(self.config.get("language", "zh"))),
        )
        try:
            response = self.llm_accessor.complete(messages, dict(self.config.get("call_options", {})))
        except LLMClientError as exc:
            return MapperResult(
                items=[],
                issues=[{"type": "llm_call_failed", "message": str(exc)}],
                lineage={"mapper": self.mapper_name},
                failed=True,
            )
        rewritten = response.content.strip()
        if not rewritten:  # Treat empty model output as unusable.
            return MapperResult(
                items=[],
                issues=[{"type": "invalid_mapper_output", "message": "Rewrite result is empty"}],
                lineage={"mapper": self.mapper_name, "model": response.model},
                failed=True,
            )
        min_output_length = max(1, int(self.config.get("min_output_length", 8)))
        if len(rewritten) < min_output_length:
            return MapperResult(
                items=[],
                issues=[{"type": "rewrite_too_short", "message": f"Rewrite result is shorter than {min_output_length} characters"}],
                lineage={"mapper": self.mapper_name, "model": response.model},
                failed=True,
            )
        if rewritten == text:
            return MapperResult(
                items=[],
                issues=[{"type": "rewrite_unchanged", "message": "Rewrite result is identical to the original text"}],
                lineage={"mapper": self.mapper_name, "model": response.model},
                failed=True,
            )
        return MapperResult(
            items=[{"text": rewritten}],
            metrics={
                "rewrite_changed": True,
                "source_length": len(text),
                "rewritten_length": len(rewritten),
            },
            issues=[],
            lineage={"mapper": self.mapper_name, "mapper_version": self.mapper_version, "model": response.model, "provider": response.provider},
            failed=False,
        )


def _build_rewrite_prompt_variables(text: str, language: str) -> dict[str, str]:
    """Build template variables for text rewriting

    Business logic:
        1. Preserve the original text as a template variable
        2. Forward the language for optional template branching
        3. Keep the mapper prompt contract explicit and serializable

    Args:
        text (str): Original text.
        language (str): Language identifier.

    Returns:
        dict[str, str]: Prompt variables.

    Examples:
        >>> _build_rewrite_prompt_variables('abc', 'en')["text"]
        'abc'
    """
    return {"text": text, "language": language}
