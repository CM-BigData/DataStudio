from __future__ import annotations

from pathlib import Path

from PIL import Image

from synthesis_engine.llm import ImageGenerationConfig, LLMClientError, OpenAIImageClient
from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator



class ImageCardSynthesisOperator(BaseOperator):
    operator_name = "image_card_synthesis"  # Registry name for the local image-card synthesis workflow entry.

    def __init__(self, config: dict | None = None) -> None:
        """Initialize the image model synthesis operator

        Business logic:
            1. Store operator configuration through the base class
            2. Accept an injectable image client for tests
            3. Keep the public operator name stable for existing workflows

        Args:
            config (dict | None): Operator configuration.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> ImageCardSynthesisOperator().operator_name
            'image_card_synthesis'
        """
        super().__init__(config)
        self.image_client = self.config.get("image_client")  # Optional test or platform-injected image-generation client.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Generate an image with a text-to-image model

        Business logic:
            1. Skip non-image task samples
            2. Call the configured text-to-image model with prompt and negative prompt
            3. Save the generated image bytes and record model lineage

        Args:
            item (GenerationItem): Sample to process.

        Returns:
            GenerationItem: Sample updated with image-generation results.

        Examples:
            >>> ImageCardSynthesisOperator().operator_name
            'image_card_synthesis'
        """
        if item.task_type != "image":  # Image operators only handle image tasks and leave others unchanged.
            return item

        output_dir = Path(self.config.get("output_dir", "generated_images"))
        if not output_dir.is_absolute():  # Resolve relative output directories from the current working directory for local command-line runs.
            output_dir = Path.cwd() / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        prompt = _build_image_prompt(item, self.config)
        negative_prompt = str(item.generated.get("negative_prompt", self.config.get("negative_prompt", ""))).strip()
        call_options = dict(self.config.get("call_options", {}))
        if negative_prompt:  # Many image providers accept negative_prompt as a provider-specific option.
            call_options.setdefault("negative_prompt", negative_prompt)

        try:
            response = self._build_image_client().generate(prompt, call_options)
        except LLMClientError as exc:
            item.action = str(self.config.get("failed_action", "needs_retry"))
            item.issues.append({"type": "image_generation_failed", "message": str(exc)})
            item.lineage["generator"] = self.operator_name
            return item

        filename = f"{_slug(item.id)}.png"
        image_path = output_dir / filename
        image_path.write_bytes(response.image_bytes)

        with Image.open(image_path) as image:
            width, height = image.size

        item.generated["image_path"] = str(image_path)
        item.generated["format"] = "png"
        item.generated["image_prompt"] = prompt
        if response.revised_prompt:  # Preserve provider prompt revisions for auditability.
            item.generated["revised_prompt"] = response.revised_prompt
        if negative_prompt:  # Preserve upstream negative prompts for trace inspection.
            item.generated["negative_prompt"] = negative_prompt
        item.metrics["width"] = width
        item.metrics["height"] = height
        item.metrics["image_generation_latency_ms"] = response.latency_ms
        item.lineage["generator"] = self.operator_name
        item.lineage["model"] = response.model
        item.lineage["provider"] = response.provider
        if response.request_id:  # Keep provider request id when available for support tracing.
            item.lineage["request_id"] = response.request_id
        return item

    def _build_image_client(self) -> OpenAIImageClient:
        """Build the image-generation client

        Business logic:
            1. Prefer an injected image client from config
            2. Build an OpenAIImageClient from model_config otherwise
            3. Return a client with a generate method

        Args:
            None.

        Returns:
            OpenAIImageClient: Image-generation client.

        Examples:
            >>> hasattr(ImageCardSynthesisOperator({'image_client': object()})._build_image_client(), '__class__')
            True
        """
        if self.image_client is not None and hasattr(self.image_client, "generate"):  # Tests and platform adapters can inject a fake or custom client.
            return self.image_client
        return OpenAIImageClient(ImageGenerationConfig.from_dict(dict(self.config.get("model_config", {}))))


def _build_image_prompt(item: GenerationItem, config: dict) -> str:
    """Build the text-to-image prompt

    Business logic:
        1. Prefer explicit prompt_template when configured
        2. Otherwise combine prompt, title, and subtitle into one model prompt
        3. Return normalized non-empty prompt text

    Args:
        item (GenerationItem): Image synthesis sample.
        config (dict): Operator configuration.

    Returns:
        str: Prompt sent to the image model.

    Examples:
        >>> _build_image_prompt(GenerationItem('a', 'image', 'draw a card'), {})
        'draw a card'
    """
    template = str(config.get("prompt_template", "")).strip()
    title = str(item.payload.get("title", "")).strip()
    subtitle = str(item.payload.get("subtitle", "")).strip()
    prompt = str(item.prompt or item.payload.get("prompt", "")).strip()
    if template:  # Allow workflow authors to control exact prompt wording for a target image model.
        variables = {**item.payload, "prompt": prompt, "title": title, "subtitle": subtitle}
        return template.format(**variables).strip()
    parts = [part for part in [prompt, title, subtitle] if part]
    return "\n".join(parts).strip()


def _slug(value: str) -> str:
    """Build a filesystem-safe filename fragment

    Business logic:
        1. Replace non-filename-safe characters with underscores
        2. Strip leading and trailing underscores
        3. Fall back to image when the result is empty

    Args:
        value (str): Raw identifier text.

    Returns:
        str: Filename-safe fragment.

    Examples:
        >>> _slug('a b')
        'a_b'
    """
    safe = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)
    return safe.strip("_") or "image"
