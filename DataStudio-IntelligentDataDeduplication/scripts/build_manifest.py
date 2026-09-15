from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
DEFAULT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".ppm", ".pgm", ".tif", ".tiff"}
DEFAULT_AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wma"}
STRUCTURED_TEXT_EXTENSIONS = {".jsonl", ".json", ".csv"}


def _validated_path_text(value: str | Path, name: str) -> str:
    """Validate the textual form of a filesystem path."""
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if "\x00" in text or any(ord(char) < 32 for char in text):
        raise ValueError(f"{name} contains unsupported control characters")
    return text


def _allowed_roots(values: Sequence[str | Path] | None = None, *, default_root: Path | None = None) -> tuple[Path, ...]:
    """Resolve existing directories that explicitly authorize path access."""
    roots: list[Path] = []
    for value in (default_root or Path.cwd(), *(values or [])):
        text = os.path.expanduser(_validated_path_text(value, "allow-root"))
        root = Path.cwd().joinpath(text).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("allow-root must be an existing directory")
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def _safe_cli_path(
    value: str | Path,
    name: str,
    *,
    allowed_roots: Sequence[Path] | None = None,
    base_dir: Path | None = None,
) -> Path:
    """Validate, normalize, and optionally authorize a command-line path."""
    text = os.path.expanduser(_validated_path_text(value, name))
    path = (base_dir or Path.cwd()).joinpath(text)
    resolved = path.resolve(strict=False)
    if allowed_roots is not None and not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
        raise ValueError(f"{name} must stay under an authorized root")
    return resolved


def _safe_cli_dirs(values: Sequence[str | Path], name: str, *, allowed_roots: Sequence[Path] | None = None) -> list[Path]:
    """Validate and normalize repeatable directory arguments."""
    return [_safe_cli_path(value, name, allowed_roots=allowed_roots) for value in values]


def _iter_files(
    directories: Iterable[Path],
    extensions: set[str],
    recursive: bool,
    allowed_roots: Sequence[Path] | None = None,
) -> list[Path]:
    """按扩展名扫描目录中的文件

    业务逻辑：
        1. 遍历传入目录列表并跳过不存在的目录
        2. 按是否递归选择 `rglob` 或 `glob`
        3. 仅保留扩展名匹配且确认为文件的路径并排序返回

    Args:
        directories (Iterable[Path]): 待扫描目录列表
        extensions (set[str]): 允许的文件扩展名集合
        recursive (bool): 是否递归扫描子目录
        allowed_roots (Sequence[Path] | None): 每个扫描结果必须位于其中一个授权根目录内

    Returns:
        list[Path]: 排序后的文件路径列表

    Examples:
        >>> _iter_files([Path(".")], {".py"}, recursive=False)  # doctest: +ELLIPSIS
        [...]
    """
    files: list[Path] = []
    for directory in directories:
        if not directory.exists() or not directory.is_dir():
            continue
        iterator = directory.rglob("*") if recursive else directory.glob("*")
        for path in iterator:
            resolved = _safe_cli_path(path, "input file", allowed_roots=allowed_roots) if allowed_roots is not None else path
            if resolved.is_file() and resolved.suffix.lower() in extensions:
                files.append(resolved)
    return sorted(files)


def _normalize_path(path: Path, path_mode: str, relative_base: Path) -> str:
    """将路径转换为输出清单使用的字符串

    业务逻辑：
        1. 先把路径解析为绝对路径
        2. 当 `path_mode=relative` 时尝试转成相对路径
        3. 其余情况统一输出绝对路径字符串

    Args:
        path (Path): 原始文件路径
        path_mode (str): `absolute` 或 `relative`
        relative_base (Path): 生成相对路径时的基准目录

    Returns:
        str: 归一化后的路径字符串

    Examples:
        >>> _normalize_path(Path("a.txt"), "absolute", Path(".")).endswith("a.txt")
        True
    """
    resolved = path.resolve()
    if path_mode == "relative":
        try:
            return str(resolved.relative_to(relative_base.resolve()))
        except ValueError:
            return str(resolved)
    return str(resolved)


