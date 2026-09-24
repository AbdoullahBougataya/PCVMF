"""Child-owned ZeroMQ resources with explicit IPC ownership."""

import logging
import os
import time
from pathlib import Path

import zmq

from .api import Publisher, Subscriber

logger = logging.getLogger(__name__)


class ZMQPublisher(Publisher):
    def __init__(self, endpoint, source, topics, registry, hwm=100, wall_clock=time.time, *, recorder=None):
        self.endpoint = endpoint
        self.source = source
        self.topics = set(topics)
        self.registry = registry
        self.wall_clock = wall_clock
        self.recorder = recorder
        self.sequence = 0
        self.context = None
        self.socket = None
        self.ipc_path = Path(endpoint[6:]) if endpoint.startswith("ipc://") else None
        self.lock_path = Path(str(self.ipc_path) + ".lock") if self.ipc_path else None
        self.owns_lock = False
        self.bound_identity = None
        try:
            if self.ipc_path:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                self.owns_lock = True
                if os.path.lexists(self.ipc_path):
                    raise RuntimeError(f"IPC endpoint already exists: {self.ipc_path}")
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.PUB)
            self.socket.setsockopt(zmq.SNDHWM, hwm)
            self.socket.bind(endpoint)
            if self.ipc_path:
                stat = self.ipc_path.stat()
                self.bound_identity = (stat.st_dev, stat.st_ino)
        except BaseException:
            self.close()
            raise

    def owned_paths(self):
        paths = []
        for path in (self.ipc_path, self.lock_path):
            if path is not None and path.exists():
                stat = path.lstat()
                paths.append((str(path), (stat.st_dev, stat.st_ino)))
        return paths

    def publish(self, topic, payload):
        if topic not in self.topics:
            raise ValueError(f"{self.source}: undeclared publication {topic!r}")
        wire = self.registry.encode(self.source, self.sequence, self.wall_clock(), payload)
        self.sequence += 1
        self.socket.send_multipart([topic.encode(), wire], flags=zmq.NOBLOCK)
        if self.recorder is not None:
            self.recorder.record_message(topic, wire)

    def close(self):
        try:
            if self.socket is not None:
                self.socket.close(linger=0)
                self.socket = None
        finally:
            try:
                if self.context is not None:
                    self.context.term()
                    self.context = None
            finally:
                if self.ipc_path and self.bound_identity and self.ipc_path.exists():
                    stat = self.ipc_path.stat()
                    if (stat.st_dev, stat.st_ino) == self.bound_identity:
                        self.ipc_path.unlink()
                self.bound_identity = None
                if self.owns_lock:
                    self.lock_path.unlink(missing_ok=True)
                    self.owns_lock = False


class ZMQSubscriber(Subscriber):
    def __init__(self, subscriptions, endpoints, registry, hwm=100):
        self.registry = registry
        self.routes = {(s.source, s.topic): s.delivery for s in subscriptions}
        self.decode_errors = 0
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        try:
            self.socket.setsockopt(zmq.RCVHWM, hwm)
            for topic in {s.topic for s in subscriptions}:
                self.socket.setsockopt(zmq.SUBSCRIBE, topic.encode())
            for source in {s.source for s in subscriptions}:
                self.socket.connect(endpoints[source])
        except BaseException:
            self.close()
            raise

    def receive(self, timeout_ms=0):
        if not self.socket.poll(timeout_ms, zmq.POLLIN):
            return None
        # One wire message per call: malformed traffic cannot create an unbounded loop.
        parts = self.socket.recv_multipart(flags=zmq.NOBLOCK)
        try:
            if len(parts) != 2:
                raise ValueError("expected topic and envelope")
            topic = parts[0].decode()
            message = self.registry.decode(topic, parts[1])
            if (message.source, topic) not in self.routes:
                return None
            return message
        except Exception as exc:
            self.decode_errors += 1
            logger.warning(
                "Discarded invalid message (decode_errors=%d): %s",
                self.decode_errors,
                exc,
            )
            return None

    def close(self):
        try:
            if self.socket is not None:
                self.socket.close(linger=0)
                self.socket = None
        finally:
            if self.context is not None:
                self.context.term()
                self.context = None
