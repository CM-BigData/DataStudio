from __future__ import annotations

from pathlib import Path

from PIL import Image


def build_negative_prompt(avoid: list[str] | tuple[str, ...] | None) -> str:
    """构建图像负向提示词

    业务逻辑：
        1. 读取 avoid 配置
        2. 对空配置使用默认负向短语
        3. 返回逗号拼接后的 negative prompt

    Args:
        avoid (list[str] | tuple[str, ...] | None): 需要规避的短语列表。

    Returns:
        str: 逗号拼接后的负向提示词。

    Examples:
        >>> build_negative_prompt(["blur", "watermark"])
        'blur, watermark'
    """
    banned = list(avoid or ["blur", "watermark", "low resolution", "unsafe content"])
    return ", ".join(str(item) for item in banned)


def validate_image_quality(
    image_path: str | Path | None,
    min_width: int,
    min_height: int,
) -> list[dict[str, str]]:
    """校验图像文件是否存在且分辨率达标

    业务逻辑：
        1. 校验 image_path 是否存在
        2. 读取图像宽高
        3. 在缺图或低分辨率时返回 issue 列表

    Args:
        image_path (str | Path | None): 图像文件路径。
        min_width (int): 最小宽度。
        min_height (int): 最小高度。

    Returns:
        list[dict[str, str]]: 需要追加到样本上的质量问题列表。

    Examples:
        >>> validate_image_quality(None, 128, 128)[0]["type"]
        'image_missing'
    """
    if not image_path or not Path(image_path).exists():
        return [{"type": "image_missing", "message": "Image file was not generated"}]

    with Image.open(image_path) as image:
        width, height = image.size
    if width < min_width or height < min_height:
        return [{"type": "low_resolution", "message": f"Image resolution is too small: {width}x{height}"}]
    return []