def _build_text_row(path: Path, source_path: str, max_text_chars: int) -> dict[str, object]:
    """构造文本样本行

    业务逻辑：
        1. 读取 UTF-8 文本文件内容
        2. 根据 `max_text_chars` 选择是否截断
        3. 组装文本模态所需的标准输入结构

    Args:
        path (Path): 文本文件路径
        source_path (str): 写入清单的源路径
        max_text_chars (int): 最大保留字符数，0 或负数表示不截断

    Returns:
        dict[str, object]: 单条文本 manifest 记录

    Examples:
        >>> row = _build_text_row(Path("note.txt"), "note.txt", 3)
        >>> row["modality"]
        'text'
    """
    text = path.read_text(encoding="utf-8")
    if max_text_chars > 0:
        text = text[:max_text_chars]
    return {
        "id": f"text_{path.stem}",
        "modality": "text",
        "payload": {"text": text},
        "meta": {"source_path": source_path},
    }


def _resolve_text_payload(raw: dict[str, object]) -> str:
    """从结构化文本记录中提取文本内容

    业务逻辑：
        1. 优先读取 `payload.text`
        2. 回退读取常见文本字段 `text`、`content`、`body`
        3. 没有文本时返回空字符串

    Args:
        raw (dict[str, object]): 一条结构化记录

    Returns:
        str: 提取到的文本内容

    Examples:
        >>> _resolve_text_payload({"payload": {"text": "hello"}})
        'hello'
    """
    payload = raw.get("payload", {})
    if isinstance(payload, dict) and payload.get("text") not in (None, ""):
        return str(payload["text"])

    for key in ("text", "content", "body"):
        if raw.get(key) not in (None, ""):
            return str(raw[key])

    return ""


def _build_structured_text_rows(path: Path, source_path: str, max_text_chars: int) -> list[dict[str, object]]:
    """把结构化文本清单转换成文本样本行

    业务逻辑：
        1. 根据扩展名读取 JSONL、JSON 或 CSV
        2. 从每条记录提取文本字段并保留可用 id
        3. 产出统一的文本模态输入结构

    Args:
        path (Path): 结构化文本清单路径
        source_path (str): 写入清单的源路径
        max_text_chars (int): 最大保留字符数，0 或负数表示不截断

    Returns:
        list[dict[str, object]]: 转换后的文本 manifest 记录列表

    Examples:
        >>> _build_structured_text_rows(Path('x.jsonl'), 'x.jsonl', 0)  # doctest: +SKIP
        []
    """
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    elif suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else [data]
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            records = [dict(row) for row in csv.DictReader(handle)]
    else:
        return []

    rows: list[dict[str, object]] = []
    for index, raw in enumerate(records, start=1):
        text = _resolve_text_payload(raw if isinstance(raw, dict) else {})
        if text == "":
            continue

        if max_text_chars > 0:
            text = text[:max_text_chars]

        item_id = ""
        if isinstance(raw, dict):
            item_id = str(raw.get("id") or raw.get("sample_id") or raw.get("uid") or "")

        rows.append(
            {
                "id": item_id or f"text_{path.stem}_{index}",
                "modality": "text",
                "payload": {"text": text},
                "meta": {"source_path": source_path, "source_record_index": index},
            }
        )

    return rows


