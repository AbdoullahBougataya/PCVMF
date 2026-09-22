"""Spawn-importable behavioral fixtures, not part of the distributed framework."""

import json
import os
import signal
import time
from pathlib import Path

from pcvmf.api import Controller, VisionStatus, Worker


class ProbeWorker(Worker):
    @classmethod
    def validate_options(cls, options):
        pass

    def initialize(self, context):
        self.context = context
        self.started = context.monotonic()
        self.seen = {}
        action = self.options.get("action")
        if action == "init_fail":
            raise RuntimeError("intentional initialization failure")
        if action == "init_block":
            time.sleep(30)
        if action == "ignore_term":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def step(self):
        action = self.options.get("action")
        if action in ("block", "ignore_term"):
            time.sleep(30)
        if action == "fail":
            raise RuntimeError("intentional step failure")
        if action == "exit":
            os._exit(7)
        if action == "complete":
            return False
        if self.context.publisher:
            self.context.publisher.publish("sample", VisionStatus("OK", self.context.name))
        if self.context.subscriber:
            for _ in range(20):
                message = self.context.subscriber.receive(0)
                if message is None:
                    break
                self.seen[message.source] = message.payload.message
            if len(self.seen) >= self.options.get("expected_sources", 1):
                Path(self.options["output"]).write_text(json.dumps(self.seen))
                return False
        if self.context.monotonic() - self.started > self.options.get("deadline", 5):
            raise RuntimeError("no telemetry received before deadline")

    def cleanup(self):
        if "cleanup_file" in self.options:
            Path(self.options["cleanup_file"]).write_text("cleaned")
        if self.options.get("action") == "cleanup_fail":
            raise RuntimeError("intentional cleanup failure")
        if self.options.get("action") == "cleanup_block":
            time.sleep(30)


class FailingController(Controller):
    @classmethod
    def validate_options(cls, options):
        pass

    def initialize(self):
        pass

    def on_message(self, message):
        raise RuntimeError("intentional callback failure")

    def tick(self, dt):
        pass

    def cleanup(self):
        pass


class PayloadProbeWorker(ProbeWorker):
    def step(self):
        message = self.context.subscriber.receive(0)
        if message is not None:
            Path(self.options["output"]).write_text(type(message.payload).__name__)
            return False
        if self.context.monotonic() - self.started > 5:
            raise RuntimeError("external example did not deliver a message")
