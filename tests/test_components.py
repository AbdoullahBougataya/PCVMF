import json
from collections import deque

import numpy as np
import pytest

from pcvmf.api import Message, ReadStatus, VisionStatus, VisionTelemetry
from pcvmf.examples import TrackingController
from pcvmf.messages import CodecRegistry
from pcvmf.runners import ControllerRunner, VisionRunner, cleanup_all
from pcvmf.vision.pipeline import ColorTracker
from pcvmf.vision.sources import SyntheticSource
from pcvmf.vision.visualizers import DisabledVisualizer


class Collector:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload):
        self.messages.append((topic, payload))


class TestController:
    __test__ = False

    def __init__(self):
        self.messages = []
        self.ticks = []

    def initialize(self):
        pass

    def on_message(self, message):
        self.messages.append(message)

    def tick(self, dt):
        self.ticks.append(dt)

    def cleanup(self):
        pass


class QueueSubscriber:
    def __init__(self, messages):
        self.messages = deque(messages)

    def receive(self, timeout_ms=0):
        return self.messages.popleft() if self.messages else None


def message(source="one", seq=0, topic="vision/telemetry"):
    return Message(topic, "vision.telemetry", 1, source, seq, 1, VisionStatus("OK", "sample"))


def test_deterministic_source_and_pipeline():
    a, b = (SyntheticSource({"width": 320, "height": 240, "frames": 2}) for _ in range(2))
    a.open("camera", 30)
    b.open("camera", 30)
    for _ in range(2):
        assert np.array_equal(a.read().frame.image, b.read().frame.image)
    assert a.read().status is ReadStatus.END
    collector = Collector()
    runner = VisionRunner(a, ColorTracker({}), collector, DisabledVisualizer({}))
    runner.initialize()
    assert runner.step()
    telemetry = collector.messages[0][1]
    assert (telemetry.width, telemetry.height) == (320, 240)
    assert telemetry.detections[0].centroid == [160, 200]
    assert telemetry.capture_time_ms >= 0 and telemetry.processing_time_ms >= 0
    controller = TrackingController({})
    controller.initialize()
    controller.on_message(Message("vision/telemetry", "vision.telemetry", 1, "camera", 0, 1, telemetry))
    assert controller.offset == (0, 80)
    runner.cleanup()


def test_latest_per_source_and_topic_and_ordered_delivery():
    messages = [message("a", 0), message("b", 0), message("a", 1), message("a", 2, "other"), message("a", 3, "other")]
    controller = TestController()
    runner = ControllerRunner(controller, QueueSubscriber(messages), deliveries={("a", "other"): "ordered"})
    runner.initialize()
    runner.step()
    assert [(m.source, m.sequence) for m in controller.messages] == [("b", 0), ("a", 1), ("a", 2), ("a", 3)]
    assert len(controller.ticks) == 1


def test_bounded_receive_and_monotonic_tick(monkeypatch):
    now = [1.0]
    controller = TestController()
    subscriber = QueueSubscriber([message(seq=i) for i in range(1000)])
    runner = ControllerRunner(controller, subscriber, max_messages=10, monotonic=lambda: now[0])
    runner.initialize()
    monkeypatch.setattr("time.time", lambda: -10000)
    now[0] = 1.5
    runner.step()
    assert len(subscriber.messages) == 990
    assert controller.ticks == [0.5]
    assert controller.messages[0].sequence == 9


def test_time_budget_also_bounds_receive():
    now = [0.0]

    class SlowSubscriber:
        def receive(self, timeout_ms=0):
            now[0] += 0.002
            return message()

    controller = TestController()
    runner = ControllerRunner(controller, SlowSubscriber(), receive_budget_ms=5, monotonic=lambda: now[0])
    runner.initialize()
    runner.step()
    assert now[0] == 0.006
    assert len(controller.ticks) == 1


def test_callbacks_propagate():
    from tests.plugins import FailingController

    runner = ControllerRunner(FailingController({}), QueueSubscriber([message()]))
    runner.initialize()
    with pytest.raises(RuntimeError, match="callback failure"):
        runner.step()