def _build_media_row(path: Path, source_path: str, modality: str, payload_key: str) -> dict[str, object]:
    """构造图片或音频样本行

    业务逻辑：
        1. 接收文件路径和模态信息
        2. 把路径写入对应 payload 字段
        3. 组装统一的标准输入结构

    Args:
        path (Path): 媒体文件路径
        source_path (str): 写入清单的源路径
        modality (str): `image` 或 `audio`
        payload_key (str): `image_path` 或 `audio_path`

    Returns:
        dict[str, object]: 单条媒体 manifest 记录

    Examples:
        >>> row = _build_media_row(Path("a.wav"), "a.wav", "audio", "audio_path")
        >>> row["payload"]["audio_path"]
        'a.wav'
    """
    return {
        "id": f"{modality}_{path.stem}",
        "modality": modality,
        "payload": {payload_key: source_path},
        "meta": {"source_path": source_path},
    }


def build_rows(
    text_dirs: Sequence[Path],
    image_dirs: Sequence[Path],
    audio_dirs: Sequence[Path],
    text_ext: set[str] | None = None,
    image_ext: set[str] | None = None,
    audio_ext: set[str] | None = None,
    recursive: bool = True,
    path_mode: str = "absolute",
    relative_base: Path | None = None,
    max_text_chars: int = 0,
    allowed_roots: Sequence[Path] | None = None,
) -> list[dict[str, object]]:
    """把多模态目录扫描结果转换成统一输入清单

    业务逻辑：
        1. 分别扫描文本、图片、音频目录并按扩展名过滤
        2. 将不同模态文件转换成统一的 JSONL 行结构
        3. 按模态和源路径排序，确保生成结果稳定

    Args:
        text_dirs (Sequence[Path]): 文本目录列表
        image_dirs (Sequence[Path]): 图片目录列表
        audio_dirs (Sequence[Path]): 音频目录列表
        text_ext (set[str] | None): 文本扩展名集合
        image_ext (set[str] | None): 图片扩展名集合
        audio_ext (set[str] | None): 音频扩展名集合
        recursive (bool): 是否递归扫描子目录
        path_mode (str): 输出路径模式，支持 `absolute` 和 `relative`
        relative_base (Path | None): 相对路径基准目录
        max_text_chars (int): 文本最大字符数，0 或负数表示不截断
        allowed_roots (Sequence[Path] | None): 扫描得到的每个文件必须位于其中一个授权根目录内

    Returns:
        list[dict[str, object]]: 可直接写入 `input.jsonl` 的记录列表

    Examples:
        >>> build_rows([], [], [])
        []
    """
    base = (relative_base or Path.cwd()).resolve()
    rows: list[dict[str, object]] = []

    for path in _iter_files(
        text_dirs,
        {ext.lower() for ext in (text_ext or DEFAULT_TEXT_EXTENSIONS)},
        recursive,
        allowed_roots,
    ):
        source_path = _normalize_path(path, path_mode, base)
        if path.suffix.lower() in STRUCTURED_TEXT_EXTENSIONS:
            rows.extend(_build_structured_text_rows(path, source_path, max_text_chars))
        else:
            rows.append(_build_text_row(path, source_path, max_text_chars))

    for path in _iter_files(
        image_dirs,
        {ext.lower() for ext in (image_ext or DEFAULT_IMAGE_EXTENSIONS)},
        recursive,
        allowed_roots,
    ):
        source_path = _normalize_path(path, path_mode, base)
        rows.append(_build_media_row(path, source_path, "image", "image_path"))

    for path in _iter_files(
        audio_dirs,
        {ext.lower() for ext in (audio_ext or DEFAULT_AUDIO_EXTENSIONS)},
        recursive,
        allowed_roots,
    ):
        source_path = _normalize_path(path, path_mode, base)
        rows.append(_build_media_row(path, source_path, "audio", "audio_path"))

    return sorted(rows, key=lambda row: (str(row["modality"]), str(row["meta"]["source_path"])))


def _parse_extensions(value: str) -> set[str]:
    """解析命令行传入的扩展名列表

    业务逻辑：
        1. 按逗号拆分用户输入
        2. 统一补齐前导点并转为小写
        3. 过滤空值后返回集合

    Args:
        value (str): 逗号分隔的扩展名字符串

    Returns:
        set[str]: 标准化后的扩展名集合

    Examples:
        >>> _parse_extensions('txt,.md')
        {'.md', '.txt'}
    """
    result = set()
    for raw in value.split(","):
        ext = raw.strip().lower()
        if not ext:
            continue
        result.add(ext if ext.startswith(".") else f".{ext}")
    return result


