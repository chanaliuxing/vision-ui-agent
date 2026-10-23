#!/usr/bin/env python3
"""
Engine Fault Tolerance and Self-Healing System
Stage 11: Robustness & Anti-detection & Fault tolerance

Comprehensive fault tolerance with automatic recovery:
1. Circuit breaker pattern for external services
2. Exponential backoff retry logic
3. Health monitoring and alerting
4. Automatic fallback mechanisms
5. State recovery and checkpointing
6. Resource leak detection and cleanup
"""

import time
import logging
import threading
import traceback
import psutil
import gc
from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import weakref
import json
import os

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Service failure, requests blocked
    HALF_OPEN = "half_open" # Testing if service recovered

@dataclass
class HealthMetrics:
    """System health metrics"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    disk_percent: float = 0.0
    open_files: int = 0
    thread_count: int = 0
    response_time: float = 0.0
    error_rate: float = 0.0
    last_updated: float = field(default_factory=time.time)

@dataclass
class CircuitConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3
    timeout: float = 30.0

class CircuitBreaker:
    """Circuit breaker for external service calls"""

    def __init__(self, name: str, config: CircuitConfig = None):
        self.name = name
        self.config = config or CircuitConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        with self.lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")

        try:
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            if execution_time > self.config.timeout:
                raise TimeoutError(f"Function execution exceeded {self.config.timeout}s")

            self._on_success()
            return result

        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call"""
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    def _on_failure(self):
        """Handle failed call"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit state"""
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_time': self.last_failure_time
        }

