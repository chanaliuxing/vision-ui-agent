#!/usr/bin/env python3
"""
Telemetry and Metrics Collection
Comprehensive monitoring, metrics, and error tracking system
"""

import time
import uuid
from collections import defaultdict, deque
from typing import Dict, Any, Optional, List, Deque
import threading
import logging
import json
import os

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and aggregates application metrics"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.lock = threading.Lock()

        # Request metrics
        self.request_counts = defaultdict(int)
        self.request_latencies: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=max_history))
        self.error_counts = defaultdict(int)

        # Cache metrics
        self.cache_hits = 0
        self.cache_misses = 0

        # Service metrics
        self.service_calls = defaultdict(int)
        self.service_latencies: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=max_history))
        self.service_errors = defaultdict(int)

        # Start time for uptime calculation
        self.start_time = time.time()

    def record_request(self, endpoint: str, latency_ms: float, success: bool = True):
        """Record a request metric"""
        with self.lock:
            self.request_counts[endpoint] += 1
            self.request_latencies[endpoint].append(latency_ms)

            if not success:
                self.error_counts[endpoint] += 1

    def record_cache_hit(self, hit: bool):
        """Record cache hit/miss"""
        with self.lock:
            if hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

    def record_service_call(self, service: str, latency_ms: float, success: bool = True):
        """Record service call metric"""
        with self.lock:
            self.service_calls[service] += 1
            self.service_latencies[service].append(latency_ms)

            if not success:
                self.service_errors[service] += 1

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        with self.lock:
            # Calculate percentiles for request latencies
            request_metrics = {}
            for endpoint, latencies in self.request_latencies.items():
                if latencies:
                    sorted_latencies = sorted(latencies)
                    n = len(sorted_latencies)
                    request_metrics[endpoint] = {
                        "count": self.request_counts[endpoint],
                        "error_count": self.error_counts[endpoint],
                        "error_rate": self.error_counts[endpoint] / max(1, self.request_counts[endpoint]),
                        "latency_ms": {
                            "p50": sorted_latencies[int(n * 0.5)] if n > 0 else 0,
                            "p95": sorted_latencies[int(n * 0.95)] if n > 0 else 0,
                            "p99": sorted_latencies[int(n * 0.99)] if n > 0 else 0,
                            "avg": sum(sorted_latencies) / n if n > 0 else 0,
                            "max": max(sorted_latencies) if n > 0 else 0
                        }
                    }

            # Calculate service metrics
            service_metrics = {}
            for service, latencies in self.service_latencies.items():
                if latencies:
                    sorted_latencies = sorted(latencies)
                    n = len(sorted_latencies)
                    service_metrics[service] = {
                        "call_count": self.service_calls[service],
                        "error_count": self.service_errors[service],
                        "error_rate": self.service_errors[service] / max(1, self.service_calls[service]),
                        "latency_ms": {
                            "p50": sorted_latencies[int(n * 0.5)] if n > 0 else 0,
                            "p95": sorted_latencies[int(n * 0.95)] if n > 0 else 0,
                            "avg": sum(sorted_latencies) / n if n > 0 else 0
                        }
                    }

            # Cache metrics
            total_cache_requests = self.cache_hits + self.cache_misses
            cache_hit_rate = self.cache_hits / max(1, total_cache_requests)

            # System metrics
            uptime_seconds = time.time() - self.start_time

            return {
                "system": {
                    "uptime_seconds": uptime_seconds,
                    "start_time": self.start_time
                },
                "requests": request_metrics,
                "services": service_metrics,
                "cache": {
                    "hits": self.cache_hits,
                    "misses": self.cache_misses,
                    "hit_rate": cache_hit_rate,
                    "total_requests": total_cache_requests
                }
            }

    def reset_metrics(self):
        """Reset all metrics (for testing)"""
        with self.lock:
            self.request_counts.clear()
            self.request_latencies.clear()
            self.error_counts.clear()
            self.cache_hits = 0
            self.cache_misses = 0
            self.service_calls.clear()
            self.service_latencies.clear()
            self.service_errors.clear()
            self.start_time = time.time()