def test_cleanup_continues_after_failure():
    done = []

    def fail():
        raise RuntimeError("bad cleanup")

    with pytest.raises(RuntimeError, match="bad cleanup"):
        cleanup_all([fail, lambda: done.append(True)])
    assert done == [True]


def test_codecs_and_bad_payloads():
    registry = CodecRegistry()
    payload = VisionTelemetry(1, 320, 240, 0, 1, 2, [])
    wire = registry.encode("source", 0, 1, payload)
    assert registry.decode("vision/telemetry", wire).payload == payload
    for mutate in (
        lambda d: d.update(schema_version=999),
        lambda d: d["payload"].update(width=0),
        lambda d: d.update(sequence=True),
        lambda d: d.update(extra="bad"),
    ):
        data = json.loads(wire)
        mutate(data)
        with pytest.raises(ValueError):
            registry.decode("vision/telemetry", json.dumps(data).encode())
    with pytest.raises(ValueError):
        registry.decode("topic", b'{"timestamp": NaN}')


def test_stale_input_logs_once_and_recovers(caplog):
    now = [0.0]
    sub = QueueSubscriber([])
    runner = ControllerRunner(
        TestController(), sub, deliveries={("one", "vision/telemetry"): "latest"}, monotonic=lambda: now[0]
    )
    runner.initialize()
    now[0] = 2
    runner.step()
    runner.step()
    assert sum("Stale input" in r.message for r in caplog.records) == 1
    sub.messages.append(message())
    runner.step()
    assert not runner.stale


def test_unavailable_reads_recover_then_fail_at_limit():
    from pcvmf.api import FrameRead
    from pcvmf.vision.sources import OpenCVCamera

    source = SyntheticSource({})
    source.open("source", 30)
    frame = source.read()
    results = deque(
        [FrameRead(ReadStatus.UNAVAILABLE), frame, FrameRead(ReadStatus.UNAVAILABLE), FrameRead(ReadStatus.UNAVAILABLE)]
    )

    class Source:
        def read(self):
            return results.popleft()

    collector = Collector()
    pipeline = ColorTracker({})
    pipeline.initialize()
    runner = VisionRunner(Source(), pipeline, collector, DisabledVisualizer({}), failure_limit=2)
    assert runner.step()
    assert runner.step()
    assert runner.failures == 0
    assert runner.step()
    with pytest.raises(RuntimeError, match="2 consecutive"):
        runner.step()
    OpenCVCamera({}).close()  # Safe before open.


def test_video_eof_and_camera_unavailability(monkeypatch):
    from pcvmf.vision.sources import OpenCVCamera, VideoFileSource

    class Capture:
        def __init__(self, device):
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            return False, None

        def set(self, *args):
            pass

        def release(self):
            self.released = True

    monkeypatch.setattr("pcvmf.vision.sources.cv2.VideoCapture", Capture)
    video = VideoFileSource({"path": "test.mp4"})
    video.open("video", 30)
    assert video.read().status is ReadStatus.END
    cap = video.cap
    video.close()
    assert cap.released
    camera = OpenCVCamera({})
    camera.open("camera", 30)
    assert camera.read().status is ReadStatus.UNAVAILABLE
    camera.close()


def test_vision_worker_partial_initialization_cleanup(monkeypatch):
    from pcvmf.api import WorkerContext
    from pcvmf.workers import VisionWorker

    closed = []

    class Source:
        def open(self, *args):
            closed.append("opened")

        def close(self):
            closed.append("source")

    class Pipeline:
        def initialize(self):
            raise RuntimeError("model failed")

        def cleanup(self):
            closed.append("pipeline")

    class Visualizer:
        def close(self):
            closed.append("visualizer")

    components = iter([Source(), Pipeline(), Visualizer()])
    monkeypatch.setattr("pcvmf.workers.instantiate", lambda *args: next(components))
    worker = VisionWorker({})
    with pytest.raises(RuntimeError, match="model failed"):
        worker.initialize(WorkerContext("vision", 30, Collector()))
    worker.cleanup()
    worker.cleanup()
    assert closed == ["opened", "visualizer", "pipeline", "source"]