class RetryPolicy:
    """Exponential backoff retry policy"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic"""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt == self.max_retries:
                    break

                # Calculate delay with exponential backoff
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)

                # Add jitter to avoid thundering herd
                jitter = delay * 0.1 * (2 * time.time() % 1 - 1)  # ±10% jitter
                delay += jitter

                print(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                time.sleep(delay)

        raise last_exception

class HealthMonitor:
    """System health monitoring"""

    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self.metrics = HealthMetrics()
        self.status = HealthStatus.HEALTHY
        self.alerts: List[str] = []
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Thresholds
        self.cpu_warning = 80.0
        self.cpu_critical = 95.0
        self.memory_warning = 80.0
        self.memory_critical = 95.0
        self.disk_warning = 90.0
        self.disk_critical = 98.0

    def start(self):
        """Start health monitoring"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print("Health monitoring started")

    def stop(self):
        """Stop health monitoring"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self._collect_metrics()
                self._evaluate_health()
                time.sleep(self.check_interval)
            except Exception as e:
                print(f"Health monitoring error: {e}")

    def _collect_metrics(self):
        """Collect system metrics"""
        try:
            # CPU usage
            self.metrics.cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()
            self.metrics.memory_percent = memory.percent
            self.metrics.memory_mb = memory.used / 1024 / 1024

            # Disk usage
            disk = psutil.disk_usage('/')
            self.metrics.disk_percent = (disk.used / disk.total) * 100

            # Process info
            process = psutil.Process()
            self.metrics.open_files = len(process.open_files())
            self.metrics.thread_count = process.num_threads()

            self.metrics.last_updated = time.time()

        except Exception as e:
            print(f"Metrics collection error: {e}")

    def _evaluate_health(self):
        """Evaluate overall system health"""
        self.alerts.clear()
        issues = []

        # Check CPU
        if self.metrics.cpu_percent >= self.cpu_critical:
            issues.append("CPU usage critical")
            self.alerts.append(f"CPU usage: {self.metrics.cpu_percent:.1f}%")
        elif self.metrics.cpu_percent >= self.cpu_warning:
            issues.append("CPU usage high")

        # Check Memory
        if self.metrics.memory_percent >= self.memory_critical:
            issues.append("Memory usage critical")
            self.alerts.append(f"Memory usage: {self.metrics.memory_percent:.1f}%")
        elif self.metrics.memory_percent >= self.memory_warning:
            issues.append("Memory usage high")

        # Check Disk
        if self.metrics.disk_percent >= self.disk_critical:
            issues.append("Disk usage critical")
            self.alerts.append(f"Disk usage: {self.metrics.disk_percent:.1f}%")
        elif self.metrics.disk_percent >= self.disk_warning:
            issues.append("Disk usage high")

        # Check file handles
        if self.metrics.open_files > 1000:
            issues.append("Too many open files")
            self.alerts.append(f"Open files: {self.metrics.open_files}")

        # Determine overall status
        critical_issues = [issue for issue in issues if "critical" in issue]
        if critical_issues:
            self.status = HealthStatus.CRITICAL
        elif len(issues) >= 3:
            self.status = HealthStatus.UNHEALTHY
        elif len(issues) >= 1:
            self.status = HealthStatus.DEGRADED
        else:
            self.status = HealthStatus.HEALTHY

    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report"""
        return {
            'status': self.status.value,
            'metrics': {
                'cpu_percent': self.metrics.cpu_percent,
                'memory_percent': self.metrics.memory_percent,
                'memory_mb': self.metrics.memory_mb,
                'disk_percent': self.metrics.disk_percent,
                'open_files': self.metrics.open_files,
                'thread_count': self.metrics.thread_count,
                'last_updated': self.metrics.last_updated
            },
            'alerts': self.alerts.copy()
        }

class ResourceManager:
    """Resource leak detection and cleanup"""

    def __init__(self):
        self.tracked_resources: Dict[str, weakref.WeakSet] = {}
        self.cleanup_callbacks: Dict[str, Callable] = {}
        self.lock = threading.Lock()

    def register_resource(self, resource_type: str, resource: Any, cleanup_func: Callable = None):
        """Register a resource for tracking"""
        with self.lock:
            if resource_type not in self.tracked_resources:
                self.tracked_resources[resource_type] = weakref.WeakSet()

            self.tracked_resources[resource_type].add(resource)

            if cleanup_func:
                self.cleanup_callbacks[f"{resource_type}_{id(resource)}"] = cleanup_func

    def cleanup_type(self, resource_type: str):
        """Cleanup all resources of a specific type"""
        with self.lock:
            if resource_type not in self.tracked_resources:
                return

            resources = list(self.tracked_resources[resource_type])
            for resource in resources:
                try:
                    callback_key = f"{resource_type}_{id(resource)}"
                    if callback_key in self.cleanup_callbacks:
                        self.cleanup_callbacks[callback_key]()
                        del self.cleanup_callbacks[callback_key]
                except Exception as e:
                    print(f"Resource cleanup error: {e}")

            self.tracked_resources[resource_type].clear()

    def force_garbage_collection(self):
        """Force garbage collection and cleanup"""
        collected = gc.collect()
        print(f"Garbage collection freed {collected} objects")

    def get_resource_counts(self) -> Dict[str, int]:
        """Get current resource counts"""
        with self.lock:
            return {
                resource_type: len(resources)
                for resource_type, resources in self.tracked_resources.items()
            }

class StateRecovery:
    """State recovery and checkpointing"""

    def __init__(self, checkpoint_dir: str = "checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

    def save_checkpoint(self, name: str, state: Dict[str, Any]):
        """Save state checkpoint"""
        try:
            checkpoint_file = os.path.join(self.checkpoint_dir, f"{name}.json")
            with open(checkpoint_file, 'w') as f:
                json.dump({
                    'timestamp': time.time(),
                    'state': state
                }, f, indent=2)
            print(f"Checkpoint saved: {name}")
        except Exception as e:
            print(f"Failed to save checkpoint {name}: {e}")

    def load_checkpoint(self, name: str) -> Optional[Dict[str, Any]]:
        """Load state checkpoint"""
        try:
            checkpoint_file = os.path.join(self.checkpoint_dir, f"{name}.json")
            if not os.path.exists(checkpoint_file):
                return None

            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
                print(f"Checkpoint loaded: {name}")
                return data.get('state')
        except Exception as e:
            print(f"Failed to load checkpoint {name}: {e}")
            return None

    def list_checkpoints(self) -> List[str]:
        """List available checkpoints"""
        try:
            files = os.listdir(self.checkpoint_dir)
            return [f.replace('.json', '') for f in files if f.endswith('.json')]
        except Exception:
            return []

class FaultTolerantEngine:
    """Main fault tolerance coordinator"""

    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.retry_policies: Dict[str, RetryPolicy] = {}
        self.health_monitor = HealthMonitor()
        self.resource_manager = ResourceManager()
        self.state_recovery = StateRecovery()
        self.fallback_handlers: Dict[str, Callable] = {}

        # Start monitoring
        self.health_monitor.start()

    def get_circuit_breaker(self, name: str, config: CircuitConfig = None) -> CircuitBreaker:
        """Get or create circuit breaker"""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(name, config)
        return self.circuit_breakers[name]

    def get_retry_policy(self, name: str, max_retries: int = 3) -> RetryPolicy:
        """Get or create retry policy"""
        if name not in self.retry_policies:
            self.retry_policies[name] = RetryPolicy(max_retries=max_retries)
        return self.retry_policies[name]

    def register_fallback(self, service_name: str, fallback_func: Callable):
        """Register fallback handler for service"""
        self.fallback_handlers[service_name] = fallback_func

    def execute_with_protection(self, service_name: str, func: Callable, *args, **kwargs) -> Any:
        """Execute function with full fault tolerance protection"""
        circuit_breaker = self.get_circuit_breaker(service_name)
        retry_policy = self.get_retry_policy(service_name)

        def protected_call():
            return circuit_breaker.call(func, *args, **kwargs)

        try:
            return retry_policy.execute(protected_call)
        except Exception as e:
            # Try fallback if available
            if service_name in self.fallback_handlers:
                try:
                    print(f"Using fallback for {service_name}")
                    return self.fallback_handlers[service_name](*args, **kwargs)
                except Exception as fallback_error:
                    print(f"Fallback also failed: {fallback_error}")

            # Re-raise original exception
            raise e

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        circuit_states = {
            name: breaker.get_state()
            for name, breaker in self.circuit_breakers.items()
        }

        resource_counts = self.resource_manager.get_resource_counts()

        return {
            'health': self.health_monitor.get_health_report(),
            'circuits': circuit_states,
            'resources': resource_counts,
            'checkpoints': self.state_recovery.list_checkpoints()
        }

    def emergency_recovery(self):
        """Emergency recovery procedure"""
        print("🚨 Emergency recovery initiated")

        # Force garbage collection
        self.resource_manager.force_garbage_collection()

        # Reset all circuit breakers
        for breaker in self.circuit_breakers.values():
            breaker.state = CircuitState.CLOSED
            breaker.failure_count = 0

        # Save emergency checkpoint
        system_state = {
            'timestamp': time.time(),
            'health': self.health_monitor.get_health_report(),
            'recovery_reason': 'emergency'
        }
        self.state_recovery.save_checkpoint('emergency', system_state)

        print("Emergency recovery completed")

    def shutdown(self):
        """Clean shutdown"""
        print("Shutting down fault tolerance engine...")

        # Stop monitoring
        self.health_monitor.stop()

        # Cleanup resources
        for resource_type in list(self.resource_manager.tracked_resources.keys()):
            self.resource_manager.cleanup_type(resource_type)

        print("Fault tolerance engine shut down")

# Custom exceptions
class CircuitBreakerOpenError(Exception):
    """Circuit breaker is open"""
    pass

class HealthCheckFailedError(Exception):
    """Health check failed"""
    pass

# Decorators for easy integration
def circuit_breaker(name: str, config: CircuitConfig = None):
    """Decorator for circuit breaker protection"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            engine = get_fault_tolerance_engine()
            breaker = engine.get_circuit_breaker(name, config)
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator

def retry(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retry logic"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            policy = RetryPolicy(max_retries, base_delay)
            return policy.execute(func, *args, **kwargs)
        return wrapper
    return decorator

def with_fallback(fallback_func: Callable):
    """Decorator to provide fallback function"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                return fallback_func(*args, **kwargs)
        return wrapper
    return decorator

# Global fault tolerance engine
_fault_tolerance_engine: Optional[FaultTolerantEngine] = None

def get_fault_tolerance_engine() -> FaultTolerantEngine:
    """Get global fault tolerance engine instance"""
    global _fault_tolerance_engine
    if _fault_tolerance_engine is None:
        _fault_tolerance_engine = FaultTolerantEngine()
    return _fault_tolerance_engine