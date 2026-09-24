"""Failure boundaries and exact wire preservation for the recording transport."""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import zmq
from mcap.reader import make_reader

from pcvmf.api import VisionStatus
from pcvmf.config import parse_config
from pcvmf.messages import CodecRegistry
from pcvmf.recording import McapLogHandler, McapRecorder, RecordingClient, RecordingError
from pcvmf.runtime import Application
from pcvmf.transport import ZMQPublisher
from tests.test_runtime import worker


def options(tmp_path, **kwargs):
    return {"directory": str(tmp_path / "recordings"), "compression": "none", "queue_size": 10, **kwargs}


def read_records(path):
    with open(path, "rb") as stream:
        reader = make_reader(stream, validate_crcs=True)
        assert reader.get_summary() is not None
        return list(reader.iter_messages(log_time_order=False))


@pytest.mark.parametrize("compression", ["none", "lz4", "zstd"])
def test_exact_wire_schema_times_and_sequence_wrap(tmp_path, compression):
    recorder = McapRecorder(options(tmp_path, compression=compression), f"ipc://{tmp_path}/recorder")
    registry = CodecRegistry()
    sequence = 2**32 + 7
    wire = registry.encode("source", sequence, 1234.25, VisionStatus("OK", "original bytes"))
    recorder.record("message", "sample", wire, 999_000_000_000)
    recorder.close()
    recorder.close()
    [(schema, channel, message)] = read_records(recorder.path)
    assert message.data == wire
    assert message.sequence == 7
    assert message.publish_time == 1_234_250_000_000
    assert message.log_time == 999_000_000_000
    assert channel.topic == "sample"
    assert channel.message_encoding == "json"
    assert channel.metadata == {"source": "source", "message_type": "vision.status", "schema_version": "1"}
    assert schema.encoding == "jsonschema"
    assert json.loads(schema.data)["properties"]["message_type"]["const"] == "vision.status"


def test_publisher_records_the_transmitted_bytes_and_skips_rejected_publications(tmp_path):
    class Sink:
        def __init__(self):
            self.records = []

        def record_message(self, topic, wire):
            self.records.append((topic, wire))

    sink = Sink()
    publisher = ZMQPublisher(
        f"ipc://{tmp_path}/source", "source", ["sample"], CodecRegistry(), wall_clock=lambda: 1234.25, recorder=sink
    )
    try:
        publisher.publish("sample", VisionStatus("OK", "value"))
        with pytest.raises(ValueError, match="undeclared"):
            publisher.publish("other", VisionStatus("OK", "rejected"))
        with pytest.raises(ValueError, match="no codec"):
            publisher.publish("sample", object())
        assert sink.records == [("sample", CodecRegistry().encode("source", 0, 1234.25, VisionStatus("OK", "value")))]
    finally:
        publisher.close()


def test_full_queue_is_sticky_and_log_handler_does_not_hide_failure(tmp_path):
    recorder = McapRecorder(options(tmp_path, queue_size=1), f"ipc://{tmp_path}/recorder")

    def produce():
        client = RecordingClient(f"ipc://{tmp_path}/recorder", "source", 1, 2)
        handler = McapLogHandler(client, "source")
        try:
            record = logging.LogRecord("test", logging.INFO, __file__, 1, "%s", ("x" * 4096,), None)
            for _ in range(10000):
                handler.handle(record)
                if client.error:
                    break
            assert client.error is not None
            with pytest.raises(RecordingError, match="queue is full"):
                client.check()
        finally:
            handler.close()
            client.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(produce)
            # Only acknowledge hello. Deliberately never drain the records.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if recorder.socket.poll(10, zmq.POLLIN):
                    recorder.poll(limit=1)
                    break
            future.result(timeout=3)
    finally:
        recorder.close()


def test_missing_recorder_connection_times_out(tmp_path):
    with pytest.raises(RecordingError, match="connection timed out"):
        RecordingClient(f"ipc://{tmp_path}/absent", "source", 1, 0.05)


