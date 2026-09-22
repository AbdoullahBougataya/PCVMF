import logging
import math
from dataclasses import dataclass

from pcvmf.api import ConfigurationError, Controller, MessageCodec, Worker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Temperature:
    celsius: float


class TemperatureCodec(MessageCodec):
    message_type = "sensor.temperature"
    payload_type = Temperature

    def encode(self, payload):
        data = {"celsius": payload.celsius}
        self.decode(data)
        return data

    def decode(self, payload):
        if set(payload) != {"celsius"}:
            raise ValueError("temperature requires only celsius")
        value = payload["celsius"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("celsius must be finite")
        return Temperature(float(value))


class TemperatureWorker(Worker):
    @classmethod
    def validate_options(cls, options):
        if options:
            raise ConfigurationError("TemperatureWorker takes no options")

    def initialize(self, context):
        if context.publisher is None:
            raise ValueError("temperature worker requires a publication")
        self.context = context
        self.index = 0

    def step(self):
        self.context.publisher.publish("sensor/temperature", Temperature(20 + math.sin(self.index / 10)))
        self.index += 1

    def cleanup(self):
        pass


class TemperatureController(Controller):
    @classmethod
    def validate_options(cls, options):
        if options:
            raise ConfigurationError("TemperatureController takes no options")

    def initialize(self):
        self.seen = False

    def on_message(self, message):
        if isinstance(message.payload, Temperature) and not self.seen:
            logger.info("Received temperature from %s: %.2f C", message.source, message.payload.celsius)
            self.seen = True

    def tick(self, dt):
        pass

    def cleanup(self):
        pass
