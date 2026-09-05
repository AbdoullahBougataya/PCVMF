import time
import pytest
import numpy as np
from core.ipc import DataPacket, IPCChannel


def test_data_packet_creation():
    frame_data = np.zeros((100, 100, 3), dtype=np.uint8)
    packet = DataPacket(
        frame_id=1,
        timestamp=time.time(),
        data={"detections": [{"label": "cat", "confidence": 0.9}]},
        frame=frame_data,
        metadata={"camera": 0}
    )
    assert packet.frame_id == 1
    assert len(packet.data["detections"]) == 1
    assert packet.frame.shape == (100, 100, 3)
    assert packet.is_sentinel is False


def test_ipc_channel_send_receive():
    channel = IPCChannel(maxsize=10, drop_when_full=True)
    packet_sent = DataPacket(frame_id=42, data={"test": True})

    assert channel.send(packet_sent) is True
    packet_recv = channel.receive(timeout=0.5)

    assert packet_recv is not None
    assert packet_recv.frame_id == 42
    assert packet_recv.data["test"] is True
    channel.close()


def test_ipc_channel_drop_when_full():
    channel = IPCChannel(maxsize=3, drop_when_full=True)
    
    # Fill the queue
    for i in range(5):
        channel.send(DataPacket(frame_id=i))

    assert channel.dropped_count > 0
    channel.close()


def test_ipc_channel_timeout():
    channel = IPCChannel(maxsize=5)
    packet = channel.receive(block=True, timeout=0.05)
    assert packet is None
    channel.close()
