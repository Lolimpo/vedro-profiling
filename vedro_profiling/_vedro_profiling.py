import json
import os
import threading
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Type, TypedDict

import docker
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import psutil
from docker import errors as docker_errors
from vedro.core import Dispatcher, Plugin, PluginConfig
from vedro.events import ArgParsedEvent, ArgParseEvent, CleanupEvent, StartupEvent


# Type aliases for better type safety
class DataPointData(TypedDict):
    """Data structure for a profiling data point."""
    time: str
    value: float
    tags: dict[str, str]


class DataPoint(TypedDict):
    """Complete data point structure for profiling metrics."""
    type: str
    metric: str
    data: DataPointData


MetricStats = dict[str, list[Any]]  # Contains CPU, MEM lists and timestamps
StatsDict = dict[str, MetricStats]


class VedroProfilingPlugin(Plugin):
    """
    Adds profiling support to the Vedro framework.
    """

    def __init__(self, config: Type["VedroProfiling"]):
        super().__init__(config)
        self._enable_profiling: bool = config.enable_profiling
        self._poll_time: float = config.poll_time
        self._profiling_methods: list[str] = config.profiling_methods
        self._draw_plots: bool = config.draw_plots
        self._docker_compose_project_name: str = config.docker_compose_project_name
        self._profiling_run_id: str | None = config.profiling_run_id
        self._additional_tags: dict[str, str] = config.additional_tags
        
        # New data structure for k6-compatible format
        self._data_points: list[DataPoint] = []
        self._metrics_definitions: dict[str, dict[str, str]] = {
            "cpu_percent": {"type": "gauge", "unit": "percent"},
            "memory_usage": {"type": "gauge", "unit": "megabytes"}
        }
        self._run_id: str = ""

        self._running: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._docker_thread: threading.Thread | None = None
        self._psutil_thread: threading.Thread | None = None

    def subscribe(self, dispatcher: Dispatcher) -> None:
        dispatcher.listen(ArgParseEvent, self.on_arg_parse) \
            .listen(ArgParsedEvent, self.on_arg_parsed) \
            .listen(StartupEvent, self.on_startup) \
            .listen(CleanupEvent, self.on_cleanup)

    def on_arg_parse(self, event: ArgParseEvent) -> None:
        group = event.arg_parser.add_argument_group("VedroProfiling")
        group.add_argument(
            "--enable-profiling",
            action="store_true",
            default=self._enable_profiling,
            help="Enable recording of containers stats during scenario execution"
        )
        group.add_argument(
            "--draw-plots",
            action="store_true",
            default=self._draw_plots,
            help="Draw CPU/MEM plots after test run"
        )
        group.add_argument(
            "--run-id",
            type=str,
            default=None,
            help="Unique identifier for this profiling run (default: auto-generated)"
        )

    def on_arg_parsed(self, event: ArgParsedEvent) -> None:
        self._enable_profiling = event.args.enable_profiling
        self._draw_plots = event.args.draw_plots
        if event.args.run_id:
            self._profiling_run_id = event.args.run_id

    def _create_data_point(
        self,
        metric: str,
        value: float,
        target: str,
        method: str,
        timestamp: str | None = None
    ) -> DataPoint:
        """Create a standardized data point for profiling metrics."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        return {
            "type": "Point",
            "metric": metric,
            "data": {
                "time": timestamp,
                "value": value,
                "tags": {
                    "target": target,
                    "method": method,
                    "run": self._run_id,
                    **self._additional_tags
                }
            }
        }

    def _collect_docker_stats(self) -> None:
        try:
            client = docker.from_env()
        except docker_errors.DockerException:
            warnings.warn("Docker is unavailable, containers metrics are disabled.")
            return

        containers = client.containers.list(
            filters={
                "label": [
                    "com.docker.compose.project=" + self._docker_compose_project_name
                ]
            }
        )
        if not containers:
            warnings.warn("No containers found for profiling.")
            return

        while not self._stop_event.is_set():
            for container in containers:
                if self._stop_event.is_set():
                    break

                try:
                    stats_raw = container.stats(decode=None, stream=False)
                    # Stats structure: {"cpu_stats": {...}, "memory_stats": {...}, "precpu_stats": {...}}
                    stats: dict[str, Any] = stats_raw  # type: ignore[assignment]

                    cpu_delta = (stats["cpu_stats"]["cpu_usage"]["total_usage"] -
                                 stats["precpu_stats"]["cpu_usage"]["total_usage"])
                    system_delta = (stats["cpu_stats"]["system_cpu_usage"] -
                                    stats["precpu_stats"]["system_cpu_usage"])

                    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                    container_name = container.name or "unknown"
                    
                    if system_delta > 0 and stats["cpu_stats"].get("online_cpus"):
                        cpu_percent = ((cpu_delta / system_delta) *
                                       stats["cpu_stats"]["online_cpus"] * 100)
                        
                        # CPU point
                        self._data_points.append(
                            self._create_data_point(
                                metric="cpu_percent",
                                value=cpu_percent,
                                target=container_name,
                                method="docker",
                                timestamp=timestamp
                            )
                        )

                    mem = stats["memory_stats"]["usage"]
                    mem_mb = mem / 1e6
                    
                    # Memory point
                    self._data_points.append(
                        self._create_data_point(
                            metric="memory_usage",
                            value=mem_mb,
                            target=container_name,
                            method="docker",
                            timestamp=timestamp
                        )
                    )
                except (KeyError, docker_errors.APIError):
                    continue

            self._stop_event.wait(self._poll_time)

    def _collect_psutil_stats(self) -> None:
        proc = psutil.Process()

        while not self._stop_event.is_set():
            try:
                proc_cpu = proc.cpu_percent()
                proc_mem = proc.memory_info().rss / 1e6  # Memory in MB

                system_cpu = psutil.cpu_percent()
                system_mem = psutil.virtual_memory().used / 1e6  # Memory in MB

                timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                proc_name = proc.name() or "unknown"

                # Process CPU point
                self._data_points.append(
                    self._create_data_point(
                        metric="cpu_percent",
                        value=proc_cpu,
                        target=proc_name,
                        method="default",
                        timestamp=timestamp
                    )
                )
                
                # Process memory point
                self._data_points.append(
                    self._create_data_point(
                        metric="memory_usage",
                        value=proc_mem,
                        target=proc_name,
                        method="default",
                        timestamp=timestamp
                    )
                )
                
                # System CPU point
                self._data_points.append(
                    self._create_data_point(
                        metric="cpu_percent",
                        value=system_cpu,
                        target="system",
                        method="default",
                        timestamp=timestamp
                    )
                )
                
                # System memory point
                self._data_points.append(
                    self._create_data_point(
                        metric="memory_usage",
                        value=system_mem,
                        target="system",
                        method="default",
                        timestamp=timestamp
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break

            self._stop_event.wait(self._poll_time)

    def on_startup(self, event: StartupEvent) -> None:
        if not self._enable_profiling:
            return

        # Generate run ID if not provided
        if self._profiling_run_id:
            self._run_id = self._profiling_run_id
        else:
            self._run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        self._running = True
        self._stop_event.clear()

        if "default" in self._profiling_methods:
            self._psutil_thread = threading.Thread(
                target=self._collect_psutil_stats,
                daemon=False,
                name="vedro-profiling-psutil"
            )
            self._psutil_thread.start()

        if "docker" in self._profiling_methods:
            self._docker_thread = threading.Thread(
                target=self._collect_docker_stats,
                daemon=False,
                name="vedro-profiling-docker"
            )
            self._docker_thread.start()

    def _ensure_profiling_dir(self) -> str:
        profiling_dir = ".profiling"
        os.makedirs(profiling_dir, exist_ok=True)
        return profiling_dir
    
    def _write_profiling_log(self) -> None:
        """Write metrics in NDJSON format (k6-compatible)"""
        profiling_dir = self._ensure_profiling_dir()
        log_path = os.path.join(profiling_dir, "profiling.ndjson")
        
        with open(log_path, "w") as f:
            # Write metric definitions first
            for metric_name, definition in self._metrics_definitions.items():
                metric_def = {
                    "type": "Metric",
                    "metric": metric_name,
                    "data": definition
                }
                f.write(json.dumps(metric_def) + "\n")
            
            # Write data points
            for point in self._data_points:
                f.write(json.dumps(point) + "\n")

    def _prepare_stats_for_plotting(self) -> StatsDict:
        """Convert data points to format for plotting"""
        stats: StatsDict = defaultdict(
            lambda: {"CPU": [], "MEM": [], "timestamps": []}
        )
        
        for point in self._data_points:
            target = point["data"]["tags"]["target"]
            metric = point["metric"]
            time = point["data"]["time"].rstrip("Z")  # Remove Z for parsing
            
            if metric == "cpu_percent":
                stats[target]["CPU"].append(point["data"]["value"])
                if time not in stats[target]["timestamps"]:
                    stats[target]["timestamps"].append(time)
            elif metric == "memory_usage":
                stats[target]["MEM"].append(point["data"]["value"])
        
        return dict(stats)
    
    def _generate_plots(self) -> None:
        if not self._data_points:
            return

        stats = self._prepare_stats_for_plotting()
        
        plt.style.use('default')
        profiling_dir = self._ensure_profiling_dir()

        for name, metrics in stats.items():
            if not metrics["CPU"] and not metrics["MEM"]:
                continue

            self._create_individual_plot(name, metrics, profiling_dir)

        if len(stats) > 1:
            self._create_comparison_plot_from_stats(stats, profiling_dir)

    def _create_individual_plot(
        self,
        name: str,
        metrics: MetricStats,
        profiling_dir: str
    ) -> None:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        timestamps = [datetime.fromisoformat(str(ts)) for ts in metrics["timestamps"]]

        if metrics["CPU"]:
            ax1.plot(timestamps, metrics["CPU"], 'b-', linewidth=2, label='CPU Usage')
            ax1.set_ylabel('CPU Usage (%)', fontsize=12)
            ax1.set_title(
                f'{name} - Resource Usage Over Time',
                fontsize=14,
                fontweight='bold'
            )
            ax1.grid(True, alpha=0.3)
            ax1.legend()

            cpu_stats = self._calculate_stats(metrics["CPU"])
            stats_text = f'Avg: {cpu_stats["avg"]:.1f}% | Max: {cpu_stats["max"]:.1f}%'
            ax1.text(
                0.02, 0.95, stats_text, transform=ax1.transAxes,
                fontsize=9, verticalalignment='top'
            )

        if metrics["MEM"]:
            ax2.plot(timestamps, metrics["MEM"], 'r-', linewidth=2, label='Memory Usage')
            mem_label = 'Memory Usage (MB)'
            ax2.set_ylabel(mem_label, fontsize=12)
            ax2.set_xlabel('Time', fontsize=12)
            ax2.grid(True, alpha=0.3)
            ax2.legend()

            mem_stats = self._calculate_stats(metrics["MEM"])
            stats_text = f'Avg: {mem_stats["avg"]:.1f} MB | Max: {mem_stats["max"]:.1f} MB'
            ax2.text(
                0.02, 0.95, stats_text, transform=ax2.transAxes,
                fontsize=9, verticalalignment='top'
            )

        ax2.xaxis.set_major_formatter(
            mdates.DateFormatter('%H:%M:%S')  # type: ignore[no-untyped-call]
        )
        ax2.xaxis.set_major_locator(
            mdates.SecondLocator(  # type: ignore[no-untyped-call]
                interval=max(1, len(timestamps) // 10)
            )
        )
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

        plt.tight_layout()
        plot_path = os.path.join(profiling_dir, f'{name}_profile.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()

    def _create_comparison_plot_from_stats(
        self,
        stats: StatsDict,
        profiling_dir: str
    ) -> None:
        _, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

        colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown']

        for i, (name, metrics) in enumerate(stats.items()):
            if not metrics["CPU"] and not metrics["MEM"]:
                continue

            timestamps = [datetime.fromisoformat(ts) for ts in metrics["timestamps"]]

            if metrics["CPU"]:
                ax1.plot(
                    timestamps, metrics["CPU"],
                    color=colors[i % len(colors)],
                    linewidth=2, label=f'{name} CPU'
                )

            if metrics["MEM"]:
                ax2.plot(
                    timestamps, metrics["MEM"],
                    color=colors[i % len(colors)],
                    linewidth=2, label=f'{name} Memory', linestyle='--'
                )

        ax1.set_ylabel('CPU Usage (%)', fontsize=12)
        ax1.set_title('Resource Usage Comparison', fontsize=16, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        ax2.set_ylabel('Memory Usage', fontsize=12)
        ax2.set_xlabel('Time', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        if stats:
            first_timestamps = [
                datetime.fromisoformat(ts)
                for ts in list(stats.values())[0]["timestamps"]
            ]
            ax2.xaxis.set_major_formatter(
                mdates.DateFormatter('%H:%M:%S')  # type: ignore[no-untyped-call]
            )
            ax2.xaxis.set_major_locator(
                mdates.SecondLocator(  # type: ignore[no-untyped-call]
                    interval=max(1, len(first_timestamps) // 10)
                )
            )
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

        plt.tight_layout()
        plot_path = os.path.join(profiling_dir, 'resource_comparison.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()

    def _calculate_stats(self, data: list[float]) -> dict[str, float]:
        if not data:
            return {"avg": 0, "max": 0, "min": 0}

        return {
            "avg": sum(data) / len(data),
            "max": max(data),
            "min": min(data)
        }

    def on_cleanup(self, event: CleanupEvent) -> None:
        if not self._enable_profiling:
            return

        self._stop_event.set()
        self._running = False

        if self._docker_thread and self._docker_thread.is_alive():
            self._docker_thread.join(timeout=2.0)
        if self._psutil_thread and self._psutil_thread.is_alive():
            self._psutil_thread.join(timeout=2.0)

        try:
            self._write_profiling_log()
        except (IOError, OSError) as e:
            warnings.warn(f"Failed to write profiling log: {e}")
        except Exception as e:
            warnings.warn(f"Unexpected error writing profiling log: {e}")

        if self._draw_plots:
            try:
                self._generate_plots()
            except Exception as e:
                warnings.warn(f"Failed to generate plots: {e}")


class VedroProfiling(PluginConfig):
    plugin = VedroProfilingPlugin

    # Enable stats collection
    enable_profiling: bool = False

    # Supported profiling methods
    profiling_methods: list[str] = ["default"]

    # Poll time for stats in seconds
    poll_time: float = 1.0

    # Enable plots drawing for given profile snapshot
    draw_plots: bool = False

    # Docker Compose project name used for container profiling
    docker_compose_project_name: str = "compose"
    
    # Unique run identifier for profiling session
    profiling_run_id: str | None = None
    
    # Additional custom tags for metrics
    additional_tags: dict[str, str] = {}
