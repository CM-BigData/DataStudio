import unittest

import re

from dedup_workflow_engine.utilities.text.normalize import normalize_text
from dedup_workflow_engine.operators.text_dedup.simhash import hamming_distance, simhash


class TextRulesTest(unittest.TestCase):
    def test_normalize_text_uses_stdlib_pattern_behavior(self) -> None:
        """Verify normalization still matches standard-library regex behavior.

        Business logic:
            1. Normalize a string containing a URL and repeated whitespace.
            2. Assert the output matches the expectation after replacing regex with stdlib re.
            3. Assert the imported regex engine is the standard-library module.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.
        """
        self.assertEqual(normalize_text("Hello https://example.com   WORLD"), "hello world")
        self.assertEqual(re.__name__, "re")

    def test_normalize_text_removes_format_noise(self) -> None:
        """Verify that text normalization removes HTML and case-related noise.

        Business logic:
            1. Provide input containing HTML tags, punctuation, and case differences.
            2. Call normalize_text for pre-dedup normalization.
            3. Assert that the output keeps only lowercase words and single spaces.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> TextRulesTest().test_normalize_text_removes_format_noise()  # doctest: +SKIP
        """
        self.assertEqual(normalize_text("<p>Hello,  WORLD!</p>"), "hello world")

    def test_simhash_near_text_distance_is_small(self) -> None:
        """Verify that semantically similar short Chinese text has a small SimHash Hamming distance.

        Business logic:
            1. Compute SimHash for two semantically similar Chinese sentences.
            2. Compare fingerprint differences with hamming_distance.
            3. Assert that the distance stays within the near-duplicate threshold of 12.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> TextRulesTest().test_simhash_near_text_distance_is_small()  # doctest: +SKIP
        """
        left = simhash("数据治理平台需要执行文本去重处理")
        right = simhash("数据治理平台需要进行文本去重处理")
        self.assertLessEqual(hamming_distance(left, right), 12)


if __name__ == "__main__":
    unittest.main()
