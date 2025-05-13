import json
import threading
import time
from collections import defaultdict
from typing import Optional, Type

import docker
from vedro.core import Dispatcher, Plugin, PluginConfig
from vedro.events import ArgParsedEvent, ArgParseEvent, CleanupEvent, StartupEvent


class VedroProfilingPlugin(Plugin):
    """
    Adds docker profiling support to the framework.
    """

    def __init__(self, config: Type["VedroProfiling"]):
        super().__init__(config)
        self._poll_time = config.poll_time
        self._enable_profiling = config.enable_profiling
        self._stats = defaultdict(lambda: {"CPU": [], "MEM": []})

        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._client = docker.from_env()

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
            help="Enable recording of containers status during scenario execution"
        )

    def on_arg_parsed(self, event: ArgParsedEvent) -> None:
        self._enable_profiling = event.args.enable_profiling

    def _collect_stats(self) -> None:
        while not self._running.is_set():
            containers = self._client.containers.list()
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
        if self._enable_profiling:
            if not self._client.containers.list():
                raise RuntimeError("No running containers found for profiling.")

            self._running.clear()
            self._thread = threading.Thread(target=self._collect_stats)
            self._thread.daemon = True
            self._thread.start()

    def on_cleanup(self, event: CleanupEvent) -> None:
        if self._enable_profiling:
            if self._thread and self._thread.is_alive():
                self._running.set()
                self._thread.join(timeout=2.0)
            with open("./profiling.log", "w") as profiling_log:
                json.dump(dict(self._stats), profiling_log, indent=2)


class VedroProfiling(PluginConfig):
    plugin = VedroProfilingPlugin

    # Enable stats collection
    enable_profiling: bool = False

    # Enable plots drawing for given profile snapshot
    draw_plots: bool = False

    # Poll time for stats in seconds
    poll_time: float = 1.0
