from pathlib import Path

from synthesis_engine.llm import ImageGenerationResponse
from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.image_synthesis import ImageCardSynthesisOperator, ImageQualityValidateOperator


class FakeImageClient:
    def generate(self, prompt: str, options: dict | None = None) -> ImageGenerationResponse:
        """Return a deterministic generated image response

        Business logic:
            1. Accept the prompt and provider options
            2. Create a small deterministic PNG fixture
            3. Return normalized image-generation metadata

        Args:
            prompt (str): Image prompt.
            options (dict | None): Provider options.

        Returns:
            ImageGenerationResponse: Fake model image response.

        Examples:
            >>> hasattr(FakeImageClient(), 'generate')
            True
        """
        image_path = Path(__file__).resolve().parent / "fixtures" / "multimodal_images" / "example.jpg"
        return ImageGenerationResponse(
            image_bytes=image_path.read_bytes(),
            model="fake-image-model",
            provider="fake",
            request_id="fake-image-request",
            revised_prompt=f"{prompt} revised",
            latency_ms=3,
        )


def test_image_card_synthesis_operator_calls_text_to_image_model(tmp_path: Path) -> None:
    """Verify image model generation and quality validation

    Business logic:
        1. Build an image-task sample
        2. Generate an image through the injected text-to-image client
        3. Assert that the saved image and model lineage are recorded

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses test results through assertions.

    Examples:
        >>> callable(test_image_card_synthesis_operator_calls_text_to_image_model)
        True
    """
    item = GenerationItem(
        id="image_test",
        task_type="image",
        prompt="Generate a validation image",
        payload={"title": "Image Test", "subtitle": "local generation"},
    )
    item.generated["negative_prompt"] = "watermark"
    item = ImageCardSynthesisOperator({"output_dir": str(tmp_path), "image_client": FakeImageClient()}).process(item)
    item = ImageQualityValidateOperator({"min_width": 128, "min_height": 128}).process(item)

    assert Path(item.generated["image_path"]).exists()
    assert item.generated["image_prompt"] == "Generate a validation image\nImage Test\nlocal generation"
    assert item.generated["negative_prompt"] == "watermark"
    assert item.generated["revised_prompt"].endswith("revised")
    assert item.lineage["model"] == "fake-image-model"
    assert item.lineage["provider"] == "fake"
    assert item.lineage["request_id"] == "fake-image-request"
    assert not item.issues


def test_image_card_synthesis_operator_records_model_failure(tmp_path: Path) -> None:
    """Verify image model failures are converted into workflow issues

    Business logic:
        1. Build an image-task sample with missing model configuration
        2. Run the image synthesis operator
        3. Assert that the sample is marked for retry instead of raising

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses test results through assertions.

    Examples:
        >>> callable(test_image_card_synthesis_operator_records_model_failure)
        True
    """
    item = GenerationItem(id="image_error", task_type="image", prompt="Generate an image")
    item = ImageCardSynthesisOperator({"output_dir": str(tmp_path)}).process(item)

    assert item.action == "needs_retry"
    assert item.issues[0]["type"] == "image_generation_failed"


def test_image_card_synthesis_operator_renders_prompt_template_with_payload_fields(tmp_path: Path) -> None:
    """Verify prompt templates render payload fields without duplicate keyword failures

    Business logic:
        1. Build an image sample whose payload includes title and subtitle
        2. Render a configured prompt template through the image synthesis operator
        3. Assert the template renders and the generated image is saved

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: Expresses test results through assertions.

    Examples:
        >>> callable(test_image_card_synthesis_operator_renders_prompt_template_with_payload_fields)
        True
    """
    item = GenerationItem(
        id="image_template",
        task_type="image",
        prompt="Draw a reliable workflow.",
        payload={"title": "Workflow", "subtitle": "Retry and report"},
    )
    item = ImageCardSynthesisOperator(
        {
            "output_dir": str(tmp_path),
            "image_client": FakeImageClient(),
            "prompt_template": "Prompt: {prompt}\nTitle: {title}\nSubtitle: {subtitle}",
        }
    ).process(item)

    assert item.generated["image_prompt"] == "Prompt: Draw a reliable workflow.\nTitle: Workflow\nSubtitle: Retry and report"
    assert Path(item.generated["image_path"]).exists()
