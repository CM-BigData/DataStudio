from __future__ import annotations

from pathlib import Path
from typing import Any

from dedup_workflow_engine.operators.base import BaseOperator


class BestSampleSelector(BaseOperator):
    operator_name = "best_sample_selector"  # Workflow config: generic selector operator name for choosing the kept sample inside a duplicate group.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Choose one kept sample for each duplicate group and mark removed samples.

        Business logic:
            1. Build an index from item id to sample.
            2. Iterate over duplicate_groups and choose the highest-quality keep_id.
            3. Mark non-kept samples in the group as remove and add the duplicate_removed issue.

        Args:
            items (list[dict[str, Any]]): Workflow sample list.
            context (dict[str, Any]): Shared workflow context containing duplicate_groups.

        Returns:
            list[dict[str, Any]]: Sample list updated with keep/remove decisions.

        Examples:
            >>> BestSampleSelector({}).process_dataset([], {"duplicate_groups": []})
            []
        """
        by_id = {str(item["id"]): item for item in items}
        for group in context.get("duplicate_groups", []):  # Select one representative sample independently for each duplicate group.
            member_ids = [item_id for item_id in group.get("member_ids", []) if item_id in by_id]
            if not member_ids:  # Skip when none of the group members exist in the current dataset.
                continue
            keep_id = self._select_keep_id([by_id[item_id] for item_id in member_ids])
            remove_ids = [item_id for item_id in member_ids if item_id != keep_id]
            group["keep_id"] = keep_id
            group["remove_ids"] = remove_ids
            for item_id in member_ids:  # Write the group decision back to each member sample.
                item = by_id[item_id]
                item.setdefault("intermediate", {})["dedup_keep_id"] = keep_id
                if item_id == keep_id:  # Keep the representative sample.
                    item["action"] = "keep"
                    item.setdefault("issues", [])
                else:
                    item["action"] = "remove"
                    self.add_issue(item, "duplicate_removed")
        return items

    def _select_keep_id(self, items: list[dict[str, Any]]) -> str:
        """Choose the sample id that should be kept inside a duplicate group.

        Business logic:
            1. Compute a quality score for each sample in the group.
            2. Sort by descending quality score and ascending id.
            3. Return the sample id ranked first.

        Args:
            items (list[dict[str, Any]]): Samples belonging to one duplicate group.

        Returns:
            str: Sample id that should be kept.

        Examples:
            >>> BestSampleSelector({})._select_keep_id([{"id": "a", "metrics": {"normalized_length": 1}, "modality": "text"}])
            'a'
        """
        scored = [(self._quality_score(item), str(item["id"])) for item in items]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return scored[0][1]

    def _quality_score(self, item: dict[str, Any]) -> float:
        """Compute the keep-quality score for a sample by modality.

        Business logic:
            1. Use normalized_length for text samples.
            2. Use pixel area and file size for image samples.
            3. Use duration, sample rate, and file size for audio samples.

        Args:
            item (dict[str, Any]): Candidate sample to keep.

        Returns:
            float: Sample quality score, where higher means higher keep priority.

        Examples:
            >>> BestSampleSelector({})._quality_score({"modality": "text", "metrics": {"normalized_length": 3}})
            3.0
        """
        modality = item.get("modality")
        metrics = item.get("metrics", {})
        if modality == "text":  # Longer text usually carries more information.
            return float(metrics.get("normalized_length", 0))
        if modality == "image":  # Prefer image samples with more complete resolution and file information.
            width = float(metrics.get("image_width", 0))
            height = float(metrics.get("image_height", 0))
            file_size = float(metrics.get("file_size", 0))
            return width * height + file_size / 1024
        if modality == "audio":  # Prefer audio samples with more complete duration, sample-rate, and file information.
            duration = float(metrics.get("duration_seconds", 0))
            sample_rate = float(metrics.get("sample_rate", 0))
            file_size = float(metrics.get("file_size", 0))
            return duration * 1000 + sample_rate / 100 + file_size / 1024
        return float(item.get("meta", {}).get("quality_score", 0))


class BestTextSelector(BestSampleSelector):
    operator_name = "best_text_selector"  # Workflow config: selector operator name for choosing the kept sample in text duplicate groups.


class BestImageSelector(BestSampleSelector):
    operator_name = "best_image_selector"  # Workflow config: selector operator name for choosing the kept sample in image duplicate groups.


class BestAudioSelector(BestSampleSelector):
    operator_name = "best_audio_selector"  # Workflow config: selector operator name for choosing the kept sample in audio duplicate groups.
