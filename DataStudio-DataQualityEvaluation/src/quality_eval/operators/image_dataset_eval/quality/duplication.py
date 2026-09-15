from quality_eval.utilities.image.shared import *  # noqa: F403


class ImageDupEvalOperator(BaseOperator):
    operator_name: str = "image_dup_eval"  # Registered operator name used to detect duplicate images across samples.

    def setup(self, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        """Build the duplicate-image detection index.

        Business logic:
            1. Initialize the set of duplicate-image sample IDs.
            2. Iterate through all image samples and read their image paths.
            3. Compute a content hash for each existing image.
            4. Mark both the current sample and the first-seen sample when the hash repeats.
            5. Write duplicate IDs into context for reporting.

        Args:
            items (list[dict[str, Any]]): All image samples in this workflow run.
            context (dict[str, Any]): Context shared across operators.

        Returns:
            None: Writes directly to the instance duplicate set and shared context.

        Examples:
            >>> op = ImageDupEvalOperator({})
            >>> op.setup([], {})
            >>> op.duplicates
            set()
        """
        self.duplicates: set[str] = set()  # Duplicate-image sample ID set used by `process` to mark `duplicate_image`.
        seen: dict[str, str] = {}
        for item in items:  # Cross-sample duplicates can only be identified from a full-sample index.
            image_path = item.get("payload", {}).get("image_path")
            image_hash = None
            if image_path and Path(image_path).exists():  # Content hashes can be computed only for files that actually exist.
                try:
                    with Image.open(image_path) as image:
                        image_hash = _average_hash(image)
                except Exception:
                    image_hash = None
            if not image_hash:  # Unreadable-image issues are handled by the decode operator, so this operator skips indexing.
                continue
            if image_hash in seen:  # When the same hash appears again, both samples should enter the duplicate list.
                self.duplicates.add(item["id"])
                self.duplicates.add(seen[image_hash])
            else:
                seen[image_hash] = item["id"]
        context["image_duplicate_ids"] = sorted(self.duplicates)

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Mark whether one sample is a duplicate image.

        Business logic:
            1. Look up the current sample in the duplicate-ID set built during setup.
            2. Append the `duplicate_image` issue and record the metric as True for duplicate images.
            3. Record the metric as False for non-duplicate images.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with duplicate metrics and issues written back.

        Examples:
            >>> op = ImageDupEvalOperator({})
            >>> op.duplicates = {"img1"}
            >>> op.process({"id": "img1", "metrics": {}, "issues": []})["issues"]
            ['duplicate_image']
        """
        if item.get("id") in self.duplicates:  # Append a sample-level issue when the full-sample index already confirmed duplication.
            self.add_issue(item, "duplicate_image")
            self.metric(item, "is_duplicate", True)
        else:
            self.metric(item, "is_duplicate", False)
        return item
