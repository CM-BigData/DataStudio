import json
import tempfile
import unittest
from pathlib import Path

from dedup_workflow_engine.runtime.router import detect_modality, load_and_route_input


class RouterTest(unittest.TestCase):
    def test_detect_modality_from_explicit_field(self) -> None:
        """Verify that an explicit modality field takes precedence when deciding sample modality.

        Business logic:
            1. Build a minimal sample with modality=text.
            2. Call detect_modality to identify the modality.
            3. Assert that the explicit text declaration is returned.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> RouterTest().test_detect_modality_from_explicit_field()  # doctest: +SKIP
        """
        self.assertEqual(detect_modality({"modality": "text", "payload": {}}), "text")

    def test_detect_modality_from_payload(self) -> None:
        """Verify that payload path fields can infer modality when explicit modality is missing.

        Business logic:
            1. Build a sample containing only image_path and verify it resolves to image.
            2. Build a sample containing only audio_path and verify it resolves to audio.
            3. Assert that the payload structure is sufficient to support auto-routing.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> RouterTest().test_detect_modality_from_payload()  # doctest: +SKIP
        """
        self.assertEqual(detect_modality({"payload": {"image_path": "a.ppm"}}), "image")
        self.assertEqual(detect_modality({"payload": {"audio_path": "a.wav"}}), "audio")

    def test_detect_modality_rejects_ambiguous_payload_without_explicit_modality(self) -> None:
        """Verify that ambiguous payloads are not guessed without explicit modality.

        Business logic:
            1. Build a sample containing both text and image_path.
            2. Call detect_modality to try auto-inference.
            3. Assert that None is returned, requiring upstream explicit modality.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> RouterTest().test_detect_modality_rejects_ambiguous_payload_without_explicit_modality()  # doctest: +SKIP
        """
        self.assertIsNone(detect_modality({"payload": {"text": "a", "image_path": "a.ppm"}}))

    def test_load_and_route_input_groups_by_modality(self) -> None:
        """Verify that JSONL input is routed into modality groups.

        Business logic:
            1. Create a temporary JSONL containing text, image, and audio samples.
            2. Call load_and_route_input to read and group them.
            3. Assert that all three modalities exist and the text sample id stays unchanged.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> RouterTest().test_load_and_route_input_groups_by_modality()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.jsonl"
            rows = [
                {"id": "t1", "modality": "text", "payload": {"text": "a"}},
                {"id": "i1", "payload": {"image_path": "a.ppm"}},
                {"id": "a1", "payload": {"audio_path": "a.wav"}},
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            routed = load_and_route_input(path)

            self.assertEqual(set(routed), {"text", "image", "audio"})
            self.assertEqual(routed["text"][0]["id"], "t1")

    def test_load_and_route_input_accepts_utf8_bom(self) -> None:
        """Verify that the routing loader accepts JSONL files with a UTF-8 BOM.

        Business logic:
            1. Write one text sample using utf-8-sig.
            2. Call load_and_route_input to read the file.
            3. Assert that the BOM does not affect the sample id or modality grouping.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> RouterTest().test_load_and_route_input_accepts_utf8_bom()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.jsonl"
            row = {"id": "t1", "modality": "text", "payload": {"text": "a"}}
            path.write_text(json.dumps(row) + "\n", encoding="utf-8-sig")

            routed = load_and_route_input(path)

            self.assertEqual(routed["text"][0]["id"], "t1")

    def test_load_and_route_input_rejects_ground_truth_path(self) -> None:
        """Verify that the input loader rejects ground-truth paths.

        Business logic:
            1. Create a temporary JSONL whose filename contains ground_truth.
            2. Call load_and_route_input as if it were workflow input.
            3. Assert that ValueError is raised to prevent evaluation-truth leakage.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> RouterTest().test_load_and_route_input_rejects_ground_truth_path()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ground_truth.jsonl"
            path.write_text(json.dumps({"id": "t1", "payload": {"text": "a"}}) + "\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_and_route_input(path)


if __name__ == "__main__":
    unittest.main()
