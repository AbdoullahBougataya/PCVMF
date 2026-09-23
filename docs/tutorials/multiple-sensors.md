# Combine vision and temperature

[Documentation home](../README.md) · [Tutorials](README.md)

**Outcome:** receive two independent publishers in one controller and distinguish their typed payloads.

Complete [your first vision plugin](vision-plugin.md) first: this exercise adds a module to its installed `my_robot` package. Run every command from the repository root and use `uv run --no-sync` after installing separate plugins. We will also use the repository's synthetic temperature example. No sensor hardware is required.

## 1. Install the temperature example

From the repository root:

```bash
uv pip install --python .venv/bin/python --no-deps --editable ./examples/external_plugins
```

The package provides `TemperatureWorker`, `TemperatureCodec`, and the `Temperature` dataclass in `robot_plugins.sensor`. Check that the package is available in the environment used for the run:

```bash
uv run --no-sync python -c "from robot_plugins.sensor import Temperature; print(Temperature.__name__)"
```

Expected output: `Temperature`. If import fails after a later `uv sync`, repeat the installation command above.

## 2. Write a controller that recognizes both payloads

Create `tutorial_plugins/my_robot/controller.py`:

```python
import logging

from pcvmf.api import ConfigurationError, Controller, VisionTelemetry
from robot_plugins.sensor import Temperature

logger = logging.getLogger(__name__)


class CombinedController(Controller):
    @classmethod
    def validate_options(cls, options):
        if options:
            raise ConfigurationError("CombinedController takes no options")

    def initialize(self):
        self.seen_vision = False
        self.seen_temperature = False

    def on_message(self, message):
        if isinstance(message.payload, VisionTelemetry) and not self.seen_vision:
            logger.info("Received vision from %s", message.source)
            self.seen_vision = True
        elif isinstance(message.payload, Temperature) and not self.seen_temperature:
            logger.info("Received temperature from %s", message.source)
            self.seen_temperature = True

    def tick(self, dt):
        if self.seen_vision and self.seen_temperature:
            logger.info("Both sources received; completing the application")
            return False

    def cleanup(self):
        pass
```

The package is already editable, so this new module is available without reinstalling it. This exercise imports the separately installed example package; a distributed application would also declare that package as a dependency.

## 3. Connect the three workers

Create `config/tutorial-multiple.yaml`:

```yaml
codecs: ['robot_plugins.sensor:TemperatureCodec']
workers:
  - name: vision
    plugin:
      class: pcvmf.workers:VisionWorker
      options:
        pipeline: {class: 'my_robot.vision:BrightDetector'}
    rate_hz: 30
    publications: [vision/telemetry]
  - name: temperature
    plugin: {class: 'robot_plugins.sensor:TemperatureWorker'}
    rate_hz: 10
    publications: [sensor/temperature]
  - name: controller
    plugin:
      class: pcvmf.workers:ControllerWorker
      options:
        controller: {class: 'my_robot.controller:CombinedController'}
    rate_hz: 50
    subscriptions:
      - {source: vision, topic: vision/telemetry, delivery: latest}
      - {source: temperature, topic: sensor/temperature, delivery: ordered}
```

```bash
uv run --no-sync pcvmf config validate config/tutorial-multiple.yaml
uv run --no-sync pcvmf run --config config/tutorial-multiple.yaml
```

Validation should report three workers. After readiness, the controller logs receipt from `vision` and `temperature`, then logs `Both sources received; completing the application` and stops the application normally. The order of the two receipt messages is unspecified.

The publisher names in subscriptions identify the source; the topic identifies its publication. Each publisher received its own automatically allocated endpoint. The custom codec converts the temperature payload back into a `Temperature` instance before the controller sees it.

## 4. Keep the application running

Replace the body of `tick()` with `pass` and run again. The controller now continues after receiving both sources; press Ctrl+C to stop. You have changed the application completion policy without changing transport or supervision code.

You now have a working pattern for adding sensors to an application. See [add a sensor and message type](../how-to/add-sensor.md) for adapting it to a device, and [delivery and timing](../explanation/delivery-and-timing.md) for the limits of this messaging pattern.
