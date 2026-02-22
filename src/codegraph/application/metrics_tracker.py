"""In-memory metrics tracker for token savings per session."""
from __future__ import annotations

import json
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from codegraph.domain.metrics import ToolMetricEntry, SessionMetrics


@dataclass
class _ToolAccumulator:
    calls: int = 0
    naive_tokens: int = 0
    actual_tokens: int = 0


class MetricsTracker:
    """Tracks token savings per tool call within a session."""

    def __init__(
        self,
        metrics_dir: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self._metrics_dir = metrics_dir
        self._tools: dict[str, _ToolAccumulator] = defaultdict(_ToolAccumulator)
        self._total_saved: int = 0

    @property
    def session_tokens_saved(self) -> int:
        return self._total_saved

    def record(self, tool: str, naive_tokens: int, actual_tokens: int) -> None:
        """Record a single tool call's token metrics."""
        acc = self._tools[tool]
        acc.calls += 1
        acc.naive_tokens += naive_tokens
        acc.actual_tokens += actual_tokens
        saved = max(0, naive_tokens - actual_tokens)
        self._total_saved += saved

    def get_session_metrics(self) -> SessionMetrics:
        """Return aggregated session metrics."""
        entries = [
            ToolMetricEntry(
                tool=name,
                calls=acc.calls,
                naive_tokens=acc.naive_tokens,
                actual_tokens=acc.actual_tokens,
            )
            for name, acc in sorted(self._tools.items())
        ]
        return SessionMetrics.from_entries(entries)

    def persist(self) -> None:
        """Write metrics to disk if metrics_dir is set."""
        if not self._metrics_dir:
            return
        metrics = self.get_session_metrics()
        data = {
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "tools": [
                    {
                        "tool": t.tool,
                        "calls": t.calls,
                        "naive_tokens": t.naive_tokens,
                        "actual_tokens": t.actual_tokens,
                        "tokens_saved": t.tokens_saved,
                    }
                    for t in metrics.tools
                ],
                "total_naive": metrics.total_naive,
                "total_actual": metrics.total_actual,
                "total_saved": metrics.total_saved,
                "percent_saved": round(metrics.percent_saved, 1),
            },
        }
        payload = json.dumps(data, indent=2)

        os.makedirs(self._metrics_dir, exist_ok=True)
        with open(os.path.join(self._metrics_dir, "last-session.json"), "w") as f:
            f.write(payload)

        sessions_dir = os.path.join(self._metrics_dir, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        with open(
            os.path.join(sessions_dir, f"{self.session_id}.json"), "w"
        ) as f:
            f.write(payload)

    def format_markdown(self) -> str:
        """Format metrics as a markdown table."""
        metrics = self.get_session_metrics()
        lines = [
            "\n### codegraph Session Metrics\n",
            "| Tool | Calls | Tokens saved |",
            "| :--- | :---: | :--- |",
        ]
        for t in metrics.tools:
            lines.append(f"| {t.tool} | {t.calls} | {t.tokens_saved:,} |")
        lines.append("")
        lines.append("**Totals:**")
        lines.append(f"- Tokens without codegraph: {metrics.total_naive:,}")
        lines.append(f"- Actual tokens returned:   {metrics.total_actual:,}")
        lines.append(f"- Total tokens saved:       {metrics.total_saved:,}")
        lines.append(f"- Percent saved:            {metrics.percent_saved:.1f}%")
        return "\n".join(lines)
