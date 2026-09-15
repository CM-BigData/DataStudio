from pathlib import Path

import yaml


PUBLIC_SAMPLE_WORKFLOWS = [
    "image_aigc_eval.yaml",
    "image_blank_eval.yaml",
    "real_oxford_pet_eval.yaml",
    "real_tnews_eval.yaml",
    "text_consecutive_punctuation_eval.yaml",
    "text_punctuation_pairing_eval.yaml",
    "text_special_characters_eval.yaml",
]


def test_public_sample_workflows_use_example_data() -> None:
    """Verify that public sample workflows do not depend on local real_data fixtures.

    Business logic:
        1. Load every workflow that is used as a runnable sample.
        2. Inspect configured input paths.
        3. Assert that those inputs point to example_data and exist in the repository.

    Args:
        None.

    Returns:
        None: Assertions define the workflow sample contract.

    Examples:
        >>> callable(test_public_sample_workflows_use_example_data)
        True
    """
    project_root = Path(__file__).resolve().parents[1]
    for workflow_name in PUBLIC_SAMPLE_WORKFLOWS:
        config_path = project_root / "workflows" / workflow_name
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        input_config = config["input"]
        for key in ("path", "annotation_path"):
            value = input_config.get(key)
            if value:
                assert value.startswith("./example_data/"), f"{workflow_name} {key} should use example_data"
                assert (project_root / value[2:]).exists(), f"{workflow_name} {key} does not exist: {value}"
