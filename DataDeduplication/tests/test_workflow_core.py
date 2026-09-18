import tempfile
import unittest
from pathlib import Path

from dedup_workflow_engine.cli.main import build_parser
from dedup_workflow_engine.operators.base import BaseOperator
from dedup_workflow_engine.runtime.checkpoint import CheckpointManager
from dedup_workflow_engine.runtime.dag import build_execution_plan
from dedup_workflow_engine.runtime.registry import OperatorRegistry
from dedup_workflow_engine.utilities.vector import (
    call_json_api,
    call_openai_chat,
    join_api_endpoint,
    validate_http_endpoint,
)


class WorkflowCoreTest(unittest.TestCase):
    def test_dag_execution_plan_groups_ready_steps(self) -> None:
        """Verify that a DAG execution plan groups runnable steps in the same level.

        Business logic:
            1. Build four dependent steps: load, left, right, and merge.
            2. Call build_execution_plan to produce DAG execution levels.
            3. Assert that left and right share a level and merge is placed in the final level.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> WorkflowCoreTest().test_dag_execution_plan_groups_ready_steps()  # doctest: +SKIP
        """
        plan = build_execution_plan(
            [
                {"id": "load", "operator": "A"},
                {"id": "left", "operator": "B", "depends_on": "load"},
                {"id": "right", "operator": "C", "depends_on": "load"},
                {"id": "merge", "operator": "D", "depends_on": ["left", "right"]},
            ],
            mode="dag",
        )

        self.assertEqual([[step.id for step in level] for level in plan], [["load"], ["left", "right"], ["merge"]])

    def test_checkpoint_state_round_trip(self) -> None:
        """Verify that checkpoint writes can restore the latest successful run state.

        Business logic:
            1. Create an enabled CheckpointManager.
            2. Write step state and a runtime items/state snapshot.
            3. Assert that latest_successful_state returns the written data.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> WorkflowCoreTest().test_checkpoint_state_round_trip()  # doctest: +SKIP
        """
        with tempfile.TemporaryDirectory() as tmp:
            manager = CheckpointManager(Path(tmp), enabled=True)
            manager.write_step("normalize", "TextNormalize", {"status": "success"})
            manager.write_runtime_state("normalize", [{"id": "x"}], {"duplicate_edges": [], "workflow_id": "wf"})

            latest = manager.latest_successful_state(["normalize"])

            self.assertIsNotNone(latest)
            self.assertEqual(latest[0], 0)
            self.assertEqual(latest[1]["items"], [{"id": "x"}])

    def test_join_api_endpoint(self) -> None:
        """Verify API base URL and endpoint path joining rules.

        Business logic:
            1. Cover relative endpoints against base URLs with and without trailing slashes.
            2. Cover the case where an empty endpoint returns the base URL.
            3. Cover the case where the endpoint is already an absolute URL and should be returned directly.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> WorkflowCoreTest().test_join_api_endpoint()  # doctest: +SKIP
        """
        self.assertEqual(join_api_endpoint("https://example.com/v1", "/embeddings"), "https://example.com/v1/embeddings")
        self.assertEqual(join_api_endpoint("https://example.com/v1/", "embeddings"), "https://example.com/v1/embeddings")
        self.assertEqual(join_api_endpoint("https://example.com/v1", ""), "https://example.com/v1")
        self.assertEqual(
            join_api_endpoint("https://example.com/v1", "https://other.example.com/embed"),
            "https://other.example.com/embed",
        )

    def test_http_endpoint_validation_accepts_supported_urls(self) -> None:
        """Verify that valid HTTP(S) endpoints, hosts, and ports remain supported."""
        self.assertEqual(validate_http_endpoint("http://23.254.197.253:8080/v1"), "http://23.254.197.253:8080/v1")
        self.assertEqual(validate_http_endpoint("https://example.com/api"), "https://example.com/api")

    def test_api_calls_reject_unsafe_endpoint_schemes(self) -> None:
        """Verify that local files and unsupported URL schemes cannot reach urlopen."""
        unsafe_urls = (
            "file:///tmp/local.json",
            "ftp://example.com/data.json",
            "https:///missing-host",
            " https://example.com/api",
            "https://example.com/api\n",
            "https://example.com:70000/api",
        )
        for url in unsafe_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_http_endpoint(url)

        with self.assertRaises(ValueError):
            call_json_api("file:///tmp/local.json", "key", {})
        with self.assertRaises(ValueError):
            call_openai_chat("file:///tmp/local.json", "key", "model", [])

    def test_registry_requires_snake_case(self) -> None:
        """Verify that the registry rejects non-snake_case operator names.

        Business logic:
            1. Build valid and invalid test operator classes.
            2. Register the valid operator and confirm its class-name alias is unavailable.
            3. Assert that registering the invalid operator raises ValueError.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> WorkflowCoreTest().test_registry_requires_snake_case()  # doctest: +SKIP
        """

        class DemoOperator(BaseOperator):
            operator_name = "demo_operator"  # operator_name: valid snake_case test operator registration name

        class BadOperator(BaseOperator):
            operator_name = "BadOperator"  # operator_name: invalid PascalCase test operator registration name

        registry = OperatorRegistry()
        registry.register(DemoOperator)
        with self.assertRaises(KeyError):
            registry.create("DemoOperator", {})
        with self.assertRaises(ValueError):
            registry.register(BadOperator)

    def test_run_parser_accepts_resume_flag(self) -> None:
        """Verify that the dedup run command accepts the resume flag.

        Business logic:
            1. Build the command-line parser.
            2. Parse the run subcommand with --resume.
            3. Assert that the resume flag is written into the argparse namespace.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> WorkflowCoreTest().test_run_parser_accepts_resume_flag()  # doctest: +SKIP
        """
        args = build_parser().parse_args(["run", "-c", "workflow.yaml", "--resume"])
        self.assertTrue(args.resume)


if __name__ == "__main__":
    unittest.main()
