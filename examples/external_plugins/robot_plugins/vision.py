from pcvmf.api import ConfigurationError, PipelineResult, TargetDetection, VisionPipeline


class BrightPixelPipeline(VisionPipeline):
    @classmethod
    def validate_options(cls, options):
        if options:
            raise ConfigurationError("BrightPixelPipeline takes no options")

    def initialize(self):
        pass

    def process(self, frame):
        mask = frame.image.max(axis=2) > 100
        ys, xs = mask.nonzero()
        if not len(xs):
            return PipelineResult([], "NO_TARGETS")
        x, y = int(xs.min()), int(ys.min())
        width, height = int(xs.max()) - x + 1, int(ys.max()) - y + 1
        detection = TargetDetection("bright", 1.0, [x, y, width, height], [int(xs.mean()), int(ys.mean())])
        return PipelineResult([detection])

    def cleanup(self):
        pass
