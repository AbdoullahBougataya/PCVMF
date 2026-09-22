<p align="center"><img src="img/PCVMF.png" alt="PCVMF Logo" width="180" /></p>

# PCVMF

PCVMF runs computer vision, application control, and sensor workers in independent Python processes. Applications provide plugins and connect their publications through YAML. ZeroMQ carries typed JSON messages; a separate lifecycle channel supervises startup, progress, and shutdown.

Version **0.3.0** introduces a breaking public API. See [migration notes](docs/how-to/migrate-to-0.3.md). Linux and Python 3.10–3.12 are tested. Scheduling is best-effort, not a hard real-time guarantee.

## Documentation

The [documentation hub](docs/README.md) organizes the full guide using Diátaxis:

- [Tutorials](docs/tutorials/README.md): build a first application, an external detector, and a multi-sensor application.
- [How-to guides](docs/how-to/README.md): use hardware, add sensors, test, embed, package, migrate, and troubleshoot.
- [Reference](docs/reference/README.md): configuration, components, public APIs, messages, and CLI behavior.
- [Explanation](docs/explanation/README.md): architecture, delivery and timing, lifecycle, and failure policy.

## Quick start

You need Linux, Python 3.10–3.12, and `uv` for the commands below. Open a terminal in the repository root (the directory containing `pyproject.toml`). No camera, GPU, or desktop session is required.

### 1. Install the framework

```bash
uv sync --frozen --extra dev
```

This creates the project virtual environment and installs PCVMF with its development tools. You do not need to activate the environment when using `uv run`.

### 2. Run the built-in demo

```bash
uv run --frozen pcvmf run
```

The demo starts two workers: a vision pipeline tracking a moving synthetic target, and a controller receiving its detections. Look for these messages in the logs (worker readiness order may vary):

```text
Worker vision ready
Worker controller ready
Application ready: 2 workers
```

The default demo runs headlessly, so no window opens. It does not print every detection at the default INFO log level. **Press Ctrl+C to stop** before starting another example.

### 3. Run with your own configuration

Start with the supplied configuration, validate it, then run it:

```bash
cp config/default_config.yaml config/my_app.yaml
uv run --frozen pcvmf config validate config/my_app.yaml
uv run --frozen pcvmf run --config config/my_app.yaml
```

A valid configuration prints `Valid configuration: 2 workers`. Edit `config/my_app.yaml` to change the image dimensions, pipeline options, or worker rates; the [configuration reference](docs/reference/configuration.md) describes each field. For detection offsets in the demo logs, change `logging.level` to `DEBUG`.

### Using pip instead of uv

Choose this setup if you do not use `uv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pcvmf run
```

With the environment activated, use `pcvmf ...` directly wherever this guide shows `uv run ... pcvmf ...`. `python -m pcvmf run` is also supported. Running without `--config` loads packaged defaults and works outside the checkout; relative configuration paths are resolved from your current directory.

Configuration errors exit with code 2; runtime or cleanup failures exit with code 1; normal completion and successful signal shutdown exit with code 0.

## How to use the examples

The examples demonstrate plugins maintained outside the framework package. Both use synthetic input, so you can run them without hardware. Run the following commands from the repository root after completing the installation above.

### 1. Install the example plugins once

```bash
uv pip install --python .venv/bin/python --no-deps --editable ./examples/external_plugins
```

For a pip-based setup, with your environment activated, use:

```bash
python -m pip install --no-deps -e ./examples/external_plugins
```

The editable install lets you change the example Python files and use those changes on the next run. The examples below use `uv run --no-sync` to preserve this separately installed package. If you run `uv sync` later and an example reports `cannot import robot_plugins...`, repeat the installation command.

### 2. Try the external vision pipeline

```bash
uv run --no-sync pcvmf config validate examples/vision.yaml
uv run --no-sync pcvmf run --config examples/vision.yaml
```

[The vision configuration](examples/vision.yaml) connects synthetic camera frames to [BrightPixelPipeline](examples/external_plugins/robot_plugins/vision.py), which detects bright pixels and returns a bounding box and centroid. The bundled tracking controller consumes those detections. Expect `Application ready: 2 workers`; this example is also headless and quiet at INFO level. Press Ctrl+C when finished.

To see target offsets, copy the configuration and add a top-level logging setting:

```bash
cp examples/vision.yaml config/my_vision.yaml
```

```yaml
logging:
  level: DEBUG
```

Then run `uv run --no-sync pcvmf run --config config/my_vision.yaml`. To display the frames in a desktop session, also add the following under the vision worker's `plugin.options`, alongside `pipeline`:

```yaml
visualizer:
  class: pcvmf.vision.visualizers:OpenCVVisualizer
```

### 3. Try a non-vision sensor

```bash
uv run --no-sync pcvmf config validate examples/sensor.yaml
uv run --no-sync pcvmf run --config examples/sensor.yaml
```

[The sensor configuration](examples/sensor.yaml) starts a synthetic temperature publisher and a controller. [The sensor plugin module](examples/external_plugins/robot_plugins/sensor.py) includes the worker, the typed `Temperature` payload, its JSON codec, and the controller. After readiness, expect a message like:

```text
Received temperature from temperature: 20.00 C
```

