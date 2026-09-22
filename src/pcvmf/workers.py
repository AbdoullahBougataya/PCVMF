"""Built-in adapters from plugin contracts to the generic worker runtime."""

from .api import Controller, FrameSource, VisionPipeline, Visualizer, Worker
from .plugins import instantiate, plugin_spec
from .runners import ControllerRunner, VisionRunner, cleanup_all
from .validation import keys, number, string

SOURCE = {"class": "pcvmf.vision.sources:SyntheticSource"}
PIPELINE = {"class": "pcvmf.vision.pipeline:ColorTracker"}
VISUALIZER = {"class": "pcvmf.vision.visualizers:DisabledVisualizer"}
CONTROLLER = {"class": "pcvmf.examples:TrackingController"}


class VisionWorker(Worker):
    @classmethod
    def validate_options(cls, options):
        keys(
            options,
            {"source", "pipeline", "visualizer", "failure_limit", "topic"},
            "vision.options",
        )
        for key, default, base in (
            ("source", SOURCE, FrameSource),
            ("pipeline", PIPELINE, VisionPipeline),
            ("visualizer", VISUALIZER, Visualizer),
        ):
            plugin_spec(options.get(key, default), base, key)
        number(options.get("failure_limit", 10), "failure_limit", integer=True)
        string(options.get("topic", "vision/telemetry"), "topic")

    def initialize(self, context):
        self.resources = []
        if context.publisher is None:
            raise ValueError("VisionWorker requires a publication")
        source = instantiate(self.options.get("source", SOURCE), FrameSource)
        self.resources.append(source.close)
        pipeline = instantiate(self.options.get("pipeline", PIPELINE), VisionPipeline)
        self.resources.append(pipeline.cleanup)
        visualizer = instantiate(self.options.get("visualizer", VISUALIZER), Visualizer)
        self.resources.append(visualizer.close)
        self.runner = VisionRunner(
            source,
            pipeline,
            context.publisher,
            visualizer,
            source_id=context.name,
            rate_hz=context.rate_hz,
            failure_limit=self.options.get("failure_limit", 10),
            topic=self.options.get("topic", "vision/telemetry"),
            monotonic=context.monotonic,
        )
        self.runner.initialize()

    def step(self):
        return self.runner.step()

    def cleanup(self):
        callbacks = getattr(self, "resources", [])
        self.resources = []
        cleanup_all(reversed(callbacks))


class ControllerWorker(Worker):
    @classmethod
    def validate_options(cls, options):
        keys(
            options,
            {
                "controller",
                "max_messages",
                "receive_budget_ms",
                "stale_after_s",
                "deliveries",
            },
            "controller.options",
        )
        # Delivery policy belongs to subscriptions, never plugin options.
        if "deliveries" in options:
            raise ValueError("configure delivery on worker subscriptions")
        plugin_spec(options.get("controller", CONTROLLER), Controller, "controller")
        number(options.get("max_messages", 100), "max_messages", integer=True)
        number(options.get("receive_budget_ms", 5), "receive_budget_ms")
        number(options.get("stale_after_s", 1), "stale_after_s")

    def initialize(self, context):
        self.controller = instantiate(self.options.get("controller", CONTROLLER), Controller)
        self.runner = ControllerRunner(
            self.controller,
            context.subscriber,
            deliveries=getattr(context.subscriber, "routes", {}),
            max_messages=self.options.get("max_messages", 100),
            receive_budget_ms=self.options.get("receive_budget_ms", 5),
            stale_after_s=self.options.get("stale_after_s", 1),
            monotonic=context.monotonic,
        )
        self.runner.initialize()

    def step(self):
        return self.runner.step()

    def cleanup(self):
        controller = getattr(self, "controller", None)
        self.controller = None
        if controller is not None:
            controller.cleanup()
