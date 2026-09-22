# Built-in components

[Documentation home](../README.md) · [Reference](README.md)

Implementation: [workers.py](../../src/pcvmf/workers.py), [vision sources](../../src/pcvmf/vision/sources.py), [pipeline](../../src/pcvmf/vision/pipeline.py), and [visualizers](../../src/pcvmf/vision/visualizers.py).

All values in the following tables belong in a plugin's `options` mapping. Unknown options are rejected by the built-ins.

## VisionWorker

Import path: `pcvmf.workers:VisionWorker`.

| Option | Default | Meaning |
|---|---|---|
| `source` | `pcvmf.vision.sources:SyntheticSource` | Frame-source plugin specification |
| `pipeline` | `pcvmf.vision.pipeline:ColorTracker` | Vision-pipeline plugin specification |
| `visualizer` | `pcvmf.vision.visualizers:DisabledVisualizer` | Visualizer plugin specification |
| `failure_limit` | `10` | Positive integer consecutive unavailable reads before failure |
| `topic` | `vision/telemetry` | Declared publication receiving `VisionTelemetry` |

Initialize opens the source and initializes the pipeline. Each step reads one frame, runs the pipeline, publishes telemetry, and renders if enabled. A successful read resets the consecutive-failure counter. End-of-stream or a visualizer returning `False` requests normal completion of the application.

`rate_hz` belongs to the worker, not these options. Sources do not add a scheduling sleep.

## Frame sources

### SyntheticSource

Import path: `pcvmf.vision.sources:SyntheticSource`.

| Option | Default | Constraint |
|---|---|---|
| `width` | `640` | Positive integer pixels |
| `height` | `480` | Positive integer pixels |
| `frames` | Unlimited | Positive integer frame count when supplied |

Produces a green moving circle on a black BGR image. Its trajectory is deterministic from sequence and rate, while capture timestamps use wall-clock time. Sequence starts at zero. A finite source returns `END` on the read after its last frame.

### OpenCVCamera

Import path: `pcvmf.vision.sources:OpenCVCamera`.

| Option | Default | Constraint |
|---|---|---|
| `device` | `0` | Nonnegative integer OpenCV camera index |
| `width` | Backend default | Positive integer requested pixels |
| `height` | Backend default | Positive integer requested pixels |

Requests the worker's `rate_hz` from the capture backend. Hardware may ignore requested resolution or FPS; returned frames carry actual dimensions. An unsuccessful open raises an error. A failed read returns `UNAVAILABLE`.

### VideoFileSource

Import path: `pcvmf.vision.sources:VideoFileSource`.

The only option is required nonempty string `path`. Relative paths resolve from the process working directory, not from the YAML file location. A failed open raises an error. A failed read becomes `END`, including decode failures the backend does not distinguish from EOF. Playback follows the worker's configured rate; the file's embedded FPS is not adopted automatically.

## ColorTracker

Import path: `pcvmf.vision.pipeline:ColorTracker`.

| Option | Default | Constraint |
|---|---|---|
| `min_area` | `300` | Finite nonnegative contour area |
| `lower_hsv` | `[35, 100, 100]` | Three integers: H 0–179, S/V 0–255 |
| `upper_hsv` | `[85, 255, 255]` | Same ranges; each value at least its lower bound |

Converts BGR to HSV, thresholds the image, applies morphological opening, and finds contours. Each qualifying contour produces label `color_target`, confidence `1.0`, an axis-aligned box, box-center centroid, and `extra_attributes.area`. Confidence is a fixed example value, not a calibrated probability. Detection order is not a ranking guarantee.

Returns status `OK` when detections exist and `NO_TARGETS` otherwise.

## Visualizers

| Import path | Behavior |
|---|---|
| `pcvmf.vision.visualizers:DisabledVisualizer` | No display; `render()` returns `True` |
| `pcvmf.vision.visualizers:OpenCVVisualizer` | Copies the frame, draws boxes and labels, shows the `PCVMF` window |

Neither accepts options. OpenCV visualization requires a working graphical session. Escape or Q returns `False`, ending the application normally. Multiple GUI workers are not part of the headless examples.

## ControllerWorker

Import path: `pcvmf.workers:ControllerWorker`.

| Option | Default | Constraint or meaning |
|---|---|---|
| `controller` | `pcvmf.examples:TrackingController` | Controller plugin specification |
| `max_messages` | `100` | Positive integer batch limit |
| `receive_budget_ms` | `5` | Positive receive-batch budget in milliseconds |
| `stale_after_s` | `1` | Positive local input-silence threshold in seconds |

Receives a bounded batch, applies subscription delivery policies, invokes callbacks, logs stale/recovered routes, and calls `tick(dt)`. The receive budget does not bound callback execution time. Controller exceptions fail the worker. Returning `False` from `tick()` ends the whole application normally.

## TrackingController

Import path: `pcvmf.examples:TrackingController`. No options.

For received `VisionTelemetry`, selects the first detection and stores its centroid offset from the image center. No detections clears the offset. Non-vision messages are ignored. Target offsets are logged at DEBUG. This is a demonstration controller; it does not operate hardware or implement a stale-data stop policy.

The independent [example package](../../examples/external_plugins) adds a bright-pixel pipeline and temperature worker/codec/controller. It must be installed separately and is not part of the PCVMF wheel.