def _build_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器

    业务逻辑：
        1. 定义多目录输入参数
        2. 定义输出路径、扫描方式和扩展名参数
        3. 返回供主入口复用的解析器实例

    Args:
        None: 该函数不需要额外参数

    Returns:
        argparse.ArgumentParser: 配置完成的参数解析器

    Examples:
        >>> isinstance(_build_parser(), argparse.ArgumentParser)
        True
    """
    parser = argparse.ArgumentParser(description="Scan client directories and build a dedup workflow input manifest.")
    parser.add_argument("--text-dir", action="append", type=Path, default=[], help="Directory containing text files.")
    parser.add_argument("--image-dir", action="append", type=Path, default=[], help="Directory containing image files.")
    parser.add_argument("--audio-dir", action="append", type=Path, default=[], help="Directory containing audio files.")
    parser.add_argument("--output", required=True, type=Path, help="Output JSONL file path.")
    parser.add_argument(
        "--allow-root",
        action="append",
        type=Path,
        default=[],
        help="Authorize path access under an existing directory. Repeat for multiple roots.",
    )
    parser.add_argument("--path-mode", choices=("absolute", "relative"), default="absolute", help="Path style written into manifest payloads.")
    parser.add_argument("--relative-base", type=Path, default=Path("."), help="Base directory used when path-mode=relative.")
    parser.add_argument("--text-ext", default=",".join(sorted(DEFAULT_TEXT_EXTENSIONS)), help="Comma-separated text extensions.")
    parser.add_argument("--image-ext", default=",".join(sorted(DEFAULT_IMAGE_EXTENSIONS)), help="Comma-separated image extensions.")
    parser.add_argument("--audio-ext", default=",".join(sorted(DEFAULT_AUDIO_EXTENSIONS)), help="Comma-separated audio extensions.")
    parser.add_argument("--max-text-chars", type=int, default=0, help="Maximum text characters to keep, 0 for unlimited.")
    parser.add_argument("--no-recursive", action="store_true", help="Only scan the top level of each directory.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行目录扫描并生成 JSONL 清单

    业务逻辑：
        1. 解析命令行参数并规范化目录、扩展名和输出路径
        2. 调用 `build_rows` 生成统一输入记录
        3. 将记录写入 JSONL 文件并返回退出码

    Args:
        argv (Sequence[str] | None): 可选命令行参数列表

    Returns:
        int: 成功返回 0

    Examples:
        >>> main(['--output', 'tmp.jsonl'])  # doctest: +SKIP
        0
    """
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    allowed_roots = _allowed_roots(args.allow_root)
    output = _safe_cli_path(args.output, "output", allowed_roots=allowed_roots)
    if output.exists() and output.is_dir():
        raise ValueError("output must be a file path")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows(
        text_dirs=_safe_cli_dirs(args.text_dir, "text-dir", allowed_roots=allowed_roots),
        image_dirs=_safe_cli_dirs(args.image_dir, "image-dir", allowed_roots=allowed_roots),
        audio_dirs=_safe_cli_dirs(args.audio_dir, "audio-dir", allowed_roots=allowed_roots),
        text_ext=_parse_extensions(args.text_ext),
        image_ext=_parse_extensions(args.image_ext),
        audio_ext=_parse_extensions(args.audio_ext),
        recursive=not args.no_recursive,
        path_mode=args.path_mode,
        relative_base=_safe_cli_path(args.relative_base, "relative-base", allowed_roots=allowed_roots),
        max_text_chars=args.max_text_chars,
        allowed_roots=allowed_roots,
    )

    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
