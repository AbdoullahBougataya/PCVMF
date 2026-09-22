import math
import time

import cv2
import numpy as np

from pcvmf.api import Frame, FrameRead, FrameSource, ReadStatus
from pcvmf.validation import keys, number, string


class SyntheticSource(FrameSource):
    @classmethod
    def validate_options(cls, options):
        keys(options, {"width", "height", "frames"}, "source.options")
        for key, default in (("width", 640), ("height", 480)):
            number(options.get(key, default), key, integer=True)
        if "frames" in options:
            number(options["frames"], "frames", integer=True)

    def open(self, source_id, rate_hz):
        self.source_id = source_id
        self.rate_hz = rate_hz
        self.sequence = 0

    def read(self):
        if self.sequence >= self.options.get("frames", float("inf")):
            return FrameRead(ReadStatus.END)
        width = self.options.get("width", 640)
        height = self.options.get("height", 480)
        image = np.zeros((height, width, 3), dtype=np.uint8)
        t = self.sequence / self.rate_hz
        cx = int(width / 2 + width / 3 * math.sin(t * 1.5))
        cy = int(height / 2 + height / 3 * math.cos(t * 2.1))
        cv2.circle(image, (cx, cy), max(1, min(25, width // 8, height // 8)), (0, 255, 0), -1)
        frame = Frame(image, self.source_id, self.sequence, time.time(), width, height)
        self.sequence += 1
        return FrameRead(ReadStatus.FRAME, frame)

    def close(self):
        pass


class OpenCVCamera(FrameSource):
    @classmethod
    def validate_options(cls, options):
        keys(options, {"device", "width", "height"}, "source.options")
        number(options.get("device", 0), "device", integer=True, inclusive=True)
        for key in ("width", "height"):
            if key in options:
                number(options[key], key, integer=True)

    def open(self, source_id, rate_hz):
        self.source_id = source_id
        self.sequence = 0
        self.cap = cv2.VideoCapture(self.options.get("device", 0))
        if not self.cap.isOpened():
            raise RuntimeError("could not open camera")
        for key, prop in (
            ("width", cv2.CAP_PROP_FRAME_WIDTH),
            ("height", cv2.CAP_PROP_FRAME_HEIGHT),
        ):
            if key in self.options:
                self.cap.set(prop, self.options[key])
        self.cap.set(cv2.CAP_PROP_FPS, rate_hz)

    def read(self):
        ok, image = self.cap.read()
        captured_at = time.time()
        if not ok or image is None:
            return FrameRead(ReadStatus.UNAVAILABLE)
        h, w = image.shape[:2]
        frame = Frame(image, self.source_id, self.sequence, captured_at, w, h)
        self.sequence += 1
        return FrameRead(ReadStatus.FRAME, frame)

    def close(self):
        cap = getattr(self, "cap", None)
        if cap is not None:
            cap.release()
            self.cap = None


class VideoFileSource(OpenCVCamera):
    @classmethod
    def validate_options(cls, options):
        keys(options, {"path"}, "source.options")
        string(options.get("path"), "path")

    def open(self, source_id, rate_hz):
        self.source_id = source_id
        self.sequence = 0
        self.cap = cv2.VideoCapture(self.options["path"])
        if not self.cap.isOpened():
            raise RuntimeError(f"could not open video {self.options['path']!r}")

    def read(self):
        result = super().read()
        return FrameRead(ReadStatus.END) if result.status is ReadStatus.UNAVAILABLE else result