The value may differ; the controller logs the first received reading once and then keeps running. Press Ctrl+C to stop.

### 4. Adapt an example for your project

Use the vision example to replace image processing, or the sensor example to add a new data source and message type. Edit the plugin implementation, point your copied YAML at its `module:Class`, then validate and rerun it. Every published topic must appear in the worker's `publications`, and subscriptions must reference that worker and topic. See [Develop a plugin](#develop-a-plugin) and the [plugin guide](docs/reference/api.md) for the contracts.

## Connect workers

```yaml
logging: {level: INFO}
workers:
  - name: vision
    plugin:
      class: pcvmf.workers:VisionWorker
      options:
        source:
          class: pcvmf.vision.sources:SyntheticSource
          options: {width: 320, height: 240}
        pipeline:
          class: pcvmf.vision.pipeline:ColorTracker
          options: {min_area: 100}
    rate_hz: 30
    publications: [vision/telemetry]
  - name: controller
    plugin: {class: 'pcvmf.workers:ControllerWorker'}
    rate_hz: 50
    subscriptions:
      - {source: vision, topic: vision/telemetry, delivery: latest}
```

Each publisher owns its own endpoint. The runtime allocates a unique IPC directory for each application instance. Subscriptions name an upstream worker and an exact topic; adding another publisher does not require modifying the supervisor or sharing a bind address.

Configuration is checked before processes start: unknown keys, invalid plugin types/options, duplicate names/endpoints, and missing publication references are errors. Plugin imports and validators must not acquire resources. Configuration files select Python code, so use trusted configuration and installed plugins.

See the [configuration and lifecycle reference](docs/reference/configuration.md).

## Develop a plugin

Import extension contracts from `pcvmf.api`. Supply a concrete subclass with a resource-free `validate_options()` method. Put the plugin in your own installable package and reference `your_package.module:Class` in YAML.

```python
from pcvmf.api import ConfigurationError, PipelineResult, VisionPipeline

class MyPipeline(VisionPipeline):
    @classmethod
    def validate_options(cls, options):
        if options:
            raise ConfigurationError("MyPipeline takes no options")

    def initialize(self):
        # Load your model here, inside the vision process.
        pass

    def process(self, frame):
        # frame.image is a BGR NumPy array; return TargetDetection objects.
        return PipelineResult([], "NO_TARGETS")

    def cleanup(self):
        # Must also work if initialize() failed partway through.
        pass
```

Supported contracts include `Worker`, `FrameSource`, `VisionPipeline`, `Controller`, `Visualizer`, `Publisher`, `Subscriber`, and `MessageCodec`. Constructors and validators must remain resource-free. Methods must return within the worker's configured timeouts.

The [plugin guide](docs/reference/api.md) explains custom messages and component testing. For installation and runnable walkthroughs, see [How to use the examples](#how-to-use-the-examples).

## Embed and test

The configuration loader, application runner, and component runners are supported application APIs alongside `pcvmf.api`:

```python
from pcvmf.config import load_config
from pcvmf.runtime import Application

if __name__ == "__main__":
    app = Application(load_config("application.yaml"))
    result = app.run()
    raise SystemExit(result.exit_code)
```

Use the `__main__` guard because workers use multiprocessing's `spawn` context. `Application` does not install signal handlers; an embedding application can call `request_stop()`. Each instance runs once. `RunResult` contains `exit_code`, `errors`, and whether the application became `ready`. An optional `on_event(worker_name, event)` callback receives lifecycle notifications in the supervisor; it must return promptly.

`VisionRunner` and `ControllerRunner` in `pcvmf.runners` accept injectable components and monotonic clocks for synchronous testing without multiprocessing or ZeroMQ. Plugin cleanup does not own framework-provided transports: the runtime closes them after plugin cleanup.

```bash
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen black --check .
uv build
```

The suite exercises actual telemetry exchange, multiple publishers, external plugins, scheduling limits, signals, failures, timeouts, and cleanup. If another environment injects unrelated pytest plugins, use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

## Distribution and containers

`requirements.txt` contains locked runtime dependencies; it does not install PCVMF itself. Build and install the wheel separately:

```bash
uv build
uv venv /tmp/pcvmf-wheel
uv pip install --python /tmp/pcvmf-wheel/bin/python -r requirements.txt dist/*.whl
/tmp/pcvmf-wheel/bin/python scripts/smoke.py
```

The smoke script runs the installed demo outside the checkout, waits for readiness, and verifies successful SIGTERM shutdown.

```bash
docker build -t pcvmf:local .
docker run --rm pcvmf:local
docker run --rm pcvmf:local python /opt/pcvmf-smoke.py
```

The image installs a wheel and runs as a non-root user. For a custom application, install its plugin package in a derived image and mount/pass its configuration. GUI support remains opt-in; the standard container runs headlessly.

Regenerate locked requirements after changing dependencies:

```bash
uv lock
uv export --frozen --format requirements-txt --no-hashes --no-dev --no-emit-project -o requirements.txt
```

GitHub and GitLab CI test Python 3.10, 3.11, and 3.12, clean wheel installations, both external examples, and the Docker image. Publishing is handled separately by the release workflow.
