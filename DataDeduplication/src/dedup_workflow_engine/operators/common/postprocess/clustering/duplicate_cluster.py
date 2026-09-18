from __future__ import annotations

from collections import defaultdict
from typing import Any

from dedup_workflow_engine.operators.base import BaseOperator


class DuplicateEdgeFusionOperator(BaseOperator):
    operator_name = "duplicate_edge_fusion"  # Workflow config: generic operator name for fusing duplicate candidate edges across operators.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Fuse duplicate candidate edges produced by different operators.

        Business logic:
            1. Aggregate duplicate_edges by undirected sample pair.
            2. Keep the highest score, all reasons, and all operators for the same pair.
            3. Mark the fused edge as exact_duplicate when any source edge is exact_duplicate.

        Args:
            items (list[dict[str, Any]]): Workflow sample list.
            context (dict[str, Any]): Shared workflow context containing duplicate_edges.

        Returns:
            list[dict[str, Any]]: Original sample list.

        Examples:
            >>> context = {"duplicate_edges": []}
            >>> DuplicateEdgeFusionOperator({}).process_dataset([], context)
            []
        """
        fused: dict[tuple[str, str], dict[str, Any]] = {}
        for edge in context.get("duplicate_edges", []):  # Merge every edge by its sorted sample pair.
            key = tuple(sorted([edge["left_id"], edge["right_id"]]))
            if key not in fused:  # Create a fused record when the pair appears for the first time.
                fused[key] = {
                    "left_id": key[0],
                    "right_id": key[1],
                    "score": edge.get("score", 0),
                    "duplicate_type": edge.get("duplicate_type", "near_duplicate"),
                    "reasons": [edge.get("reason", "unknown")],
                    "operators": [edge.get("operator", "unknown")],
                }
                continue
            fused_edge = fused[key]
            fused_edge["score"] = max(float(fused_edge["score"]), float(edge.get("score", 0)))
            reason = edge.get("reason", "unknown")
            operator = edge.get("operator", "unknown")
            if reason not in fused_edge["reasons"]:  # Keep each reason only once.
                fused_edge["reasons"].append(reason)
            if operator not in fused_edge["operators"]:  # Keep each operator name only once.
                fused_edge["operators"].append(operator)
            if edge.get("duplicate_type") == "exact_duplicate":  # Exact duplicates take priority over near duplicates.
                fused_edge["duplicate_type"] = "exact_duplicate"

        context["duplicate_edges"] = list(fused.values())
        return items


class DuplicateClusterOperator(BaseOperator):
    operator_name = "duplicate_cluster"  # Workflow config: operator name for aggregating duplicate edges into duplicate groups.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate duplicate groups from duplicate edges.

        Business logic:
            1. Use union-find to connect edges whose score reaches min_score into clusters.
            2. Generate one duplicate group for each connected component whose member count is greater than 1.
            3. Write the group id back into each member sample's intermediate fields.

        Args:
            items (list[dict[str, Any]]): Workflow sample list.
            context (dict[str, Any]): Shared workflow context containing duplicate_edges.

        Returns:
            list[dict[str, Any]]: Sample list updated with duplicate_group_id.

        Examples:
            >>> DuplicateClusterOperator({}).process_dataset([], {"duplicate_edges": []})
            []
        """
        min_score = float(self.config.get("min_score", 0.75))
        ids = [str(item["id"]) for item in items]
        parent = {item_id: item_id for item_id in ids}

        def find(item_id: str) -> str:
            """Find the union-find root node for a sample.

            Business logic:
                1. Follow parent pointers from the current item_id to the root node.
                2. Apply path compression during lookup.
                3. Return the compressed root id.

            Args:
                item_id (str): Sample id.

            Returns:
                str: Root id of the sample's connected component.

            Examples:
                >>> find("x")  # doctest: +SKIP
                'x'
            """
            while parent[item_id] != item_id:  # Path compression reduces the cost of later find calls.
                parent[item_id] = parent[parent[item_id]]
                item_id = parent[item_id]
            return item_id

        def union(left: str, right: str) -> None:
            """Merge the union-find connected components of two samples.

            Business logic:
                1. Find the root nodes of the left and right samples.
                2. When the roots differ, attach the right root to the left root.
                3. Do nothing when both samples already share the same root.

            Args:
                left (str): Left sample id.
                right (str): Right sample id.

            Returns:
                None: Updates the parent mapping in place.

            Examples:
                >>> union("a", "b")  # doctest: +SKIP
            """
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:  # Only different connected components need merging.
                parent[right_root] = left_root

        eligible_edges = []
        for edge in context.get("duplicate_edges", []):  # Only use edges that meet the threshold for clustering.
            if float(edge.get("score", 0)) < min_score:  # Low-score candidates should not enter final duplicate groups.
                continue
            left = str(edge["left_id"])
            right = str(edge["right_id"])
            if left in parent and right in parent:  # Both samples referenced by an edge must exist in the current dataset.
                union(left, right)
                eligible_edges.append(edge)

        members: dict[str, list[str]] = defaultdict(list)
        for item_id in ids:  # Assign each sample to its union-find root node.
            members[find(item_id)].append(item_id)

        edges_by_pair = {(edge["left_id"], edge["right_id"]): edge for edge in eligible_edges}
        groups = []
        index = 1
        for member_ids in members.values():  # Generate at most one duplicate group per connected component.
            if len(member_ids) < 2:  # A single-sample component is not a duplicate group.
                continue
            member_ids = sorted(member_ids)
            group_edges = [
                edge
                for key, edge in edges_by_pair.items()
                if key[0] in member_ids and key[1] in member_ids  # Collect only edges between members inside the group.
            ]
            reasons = sorted({reason for edge in group_edges for reason in edge.get("reasons", [edge.get("reason", "unknown")])})
            duplicate_type = "exact_duplicate" if any(edge.get("duplicate_type") == "exact_duplicate" for edge in group_edges) else "near_duplicate"
            score = max([float(edge.get("score", 0)) for edge in group_edges] or [0])
            group_id = f"dup_group_{index:06d}"
            groups.append(
                {
                    "group_id": group_id,
                    "modality": context.get("modality", "unknown"),
                    "duplicate_type": duplicate_type,
                    "member_ids": member_ids,
                    "score": round(score, 6),
                    "reasons": reasons,
                    "edges": group_edges,
                }
            )
            for item in items:  # Write the group id back to member samples for selector and inspect commands.
                if str(item["id"]) in member_ids:  # Mark only the members of the current duplicate group.
                    item.setdefault("intermediate", {})["duplicate_group_id"] = group_id
            index += 1

        context["duplicate_groups"] = groups
        return items
