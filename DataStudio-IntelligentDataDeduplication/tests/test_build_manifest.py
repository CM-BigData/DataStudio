import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_manifest.py"  # Workflow config: path to the manifest-building script under test.
SPEC = importlib.util.spec_from_file_location("build_manifest", SCRIPT_PATH)  # Workflow config: dynamically load the module spec from the script file so scripts/ does not need to be a package.
build_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(build_manifest)


class BuildManifestTest(unittest.TestCase):
    def test_build_rows_from_client_directories(self) -> None:
        """Verify that client multimodal directories are converted into sorted manifest rows.

        Business logic:
            1. Create text, image, and audio files in a temporary directory.
            2. Call build_rows to generate unified input rows.
            3. Assert that modality ordering, text content, and source metadata match workflow-input expectations.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> BuildManifestTest().test_build_rows_from_client_directories()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_dir = root / "texts"
            image_dir = root / "images"
            audio_dir = root / "audios"
            text_dir.mkdir()
            image_dir.mkdir()
            audio_dir.mkdir()
            (text_dir / "a.txt").write_text("hello", encoding="utf-8")
            (image_dir / "a.ppm").write_text("P3\n1 1\n255\n0 0 0\n", encoding="ascii")
            (audio_dir / "a.wav").write_bytes(b"RIFF")

            rows = build_manifest.build_rows(
                text_dirs=[text_dir],
                image_dirs=[image_dir],
                audio_dirs=[audio_dir],
                text_ext={".txt"},
                image_ext={".ppm"},
                audio_ext={".wav"},
                recursive=True,
                path_mode="absolute",
                relative_base=root,
                max_text_chars=0,
            )

            self.assertEqual([row["modality"] for row in rows], ["audio", "image", "text"])
            self.assertEqual(rows[2]["payload"]["text"], "hello")
            self.assertIn("source_path", rows[0]["meta"])

    def test_main_writes_jsonl(self) -> None:
        """Verify that the command entrypoint writes scan results into a JSONL file.

        Business logic:
            1. Create a temporary client directory containing only text files.
            2. Call main with text-dir and output arguments.
            3. Assert that the exit code is 0 and the first JSONL row is a text sample.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> BuildManifestTest().test_main_writes_jsonl()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_dir = root / "texts"
            text_dir.mkdir()
            (text_dir / "a.txt").write_text("hello", encoding="utf-8")
            output = root / "input.jsonl"

            exit_code = build_manifest.main(
                ["--text-dir", str(text_dir), "--output", str(output), "--allow-root", str(root)]
            )

            self.assertEqual(exit_code, 0)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["modality"], "text")

    def test_safe_cli_path_rejects_control_characters(self) -> None:
        """Verify command-line paths reject unsupported control characters."""
        with self.assertRaises(ValueError):
            build_manifest._safe_cli_path("bad\x00path.jsonl", "output")

    def test_parser_converts_cli_paths_to_path_objects(self) -> None:
        """Verify argparse converts path options before command dispatch."""
        args = build_manifest._build_parser().parse_args(
            [
                "--text-dir",
                "data/text",
                "--output",
                "data/input.jsonl",
                "--allow-root",
                "data",
                "--relative-base",
                ".",
            ]
        )

        self.assertEqual(args.text_dir, [Path("data/text")])
        self.assertEqual(args.output, Path("data/input.jsonl"))
        self.assertEqual(args.allow_root, [Path("data")])
        self.assertEqual(args.relative_base, Path("."))

    def test_safe_cli_path_enforces_authorized_roots(self) -> None:
        """Verify canonical paths cannot escape their authorized root."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            allowed_roots = build_manifest._allowed_roots([str(root)])

            accepted = build_manifest._safe_cli_path(
                root / "中文 data" / "input.jsonl",
                "input",
                allowed_roots=allowed_roots,
            )
            self.assertEqual(accepted, (root / "中文 data" / "input.jsonl").resolve())
            with self.assertRaisesRegex(ValueError, "authorized root"):
                build_manifest._safe_cli_path(
                    Path(outside) / "input.jsonl",
                    "input",
                    allowed_roots=allowed_roots,
                )

    def test_safe_cli_path_rejects_symlink_escape(self) -> None:
        """Verify a link inside an allowed root cannot redirect outside it."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            link = root / "external-link"
            try:
                os.symlink(outside, link, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "authorized root"):
                build_manifest._safe_cli_path(
                    link / "input.jsonl",
                    "input",
                    allowed_roots=(root,),
                )

    def test_build_rows_revalidates_each_discovered_file(self) -> None:
        """Verify directory traversal cannot return a file outside the authorized root."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            outside_file = Path(outside).resolve() / "secret.txt"
            outside_file.write_text("outside secret", encoding="utf-8")

            with patch.object(Path, "rglob", return_value=iter([outside_file])):
                with self.assertRaisesRegex(ValueError, "authorized root"):
                    build_manifest.build_rows(
                        text_dirs=[root],
                        image_dirs=[],
                        audio_dirs=[],
                        text_ext={".txt"},
                        allowed_roots=(root,),
                    )

    def test_main_rejects_directory_output(self) -> None:
        """Verify the manifest command refuses a directory as the output target."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                build_manifest.main(["--output", str(root), "--allow-root", str(root)])

    def test_build_rows_reads_structured_text_manifest(self) -> None:
        """Verify that text directories can include structured JSONL manifests.

        Business logic:
            1. Create a temporary text directory containing an input.jsonl file.
            2. Call build_rows with `.jsonl` added to text extensions.
            3. Assert that the generated row keeps text modality and payload text.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> BuildManifestTest().test_build_rows_reads_structured_text_manifest()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_dir = root / "texts"
            text_dir.mkdir()
            (text_dir / "input.jsonl").write_text(
                json.dumps({"id": "t1", "modality": "text", "payload": {"text": "hello from manifest"}}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            rows = build_manifest.build_rows(
                text_dirs=[text_dir],
                image_dirs=[],
                audio_dirs=[],
                text_ext={".txt", ".jsonl"},
                image_ext={".ppm"},
                audio_ext={".wav"},
                recursive=True,
                path_mode="absolute",
                relative_base=root,
                max_text_chars=0,
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["modality"], "text")
            self.assertEqual(rows[0]["payload"]["text"], "hello from manifest")

    def test_build_rows_skips_structured_records_without_text(self) -> None:
        """Verify that structured text manifests skip records without text payload.

        Business logic:
            1. Create a JSONL file containing a non-text metadata record.
            2. Call build_rows with `.jsonl` added to text extensions.
            3. Assert that records without usable text are skipped.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> BuildManifestTest().test_build_rows_skips_structured_records_without_text()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_dir = root / "texts"
            text_dir.mkdir()
            (text_dir / "ground_truth.jsonl").write_text(
                json.dumps({"group_id": "g1", "member_ids": ["a", "b"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            rows = build_manifest.build_rows(
                text_dirs=[text_dir],
                image_dirs=[],
                audio_dirs=[],
                text_ext={".txt", ".jsonl"},
                image_ext={".ppm"},
                audio_ext={".wav"},
                recursive=True,
                path_mode="absolute",
                relative_base=root,
                max_text_chars=0,
            )

            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
