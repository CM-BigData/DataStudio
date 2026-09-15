from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class MetricsCollector:
    started_at: float = field(default_factory=time.perf_counter)  # Metric start time used to compute elapsed time and throughput.
    processed_count: int = 0  # Number of processed samples used to summarize progress.
    failed_count: int = 0  # Number of failed samples caused by operator exceptions.
    latency_ms: list[float] = field(default_factory=list)  # Operator latency list used to compute average latency.
    issue_distribution: Counter[str] = field(default_factory=Counter)  # Issue distribution counter used in summary reporting.

    def record_sample(self, result: dict) -> None:
        """Record a sample-level execution result.

        Business logic:
            1. Increment the processed sample count.
            2. Increment the failed count when the sample status is `failed`.
            3. Accumulate sample issue codes into the issue distribution.

        Args:
            result (dict): Result of a single sample.

        Returns:
            None: Updates the metrics collector state directly.

        Examples:
            >>> metrics = MetricsCollector()
            >>> metrics.record_sample({"issues": ["empty_text"]})
        """
        self.processed_count += 1
        if result.get("status") == "failed":  # Failed status comes from operator exceptions captured by the executor.
            self.failed_count += 1
        self.issue_distribution.update(result.get("issues", []))

    def record_operator_latency(self, latency_ms: float) -> None:
        """Record the latency of one operator execution.

        Business logic:
            1. Receive the latency in milliseconds computed by the executor.
            2. Append it to the latency list.
            3. Let `snapshot` use it to compute average latency.

        Args:
            latency_ms (float): Processing time of one operator run.

        Returns:
            None: Updates the latency list directly.

        Examples:
            >>> metrics = MetricsCollector()
            >>> metrics.record_operator_latency(1.5)
        """
        self.latency_ms.append(latency_ms)

    def snapshot(self) -> dict:
        """Generate the current metrics snapshot.

        Business logic:
            1. Compute the total elapsed time since initialization.
            2. Compute average latency from the operator latency list.
            3. Compute throughput from the processed sample count.
            4. Return a serializable metrics dictionary.

        Args:
            None.

        Returns:
            dict: Metrics snapshot of the current task.

        Examples:
            >>> snapshot = MetricsCollector().snapshot()
            >>> "throughput_qps" in snapshot
            True
        """
        elapsed_ms = max((time.perf_counter() - self.started_at) * 1000, 0.001)
        avg_latency = round(sum(self.latency_ms) / len(self.latency_ms), 2) if self.latency_ms else 0
        throughput = round(self.processed_count / (elapsed_ms / 1000), 4)
        return {
            "processed_count": self.processed_count,
            "failed_count": self.failed_count,
            "avg_latency_ms": avg_latency,
            "throughput_qps": throughput,
            "issue_distribution": dict(self.issue_distribution),
            "elapsed_ms": elapsed_ms,
        }
