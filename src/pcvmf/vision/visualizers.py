import cv2

from pcvmf.api import Visualizer
from pcvmf.validation import keys


class DisabledVisualizer(Visualizer):
    @classmethod
    def validate_options(cls, options):
        keys(options, set(), "visualizer.options")

    def render(self, frame, result):
        return True

    def close(self):
        pass


class OpenCVVisualizer(DisabledVisualizer):
    def render(self, frame, result):
        image = frame.image.copy()
        for detection in result.detections:
            x, y, w, h = detection.bbox
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                image,
                detection.label,
                (x, max(15, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )
        cv2.imshow("PCVMF", image)
        self.opened = True
        return cv2.waitKey(1) & 0xFF not in (27, ord("q"))

    def close(self):
        if getattr(self, "opened", False):
            cv2.destroyWindow("PCVMF")
            self.opened = False
