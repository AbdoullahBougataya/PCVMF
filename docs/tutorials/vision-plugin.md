# Your first vision plugin

[Documentation home](../README.md) · [Tutorials](README.md)

**Outcome:** install a small application package and select its detector through YAML. You will not change framework source files.

Complete [your first application](first-application.md) first. All commands below run from the PCVMF repository root. Use the new `tutorial_plugins` directory only for this exercise.

## 1. Create a package

```bash
mkdir -p tutorial_plugins/my_robot
```

Create the package marker:

```bash
touch tutorial_plugins/my_robot/__init__.py
```

Create `tutorial_plugins/pyproject.toml` with:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pcvmf-tutorial-robot"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["PCVMF>=0.3.0"]

[tool.hatch.build.targets.wheel]
packages = ["my_robot"]
```

## 2. Implement the detector

Create `tutorial_plugins/my_robot/vision.py`:

```python
from pcvmf.api import (
    ConfigurationError,
    PipelineResult,
    TargetDetection,
    VisionPipeline,
)


class BrightDetector(VisionPipeline):
    @classmethod
    def validate_options(cls, options):
        if options:
            raise ConfigurationError("BrightDetector takes no options")

    def initialize(self):
        pass

    def process(self, frame):
        mask = frame.image.max(axis=2) > 100
        ys, xs = mask.nonzero()
        if len(xs) == 0:
            return PipelineResult([], "NO_TARGETS")
        x, y = int(xs.min()), int(ys.min())
        width = int(xs.max()) - x + 1
        height = int(ys.max()) - y + 1
        detection = TargetDetection(
            label="bright_target",
            confidence=1.0,
            bbox=[x, y, width, height],
            centroid=[int(xs.mean()), int(ys.mean())],
        )
        return PipelineResult([detection])

    def cleanup(self):
        pass
```

The detector finds the bounding rectangle and average position of pixels with a bright channel. The synthetic green target satisfies that condition. This small algorithm does not acquire resources, so its initialization and cleanup methods are empty.

## 3. Install your package

```bash
uv pip install --python .venv/bin/python --no-deps --editable ./tutorial_plugins
```

PCVMF is already installed, so `--no-deps` keeps this step focused on the plugin. Editable installation allows changes to your module to take effect the next time you start workers. Use `uv run --no-sync` for the rest of this tutorial so `uv` keeps the separately installed package. If you later run `uv sync`, repeat this installation.

## 4. Select your detector

Create `config/tutorial-plugin.yaml`:

```yaml
logging: {level: DEBUG}
workers:
  - name: vision
    plugin:
      class: pcvmf.workers:VisionWorker
      options:
        source:
          class: pcvmf.vision.sources:SyntheticSource
          options: {width: 320, height: 240, frames: 60}
        pipeline:
          class: my_robot.vision:BrightDetector
    publications: [vision/telemetry]
  - name: controller
    plugin: {class: 'pcvmf.workers:ControllerWorker'}
    rate_hz: 50
    subscriptions:
      - {source: vision, topic: vision/telemetry}
```

```bash
uv run --no-sync pcvmf config validate config/tutorial-plugin.yaml
uv run --no-sync pcvmf run --config config/tutorial-plugin.yaml
```

Expect validation for two workers, readiness messages, target offsets, and automatic completion. `my_robot.vision:BrightDetector` names a module and class in your package; no registry inside PCVMF needs editing.

## 5. Check the algorithm directly

Create `tutorial_plugins/check_detector.py`:

```python
import numpy as np

from my_robot.vision import BrightDetector
from pcvmf.api import Frame

image = np.zeros((100, 100, 3), dtype=np.uint8)
image[20:40, 30:50, 1] = 255
frame = Frame(image, "test", 0, 1.0, 100, 100)
pipeline = BrightDetector({})
try:
    pipeline.initialize()
    result = pipeline.process(frame)
    assert result.detections[0].bbox == [30, 20, 20, 20]
    assert result.detections[0].centroid == [39, 29]
    print("Detector check passed")
finally:
    pipeline.cleanup()
```

```bash
uv run --no-sync python tutorial_plugins/check_detector.py
```

Expected output: `Detector check passed`. This check uses no processes, camera, or sockets. You have tested your algorithm separately from its runtime integration.

Continue with [multiple sensors](multiple-sensors.md), or consult the [extension contracts](../reference/api.md) when adding options or model resources.
