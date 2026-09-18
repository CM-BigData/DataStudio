import json
import tempfile
import unittest
from pathlib import Path

from dedup_workflow_engine.runtime.executor import WorkflowExecutor
from dedup_workflow_engine.runtime.registry import build_default_registry


class ParallelExecutorTest(unittest.TestCase):
    def test_end_to_end_text_dedup_matches_expected_output(self) -> None:
        """Verify that the public text_dedup operator produces the expected text-dedup result.

        Business logic:
            1. Build temporary input containing two duplicate texts and one different text.
            2. Run the text-dedup workflow through a single public end-to-end operator.
            3. Assert that duplicate-group count, removed count, operator logs, and checkpoints are correct.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> ParallelExecutorTest().test_end_to_end_text_dedup_matches_expected_output()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.jsonl"
            run_dir = root / "run"
            rows = [
                {"id": "t1", "modality": "text", "payload": {"text": "alpha beta gamma duplicate sample"}},
                {"id": "t2", "modality": "text", "payload": {"text": "alpha beta gamma duplicate sample"}},
                {"id": "t3", "modality": "text", "payload": {"text": "completely different record"}},
            ]
            input_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            config = {
                "workflow": {"id": "text_dedup_test", "modality": "text", "mode": "pipeline", "checkpoint": True},
                "runtime": {"checkpoint": True},
                "input": {"type": "jsonl", "path": str(input_path)},
                "output": {"run_dir": str(run_dir)},
                "steps": [
                    {
                        "id": "text_dedup",
                        "operator": "text_dedup",
                        "params": {
                            "profile": "basic",
                            "methods": {"simhash": {"max_hamming_distance": 3}},
                            "thresholds": {"cluster_min_score": 0.55},
                        },
                    },
                ],
            }

            summary = WorkflowExecutor(config, build_default_registry()).run()

            self.assertEqual(summary["duplicate_group_count"], 1)
            self.assertEqual(summary["removed_count"], 1)
            logs = [json.loads(line) for line in (run_dir / "operator_logs.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["operator"] for row in logs], ["text_dedup"])
            checkpoint = json.loads((run_dir / "checkpoints" / "text_dedup.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["operator"], "text_dedup")


if __name__ == "__main__":
    unittest.main()
