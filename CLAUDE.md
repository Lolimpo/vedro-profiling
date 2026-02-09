# CLAUDE.md - AI Assistant Guide for vedro-profiling

This document provides comprehensive guidance for AI assistants working on the vedro-profiling codebase.

## Project Overview

**vedro-profiling** is a plugin for the [Vedro](https://vedro.io/) testing framework that measures resource usage (CPU and memory) during test execution. It supports multiple profiling methods including Docker container monitoring and system-level process monitoring via psutil.

- **Repository**: https://github.com/Lolimpo/vedro-profiling
- **PyPI Package**: vedro-profiling
- **Current Version**: 0.1.2
- **License**: Apache 2.0
- **Python Support**: 3.10, 3.11, 3.12, 3.13, 3.14

## Architecture

### Project Structure

```
vedro-profiling/
├── vedro_profiling/          # Main package
│   ├── __init__.py          # Package exports
│   ├── _vedro_profiling.py  # Core plugin implementation
│   └── py.typed             # Type checking marker
├── tests/                    # Test suite
│   ├── scenarios/           # Vedro test scenarios
│   │   └── base_test.py    # Example test scenario
│   └── vedro.cfg.py        # Vedro test configuration
├── .github/workflows/       # CI/CD pipelines
│   ├── test.yml            # Testing workflow
│   └── publish.yml         # PyPI publishing workflow
├── pyproject.toml          # Project metadata and dependencies
├── Makefile                # Development commands
└── README.md               # User documentation
```

### Core Components

#### 1. VedroProfilingPlugin (`_vedro_profiling.py:18-324`)

The main plugin class that implements profiling functionality. Key responsibilities:

- **Event Handling**: Subscribes to Vedro lifecycle events (ArgParse, ArgParsed, Startup, Cleanup)
- **Data Collection**: Runs background threads to collect CPU and memory statistics
- **Statistics Storage**: Maintains metrics as data points in a list structure
- **Visualization**: Generates matplotlib plots and comparison charts
- **Logging**: Saves profiling data in k6-compatible NDJSON format

#### 2. VedroProfiling Configuration (`_vedro_profiling.py:326-343`)

Configuration class that defines plugin settings:

```python
class VedroProfiling(PluginConfig):
    plugin = VedroProfilingPlugin
    enable_profiling: bool = False
    profiling_methods: list[str] = ["default", "docker"]
    poll_time: float = 1.0
    draw_plots: bool = False
    docker_compose_project_name: str = "compose"
    profiling_run_id: Optional[str] = None
    additional_tags: dict[str, str] = {}
```

### Key Features

#### Profiling Methods

1. **Default (psutil)** (`_vedro_profiling.py:110-133`)
   - Monitors the current process and system-level metrics
   - Tracks CPU percentage and memory usage (RSS in MB)
   - Non-daemon thread for proper interruption handling

2. **Docker** (`_vedro_profiling.py:64-108`)
   - Monitors Docker containers by compose project name
   - Filters containers by label: `com.docker.compose.project`
   - Tracks CPU percentage and memory usage (in MB)
   - Gracefully handles Docker unavailability with warnings

#### Data Collection

- Uses **threading** for concurrent metric collection
- Non-daemon threads ensure proper cleanup on interruption
- Poll interval configurable via `poll_time` (default: 1.0 seconds)
- Thread-safe stop mechanism using `threading.Event`
- Data stored as list of data points with full metadata and tags
- Each data point includes: metric name, timestamp, value, and tags (target, method, run, custom)

#### Output

1. **NDJSON Logs** (`.profiling/profiling.ndjson`)
   - k6-compatible newline-delimited JSON format
   - Metric definitions followed by data points
   - Structure: Each line is a separate JSON object (either Metric or Point type)
   - Tags for filtering: `target`, `method`, `run`, and custom tags
   - Example:
     ```json
     {"type":"Metric","metric":"cpu_percent","data":{"type":"gauge","unit":"percent"}}
     {"type":"Point","metric":"cpu_percent","data":{"time":"2026-01-26T10:00:00.123Z","value":25.5,"tags":{"target":"app-1","method":"docker","run":"test-123"}}}
     ```

2. **Visualization Plots** (`.profiling/`)
   - Individual plots per container/process (`{name}_profile.png`)
   - Comparison plot for multiple targets (`resource_comparison.png`)
   - Includes statistics annotations (avg, max, min)
   - 300 DPI resolution for high quality

## Development Workflow

### Setup

```bash
# Install dependencies using uv
make install

# Or manually
uv sync --group dev
```

### Code Quality

#### Linting

```bash
# Run type checking and linting
make lint

# Individual commands
uv run mypy vedro_profiling --strict
uv run ruff check --fix vedro_profiling
```

#### Type Checking

- **Strict mypy mode** enforced
- Type hints required for all functions
- `py.typed` marker included for PEP 561 compliance

### Testing

Tests are located in `tests/scenarios/` and use the Vedro framework:

```bash
# Run tests (command line)
vedro run tests/

# Configuration in tests/vedro.cfg.py
```

### Building

```bash
# Build package
uv build

# Clean build artifacts
make clean
```

## CI/CD

### Test Workflow (`.github/workflows/test.yml`)

- **Trigger**: On every push
- **Matrix**: Python 3.10, 3.11, 3.12, 3.13, 3.14
- **Steps**:
  1. Install uv package manager
  2. Install dependencies (`make install`)
  3. Run linting (`make lint`)

### Publish Workflow (`.github/workflows/publish.yml`)

- **Trigger**: On tag push
- **Steps**:
  1. Build package (`uv build`)
  2. Publish to PyPI (`uv publish`)
- **Requirements**: `PYPI_TOKEN` secret configured

## Dependencies

### Runtime Dependencies

```toml
docker>=7.0.0,<8.0.0         # Docker container monitoring
matplotlib>=3.10.0,<4.0.0    # Plot generation
psutil>=7.0.0,<8.0.0         # System/process monitoring
vedro>=1.13.0,<2.0.0         # Vedro framework integration
```

### Development Dependencies

```toml
mypy==1.18.2                 # Type checking
ruff==0.14.4                 # Linting and formatting
types-docker                 # Type stubs for docker
types-psutil                 # Type stubs for psutil
```

## Code Style and Conventions

### General Conventions

1. **Type Hints**: All functions must have complete type annotations
2. **Docstrings**: Classes should have descriptive docstrings
3. **Line Length**: Follow Ruff defaults
4. **Imports**: Organized by standard library, third-party, local
5. **Naming**:
   - Private methods/attributes: prefix with `_`
   - Classes: PascalCase
   - Functions/variables: snake_case

### Threading Patterns

```python
# Non-daemon threads for proper cleanup
thread = threading.Thread(
    target=self._collect_stats,
    daemon=False,  # Important for interruption handling
    name="vedro-profiling-{method}"
)
```

### Error Handling

- Use `warnings.warn()` for non-critical failures (e.g., Docker unavailable)
- Use try-except blocks for expected errors (e.g., `docker_errors.APIError`)
- Silent failures in cleanup (`on_cleanup`) to prevent test interference

### Memory Units

- **Always use MB (megabytes)** for memory metrics
- Convert using: `bytes / 1e6`
- Example: `stats["memory_stats"]["usage"] / 1e6`

## Key Patterns and Practices

### 1. Plugin Lifecycle

```python
def subscribe(self, dispatcher: Dispatcher) -> None:
    dispatcher.listen(ArgParseEvent, self.on_arg_parse) \
        .listen(ArgParsedEvent, self.on_arg_parsed) \
        .listen(StartupEvent, self.on_startup) \
        .listen(CleanupEvent, self.on_cleanup)
```

**Hook Points**:
- `on_arg_parse`: Add CLI arguments
- `on_arg_parsed`: Process parsed arguments
- `on_startup`: Initialize profiling threads
- `on_cleanup`: Stop threads and generate output

### 2. Thread Synchronization

```python
self._stop_event = threading.Event()
self._stop_event.clear()  # Start
self._stop_event.set()    # Stop
self._stop_event.wait(timeout)  # Poll with timeout
```

### 3. Statistics Collection Pattern

```python
# New k6-compatible data structure
self._data_points: list[dict[str, Any]] = []
self._metrics_definitions: dict[str, dict[str, str]] = {
    "cpu_percent": {"type": "gauge", "unit": "percent"},
    "memory_usage": {"type": "gauge", "unit": "megabytes"}
}

# Data point example
data_point = {
    "type": "Point",
    "metric": "cpu_percent",
    "data": {
        "time": "2026-01-26T10:00:00.123Z",
        "value": 25.5,
        "tags": {
            "target": "container-name",
            "method": "docker",
            "run": "run-20260126-100000",
            **additional_tags
        }
    }
}
```

### 4. Docker Container Filtering

```python
containers = client.containers.list(
    filters={
        "label": [f"com.docker.compose.project={project_name}"]
    }
)
```

## Configuration Best Practices

### For Users

```python
# vedro.cfg.py
import vedro
import vedro_profiling

class Config(vedro.Config):
    class Plugins(vedro.Config.Plugins):
        class VedroProfiling(vedro_profiling.VedroProfiling):
            enabled = True
            enable_profiling = True  # Or use --enable-profiling flag
            profiling_methods = ["default", "docker"]
            poll_time = 1.0
            draw_plots = True
            docker_compose_project_name = "your-project-name"
            profiling_run_id = "load-test-2026-01-26"  # Optional custom run ID
            additional_tags = {  # Optional custom tags
                "env": "staging",
                "team": "performance"
            }
```

### CLI Arguments

- `--enable-profiling`: Enable profiling for this run
- `--draw-plots`: Generate visualization plots
- `--run-id <id>`: Set custom run identifier (default: auto-generated timestamp)

## Common Development Tasks

### Adding a New Profiling Method

1. Add method name to `profiling_methods` default list
2. Create `_collect_{method}_stats` method following the pattern
3. Add thread initialization in `on_startup`
4. Add thread cleanup in `on_cleanup`
5. Ensure data points are generated with proper structure:
   ```python
   self._data_points.append({
       "type": "Point",
       "metric": "cpu_percent" or "memory_usage",
       "data": {
           "time": datetime.now().isoformat() + "Z",
           "value": <numeric_value>,
           "tags": {
               "target": <target_name>,
               "method": <method_name>,
               "run": self._run_id,
               **self._additional_tags
           }
       }
   })
   ```

### Modifying Plot Generation

- Data preparation: `_prepare_stats_for_plotting` - converts data points to plotting format
- Individual plots: `_create_individual_plot` - generates per-target plots
- Comparison plots: `_create_comparison_plot_from_stats` - generates multi-target comparison
- Statistics: `_calculate_stats` - calculates avg/max/min statistics

### Adding Configuration Options

1. Add to `VedroProfiling` class attributes (`_vedro_profiling.py:326-343`)
2. Initialize in `VedroProfilingPlugin.__init__`
3. If CLI-exposed, add argument in `on_arg_parse`
4. Process argument in `on_arg_parsed`

## Troubleshooting

### Docker Connection Issues

The plugin handles Docker unavailability gracefully:
- Checks for `DockerException` during client initialization
- Issues warning instead of failing
- Allows tests to continue without Docker metrics

### Thread Cleanup

Threads are non-daemon to ensure proper cleanup:
- `join(timeout=2.0)` waits for thread completion
- `_stop_event.set()` signals threads to stop
- Prevents orphaned threads or incomplete data

### Memory Measurements

- **psutil**: Reports RSS (Resident Set Size) in bytes
- **Docker**: Reports container memory usage in bytes
- **Both**: Converted to MB by dividing by `1e6`

## Version Control

### Branch Strategy

- Development happens on feature branches with prefix `claude/`
- Branch names include session IDs for tracking
- Example: `claude/claude-md-mi78pt76euvq5ibw-01NAGwAPs5edBYhsF3t1476b`

### Commit Messages

Follow conventional commit style based on repository history:
- Focus on the "why" rather than the "what"
- Be concise (1-2 sentences)
- Examples from history:
  - "Refactor memory metrics to display in MB; update labels and statistics accordingly"
  - "Update threads to be non daemon for correct interruption"
  - "Added: support for multiple profiling methods"

### Git Operations

- Use `git push -u origin <branch-name>` for new branches
- Branch must start with `claude/` for proper permissions
- Retry network failures up to 4 times with exponential backoff

## AI Assistant Guidelines

### When Working on This Codebase

1. **Always run type checking**: Changes must pass `mypy --strict`
2. **Test Docker gracefully**: Don't assume Docker is available
3. **Maintain thread safety**: Use proper synchronization primitives
4. **Convert memory units**: Always display memory in MB
5. **Update version**: Modify `pyproject.toml` version for releases
6. **Non-daemon threads**: Don't change thread daemon status
7. **Preserve event patterns**: Follow existing Vedro event subscription patterns
8. **NDJSON format**: All data points must follow k6-compatible structure with proper tags
9. **Tags consistency**: Always include target, method, and run tags in data points

### Before Making Changes

1. Read the specific file you're modifying
2. Understand the threading model (non-daemon, event-based stopping)
3. Check if changes affect CLI arguments
4. Consider Docker availability scenarios
5. Verify type hints are complete

### Testing Changes

1. Run `make lint` before committing
2. Test with and without Docker available
3. Verify plots are generated correctly
4. Check NDJSON log format is valid (each line is valid JSON)
5. Verify all data points include required tags (target, method, run)
6. Test thread cleanup (interruption handling)
7. Validate compatibility with k6/monitoring tools if possible

### Documentation Updates

When changing functionality:
1. Update docstrings if adding/modifying public APIs
2. Update README.md for user-facing changes
3. Update this CLAUDE.md for architectural changes
4. Include configuration examples if adding options

## Resources

- **Vedro Framework**: https://vedro.io/
- **Docker SDK**: https://docker-py.readthedocs.io/
- **psutil**: https://psutil.readthedocs.io/
- **matplotlib**: https://matplotlib.org/
- **uv Package Manager**: https://github.com/astral-sh/uv

## Project-Specific Notes

### Recent Changes (as of v0.2.0)

- **BREAKING**: Log format changed from JSON to k6-compatible NDJSON
- **NEW**: Support for custom run IDs and additional tags
- **NEW**: Data points include full metadata and tags for filtering
- Memory metrics now displayed in MB (previously in bytes)
- Threads changed to non-daemon for correct interruption handling
- Support for multiple profiling methods (docker, psutil)
- Statistics collection refactored to use data points structure

### Known Considerations

- Docker profiling requires containers with proper compose labels
- Thread join timeout is 2.0 seconds (may need adjustment for slow systems)
- Plot colors are limited to 6 (cycles after that)
- Timestamps are ISO format strings with 'Z' suffix (UTC timezone)
- NDJSON output: each line is a separate JSON object (not a single JSON array)
- Run ID is auto-generated if not provided (format: `run-YYYYMMDD-HHMMSS`)

## Quick Reference

```bash
# Setup
make install

# Lint
make lint

# Clean
make clean

# Build
uv build

# Run tests
vedro run tests/

# Run with profiling
vedro run tests/ --enable-profiling --draw-plots

# Run with custom run ID
vedro run tests/ --enable-profiling --run-id my-test-123

# Process NDJSON output
cat .profiling/profiling.ndjson | jq -c 'select(.type=="Point")'
```

---

**Last Updated**: 2025-11-20
**Document Version**: 1.0
**Codebase Version**: 0.1.2
