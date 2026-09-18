from __future__ import annotations

from typing import Any

from denoise_workflow_engine.operators.auto_denoising.pipeline import process_auto_denoise
from denoise_workflow_engine.operators.base import BaseOperator


class AutoDenoiseOperator(BaseOperator):
    operator_name: str = "auto_denoise"  # Public registry name for mixed-input automatic end-to-end denoising.
    operator_version: str = "1.0.0"  # Version marker written to run results for implementation tracing.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """运行自动路由端到端去噪算子

        业务逻辑：
            1. 读取当前端到端算子配置
            2. 调用自动路由去噪 pipeline
            3. 返回处理后的标准样本

        Args:
            item (dict[str, Any]): 当前样本

        Returns:
            dict[str, Any]: 处理后的样本

        Examples:
            >>> AutoDenoiseOperator().operator_name
            'auto_denoise'
        """
        return process_auto_denoise(item, self.config)
