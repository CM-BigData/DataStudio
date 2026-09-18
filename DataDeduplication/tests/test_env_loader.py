import os
import tempfile
import unittest
from pathlib import Path

from dedup_workflow_engine.runtime.env import load_local_env_files


class EnvLoaderTest(unittest.TestCase):
    def test_loads_local_powershell_env_file(self) -> None:
        """Verify that a local PowerShell env file is loaded into process environment variables.

        Business logic:
            1. Temporarily remove TEXT_RERANK_MODEL to isolate external environment state.
            2. Create configs/api_env.local.ps1 and write the model environment variable.
            3. Call the loader and assert the environment value and loaded file path.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> EnvLoaderTest().test_loads_local_powershell_env_file()  # doctest: +SKIP
        """
        original = os.environ.pop("TEXT_RERANK_MODEL", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "configs").mkdir()
                (root / "configs" / "api_env.local.ps1").write_text(
                    '$env:TEXT_RERANK_MODEL = "qwen3.6-plus"\n',
                    encoding="utf-8",
                )

                loaded = load_local_env_files(root)

                self.assertEqual(os.environ["TEXT_RERANK_MODEL"], "qwen3.6-plus")
                self.assertEqual(loaded, [root / "configs" / "api_env.local.ps1"])
        finally:
            if original is None:  # Workflow config: restore the variable to an unset state when it did not exist originally, avoiding pollution of later tests.
                os.environ.pop("TEXT_RERANK_MODEL", None)
            else:
                os.environ["TEXT_RERANK_MODEL"] = original


if __name__ == "__main__":
    unittest.main()
