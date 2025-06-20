# Vedro profiling

[![PyPI](https://img.shields.io/pypi/v/vedro-profiling.svg)](https://pypi.python.org/pypi/vedro-profiling/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/vedro-profiling)](https://pypi.python.org/pypi/vedro-profiling/)
[![Python Version](https://img.shields.io/pypi/pyversions/vedro-profiling.svg)](https://pypi.python.org/pypi/vedro-profiling/)

> **Vedro profiling** - plugin for [Vedro](https://vedro.io/) framework for measuring resource usage of tests

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
