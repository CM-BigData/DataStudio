from denoise_workflow_engine.utilities.text.base import *  # noqa: F403

class SensitiveContentFilter(TextOperator):
    operator_name: str = "sensitive_content_filter"  # Operator identifier used by workflow configs and the registry.

    DEFAULT_CATEGORIES: dict[str, list[str]] = {  # Local keyword rules mapped by risk category.
        "violence": ["暴恐", "恐怖袭击", "极端组织"],
        "porn": ["涉黄", "色情", "裸聊"],
        "gambling": ["赌博", "博彩", "六合彩"],
        "fraud": ["诈骗", "刷单返利", "套现", "杀猪盘"],
        "abuse": ["辱骂", "人身攻击"],
        "spam": ["加微信", "推广返佣", "点击领取"],
    }

    def process(self, item: dict) -> dict:
        """Detect risky sensitive-content keywords in one text sample.

        Business logic:
            1. Load category-specific keyword lists from config or defaults.
            2. Normalize the text and search for keyword hits by category.
            3. Record issues and detection metrics when any category is hit.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out text processing.
            return item
        categories = self.config.get("categories") or self.DEFAULT_CATEGORIES
        keywords = self.config.get("keywords")
        text = self.get_text(item)
        normalized_text = self._normalize_text(text)
        category_hits: dict[str, list[str]] = {}
        if keywords:  # Replace default categories when custom keywords are configured.
            categories = {"custom": keywords}
        for category, category_keywords in categories.items():  # Scan the normalized text against each category keyword list.
            hits = [keyword for keyword in category_keywords if self._normalize_text(keyword) in normalized_text]
            if hits:  # Record per-category evidence when matches are found.
                category_hits[str(category)] = hits
        if category_hits:  # Add a sensitive-risk issue when any category is hit.
            self.add_issue(item, "sensitive_risk")
            self.set_metric(item, "sensitive_categories", category_hits)
            self.set_metric(item, "sensitive_detection_method", "normalized_keyword_rules")
            self.set_metric(item, "sensitive_detection_confidence", 0.45)
        return item

    def _normalize_text(self, text: str) -> str:
        """Normalize text for sensitive-keyword matching.

        Business logic:
            1. Apply NFKC normalization and lowercase conversion.
            2. Remove whitespace and non-word separators.
            3. Return the compact normalized text used for matching.

        Args:
                text (str): Input text content.

        Returns:
            str: Normalized text used for keyword matching.

        Examples:
            >>> _normalize_text
            _normalize_text
        """
        normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
        return re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)
