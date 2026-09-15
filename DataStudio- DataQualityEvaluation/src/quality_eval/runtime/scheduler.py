from __future__ import annotations

from .dag import WorkflowDAG, WorkflowNode


class TaskScheduler:
    def order(self, dag: WorkflowDAG) -> list[WorkflowNode]:
        """Generate an executable node order from dependencies.

        Business logic:
            1. Build an index from node IDs to node objects.
            2. Maintain the remaining-node set and completed-node set.
            3. Select nodes whose dependencies are already completed in each round.
            4. Raise a dependency error when no node is executable.

        Args:
            dag (WorkflowDAG): Validated workflow DAG.

        Returns:
            list[WorkflowNode]: Node list ordered by dependency.

        Examples:
            >>> TaskScheduler().order(WorkflowDAG(nodes=[]))
            []
        """
        known = dag.by_id()
        remaining = {node.id for node in dag.nodes}
        completed: set[str] = set()
        ordered: list[WorkflowNode] = []

        while remaining:
            ready = [
                known[node_id]
                for node_id in sorted(remaining)  # Sorting keeps the execution order stable among ready nodes at the same layer.
                if set(known[node_id].depends_on).issubset(completed)
            ]
            if not ready:  # A cycle or missing dependency exists when no remaining node can run.
                raise ValueError("Workflow DAG cannot be scheduled. Check dependencies.")
            for node in ready:  # Append ready nodes one by one into the final execution order.
                ordered.append(node)
                completed.add(node.id)
                remaining.remove(node.id)
        return ordered