@pytest.mark.parametrize("method", ["add_message", "finish"])
def test_disk_failure_fails_run_and_releases_logging_handler(tmp_path, monkeypatch, method):
    from pcvmf.recording import Writer

    def fail(*args, **kwargs):
        raise OSError("simulated full disk")

    monkeypatch.setattr(Writer, method, fail)
    config = parse_config({"workers": [worker(action="complete")], "logging": {"mcap": options(tmp_path)}})
    before = list(logging.getLogger().handlers)
    # Ensure a supervisor record exercises add_message, without reconfiguring handlers.
    with monkeypatch.context() as context:
        context.setattr(logging.getLogger(), "level", logging.INFO)
        logging.Logger.manager._clear_cache()
        result = Application(config).run()
    logging.Logger.manager._clear_cache()
    assert result.exit_code == 1
    assert any("simulated full disk" in error for error in result.errors), result.errors
    assert logging.getLogger().handlers == before


def test_killed_worker_does_not_block_finalization(tmp_path):
    config = parse_config({"workers": [worker(action="block")], "logging": {"mcap": options(tmp_path)}})
    result = Application(config).run()
    assert result.exit_code == 1
    assert any("progress timeout" in error for error in result.errors)
    assert result.recording_path
    read_records(result.recording_path)


def test_flush_acknowledgement_timeout(tmp_path):
    recorder = McapRecorder(options(tmp_path), f"ipc://{tmp_path}/recorder")

    def produce():
        client = RecordingClient(f"ipc://{tmp_path}/recorder", "source", 10, 2)
        try:
            with pytest.raises(RecordingError, match="acknowledgement timed out"):
                client.flush(0.05)
        finally:
            client.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(produce)
            assert recorder.socket.poll(2000, zmq.POLLIN)
            recorder.poll(limit=1)  # Acknowledge hello, but deliberately not flush.
            future.result(timeout=3)
    finally:
        recorder.close()


def test_flush_waits_for_multiple_recording_batches(tmp_path):
    recorder = McapRecorder(options(tmp_path, queue_size=1000), f"ipc://{tmp_path}/recorder")

    def produce():
        client = RecordingClient(f"ipc://{tmp_path}/recorder", "source", 1000, 2)
        try:
            registry = CodecRegistry()
            for sequence in range(250):
                client.record_message(
                    "sample", registry.encode("source", sequence, 1234.25, VisionStatus("OK", "burst"))
                )
            client.flush(2)
        finally:
            client.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(produce)
            deadline = time.monotonic() + 3
            while not future.done() and time.monotonic() < deadline:
                if recorder.socket.poll(10, zmq.POLLIN):
                    recorder.poll(limit=25)
            future.result(timeout=1)
    finally:
        recorder.close()
    records = read_records(recorder.path)
    assert [message.sequence for _, _, message in records] == list(range(250))


def test_signal_style_logging_cannot_reenter_writer(tmp_path, monkeypatch):
    recorder = McapRecorder(options(tmp_path), f"ipc://{tmp_path}/recorder")
    handler = McapLogHandler(recorder, "application")
    original = recorder.writer.add_message
    active = False
    triggered = False

    def write_with_signal(**kwargs):
        nonlocal active, triggered
        assert not active, "signal log re-entered the MCAP writer"
        active = True
        if not triggered:
            triggered = True
            handler.handle(logging.LogRecord("test", logging.INFO, __file__, 1, "signal received", (), None))
        original(**kwargs)
        active = False

    monkeypatch.setattr(recorder.writer, "add_message", write_with_signal)
    try:
        wire = CodecRegistry().encode("source", 0, 1234.25, VisionStatus("OK", "value"))
        recorder.record("message", "sample", wire, time.time_ns())
        recorder.poll()
    finally:
        handler.close()
        recorder.close()
    records = read_records(recorder.path)
    assert [channel.topic for _, channel, _ in records] == ["sample", "/pcvmf/logs"]
    assert json.loads(records[1][2].data)["message"] == "signal received"
