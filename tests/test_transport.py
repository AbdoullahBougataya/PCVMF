import time

import pytest

from pcvmf.api import VisionStatus
from pcvmf.config import Subscription
from pcvmf.messages import CodecRegistry
from pcvmf.transport import ZMQPublisher, ZMQSubscriber


def test_existing_endpoint_is_never_unlinked(tmp_path):
    path = tmp_path / "owned"
    path.write_text("another process owns this")
    with pytest.raises(RuntimeError, match="already exists"):
        ZMQPublisher(f"ipc://{path}", "a", ["sample"], CodecRegistry())
    assert path.read_text() == "another process owns this"
    assert not (tmp_path / "owned.lock").exists()


def test_publisher_conflict_does_not_remove_original(tmp_path):
    endpoint = f"ipc://{tmp_path}/bus"
    original = ZMQPublisher(endpoint, "a", ["sample"], CodecRegistry())
    try:
        with pytest.raises(FileExistsError):
            ZMQPublisher(endpoint, "b", ["sample"], CodecRegistry())
        assert (tmp_path / "bus").exists()
    finally:
        original.close()
    assert not list(tmp_path.iterdir())


def test_decode_errors_and_exact_topic_dispatch(tmp_path):
    registry = CodecRegistry()
    endpoint = f"ipc://{tmp_path}/bus"
    publisher = ZMQPublisher(endpoint, "a", ["sample"], registry)
    subscriber = ZMQSubscriber([Subscription("a", "sample")], {"a": endpoint}, registry)
    try:
        deadline = time.monotonic() + 3
        received = None
        while time.monotonic() < deadline and received is None:
            publisher.publish("sample", VisionStatus("OK", "known"))
            received = subscriber.receive(20)
        assert received is not None
        assert received.payload.message == "known"
        while subscriber.receive(0) is not None:
            pass
        publisher.socket.send_multipart([b"sample", b"bad json"])
        assert subscriber.receive(1000) is None
        assert subscriber.decode_errors == 1
        wire = registry.encode("a", 100, time.time(), VisionStatus("OK", "bad topic"))
        publisher.socket.send_multipart([b"sample/extra", wire])
        assert subscriber.receive(1000) is None
        assert subscriber.decode_errors == 1
    finally:
        subscriber.close()
        publisher.close()
