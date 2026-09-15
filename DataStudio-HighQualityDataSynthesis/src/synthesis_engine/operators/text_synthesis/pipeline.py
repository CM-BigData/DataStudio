from __future__ import annotations

from synthesis_engine.mappers import BaseMapper, MapperInput, MapperResult


class TextGenerationPipeline:
    def __init__(self, mapper: BaseMapper, retry_limit: int = 0) -> None:
        """初始化文本生成编排管线

        业务逻辑：
            1. 保存 mapper 实例
            2. 规范化 retry_limit
            3. 暴露统一 run 入口供 text_synthesis 相关 operator 调用

        Args:
            mapper (BaseMapper): 文本生成 mapper。
            retry_limit (int): mapper 失败后的重试次数。

        Returns:
            None: 初始化不返回业务数据。

        Examples:
            >>> TextGenerationPipeline.__name__
            'TextGenerationPipeline'
        """
        self.mapper = mapper
        self.retry_limit = max(0, int(retry_limit))

    def run(self, input: MapperInput) -> MapperResult:
        """执行 mapper 并按配置重试

        业务逻辑：
            1. 首次调用 mapper.map
            2. 当结果失败时按 retry_limit 重试
            3. 返回最终 MapperResult

        Args:
            input (MapperInput): Mapper 输入。

        Returns:
            MapperResult: Mapper 输出结果。

        Examples:
            >>> callable(TextGenerationPipeline.run)
            True
        """
        result = self.mapper.map(input)
        for _ in range(self.retry_limit):
            if not result.failed:
                break
            result = self.mapper.map(input)
        return result
