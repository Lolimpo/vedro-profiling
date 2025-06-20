import json
import threading
import time
from collections import defaultdict
from typing import Any, DefaultDict, Optional, Type

import docker
from matplotlib import pyplot as plt
from vedro.core import Dispatcher, Plugin, PluginConfig
from vedro.events import ArgParsedEvent, ArgParseEvent, CleanupEvent, StartupEvent


class VedroProfilingPlugin(Plugin):
    """
    Adds docker profiling support to the Vedro framework.
    """

    def __init__(self, config: Type["VedroProfiling"]):
        super().__init__(config)
        self._poll_time: float = config.poll_time
        self._enable_profiling: bool = config.enable_profiling
        self._draw_plots: bool = config.draw_plots
        self._docker_compose_project_name: str = config.docker_compose_project_name
        self._stats: DefaultDict[str, Any] = defaultdict(lambda: {"CPU": [], "MEM": []})

        self._client = docker.from_env()
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

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

    def _collect_stats(self) -> None:
        containers = self._client.containers.list(
            filters={"name": self._docker_compose_project_name}
        )
        while self._running:
            for container in containers:
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
                self._stats[container.name]["MEM"].append(mem / 1e6)  # in MB
            time.sleep(self._poll_time)

    def on_startup(self, event: StartupEvent) -> None:
        if not self._enable_profiling:
            return

        if not self._client.containers.list():
            raise RuntimeError("No running containers found for profiling.")

        self._running = True
        self._thread = threading.Thread(target=self._collect_stats, daemon=True)
        self._thread.start()

    def _generate_plots(self) -> None:
        for name, metrics in self._stats.items():
            ticks = list(range(len(metrics["CPU"])))

            # CPU plot
            plt.figure()
            plt.plot(ticks, metrics["CPU"], label="CPU (%)")
            plt.xlabel("Tick")
            plt.ylabel("CPU Usage (%)")
            plt.title(f"{name} - CPU Usage")
            plt.legend()
            plt.tight_layout()
            plt.savefig(f"{name}_cpu.png")
            plt.close()

            # Memory plot
            plt.figure()
            plt.plot(ticks, metrics["MEM"], label="Memory (MB)")
            plt.xlabel("Tick")
            plt.ylabel("Memory Usage (MB)")
            plt.title(f"{name} - Memory Usage")
            plt.legend()
            plt.tight_layout()
            plt.savefig(f"{name}_mem.png")
            plt.close()

    def on_cleanup(self, event: CleanupEvent) -> None:
        if not self._enable_profiling:
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join()

        with open("./profiling.log", "w") as profiling_log:
            json.dump(dict(self._stats), profiling_log, indent=2)

        if self._draw_plots:
            self._generate_plots()


class VedroProfiling(PluginConfig):
    plugin = VedroProfilingPlugin

    # Enable stats collection
    enable_profiling: bool = False

    # Enable plots drawing for given profile snapshot
    draw_plots: bool = False

    # Poll time for stats in seconds
    poll_time: float = 1.0

    # Docker Compose project name used for container profiling
    docker_compose_project_name: str = "compose"
