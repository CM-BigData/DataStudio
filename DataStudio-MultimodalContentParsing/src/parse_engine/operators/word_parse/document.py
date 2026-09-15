from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class WordStructureExtractOperator(BaseOperator):
    operator_name = "word_structure_extract"  # Operator name: registry name for the Word structure extraction step.

    def process(self, item: DataItem) -> DataItem:
        """Extract paragraphs, headings, and table structure from a Word document.

        Business logic:
            1. Pass non-Word samples through unchanged.
            2. Traverse paragraphs with python-docx and distinguish headings from paragraphs by style.
            3. Traverse tables and generate table artifacts while recording paragraph and table counts.

        Args:
            item: Word or non-Word data item in the current workflow.

        Returns:
            DataItem: Data item with structured Word artifacts appended and action updated.

        Examples:
            >>> WordStructureExtractOperator({}).operator_name
            'word_structure_extract'"""
        if item.modality != "word":  # Cross-modality guard: the Word structure operator only handles docx samples.
            return item

        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("python-docx is required for Word parsing") from exc

        path = Path(item.payload["path"])
        document_path, temp_dir = self._resolve_docx_path(path)
        try:
            document = Document(document_path)
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
        block_index = 0

        for paragraph in document.paragraphs:  # Paragraph iteration: generate heading or body artifacts in document order.
            text = paragraph.text.strip()
            if not text:  # Empty paragraph: skip contentless paragraphs produced by Word layout.
                continue
            block_index += 1
            style_name = paragraph.style.name if paragraph.style else ""
            artifact_type = "heading" if style_name.lower().startswith("heading") else "paragraph"
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_block_{block_index}",
                    type=artifact_type,
                    text=text,
                    data={"style": style_name},
                    source_trace=SourceTrace(file=str(path), operator=self.operator_name),
                )
            )

        for table_index, table in enumerate(document.tables, start=1):  # Table iteration: preserve a stable index for each table.
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_table_{table_index}",
                    type="table",
                    text="\n".join([" | ".join(row) for row in rows]),
                    data={"rows": rows},
                    source_trace=SourceTrace(file=str(path), operator=self.operator_name),
                )
            )

        item.metrics["paragraph_count"] = len(document.paragraphs)
        item.metrics["table_count"] = len(document.tables)
        item.action = "parsed" if item.artifacts else "failed"
        if item.action == "failed":  # No structural artifacts: record the failure reason for an empty Word document.
            item.issues.append({"type": "empty_word_document", "message": "Word extraction produced no content"})
        return item

    def _resolve_docx_path(self, path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
        """Resolve a Word input into a real docx path for python-docx.

        Business logic:
            1. Use the original path directly when it is a real docx package.
            2. Treat legacy `.doc` files and fake `.docx` exports as conversion targets.
            3. Convert unsupported Word wrappers to a temporary docx file through LibreOffice.

        Args:
            path (Path): Incoming Word file path.

        Returns:
            tuple[Path, tempfile.TemporaryDirectory[str] | None]: Resolved docx path and optional temporary directory holder.

        Examples:
            >>> WordStructureExtractOperator({})._looks_like_real_docx(Path('demo.docx')) is False
            True
        """
        if self._looks_like_real_docx(path):
            return path, None
        return self._convert_to_docx(path)

    def _looks_like_real_docx(self, path: Path) -> bool:
        """Return whether the path points to a real docx package.

        Business logic:
            1. Reject non-zip files immediately.
            2. Inspect the archive contents for `word/document.xml`.
            3. Return False when the file is only a fake `.docx` wrapper or another format.

        Args:
            path (Path): Candidate Word file path.

        Returns:
            bool: Whether the file is a real docx package.

        Examples:
            >>> WordStructureExtractOperator({})._looks_like_real_docx(Path(__file__))
            False
        """
        if not ZipFile.__module__:
            return False
        if not path.exists() or not path.is_file():
            return False
        try:
            with ZipFile(path) as archive:
                return "word/document.xml" in archive.namelist()
        except Exception:
            return False

    def _convert_to_docx(self, path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
        """Convert a legacy Word file into a temporary docx file with LibreOffice.

        Business logic:
            1. Create a temporary output directory for the converted document.
            2. Invoke headless LibreOffice to convert the source file to docx.
            3. Return the generated docx path and keep the temporary directory alive for the caller.

        Args:
            path (Path): Source `.doc` or fake docx file path.

        Returns:
            tuple[Path, tempfile.TemporaryDirectory[str]]: Converted docx path and the temporary directory handle.

        Examples:
            >>> callable(WordStructureExtractOperator({})._convert_to_docx)
            True
        """
        temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        soffice = self._resolve_soffice_command()
        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                temp_dir.name,
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            temp_dir.cleanup()
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"LibreOffice conversion failed for {path}: {stderr or result.returncode}")
        for candidate in Path(temp_dir.name).iterdir():
            if candidate.suffix.lower() == ".docx":
                return candidate, temp_dir
        temp_dir.cleanup()
        raise RuntimeError(f"LibreOffice conversion produced no docx output for {path}")

    def _resolve_soffice_command(self) -> str:
        """Resolve the configured LibreOffice command path for local document conversion.

        Business logic:
            1. Read the command path from workflow-facing operator config.
            2. Require the caller to pass an explicit executable path or command name.
            3. Raise a clear runtime error when the workflow omitted the command.

        Args:
            None.

        Returns:
            str: Executable path for the LibreOffice conversion command.

        Examples:
            >>> WordStructureExtractOperator({"soffice_command": "soffice"})._resolve_soffice_command()
            'soffice'
            True
        """
        command = str(self.config.get("soffice_command", "") or "").strip()
        if not command:
            raise RuntimeError("Workflow params.soffice_command is required for .doc or fake .docx conversion")
        return command

class WordMediaExtractOperator(BaseOperator):
    operator_name = "word_media_extract"  # Operator name: registry name for the embedded Word media extraction step.

    def process(self, item: DataItem) -> DataItem:
        """Count embedded media files inside a Word package.

        Business logic:
            1. Pass non-Word samples through unchanged.
            2. Read the docx file as a ZIP package and inspect resource paths under word/media/.
            3. Generate a word_media artifact for each media file and record the media_count metric.

        Args:
            item: Word or non-Word data item in the current workflow.

        Returns:
            DataItem: Data item with media artifacts appended and media counts recorded.

        Examples:
            >>> WordMediaExtractOperator({}).operator_name
            'word_media_extract'"""
        if item.modality != "word":  # Cross-modality guard: media extraction only reads docx archives.
            return item

        path = Path(item.payload["path"])
        structure = WordStructureExtractOperator({})
        archive_path, temp_dir = structure._resolve_docx_path(path)
        media_files: list[str] = []
        try:
            with ZipFile(archive_path) as archive:
                for name in archive.namelist():  # Package path iteration: search resources in the docx media directory.
                    if name.startswith("word/media/"):  # Media resource: only count embedded files referenced by the Word document body.
                        media_files.append(name)
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

        item.metrics["media_count"] = len(media_files)
        for index, name in enumerate(media_files, start=1):  # Media artifact generation: assign a stable id to each embedded file.
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_media_{index}",
                    type="word_media",
                    data={"archive_path": name},
                    source_trace=SourceTrace(file=str(path), operator=self.operator_name),
                )
            )
        return item
