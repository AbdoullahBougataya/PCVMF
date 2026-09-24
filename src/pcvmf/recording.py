"""Run-owned MCAP output and bounded, acknowledged worker recording transport."""

import json
import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import zmq
from mcap.writer import CompressionType, Writer

from . import __version__

LOG_TOPIC = "/pcvmf/logs"


class RecordingError(RuntimeError):
    """The configured recording could not be completed."""


def _json(data):
    return json.dumps(data, allow_nan=False, separators=(",", ":")).encode()


def _schema(properties):
    return _json(
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }
    )


class McapRecorder:
    """One writer owned by the supervisor; no writer or file is shared with children."""

    def __init__(self, options, endpoint):
        self.path = None
        self.stream = None
        self.writer = None
        self.context = None
        self.socket = None
        self.error = None
        self.schemas = {}
        self.channels = {}
        self.pending_logs = deque()
        self.queue_size = options["queue_size"]
        self.lock = threading.RLock()
        self.closed = False
        try:
            directory = Path(options["directory"]).resolve()
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            path = directory / f"pcvmf-{stamp}-{uuid.uuid4().hex}.mcap"
            self.stream = path.open("xb")
            self.path = str(path)
            self.writer = Writer(self.stream, compression=CompressionType[options["compression"].upper()])
            self.writer.start(library=f"pcvmf/{__version__}")
            self.writer.add_metadata("pcvmf.recording", {"version": "1", "pcvmf_version": __version__})
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.ROUTER)
            self.socket.setsockopt(zmq.RCVHWM, options["queue_size"])
            self.socket.setsockopt(zmq.SNDHWM, options["queue_size"])
            self.socket.setsockopt(zmq.ROUTER_MANDATORY, 1)
            self.socket.bind(endpoint)
        except BaseException:
            self.close()
            raise

    def _failed(self, exc):
        # Do not log here: this can be called from a logging handler.
        if self.error is None:
            self.error = f"MCAP recording failed: {exc}"

    def _channel(self, kind, topic, data):
        if kind == "message":
            schema_key = (kind, data["message_type"], data["schema_version"])
            metadata = {
                "source": data["source"],
                "message_type": data["message_type"],
                "schema_version": str(data["schema_version"]),
            }
            properties = {
                "message_type": {"type": "string", "const": data["message_type"]},
                "schema_version": {"type": "integer", "const": data["schema_version"]},
                "source": {"type": "string"},
                "sequence": {"type": "integer", "minimum": 0},
                "timestamp": {"type": "number", "minimum": 0},
                "payload": {"type": "object"},
            }
            schema_name = f"pcvmf.{data['message_type']}.v{data['schema_version']}"
        else:
            schema_key = ("log",)
            metadata = {"source": data["source"], "kind": "log"}
            properties = {
                key: {"type": "string"}
                for key in ("level", "message", "logger", "source", "process_name", "filename", "exception")
            }
            properties.update(timestamp={"type": "number"}, process={"type": "integer"}, line={"type": "integer"})
            schema_name = "pcvmf.Log.v1"
        key = (topic, data["source"], schema_key)
        if key not in self.channels:
            if schema_key not in self.schemas:
                self.schemas[schema_key] = self.writer.register_schema(schema_name, "jsonschema", _schema(properties))
            self.channels[key] = self.writer.register_channel(topic, "json", self.schemas[schema_key], metadata)
        return self.channels[key]

    def record(self, kind, topic, wire, log_time):
        with self.lock:
            if self.error or self.closed:
                return
            try:
                data = json.loads(wire)
                self.writer.add_message(
                    channel_id=self._channel(kind, topic, data),
                    log_time=log_time,
                    publish_time=int(data["timestamp"] * 1_000_000_000),
                    sequence=data.get("sequence", 0) % (2**32),
                    data=wire,
                )
            except Exception as exc:
                self._failed(exc)

    def record_log(self, wire, log_time):
        # A CLI signal handler logs on the supervisor thread, potentially while
        # a writer operation is in progress. Defer parent logs so they cannot
        # re-enter the MCAP writer (an RLock alone cannot prevent re-entrancy).
        if self.error or self.closed:
            return
        if len(self.pending_logs) >= self.queue_size:
            self._failed("MCAP parent log queue is full")
            return
        self.pending_logs.append((wire, log_time))

    def _drain_logs(self, limit):
        for _ in range(limit):
            if not self.pending_logs:
                break
            wire, log_time = self.pending_logs.popleft()
            self.record("log", LOG_TOPIC, wire, log_time)

    def poll(self, limit=100):
        """Bound each batch so a busy producer cannot starve supervision."""
        self._drain_logs(limit)
        for _ in range(limit):
            try:
                parts = self.socket.recv_multipart(flags=zmq.NOBLOCK)
            except zmq.Again:
                break
            identity, kind, *body = parts
            if kind in (b"hello", b"flush"):
                # ROUTER preserves each worker's order. A flush ack follows all
                # its accepted writes; finish() commits the shared footer later.
                reply = b"error" if self.error else b"ok"
                try:
                    self.socket.send_multipart([identity, reply], flags=zmq.NOBLOCK)
                except zmq.ZMQError as exc:
                    # A killed worker may disconnect before the reply. Its
                    # lifecycle already fails the run; do not abandon other peers.
                    if exc.errno not in (zmq.EHOSTUNREACH, zmq.EAGAIN):
                        raise
            else:
                topic, timestamp, wire = body
                self.record(kind.decode(), topic.decode(), wire, int(timestamp))

    def close(self):
        with self.lock:
            if self.closed:
                return
            self._drain_logs(len(self.pending_logs))
            self.closed = True
            try:
                if self.writer is not None:
                    self.writer.finish()
            except Exception as exc:
                self._failed(exc)
            finally:
                try:
                    if self.stream is not None:
                        self.stream.close()
                except Exception as exc:
                    self._failed(exc)
                finally:
                    if self.socket is not None:
                        self.socket.close(linger=0)
                    if self.context is not None:
                        self.context.term()


