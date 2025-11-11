import json
import os
import threading
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Any, DefaultDict, Optional, Type

import docker
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import psutil
from docker import errors as docker_errors
from vedro.core import Dispatcher, Plugin, PluginConfig
from vedro.events import ArgParsedEvent, ArgParseEvent, CleanupEvent, StartupEvent


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
        self._stats: DefaultDict[str, Any] = defaultdict(
            lambda: {"CPU": [], "MEM": [], "timestamps": []}
        )

        self._running: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._docker_thread: Optional[threading.Thread] = None
        self._psutil_thread: Optional[threading.Thread] = None

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

    def on_arg_parsed(self, event: ArgParsedEvent) -> None:
        self._enable_profiling = event.args.enable_profiling
        self._draw_plots = event.args.draw_plots

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
                    stats = container.stats(decode=None, stream=False)

                    cpu_delta = (stats["cpu_stats"]["cpu_usage"]["total_usage"] -
                                 stats["precpu_stats"]["cpu_usage"]["total_usage"])
                    system_delta = (stats["cpu_stats"]["system_cpu_usage"] -
                                    stats["precpu_stats"]["system_cpu_usage"])

                    if system_delta > 0 and stats["cpu_stats"].get("online_cpus"):
                        cpu_percent = ((cpu_delta / system_delta) *
                                       stats["cpu_stats"]["online_cpus"] * 100)
                        self._stats[container.name]["CPU"].append(cpu_percent)

                    mem = stats["memory_stats"]["usage"]
                    self._stats[container.name]["MEM"].append(mem / 1e6)

                    timestamp = datetime.now().isoformat()
                    self._stats[container.name]["timestamps"].append(timestamp)
                except (KeyError, docker_errors.APIError):
                    continue

            self._stop_event.wait(self._poll_time)

    def _collect_psutil_stats(self) -> None:
        proc = psutil.Process()

        while not self._stop_event.is_set():
            try:
                proc_cpu = proc.cpu_percent()
                proc_mem = proc.memory_percent()

                system_cpu = psutil.cpu_percent()
                system_mem = psutil.virtual_memory().percent

                timestamp = datetime.now().isoformat()

                self._stats[proc.name()]["CPU"].append(proc_cpu)
                self._stats["system"]["CPU"].append(system_cpu)
                self._stats[proc.name()]["MEM"].append(proc_mem)
                self._stats["system"]["MEM"].append(system_mem)

                self._stats[proc.name()]["timestamps"].append(timestamp)
                self._stats["system"]["timestamps"].append(timestamp)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break

            self._stop_event.wait(self._poll_time)

    def on_startup(self, event: StartupEvent) -> None:
        if not self._enable_profiling:
            return

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

    def _generate_plots(self) -> None:
        if not self._stats:
            return

        plt.style.use('default')
        profiling_dir = self._ensure_profiling_dir()

        for name, metrics in self._stats.items():
            if not metrics["CPU"] and not metrics["MEM"]:
                continue

            self._create_individual_plot(name, metrics, profiling_dir)

        if len(self._stats) > 1:
            self._create_comparison_plot(profiling_dir)

    def _create_individual_plot(
        self,
        name: str,
        metrics: dict[str, list[float]],
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
            mem_label = 'Memory Usage (%)' if name == 'system' else 'Memory Usage (MB)'
            ax2.set_ylabel(mem_label, fontsize=12)
            ax2.set_xlabel('Time', fontsize=12)
            ax2.grid(True, alpha=0.3)
            ax2.legend()

            mem_stats = self._calculate_stats(metrics["MEM"])
            stats_text = f'Avg: {mem_stats["avg"]:.1f} | Max: {mem_stats["max"]:.1f}'
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

    def _create_comparison_plot(self, profiling_dir: str) -> None:
        _, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

        colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown']

        for i, (name, metrics) in enumerate(self._stats.items()):
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

        if self._stats:
            first_timestamps = [
                datetime.fromisoformat(ts)
                for ts in list(self._stats.values())[0]["timestamps"]
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
            profiling_dir = self._ensure_profiling_dir()
            log_path = os.path.join(profiling_dir, "profiling.log")
            with open(log_path, "w") as profiling_log:
                json.dump(dict(self._stats), profiling_log, indent=2)
        except Exception:
            pass

        if self._draw_plots:
            self._generate_plots()


class VedroProfiling(PluginConfig):
    plugin = VedroProfilingPlugin

    # Enable stats collection
    enable_profiling: bool = False

    # Supported profiling methods
    profiling_methods: list[str] = ["default", "docker"]

    # Poll time for stats in seconds
    poll_time: float = 1.0

    # Enable plots drawing for given profile snapshot
    draw_plots: bool = False

    # Docker Compose project name used for container profiling
    docker_compose_project_name: str = "compose"
