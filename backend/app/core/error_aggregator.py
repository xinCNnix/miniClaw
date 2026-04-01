"""Error aggregation and alerting system.

Tracks error frequency and triggers alerts when thresholds are exceeded.
"""

import time
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ErrorRecord:
    """A single error occurrence."""
    error_type: str
    message: str
    timestamp: float
    count: int = 1
    last_occurrence: float = 0.0
    context: dict = field(default_factory=dict)


class ErrorAggregator:
    """Aggregates errors by type and triggers alerts when threshold is exceeded."""

    def __init__(self, threshold: int = 10, window: int = 60):
        self.threshold = threshold
        self.window = window
        self._errors: dict[str, ErrorRecord] = {}
        self._recent: list[tuple[str, float]] = []
        self._lock = threading.Lock()

    def record_error(
        self,
        error_type: str,
        message: str,
        context: Optional[dict] = None,
    ) -> Optional[dict]:
        """Record an error occurrence. Returns alert info if threshold exceeded."""
        now = time.time()
        key = f"{error_type}:{message[:100]}"

        with self._lock:
            # Cleanup old entries outside window
            cutoff = now - self.window
            self._recent = [(k, t) for k, t in self._recent if t > cutoff]

            # Add this occurrence
            self._recent.append((key, now))
            count_in_window = sum(1 for k, t in self._recent if k == key)

            # Update or create error record
            if key in self._errors:
                record = self._errors[key]
                record.count += 1
                record.last_occurrence = now
                if context:
                    record.context.update(context)
            else:
                self._errors[key] = ErrorRecord(
                    error_type=error_type,
                    message=message,
                    timestamp=now,
                    last_occurrence=now,
                    context=context or {},
                )

            # Check threshold
            if count_in_window >= self.threshold and count_in_window % self.threshold == 0:
                alert = {
                    "alert": True,
                    "error_type": error_type,
                    "message": message,
                    "count": count_in_window,
                    "window_seconds": self.window,
                    "threshold": self.threshold,
                }
                logger.warning(
                    f"[ErrorAggregator] Alert: {error_type} occurred "
                    f"{count_in_window} times in {self.window}s window"
                )
                return alert

        return None

    def get_stats(self) -> dict:
        """Get aggregation statistics."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window
            recent = [(k, t) for k, t in self._recent if t > cutoff]
            return {
                "total_error_types": len(self._errors),
                "recent_count": len(recent),
                "window_seconds": self.window,
                "threshold": self.threshold,
                "top_errors": sorted(
                    [
                        {"key": k, "count": sum(1 for rk, _ in recent if rk == k), "type": r.error_type}
                        for k, r in self._errors.items()
                    ],
                    key=lambda x: x["count"],
                    reverse=True,
                )[:10],
            }

    def reset(self):
        """Reset all aggregated data."""
        with self._lock:
            self._errors.clear()
            self._recent.clear()


# Global singleton
_aggregator: Optional[ErrorAggregator] = None


def get_error_aggregator() -> ErrorAggregator:
    global _aggregator
    if _aggregator is None:
        from app.config import get_settings
        settings = get_settings()
        _aggregator = ErrorAggregator(
            threshold=getattr(settings, "error_alert_threshold", 10),
            window=getattr(settings, "error_alert_window", 60),
        )
    return _aggregator


class ErrorAggregationHandler(logging.Handler):
    """Logging handler that feeds ERROR+ records into ErrorAggregator."""

    def __init__(self, aggregator: Optional[ErrorAggregator] = None):
        super().__init__(logging.ERROR)
        self.aggregator = aggregator or get_error_aggregator()

    def emit(self, record: logging.LogRecord):
        try:
            if record.exc_info and record.exc_info[0]:
                error_type = record.exc_info[0].__name__
            else:
                error_type = "Unknown"

            self.aggregator.record_error(
                error_type=error_type,
                message=record.getMessage(),
                context={
                    "logger": record.name,
                    "module": record.module,
                    "line": record.lineno,
                },
            )
        except Exception:
            self.handleError(record)