class RecordingClient:
    """Worker-local sender. Queue overflow is a run failure, never a silent drop."""

    def __init__(self, endpoint, source, queue_size, startup_timeout):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.lock = threading.RLock()
        self.error = None
        try:
            self.socket.setsockopt(zmq.IDENTITY, source.encode())
            self.socket.setsockopt(zmq.IMMEDIATE, 1)
            self.socket.setsockopt(zmq.SNDHWM, queue_size)
            self.socket.setsockopt(zmq.RCVHWM, 1)
            self.socket.connect(endpoint)
            self._acknowledge(b"hello", startup_timeout)
        except BaseException:
            self.close()
            raise

    def _acknowledge(self, kind, timeout):
        deadline = time.monotonic() + timeout
        if not self.socket.poll(max(1, int(timeout * 1000)), zmq.POLLOUT):
            raise RecordingError("MCAP recorder connection timed out")
        self.socket.send_multipart([kind], flags=zmq.NOBLOCK)
        remaining = max(0, int((deadline - time.monotonic()) * 1000))
        if not self.socket.poll(remaining, zmq.POLLIN):
            raise RecordingError("MCAP recorder acknowledgement timed out")
        if self.socket.recv() != b"ok":
            raise RecordingError("MCAP recorder rejected recording")

    def check(self):
        if self.error:
            raise RecordingError(self.error)

    def _send(self, kind, topic, wire, log_time):
        with self.lock:
            self.check()
            try:
                self.socket.send_multipart([kind, topic.encode(), str(log_time).encode(), wire], flags=zmq.NOBLOCK)
            except zmq.ZMQError as exc:
                self.error = f"MCAP recording queue is full or disconnected: {exc}"
                raise RecordingError(self.error) from exc

    def record_message(self, topic, wire):
        self._send(b"message", topic, wire, time.time_ns())

    def record_log(self, wire, log_time):
        self._send(b"log", LOG_TOPIC, wire, log_time)

    def flush(self, timeout):
        with self.lock:
            self._acknowledge(b"flush", timeout)
            self.check()

    def close(self):
        with self.lock:
            self.socket.close(linger=0)
            self.context.term()


class McapLogHandler(logging.Handler):
    """Format records before transport, including unpickleable args/exceptions."""

    def __init__(self, recorder, source, level="INFO"):
        super().__init__(level)
        self.recorder = recorder
        self.source = source

    def emit(self, record):
        try:
            exception = self.formatter or logging.Formatter()
            wire = _json(
                {
                    "timestamp": record.created,
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "logger": record.name,
                    "source": self.source,
                    "process": record.process,
                    "process_name": record.processName,
                    "filename": record.pathname,
                    "line": record.lineno,
                    "exception": exception.formatException(record.exc_info) if record.exc_info else "",
                }
            )
            self.recorder.record_log(wire, time.time_ns())
        except Exception as exc:
            # Logging a failure must not prevent the worker from reporting its
            # original lifecycle failure or releasing resources. check() and the
            # supervisor turn this sticky error into an unsuccessful run.
            if self.recorder.error is None:
                self.recorder.error = f"MCAP log recording failed: {exc}"
