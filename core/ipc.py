import time
import queue
import multiprocessing as mp
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import numpy as np


@dataclass
class DataPacket:
    """Standard container for data transferred from CV Pipeline to Main Task."""
    frame_id: int
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    frame: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_sentinel: bool = False  # Used to signal process shutdown through queue


class IPCChannel:
    """Thread-safe and process-safe Inter-Process Communication queue manager."""

    def __init__(self, maxsize: int = 100, drop_when_full: bool = True):
        self.maxsize = maxsize
        self.drop_when_full = drop_when_full
        self.queue: mp.Queue = mp.Queue(maxsize=maxsize)
        self._dropped_count = mp.Value('i', 0)

    def send(self, packet: DataPacket, block: bool = True, timeout: Optional[float] = None) -> bool:
        """Sends a packet to the queue.
        
        If drop_when_full is True and the queue is full, the oldest packet is dropped
        to maintain low latency for real-time video processing.
        """
        try:
            if self.drop_when_full and self.queue.full():
                try:
                    self.queue.get_nowait()
                    with self._dropped_count.get_lock():
                        self._dropped_count.value += 1
                except queue.Empty:
                    pass

            self.queue.put(packet, block=block, timeout=timeout)
            return True
        except queue.Full:
            with self._dropped_count.get_lock():
                self._dropped_count.value += 1
            return False

    def receive(self, block: bool = True, timeout: Optional[float] = 0.1) -> Optional[DataPacket]:
        """Receives a packet from the queue. Returns None if empty or timed out."""
        try:
            return self.queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    @property
    def dropped_count(self) -> int:
        """Returns total number of dropped packets due to queue backpressure."""
        with self._dropped_count.get_lock():
            return self._dropped_count.value

    def qsize(self) -> int:
        """Returns approximate queue size."""
        try:
            return self.queue.qsize()
        except NotImplementedError:
            return -1

    def close(self):
        """Closes the underlying queue."""
        self.queue.close()
        self.queue.join_thread()
