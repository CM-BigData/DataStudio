from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkflowNode:
    id: str  # Node ID used for workflow step dependency references.
    operator: str  # Operator name used to resolve the execution class from the registry.
    depends_on: tuple[str, ...] = field(default_factory=tuple)  # Dependency node IDs used for DAG scheduling order.
    config: dict[str, Any] = field(default_factory=dict)  # Raw node config used to pass step-level parameters.


@dataclass
class WorkflowDAG:
    nodes: list[WorkflowNode]  # DAG node list that stores every execution step in the workflow.

    def by_id(self) -> dict[str, WorkflowNode]:
        """Build an index by node ID.

        Business logic:
            1. Iterate through all nodes in the DAG.
            2. Use node IDs as dictionary keys.
            3. Return the mapping from node IDs to node objects.

        Args:
            None.

        Returns:
            dict[str, WorkflowNode]: Mapping from node IDs to node objects.

        Examples:
            >>> WorkflowDAG(nodes=[]).by_id()
            {}
        """
        return {node.id: node for node in self.nodes}


class DAGBuilder:
    def build(self, config: dict[str, Any]) -> WorkflowDAG:
        """Build a DAG from workflow configuration.

        Business logic:
            1. Read `workflow.mode`, defaulting to pipeline mode.
            2. Convert `steps` into a list of `WorkflowNode` objects.
            3. In pipeline mode, automatically depend on the previous step.
            4. In dag mode, read explicit `depends_on` values.
            5. Validate dependency correctness and cycles after construction.

        Args:
            config (dict[str, Any]): Full workflow configuration.

        Returns:
            WorkflowDAG: Validated workflow DAG.

        Examples:
            >>> dag = DAGBuilder().build({"workflow": {"mode": "pipeline"}, "steps": [{"operator": "op"}]})
            >>> dag.nodes[0].id
            'step_1'
        """
        mode = config.get("workflow", {}).get("mode", "pipeline")
        nodes: list[WorkflowNode] = []
        previous_id: str | None = None
        for index, step in enumerate(config["steps"], start=1):  # Generate stable step IDs and dependencies in config order.
            step_id = step.get("id") or f"step_{index}"
            if mode == "pipeline":  # In pipeline mode, each step depends on the previous step by default.
                depends_on = (previous_id,) if previous_id else ()
            else:
                raw_dependencies = step.get("depends_on", [])
                if isinstance(raw_dependencies, str):  # Accept a single string dependency as shorthand.
                    raw_dependencies = [raw_dependencies]
                depends_on = tuple(raw_dependencies)
            nodes.append(
                WorkflowNode(
                    id=step_id,
                    operator=step["operator"],
                    depends_on=depends_on,
                    config=step,
                )
            )
            previous_id = step_id
        dag = WorkflowDAG(nodes=nodes)
        self._validate(dag)
        return dag

    def _validate(self, dag: WorkflowDAG) -> None:
        """Validate DAG dependencies.

        Business logic:
            1. Build the node-ID index.
            2. Check whether each dependency points to an existing node.
            3. Run a topological traversal to detect cycles.

        Args:
            dag (WorkflowDAG): Workflow DAG to validate.

        Returns:
            None: No business value is returned when validation succeeds.

        Examples:
            >>> DAGBuilder()._validate(WorkflowDAG(nodes=[]))
        """
        known = dag.by_id()
        for node in dag.nodes:  # Every node dependency must be resolvable within the same DAG.
            for dependency in node.depends_on:  # Validate each dependency individually for precise errors.
                if dependency not in known:  # Unknown dependencies make scheduling impossible.
                    raise ValueError(f"Step {node.id} depends on unknown step: {dependency}")
        self._topological_order(dag)

    def _topological_order(self, dag: WorkflowDAG) -> list[WorkflowNode]:
        """Run DFS topological ordering and detect cycles.

        Business logic:
            1. Use the `visiting` set to track the current recursion stack.
            2. Use the `visited` set to track completed nodes.
            3. Recursively visit dependencies before appending the current node.
            4. Detect a cycle when a node reappears in the recursion stack.

        Args:
            dag (WorkflowDAG): Workflow DAG to sort.

        Returns:
            list[WorkflowNode]: Node list ordered by dependency.

        Examples:
            >>> DAGBuilder()._topological_order(WorkflowDAG(nodes=[]))
            []
        """
        known = dag.by_id()
        visiting: set[str] = set()
        visited: set[str] = set()
        ordered: list[WorkflowNode] = []

        def visit(node_id: str) -> None:
            """Recursively visit node dependencies.

            Business logic:
                1. Skip nodes that were already visited.
                2. Treat a repeated node in the current recursion stack as a cycle.
                3. Visit dependencies first, then append the current node to the result.

            Args:
                node_id (str): Node ID to visit.

            Returns:
                None: Updates the outer ordering state directly.

            Examples:
                >>> visit
                <function DAGBuilder._topological_order.<locals>.visit at ...>
            """
            if node_id in visited:  # Completed nodes do not need to enter recursion again.
                return
            if node_id in visiting:  # Seeing the same node again in the active recursion chain means the DAG has a cycle.
                raise ValueError(f"Workflow DAG contains a cycle at step: {node_id}")
            visiting.add(node_id)
            node = known[node_id]
            for dependency in node.depends_on:  # Dependencies must enter the ordered list first.
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)
            ordered.append(node)

        for node in dag.nodes:  # Start from every configured node so disconnected DAG components are also covered.
            visit(node.id)
        return ordered
