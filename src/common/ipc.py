"""
ZeroMQ IPC Communication Module.

IMPORTANT ARCHITECTURAL RULE:
ZeroMQ contexts (zmq.Context) MUST NEVER be shared across process boundaries.
ZMQPublisher and ZMQSubscriber MUST be instantiated inside the target worker process
where they will execute.
"""

import os
import zmq
from typing import Optional, Tuple
from src.common.logger import setup_logger

logger = setup_logger("ZMQ_IPC")


class ZMQPublisher:
    """Process-isolated ZeroMQ Publisher over IPC socket."""

    def __init__(self, endpoint: str, sndhwm: int = 10):
        self.endpoint = endpoint
        self.sndhwm = sndhwm
        # Process-isolated ZeroMQ context created strictly within the calling process
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.SNDHWM, self.sndhwm)

        # Cleanup existing IPC socket file if present on Linux to prevent bind errors
        if self.endpoint.startswith("ipc://"):
            ipc_path = self.endpoint.replace("ipc://", "")
            if os.path.exists(ipc_path):
                try:
                    os.remove(ipc_path)
                except OSError as e:
                    logger.warning(f"Could not remove stale IPC socket file {ipc_path}: {e}")

        self.socket.bind(self.endpoint)
        logger.info(f"ZMQ Publisher bound to {self.endpoint} (PID: {os.getpid()})")

    def publish(self, topic: str, payload: str):
        """Publishes a multipart message: [topic, payload]."""
        try:
            self.socket.send_multipart([topic.encode("utf-8"), payload.encode("utf-8")], flags=zmq.NOBLOCK)
        except zmq.Again:
            logger.warning(f"ZMQ Publisher queue full for topic: {topic}")
        except Exception as e:
            logger.error(f"Error publishing message on topic {topic}: {e}")

    def close(self):
        """Gracefully closes socket and context."""
        logger.info(f"Closing ZMQ Publisher socket at {self.endpoint}")
        try:
            self.socket.close(linger=0)
            self.context.term()
        except Exception as e:
            logger.error(f"Error closing ZMQ Publisher: {e}")

        # Clean up IPC file on exit
        if self.endpoint.startswith("ipc://"):
            ipc_path = self.endpoint.replace("ipc://", "")
            if os.path.exists(ipc_path):
                try:
                    os.remove(ipc_path)
                except OSError:
                    pass


class ZMQSubscriber:
    """Process-isolated ZeroMQ Subscriber over IPC socket."""

    def __init__(self, endpoint: str, topics: list = None, rcvhwm: int = 10):
        self.endpoint = endpoint
        self.rcvhwm = rcvhwm
        self.topics = topics or [""]
        # Process-isolated ZeroMQ context created strictly within the calling process
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.RCVHWM, self.rcvhwm)

        for topic in self.topics:
            self.socket.setsockopt_string(zmq.SUBSCRIBE, topic)

        self.socket.connect(self.endpoint)
        logger.info(f"ZMQ Subscriber connected to {self.endpoint} for topics {self.topics} (PID: {os.getpid()})")

    def receive(self, timeout_ms: int = 100) -> Optional[Tuple[str, str]]:
        """
        Polls and receives next available multipart message [topic, payload].
        Returns (topic, payload) or None if timeout occurs.
        """
        if self.socket.poll(timeout=timeout_ms, flags=zmq.POLLIN):
            try:
                topic_bytes, payload_bytes = self.socket.recv_multipart()
                return topic_bytes.decode("utf-8"), payload_bytes.decode("utf-8")
            except Exception as e:
                logger.error(f"Error receiving ZMQ message: {e}")
                return None
        return None

    def close(self):
        """Gracefully closes socket and context."""
        logger.info(f"Closing ZMQ Subscriber socket at {self.endpoint}")
        try:
            self.socket.close(linger=0)
            self.context.term()
        except Exception as e:
            logger.error(f"Error closing ZMQ Subscriber: {e}")
