# Test components without hardware

[Documentation home](../README.md) · [How-to guides](README.md)

Use direct component tests for algorithm and timing behavior, then process integration tests for wiring and lifecycle. These examples assume `uv sync --frozen --extra dev` has installed the development tools. Save test files in your application package or a dedicated test directory.

## Test a vision cycle with a collector

The following complete test uses the real synthetic source and color tracker but no ZeroMQ sockets or child processes:

```python
from pcvmf.runners import VisionRunner
from pcvmf.vision.pipeline import ColorTracker
from pcvmf.vision.sources import SyntheticSource
from pcvmf.vision.visualizers import DisabledVisualizer


def test_known_target():
    class Collector:
        def __init__(self):
            self.messages = []

        def publish(self, topic, payload):
            self.messages.append((topic, payload))

    collector = Collector()
    runner = VisionRunner(
        SyntheticSource({"width": 320, "height": 240, "frames": 1}),
        ColorTracker({}),
        collector,
        DisabledVisualizer({}),
    )
    try:
        runner.initialize()
        assert runner.step() is True
        topic, telemetry = collector.messages[0]
        assert topic == "vision/telemetry"
        assert (telemetry.width, telemetry.height) == (320, 240)
        assert telemetry.detections[0].centroid == [160, 200]
        assert runner.step() is False
    finally:
        runner.cleanup()
```

Replace `ColorTracker` with your pipeline to exercise it against reproducible frames. For exact algorithm inputs, construct a `Frame` from a NumPy array as in the [plugin tutorial](../tutorials/vision-plugin.md#5-check-the-algorithm-directly).

## Test controller timing without sleeping

Inject a clock and a fake subscriber. This test verifies that the controller sees the final value within a batch and receives the expected elapsed time:

```python
from collections import deque

from pcvmf.api import Message, VisionStatus
from pcvmf.runners import ControllerRunner


def test_latest_and_tick():
    now = [10.0]
    messages = deque(
        Message("state", "vision.status", 1, "sensor", n, 1.0,
                VisionStatus("OK", str(n)))
        for n in range(3)
    )

    class Subscriber:
        def receive(self, timeout_ms=0):
            return messages.popleft() if messages else None

    class Controller:
        def initialize(self):
            self.received = []
            self.deltas = []

        def on_message(self, message):
            self.received.append(message.payload.message)

        def tick(self, dt):
            self.deltas.append(dt)

        def cleanup(self):
            pass

    controller = Controller()
    runner = ControllerRunner(
        controller, Subscriber(),
        deliveries={("sensor", "state"): "latest"},
        monotonic=lambda: now[0],
    )
    try:
        runner.initialize()
        now[0] = 10.25
        runner.step()
        assert controller.received == ["2"]
        assert controller.deltas == [0.25]
    finally:
        runner.cleanup()
```

Direct runner tests accept simple objects implementing the required methods. Dynamically loaded production plugins must still subclass the public abstract contracts. The runner does not close a supplied subscriber or publisher; a test using real transports must close those separately.

## Verify process integration

For integration checks, exercise the actual configuration and wait for observable behavior rather than sleeping and assuming success. Use an application controller that records a known received payload and returns `False` after receipt, plus a bounded timeout for failure.

Assert that the application became ready, the expected payload was received, the result was successful, and processes and owned endpoints were cleaned up. Readiness alone does not prove delivery. Use automatic endpoints to keep parallel tests independent.

The repository contains examples in [test_runtime.py](../../tests/test_runtime.py) and [test_examples.py](../../tests/test_examples.py), including two publishers, external codecs, unexpected exits, and forced shutdown.

## Run the project checks

```bash
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen black --check .
```

Use `uv run --no-sync pytest path/to/your_test.py` if your test depends on a separately installed plugin package. If unrelated environment plugins break pytest startup, use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for that invocation. IPC integration tests require permission to bind local Unix sockets; a sandbox denial is not evidence of a pipeline failure.
