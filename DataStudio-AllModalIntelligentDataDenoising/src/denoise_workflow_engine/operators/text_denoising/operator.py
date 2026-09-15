from __future__ import annotations

from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.operators.text_denoising.pipeline import process_text_denoise


class TextDenoiseOperator(BaseOperator):
    operator_name: str = "text_denoise"  # Public registry name for the end-to-end text denoising capability.
    operator_version: str = "1.0.0"  # Version marker written to run results for implementation tracing.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """运行端到端文本去噪算子

        业务逻辑：
            1. 读取当前端到端算子配置
            2. 调用文本去噪 pipeline
            3. 返回处理后的标准样本

        Args:
            item (dict[str, Any]): 当前样本

        Returns:
            dict[str, Any]: 处理后的样本

        Examples:
            >>> TextDenoiseOperator({"thresholds": {"keep_score": 0}}).operator_name
            'text_denoise'
        """
        return process_text_denoise(item, self.config)