class RequestTracker:
    """Tracks individual request lifecycle and context"""

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def start_request(self, req_id: str, endpoint: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start tracking a request"""
        request_info = {
            "req_id": req_id,
            "endpoint": endpoint,
            "start_time": time.time(),
            "context": context or {},
            "stages": [],
            "errors": []
        }

        with self.lock:
            self.active_requests[req_id] = request_info

        return request_info

    def add_stage(self, req_id: str, stage_name: str, latency_ms: Optional[float] = None):
        """Add a stage to request tracking"""
        with self.lock:
            if req_id in self.active_requests:
                stage_info = {
                    "name": stage_name,
                    "timestamp": time.time(),
                    "latency_ms": latency_ms
                }
                self.active_requests[req_id]["stages"].append(stage_info)

                # Record service call metric if latency provided
                if latency_ms is not None:
                    self.metrics.record_service_call(stage_name, latency_ms, success=True)

    def add_error(self, req_id: str, error: str, stage: Optional[str] = None):
        """Add an error to request tracking"""
        with self.lock:
            if req_id in self.active_requests:
                error_info = {
                    "error": error,
                    "stage": stage,
                    "timestamp": time.time()
                }
                self.active_requests[req_id]["errors"].append(error_info)

                # Record service error if stage provided
                if stage:
                    self.metrics.record_service_call(stage, 0, success=False)

    def finish_request(self, req_id: str, success: bool = True) -> Optional[Dict[str, Any]]:
        """Finish tracking a request"""
        with self.lock:
            if req_id not in self.active_requests:
                return None

            request_info = self.active_requests[req_id]
            request_info["end_time"] = time.time()
            request_info["success"] = success
            request_info["total_latency_ms"] = (request_info["end_time"] - request_info["start_time"]) * 1000

            # Record request metrics
            self.metrics.record_request(
                request_info["endpoint"],
                request_info["total_latency_ms"],
                success
            )

            # Remove from active requests
            finished_request = self.active_requests.pop(req_id)

            return finished_request

    def get_active_requests(self) -> Dict[str, Dict[str, Any]]:
        """Get currently active requests"""
        with self.lock:
            return self.active_requests.copy()


class ErrorTracker:
    """Tracks and categorizes errors"""

    def __init__(self, max_errors: int = 500):
        self.max_errors = max_errors
        self.errors: Deque[Dict[str, Any]] = deque(maxlen=max_errors)
        self.error_counts = defaultdict(int)
        self.lock = threading.Lock()

    def record_error(self, error_code: str, error_message: str,
                    context: Optional[Dict[str, Any]] = None,
                    req_id: Optional[str] = None):
        """Record an error occurrence"""
        error_info = {
            "error_code": error_code,
            "error_message": error_message,
            "timestamp": time.time(),
            "context": context or {},
            "req_id": req_id,
            "id": str(uuid.uuid4())
        }

        with self.lock:
            self.errors.append(error_info)
            self.error_counts[error_code] += 1

        logger.error(f"Error recorded: {error_code} - {error_message} (req_id: {req_id})")

    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent errors"""
        with self.lock:
            return list(self.errors)[-limit:]

    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        with self.lock:
            total_errors = len(self.errors)
            return {
                "total_errors": total_errors,
                "error_counts": dict(self.error_counts),
                "recent_errors": len([e for e in self.errors if time.time() - e["timestamp"] < 3600])  # Last hour
            }


class TelemetrySystem:
    """Main telemetry system coordinating all monitoring components"""

    def __init__(self):
        self.metrics = MetricsCollector()
        self.requests = RequestTracker(self.metrics)
        self.errors = ErrorTracker()

        # Configuration
        self.export_enabled = os.getenv("TELEMETRY_EXPORT_ENABLED", "false").lower() == "true"
        self.export_interval = int(os.getenv("TELEMETRY_EXPORT_INTERVAL", "60"))
        self.export_path = os.getenv("TELEMETRY_EXPORT_PATH", "/tmp/telemetry.jsonl")

        logger.info("Telemetry system initialized")

    def start_request_tracking(self, req_id: str, endpoint: str,
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start tracking a request"""
        return self.requests.start_request(req_id, endpoint, context)

    def add_request_stage(self, req_id: str, stage_name: str, latency_ms: Optional[float] = None):
        """Add a stage to request tracking"""
        self.requests.add_stage(req_id, stage_name, latency_ms)

    def add_request_error(self, req_id: str, error: str, stage: Optional[str] = None):
        """Add an error to request tracking"""
        self.requests.add_error(req_id, error, stage)

    def finish_request_tracking(self, req_id: str, success: bool = True) -> Optional[Dict[str, Any]]:
        """Finish tracking a request"""
        return self.requests.finish_request(req_id, success)

    def record_error(self, error_code: str, error_message: str,
                    context: Optional[Dict[str, Any]] = None,
                    req_id: Optional[str] = None):
        """Record an error"""
        self.errors.record_error(error_code, error_message, context, req_id)

    def record_cache_operation(self, hit: bool):
        """Record cache hit/miss"""
        self.metrics.record_cache_hit(hit)

    def add_kv(self, req_id: str, kv_data: Dict[str, Any]):
        """Add key-value data to request context (compatibility method)"""
        # For compatibility with orchestrator, we'll add this data as context
        # This method ensures backward compatibility while we transition to the new telemetry system
        with self.requests.lock:
            if req_id in self.requests.active_requests:
                if "llm_data" not in self.requests.active_requests[req_id]["context"]:
                    self.requests.active_requests[req_id]["context"]["llm_data"] = {}
                self.requests.active_requests[req_id]["context"]["llm_data"].update(kv_data)

        # Also log this for debugging
        logger.debug(f"Added telemetry KV data for {req_id}: {kv_data}")

    def get_health_status(self) -> Dict[str, Any]:
        """Get system health status"""
        metrics = self.metrics.get_metrics_summary()
        error_stats = self.errors.get_error_stats()
        active_requests = len(self.requests.get_active_requests())

        # Determine health based on error rates and active requests
        healthy = True
        issues = []

        # Check error rates
        for endpoint, stats in metrics.get("requests", {}).items():
            if stats.get("error_rate", 0) > 0.1:  # 10% error rate threshold
                healthy = False
                issues.append(f"High error rate for {endpoint}: {stats['error_rate']:.2%}")

        # Check for stuck requests
        if active_requests > 10:  # Threshold for too many active requests
            healthy = False
            issues.append(f"Too many active requests: {active_requests}")

        return {
            "healthy": healthy,
            "issues": issues,
            "active_requests": active_requests,
            "uptime_seconds": metrics.get("system", {}).get("uptime_seconds", 0),
            "total_errors": error_stats.get("total_errors", 0),
            "recent_errors": error_stats.get("recent_errors", 0)
        }

    def get_full_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            "health": self.get_health_status(),
            "metrics": self.metrics.get_metrics_summary(),
            "errors": self.errors.get_error_stats(),
            "active_requests": self.requests.get_active_requests()
        }

    def export_metrics(self):
        """Export metrics to file (if enabled)"""
        if not self.export_enabled:
            return

        try:
            metrics_data = {
                "timestamp": time.time(),
                "metrics": self.metrics.get_metrics_summary(),
                "errors": self.errors.get_error_stats()
            }

            with open(self.export_path, "a") as f:
                f.write(json.dumps(metrics_data) + "\n")

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")


# Global telemetry instance
_telemetry_system = None

def get_telemetry_system() -> TelemetrySystem:
    """Get singleton telemetry system"""
    global _telemetry_system
    if _telemetry_system is None:
        _telemetry_system = TelemetrySystem()
    return _telemetry_system


# Decorator for automatic request tracking
def track_request(endpoint: str):
    """Decorator for automatic request tracking"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            telemetry = get_telemetry_system()
            req_id = str(uuid.uuid4())

            # Start tracking
            telemetry.start_request_tracking(req_id, endpoint)

            try:
                # Execute function
                result = func(*args, **kwargs)

                # Finish tracking (success)
                telemetry.finish_request_tracking(req_id, success=True)
                return result

            except Exception as e:
                # Record error and finish tracking
                telemetry.record_error("FUNCTION_ERROR", str(e), req_id=req_id)
                telemetry.finish_request_tracking(req_id, success=False)
                raise

        return wrapper
    return decorator


# Context manager for stage tracking
class StageTracker:
    """Context manager for tracking operation stages"""

    def __init__(self, req_id: str, stage_name: str):
        self.req_id = req_id
        self.stage_name = stage_name
        self.start_time = None
        self.telemetry = get_telemetry_system()

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            latency_ms = (time.time() - self.start_time) * 1000

            if exc_type is None:
                # Success
                self.telemetry.add_request_stage(self.req_id, self.stage_name, latency_ms)
            else:
                # Error
                self.telemetry.add_request_error(self.req_id, str(exc_val), self.stage_name)

        return False  # Don't suppress exceptions