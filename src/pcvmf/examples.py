import logging

from .api import Controller, VisionTelemetry
from .validation import keys

logger = logging.getLogger(__name__)


class TrackingController(Controller):
    @classmethod
    def validate_options(cls, options):
        keys(options, set(), "tracking.options")

    def initialize(self):
        self.offset = None

    def on_message(self, message):
        telemetry = message.payload
        if isinstance(telemetry, VisionTelemetry):
            if telemetry.detections:
                x, y = telemetry.detections[0].centroid
                self.offset = (x - telemetry.width / 2, y - telemetry.height / 2)
                logger.debug("Target offset: %s", self.offset)
            else:
                self.offset = None

    def tick(self, dt):
        pass

    def cleanup(self):
        pass
