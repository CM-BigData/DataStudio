from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.scoring import _signature, compute_diversity_score


class DiversityScoreOperator(BaseOperator):
    operator_name = "diversity_score"  # 工作流注册：多样性评分 stage 使用的稳定算子名称。
    _seen_hashes: set[str] = set()  # 进程内状态：记录已见签名哈希以识别重复生成结果。

    def process(self, item: GenerationItem) -> GenerationItem:
        """Compute the diversity score for a sample

        Business logic:
            1. Extract the sample signature and hash it
            2. Check whether the hash has already appeared
            3. Score duplicates as 0 and new samples as 1

        Args:
            item (GenerationItem): Sample to score.

        Returns:
            GenerationItem: Sample updated with diversity score.

        Examples:
            >>> DiversityScoreOperator().operator_name
            'diversity_score'
        """
        diversity_score, is_duplicate = compute_diversity_score(_signature(item), self._seen_hashes)
        item.metrics["diversity_score"] = diversity_score

        if is_duplicate:  # An existing hash means the generated result is duplicated.
            item.issues.append({"type": "duplicate_generation", "message": "Generated result is duplicated"})

        return item
