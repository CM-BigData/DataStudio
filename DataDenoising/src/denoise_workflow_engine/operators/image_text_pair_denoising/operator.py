from __future__ import annotations

from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.operators.image_text_pair_denoising.pipeline import process_image_text_pair_denoise


class ImageTextPairDenoiseOperator(BaseOperator):
    operator_name: str = "image_text_pair_denoise"  # Public registry name for end-to-end image-text pair denoising.
    operator_version: str = "1.0.0"  # Version marker written to run results for implementation tracing.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """运行端到端图文对去噪算子

        业务逻辑：
            1. 读取当前端到端算子配置
            2. 调用图文对去噪 pipeline
            3. 返回处理后的标准样本

        Args:
            item (dict[str, Any]): 当前样本

        Returns:
            dict[str, Any]: 处理后的样本

        Examples:
            >>> ImageTextPairDenoiseOperator().operator_name
            'image_text_pair_denoise'
        """
        return process_image_text_pair_denoise(item, self.config)
