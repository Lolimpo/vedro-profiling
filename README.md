# Vedro profiling

[![PyPI](https://img.shields.io/pypi/v/vedro-profiling.svg)](https://pypi.python.org/pypi/vedro-profiling/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/vedro-profiling)](https://pypi.python.org/pypi/vedro-profiling/)
[![Python Version](https://img.shields.io/pypi/pyversions/vedro-profiling.svg)](https://pypi.python.org/pypi/vedro-profiling/)

> **Vedro profiling** - plugin for [Vedro](https://vedro.io/) framework for measuring resource usage of tests

The plugin measures CPU and memory usage during test execution and exports metrics in k6-compatible NDJSON format, making it easy to integrate with performance monitoring tools like Grafana, InfluxDB, and other observability platforms.

## Installation

<details open>
<summary>Quick</summary>
<p>

For a quick installation, you can use a plugin manager as follows:

```shell
$ vedro plugin install vedro-profiling
```

</p>
</details>

<details>
<summary>Manual</summary>
<p>

To install manually, follow these steps:

1. Install the package using pip:

```shell
$ pip3 install vedro-profiling
```

2. Next, activate the plugin in your `vedro.cfg.py` configuration file:

```python
# ./vedro.cfg.py
import vedro
import vedro_profiling


class Config(vedro.Config):
    class Plugins(vedro.Config.Plugins):
        class VedroProfiling(vedro_profiling.VedroProfiling):
            enabled = True
```

</p>
</details>

## Usage

### Basic Usage

Enable profiling for your test run:

```shell
$ vedro run --enable-profiling
```

This will create a `.profiling/profiling.ndjson` file with CPU and memory metrics in k6-compatible format.

### With Custom Run ID

```shell
$ vedro run --enable-profiling --run-id load-test-2026-01-26
```

### With Visualization

Generate matplotlib plots alongside the metrics:

```shell
$ vedro run --enable-profiling --draw-plots
```

## Configuration

### Advanced Configuration

```python
# ./vedro.cfg.py
import vedro
import vedro_profiling


class Config(vedro.Config):
    class Plugins(vedro.Config.Plugins):
        class VedroProfiling(vedro_profiling.VedroProfiling):
            enabled = True
            enable_profiling = True
            
            # Profiling methods: "default" (psutil), "docker" (containers)
            profiling_methods = ["default", "docker"]
            
            # Polling interval in seconds
            poll_time = 1.0
            
            # Generate plots
            draw_plots = True
            
            # Docker Compose project name for container monitoring
            docker_compose_project_name = "my-project"
            
            # Custom run identifier
            profiling_run_id = "staging-load-test"
            
            # Additional tags for metrics
            additional_tags = {
                "env": "staging",
                "team": "performance",
                "region": "us-east-1"
            }
```

## Output Format

The plugin generates metrics in **NDJSON (newline-delimited JSON)** format compatible with k6 and other performance monitoring tools.

### File Location

- Metrics: `.profiling/profiling.ndjson`
- Plots (if enabled): `.profiling/*.png`

### NDJSON Structure

The output file contains metric definitions followed by data points:

```json
{"type":"Metric","metric":"cpu_percent","data":{"type":"gauge","unit":"percent"}}
{"type":"Metric","metric":"memory_usage","data":{"type":"gauge","unit":"megabytes"}}
{"type":"Point","metric":"cpu_percent","data":{"time":"2026-01-26T10:00:00.123Z","value":25.5,"tags":{"target":"app-1","method":"docker","run":"my-test-123"}}}
{"type":"Point","metric":"memory_usage","data":{"time":"2026-01-26T10:00:00.123Z","value":512.3,"tags":{"target":"app-1","method":"docker","run":"my-test-123"}}}
```

### Metrics

- `cpu_percent` - CPU usage percentage (gauge)
- `memory_usage` - Memory usage in megabytes (gauge)

### Tags

Each data point includes the following tags:

- `target` - Container name or process name
- `method` - Profiling method (`docker` or `default`)
- `run` - Unique run identifier
- Custom tags from configuration

## Processing Data

### Extract Data Points Only

```bash
cat .profiling/profiling.ndjson | jq -c 'select(.type=="Point")'
```

### Filter by Tags

```bash
cat .profiling/profiling.ndjson | jq -c 'select(.type=="Point" and .data.tags.env=="staging")'
```

### Convert to InfluxDB Line Protocol

```bash
cat .profiling/profiling.ndjson | jq -r '
  select(.type=="Point") | 
  "\(.metric),target=\(.data.tags.target),method=\(.data.tags.method) value=\(.data.value) \(.data.time | fromdate * 1000000000)"
'
```

### Aggregate Metrics

```bash
# Average CPU by target
cat .profiling/profiling.ndjson | jq -s '
  [.[] | select(.type=="Point" and .metric=="cpu_percent")] |
  group_by(.data.tags.target) |
  map({target: .[0].data.tags.target, avg_cpu: ([.[].data.value] | add / length)})
'
```

## Features

- **Multiple Profiling Methods**: Monitor both system-level metrics (via psutil) and Docker container metrics
- **k6-Compatible Format**: Export metrics in NDJSON format for easy integration with monitoring tools
- **Custom Tags**: Add custom tags for filtering and grouping metrics
- **Visualization**: Generate matplotlib plots for quick visual analysis
- **Non-Blocking**: Uses background threads to minimize impact on test execution
- **Flexible Configuration**: Configure via code or command-line arguments

## Integration Examples

### Grafana + InfluxDB

1. Convert NDJSON to InfluxDB Line Protocol
2. Import into InfluxDB:

```bash
influx write --bucket performance --file profiling.influx
```

3. Create Grafana dashboard using InfluxDB as data source

### Custom Analysis

```python
import json

# Read and process metrics
with open('.profiling/profiling.ndjson') as f:
    for line in f:
        point = json.loads(line)
        if point['type'] == 'Point':
            metric = point['metric']
            value = point['data']['value']
            tags = point['data']['tags']
            # Process metrics...
```
