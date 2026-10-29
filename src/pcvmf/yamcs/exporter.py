"""Worker that forwards subscribed messages to a Yamcs UDP telemetry link."""

import logging
import socket

from ..api import ConfigurationError, Worker
from ..validation import keys, number, string
from .mapping import parse_export_options
from .packets import ExtractionError, encode, extract

logger = logging.getLogger(__name__)


class YamcsExporter(Worker):
    @classmethod
    def validate_options(cls, options):
        keys(options, {"host", "port", "space_system", "packets", "batch_size"}, "yamcs.options")
        string(options.get("host", "127.0.0.1"), "host")
        port = number(options.get("port", 10015), "port", minimum=1, integer=True, inclusive=True)
        if port > 65535:
            raise ConfigurationError("port: expected at most 65535")
        number(options.get("batch_size", 100), "batch_size", integer=True)
        parse_export_options(options)

    def initialize(self, context):
        if context.subscriber is None:
            raise ValueError("YamcsExporter requires subscriptions")
        self.context = context
        self.spec = parse_export_options(self.options)
        self.address = (self.options.get("host", "127.0.0.1"), self.options.get("port", 10015))
        self.batch_size = self.options.get("batch_size", 100)
        self.sequences = {packet.apid: 0 for packet in self.spec.packets}
        self.warned = set()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _warn_once(self, key, message, *args):
        if key not in self.warned:
            self.warned.add(key)
            logger.warning(message, *args)

    def step(self):
        for _ in range(self.batch_size):
            message = self.context.subscriber.receive(0)
            if message is None:
                break
            packet = self.spec.route(message.source, message.topic)
            if packet is None:
                self._warn_once(
                    ("route", message.source, message.topic), "No Yamcs packet for %s/%s", message.source, message.topic
                )
                continue
            try:
                values = extract(packet, message.payload)
            except ExtractionError as exc:
                self._warn_once(("extract", packet.name), "Skipped Yamcs packet %s: %s", packet.name, exc)
                continue
            data = encode(packet, self.sequences[packet.apid], message.timestamp, values)
            self.sequences[packet.apid] += 1
            try:
                self.socket.sendto(data, self.address)
            except OSError as exc:
                self._warn_once(("send", type(exc)), "Yamcs send to %s:%s failed: %s", *self.address, exc)

    def cleanup(self):
        sock = getattr(self, "socket", None)
        self.socket = None
        if sock is not None:
            sock.close()
