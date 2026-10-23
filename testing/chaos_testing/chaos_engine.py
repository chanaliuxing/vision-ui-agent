#!/usr/bin/env python3
"""
Chaos Testing Engine
Stage 13: Automated Regression & E2E Testing

Comprehensive chaos engineering for system resilience:
1. Service failure injection
2. Network latency and partitions
3. Resource exhaustion scenarios
4. Data corruption testing
5. Performance degradation simulation
6. Recovery validation
"""

import random
import time
import threading
import subprocess
import psutil
import os
import signal
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import tempfile

class ChaosType(Enum):
    SERVICE_FAILURE = "service_failure"
    NETWORK_LATENCY = "network_latency"
    NETWORK_PARTITION = "network_partition"
    CPU_STRESS = "cpu_stress"
    MEMORY_STRESS = "memory_stress"
    DISK_STRESS = "disk_stress"
    DATA_CORRUPTION = "data_corruption"
    PROCESS_KILL = "process_kill"
    RESOURCE_LIMIT = "resource_limit"

@dataclass
class ChaosExperiment:
    """Chaos experiment configuration"""
    experiment_id: str
    chaos_type: ChaosType
    target: str  # Service name, process name, etc.
    duration: float  # Seconds
    intensity: float  # 0.0 - 1.0
    parameters: Dict[str, Any]
    description: str = ""

@dataclass
class ChaosResult:
    """Result of chaos experiment"""
    experiment_id: str
    success: bool
    start_time: float
    end_time: float
    duration: float
    impact_metrics: Dict[str, Any]
    recovery_time: Optional[float] = None
    error_message: Optional[str] = None

class ServiceFailureInjector:
    """Inject service failures and errors"""

    def __init__(self):
        self.active_failures = {}

    def inject_http_errors(self, target_url: str, error_rate: float,
                          duration: float) -> str:
        """Inject HTTP errors for target service"""
        failure_id = str(uuid.uuid4())

        def error_injector():
            start_time = time.time()
            while time.time() - start_time < duration:
                if random.random() < error_rate:
                    # Simulate service returning errors
                    print(f"🔥 Injecting HTTP error for {target_url}")
                time.sleep(1)

        thread = threading.Thread(target=error_injector, daemon=True)
        thread.start()

        self.active_failures[failure_id] = {
            "type": "http_errors",
            "target": target_url,
            "thread": thread,
            "start_time": time.time()
        }

        return failure_id

    def inject_response_delays(self, target_url: str, delay_factor: float,
                             duration: float) -> str:
        """Inject response delays"""
        failure_id = str(uuid.uuid4())

        def delay_injector():
            start_time = time.time()
            while time.time() - start_time < duration:
                delay = random.uniform(0.1, delay_factor)
                print(f"🐌 Injecting {delay:.2f}s delay for {target_url}")
                time.sleep(delay + 1)

        thread = threading.Thread(target=delay_injector, daemon=True)
        thread.start()

        self.active_failures[failure_id] = {
            "type": "response_delays",
            "target": target_url,
            "thread": thread,
            "start_time": time.time()
        }

        return failure_id

    def stop_injection(self, failure_id: str) -> bool:
        """Stop specific failure injection"""
        if failure_id in self.active_failures:
            del self.active_failures[failure_id]
            return True
        return False

class NetworkChaosInjector:
    """Inject network-related chaos"""

    def __init__(self):
        self.active_chaos = {}

    def inject_latency(self, interface: str, latency_ms: int,
                      duration: float) -> str:
        """Inject network latency using tc (Linux only)"""
        chaos_id = str(uuid.uuid4())

        try:
            # Add latency (requires sudo, so we'll simulate)
            print(f"🌐 Simulating {latency_ms}ms latency on {interface} for {duration}s")

            def latency_simulator():
                time.sleep(duration)

            thread = threading.Thread(target=latency_simulator, daemon=True)
            thread.start()

            self.active_chaos[chaos_id] = {
                "type": "latency",
                "interface": interface,
                "thread": thread,
                "start_time": time.time()
            }

        except Exception as e:
            print(f"⚠️  Cannot inject real network latency: {e}")
            print("    (Requires root privileges and tc command)")

        return chaos_id

    def inject_packet_loss(self, interface: str, loss_rate: float,
                          duration: float) -> str:
        """Inject packet loss"""
        chaos_id = str(uuid.uuid4())

        print(f"📡 Simulating {loss_rate*100:.1f}% packet loss on {interface}")

        def packet_loss_simulator():
            time.sleep(duration)

        thread = threading.Thread(target=packet_loss_simulator, daemon=True)
        thread.start()

        self.active_chaos[chaos_id] = {
            "type": "packet_loss",
            "interface": interface,
            "thread": thread,
            "start_time": time.time()
        }

        return chaos_id

    def stop_chaos(self, chaos_id: str) -> bool:
        """Stop network chaos"""
        if chaos_id in self.active_chaos:
            del self.active_chaos[chaos_id]
            return True
        return False

