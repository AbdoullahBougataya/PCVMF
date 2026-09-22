"""Single-step runners usable without processes, cameras, or ZeroMQ."""

import logging
import time

from .api import ReadStatus, VisionTelemetry

logger = logging.getLogger(__name__)


def cleanup_all(callbacks):
    errors = []
    for callback in callbacks:
        try:
            callback()
        except BaseException as exc:
            logger.exception("Cleanup failed")
            errors.append(exc)
    if errors:
        raise RuntimeError("cleanup failed: " + "; ".join(str(e) for e in errors)) from errors[0]


class VisionRunner:
    def __init__(
        self,
        source,
        pipeline,
        publisher,
        visualizer,
        *,
        source_id="vision",
        rate_hz=30,
        failure_limit=10,
        topic="vision/telemetry",
        monotonic=time.monotonic,
    ):
        self.source = source
        self.pipeline = pipeline
        self.publisher = publisher
        self.visualizer = visualizer
        self.source_id = source_id
        self.rate_hz = rate_hz
        self.failure_limit = failure_limit
        self.topic = topic
        self.monotonic = monotonic
        self.failures = 0

    def initialize(self):
        self.source.open(self.source_id, self.rate_hz)
        self.pipeline.initialize()

    def step(self):
        start = self.monotonic()
        result = self.source.read()
        capture_ms = (self.monotonic() - start) * 1000
        if result.status is ReadStatus.END:
            return False
        if result.status is ReadStatus.UNAVAILABLE:
            self.failures += 1
            if self.failures >= self.failure_limit:
                raise RuntimeError(f"frame source failed {self.failures} consecutive reads")
            return True
        self.failures = 0
        frame = result.frame
        if frame is None:
            raise ValueError("frame source returned FRAME without a frame")
        start = self.monotonic()
        output = self.pipeline.process(frame)
        processing_ms = (self.monotonic() - start) * 1000
        telemetry = VisionTelemetry(
            frame.captured_at,
            frame.width,
            frame.height,
            frame.sequence,
            capture_ms,
            processing_ms,
            output.detections,
            output.status,
        )
        self.publisher.publish(self.topic, telemetry)
        return self.visualizer.render(frame, output)

    def cleanup(self):
        cleanup_all([self.visualizer.close, self.pipeline.cleanup, self.source.close])


class ControllerRunner:
    def __init__(
        self,
        controller,
        subscriber,
        *,
        deliveries=None,
        max_messages=100,
        receive_budget_ms=5,
        stale_after_s=1,
        monotonic=time.monotonic,
    ):
        self.controller = controller
        self.subscriber = subscriber
        self.deliveries = deliveries or {}
        self.max_messages = max_messages
        self.receive_budget = receive_budget_ms / 1000
        self.stale_after_s = stale_after_s
        self.monotonic = monotonic
        self.last_received = {}
        self.stale = set()
        self.last_tick = None

    def initialize(self):
        self.controller.initialize()
        self.last_tick = self.monotonic()
        self.last_received = {key: self.last_tick for key in self.deliveries}

    def step(self):
        start = self.monotonic()
        pending = []
        latest_indices = {}
        if self.subscriber is not None:
            for _ in range(self.max_messages):
                if self.monotonic() - start >= self.receive_budget:
                    break
                message = self.subscriber.receive(timeout_ms=0)
                if message is None:
                    break
                key = (message.source, message.topic)
                self.last_received[key] = self.monotonic()
                if key in self.stale:
                    logger.info("Input recovered: %s/%s", *key)
                    self.stale.remove(key)
                mode = self.deliveries.get(
                    key,
                    ("latest" if message.message_type == "vision.telemetry" else "ordered"),
                )
                if mode == "latest":
                    if key in latest_indices:
                        pending[latest_indices[key]] = None
                    latest_indices[key] = len(pending)
                pending.append(message)
        for message in pending:
            if message is not None:
                self.controller.on_message(message)
        now = self.monotonic()
        for key, last in self.last_received.items():
            if now - last >= self.stale_after_s and key not in self.stale:
                logger.warning("Stale input: %s/%s (%.3fs)", *key, now - last)
                self.stale.add(key)
        dt = now - self.last_tick
        self.last_tick = now
        return self.controller.tick(dt)

    def cleanup(self):
        self.controller.cleanup()