class ResourceStressInjector:
    """Inject resource stress (CPU, memory, disk)"""

    def __init__(self):
        self.stress_processes = {}

    def stress_cpu(self, cpu_percent: float, duration: float) -> str:
        """Stress CPU to target percentage"""
        stress_id = str(uuid.uuid4())

        def cpu_stress():
            start_time = time.time()
            end_time = start_time + duration

            print(f"💻 Stressing CPU to {cpu_percent:.1f}% for {duration}s")

            while time.time() < end_time:
                # Calculate work/sleep ratio to achieve target CPU usage
                work_time = cpu_percent / 100.0 * 0.1
                sleep_time = (1.0 - cpu_percent / 100.0) * 0.1

                # Do some work
                start_work = time.time()
                while time.time() - start_work < work_time:
                    _ = sum(i * i for i in range(1000))

                # Sleep
                time.sleep(sleep_time)

        thread = threading.Thread(target=cpu_stress, daemon=True)
        thread.start()

        self.stress_processes[stress_id] = {
            "type": "cpu",
            "thread": thread,
            "start_time": time.time()
        }

        return stress_id

    def stress_memory(self, memory_mb: int, duration: float) -> str:
        """Stress memory by allocating specified amount"""
        stress_id = str(uuid.uuid4())

        def memory_stress():
            print(f"🧠 Allocating {memory_mb} MB for {duration}s")
            try:
                # Allocate memory
                memory_hog = bytearray(memory_mb * 1024 * 1024)

                # Fill with random data to prevent optimization
                for i in range(0, len(memory_hog), 4096):
                    memory_hog[i] = random.randint(0, 255)

                time.sleep(duration)

                # Clean up
                del memory_hog

            except MemoryError:
                print(f"⚠️  Cannot allocate {memory_mb} MB - insufficient memory")

        thread = threading.Thread(target=memory_stress, daemon=True)
        thread.start()

        self.stress_processes[stress_id] = {
            "type": "memory",
            "thread": thread,
            "start_time": time.time()
        }

        return stress_id

    def stress_disk(self, write_mb: int, duration: float) -> str:
        """Stress disk with write operations"""
        stress_id = str(uuid.uuid4())

        def disk_stress():
            print(f"💾 Writing {write_mb} MB to disk over {duration}s")
            try:
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    temp_filename = tmp_file.name

                    # Calculate write rate
                    chunk_size = 1024 * 1024  # 1MB chunks
                    chunks_per_second = max(1, write_mb // duration)
                    delay_between_chunks = 1.0 / chunks_per_second

                    bytes_written = 0
                    target_bytes = write_mb * 1024 * 1024

                    while bytes_written < target_bytes:
                        # Write chunk
                        chunk = os.urandom(min(chunk_size, target_bytes - bytes_written))
                        tmp_file.write(chunk)
                        tmp_file.flush()
                        os.fsync(tmp_file.fileno())

                        bytes_written += len(chunk)
                        time.sleep(delay_between_chunks)

                # Clean up
                os.unlink(temp_filename)

            except Exception as e:
                print(f"⚠️  Disk stress error: {e}")

        thread = threading.Thread(target=disk_stress, daemon=True)
        thread.start()

        self.stress_processes[stress_id] = {
            "type": "disk",
            "thread": thread,
            "start_time": time.time()
        }

        return stress_id

    def stop_stress(self, stress_id: str) -> bool:
        """Stop specific stress test"""
        if stress_id in self.stress_processes:
            del self.stress_processes[stress_id]
            return True
        return False

class ProcessChaosInjector:
    """Inject process-related chaos"""

    def __init__(self):
        self.killed_processes = []

    def kill_process_by_name(self, process_name: str) -> List[int]:
        """Kill processes by name"""
        killed_pids = []

        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if process_name.lower() in proc.info['name'].lower():
                    pid = proc.info['pid']
                    try:
                        os.kill(pid, signal.SIGTERM)
                        killed_pids.append(pid)
                        print(f"💀 Killed process {process_name} (PID: {pid})")
                    except (ProcessLookupError, PermissionError) as e:
                        print(f"⚠️  Cannot kill PID {pid}: {e}")

        except Exception as e:
            print(f"⚠️  Process kill error: {e}")

        self.killed_processes.extend(killed_pids)
        return killed_pids

    def restart_service(self, service_name: str) -> bool:
        """Restart system service (simulation)"""
        print(f"🔄 Simulating restart of {service_name}")
        # In real implementation, would use systemctl or service commands
        time.sleep(2)  # Simulate restart time
        return True

class DataCorruptionInjector:
    """Inject data corruption scenarios"""

    def __init__(self):
        self.corrupted_files = []

    def corrupt_file(self, file_path: str, corruption_percent: float = 0.1) -> bool:
        """Corrupt random bytes in file"""
        try:
            if not os.path.exists(file_path):
                print(f"⚠️  File not found: {file_path}")
                return False

            # Create backup
            backup_path = f"{file_path}.chaos_backup"
            with open(file_path, 'rb') as original:
                with open(backup_path, 'wb') as backup:
                    backup.write(original.read())

            # Corrupt file
            with open(file_path, 'r+b') as f:
                f.seek(0, 2)  # Go to end
                file_size = f.tell()

                bytes_to_corrupt = max(1, int(file_size * corruption_percent))

                for _ in range(bytes_to_corrupt):
                    # Random position
                    pos = random.randint(0, file_size - 1)
                    f.seek(pos)

                    # Write random byte
                    f.write(bytes([random.randint(0, 255)]))

            self.corrupted_files.append({
                "file_path": file_path,
                "backup_path": backup_path,
                "corruption_time": time.time()
            })

            print(f"🗂️  Corrupted {corruption_percent*100:.1f}% of {file_path}")
            return True

        except Exception as e:
            print(f"⚠️  File corruption error: {e}")
            return False

    def restore_file(self, file_path: str) -> bool:
        """Restore file from backup"""
        try:
            backup_path = f"{file_path}.chaos_backup"
            if os.path.exists(backup_path):
                with open(backup_path, 'rb') as backup:
                    with open(file_path, 'wb') as original:
                        original.write(backup.read())

                os.unlink(backup_path)
                print(f"✅ Restored {file_path}")
                return True

        except Exception as e:
            print(f"⚠️  File restoration error: {e}")

        return False

class ChaosEngine:
    """Main chaos engineering engine"""

    def __init__(self):
        self.service_injector = ServiceFailureInjector()
        self.network_injector = NetworkChaosInjector()
        self.resource_injector = ResourceStressInjector()
        self.process_injector = ProcessChaosInjector()
        self.data_injector = DataCorruptionInjector()

        self.running_experiments = {}
        self.experiment_results = []

        # System metrics before chaos
        self.baseline_metrics = self._collect_metrics()

    def _collect_metrics(self) -> Dict[str, Any]:
        """Collect system metrics"""
        try:
            return {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent,
                "process_count": len(psutil.pids()),
                "timestamp": time.time()
            }
        except Exception:
            return {"timestamp": time.time()}

    def run_experiment(self, experiment: ChaosExperiment) -> ChaosResult:
        """Run chaos experiment"""
        print(f"\n🔥 Starting chaos experiment: {experiment.experiment_id}")
        print(f"   Type: {experiment.chaos_type.value}")
        print(f"   Target: {experiment.target}")
        print(f"   Duration: {experiment.duration}s")
        print(f"   Intensity: {experiment.intensity}")

        start_time = time.time()
        result = ChaosResult(
            experiment_id=experiment.experiment_id,
            success=False,
            start_time=start_time,
            end_time=0,
            duration=0,
            impact_metrics={}
        )

        try:
            # Record pre-chaos metrics
            pre_metrics = self._collect_metrics()

            # Execute chaos based on type
            chaos_id = self._execute_chaos(experiment)

            # Wait for experiment duration
            time.sleep(experiment.duration)

            # Stop chaos if needed
            self._stop_chaos(experiment.chaos_type, chaos_id)

            # Wait for recovery
            recovery_start = time.time()
            recovery_time = self._wait_for_recovery(experiment)

            # Record post-chaos metrics
            post_metrics = self._collect_metrics()

            # Calculate impact
            impact_metrics = self._calculate_impact(pre_metrics, post_metrics)

            end_time = time.time()
            result.success = True
            result.end_time = end_time
            result.duration = end_time - start_time
            result.recovery_time = recovery_time
            result.impact_metrics = impact_metrics

            print(f"✅ Experiment completed successfully")
            if recovery_time:
                print(f"   Recovery time: {recovery_time:.2f}s")

        except Exception as e:
            result.error_message = str(e)
            result.end_time = time.time()
            result.duration = result.end_time - start_time
            print(f"❌ Experiment failed: {e}")

        self.experiment_results.append(result)
        return result

    def _execute_chaos(self, experiment: ChaosExperiment) -> str:
        """Execute specific chaos type"""
        chaos_type = experiment.chaos_type
        target = experiment.target
        duration = experiment.duration
        intensity = experiment.intensity
        params = experiment.parameters

        if chaos_type == ChaosType.SERVICE_FAILURE:
            return self.service_injector.inject_http_errors(
                target, intensity, duration
            )

        elif chaos_type == ChaosType.NETWORK_LATENCY:
            latency_ms = int(params.get("latency_ms", 100) * intensity)
            return self.network_injector.inject_latency(
                target, latency_ms, duration
            )

        elif chaos_type == ChaosType.CPU_STRESS:
            cpu_percent = intensity * 100
            return self.resource_injector.stress_cpu(cpu_percent, duration)

        elif chaos_type == ChaosType.MEMORY_STRESS:
            memory_mb = int(params.get("memory_mb", 500) * intensity)
            return self.resource_injector.stress_memory(memory_mb, duration)

        elif chaos_type == ChaosType.DISK_STRESS:
            write_mb = int(params.get("write_mb", 100) * intensity)
            return self.resource_injector.stress_disk(write_mb, duration)

        elif chaos_type == ChaosType.PROCESS_KILL:
            self.process_injector.kill_process_by_name(target)
            return "process_killed"

        elif chaos_type == ChaosType.DATA_CORRUPTION:
            corruption_rate = intensity * 0.1  # Max 10% corruption
            self.data_injector.corrupt_file(target, corruption_rate)
            return "data_corrupted"

        else:
            raise ValueError(f"Unknown chaos type: {chaos_type}")

    def _stop_chaos(self, chaos_type: ChaosType, chaos_id: str):
        """Stop ongoing chaos"""
        if chaos_type in [ChaosType.SERVICE_FAILURE]:
            self.service_injector.stop_injection(chaos_id)
        elif chaos_type in [ChaosType.NETWORK_LATENCY, ChaosType.NETWORK_PARTITION]:
            self.network_injector.stop_chaos(chaos_id)
        elif chaos_type in [ChaosType.CPU_STRESS, ChaosType.MEMORY_STRESS, ChaosType.DISK_STRESS]:
            self.resource_injector.stop_stress(chaos_id)

    def _wait_for_recovery(self, experiment: ChaosExperiment) -> Optional[float]:
        """Wait for system to recover and measure recovery time"""
        if experiment.chaos_type in [ChaosType.DATA_CORRUPTION]:
            # Restore corrupted files
            self.data_injector.restore_file(experiment.target)

        # Wait for metrics to return to baseline
        recovery_start = time.time()
        max_recovery_time = 30.0  # Max 30 seconds

        while time.time() - recovery_start < max_recovery_time:
            current_metrics = self._collect_metrics()

            # Check if CPU and memory are back to reasonable levels
            cpu_ok = current_metrics.get("cpu_percent", 0) < 50
            memory_ok = current_metrics.get("memory_percent", 0) < 80

            if cpu_ok and memory_ok:
                return time.time() - recovery_start

            time.sleep(1)

        return max_recovery_time  # Took too long to recover

    def _calculate_impact(self, pre_metrics: Dict, post_metrics: Dict) -> Dict[str, Any]:
        """Calculate impact of chaos experiment"""
        impact = {}

        for metric in ["cpu_percent", "memory_percent", "disk_usage"]:
            pre_val = pre_metrics.get(metric, 0)
            post_val = post_metrics.get(metric, 0)
            impact[f"{metric}_change"] = post_val - pre_val

        return impact

    def run_chaos_scenario(self, experiments: List[ChaosExperiment]) -> List[ChaosResult]:
        """Run multiple chaos experiments in sequence"""
        results = []

        print(f"\n🚀 Starting chaos scenario with {len(experiments)} experiments")

        for i, experiment in enumerate(experiments):
            print(f"\n--- Experiment {i+1}/{len(experiments)} ---")
            result = self.run_experiment(experiment)
            results.append(result)

            # Wait between experiments
            if i < len(experiments) - 1:
                cooldown = 5
                print(f"⏱️  Cooling down for {cooldown}s...")
                time.sleep(cooldown)

        return results

    def generate_report(self) -> Dict[str, Any]:
        """Generate chaos testing report"""
        total_experiments = len(self.experiment_results)
        successful_experiments = sum(1 for r in self.experiment_results if r.success)

        avg_recovery_time = 0
        if self.experiment_results:
            recovery_times = [r.recovery_time for r in self.experiment_results if r.recovery_time]
            if recovery_times:
                avg_recovery_time = sum(recovery_times) / len(recovery_times)

        return {
            "summary": {
                "total_experiments": total_experiments,
                "successful_experiments": successful_experiments,
                "success_rate": successful_experiments / max(1, total_experiments),
                "average_recovery_time": avg_recovery_time
            },
            "experiments": [asdict(result) for result in self.experiment_results],
            "baseline_metrics": self.baseline_metrics,
            "report_timestamp": time.time()
        }