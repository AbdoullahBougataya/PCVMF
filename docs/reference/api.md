# Python API reference

[Documentation home](../README.md) · [Reference](README.md)

Primary contract definitions: [api.py](../../src/pcvmf/api.py). All extension contracts and message dataclasses below are imported from `pcvmf.api`. Configuration loading, the application runner, and component runners have their own supported modules.

## Common plugin contract

`Plugin(options: dict[str, Any])` stores `self.options`. Subclasses implement class method `validate_options(options) -> None`, raising `ConfigurationError` or another descriptive validation exception on invalid options. The loader wraps validation exceptions with the configuration path.

Validation, imports, and constructors must not acquire resources. They can execute in the parent before workers start and again in children. Concrete subclasses must implement all abstract methods. A resource belongs in initialization/open and must be released by cleanup/close even if initialization failed partially.

## Extension interfaces

| Interface | Required methods beyond `validate_options` | Return/lifecycle contract |
|---|---|---|
| `Worker` | `initialize(context)`, `step()`, `cleanup()` | `step()` returns `False` to complete the application; `True` or `None` continues |
| `FrameSource` | `open(source_id, rate_hz)`, `read()`, `close()` | `read()` returns `FrameRead` |
| `VisionPipeline` | `initialize()`, `process(frame)`, `cleanup()` | `process()` returns `PipelineResult` |
| `Controller` | `initialize()`, `on_message(message)`, `tick(dt)`, `cleanup()` | `tick()` can return `False` for normal completion |
| `Visualizer` | `render(frame, result)`, `close()` | `render()` returns `True` to continue, `False` to finish |

Initialization returns normally or raises; boolean success flags are not used. `dt` is elapsed monotonic seconds between controller ticks. Exceptions in algorithm, callback, or tick code propagate as worker failures.

`Publisher`, `Subscriber`, and `MessageCodec` are abstract contracts but do not inherit `Plugin` and do not use its options constructor.

## WorkerContext

Frozen dataclass passed to `Worker.initialize()`:

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | Configured worker name |
| `rate_hz` | `float` | Configured scheduling rate |
| `publisher` | `Publisher \| None` | Present when publications exist |
| `subscriber` | `Subscriber \| None` | Present when subscriptions exist |
| `monotonic` | Callable returning float | Default `time.monotonic`; elapsed-time clock |
| `wall_clock` | Callable returning float | Default `time.time`; event timestamp clock |

`Publisher.publish(topic, payload)` accepts a registered typed payload and a declared topic. `Subscriber.receive(timeout_ms=0)` returns a decoded `Message` or `None`. A rejected or filtered wire message can also result in `None`; it does not necessarily mean the underlying queue is empty.

Both transports expose `close()`. When injected by the runtime, the runtime owns their cleanup. Do not pass contexts or transport instances to another process. Custom workers perform their own bounded receive processing.

## Frames and algorithm results

| Type | Fields |
|---|---|
| `Frame` | `image: np.ndarray`, `source: str`, `sequence: int`, `captured_at: float`, `width: int`, `height: int` |
| `FrameRead` | `status: ReadStatus`, `frame: Frame \| None = None` |
| `PipelineResult` | `detections: list[TargetDetection]`, `status: str = "OK"` |

`ReadStatus` values are `FRAME`, `UNAVAILABLE`, and `END`. `FRAME` requires a non-None frame. Built-in images are BGR NumPy arrays. Capture timestamps are wall-clock seconds. Dataclasses are frozen at field-assignment level; contained lists, mappings, and arrays are not deeply immutable.

Detection and telemetry fields are listed in [Messages](messages.md).

## Configuration API

From `pcvmf.config`:

- `load_config(path: str | Path | None = None) -> AppConfig`: reads YAML; `None` selects packaged defaults, independent of the working directory.
- `parse_config(raw: dict) -> AppConfig`: validates a mapping without starting workers.
- `AppConfig`, `WorkerConfig`, `Subscription`: frozen dataclasses matching [configuration fields](configuration.md). Prefer the loaders to manual construction so validation is not bypassed.

## Application API

From `pcvmf.runtime`:

```text
Application(config, *, on_event=None)
```

`run() -> RunResult` blocks while supervising workers and then returns. Each instance is single-use; a second call raises `RuntimeError`. `request_stop()` requests normal shutdown without blocking for completion. It is intended for the parent/embedding application, including its signal handler.

`RunResult` is frozen and contains `exit_code: int`, `errors: tuple[str, ...]`, `ready: bool`, and `recording_path: str | None`. `ready` indicates that all workers reached readiness; it does not prove telemetry was received. `recording_path` is the absolute MCAP file path when the recorder started, or `None` when recording is disabled or recorder startup failed. A path does not guarantee a successful recording; inspect the exit code and errors. Runtime errors may include several related reports for one failed worker.

`on_event(name, event)` runs synchronously in the supervisor. It must return promptly; a callback that raises causes unsuccessful shutdown. Filter the documented [event kinds](cli.md#lifecycle-events) and ignore unknown kinds. The callback is released after the run completes.

`Application` uses a local `spawn` context without changing the global multiprocessing start method. It does not install OS signal handlers or configure the embedding parent's logging. Put application startup under `if __name__ == "__main__":`.

`configure_logging(config.logging)` configures Python console logging using the validated settings. The CLI and child processes call it automatically. Embedding applications can call it explicitly or keep their own logging setup. When MCAP recording is enabled, parent capture covers the thread running `Application.run()`. The recording handler respects `logging.level`, but cannot capture parent log records filtered out by the caller's logger levels. See [MCAP logging](../how-to/mcap-logging.md).

## Single-step runners

From `pcvmf.runners`; these support dependency injection without sockets or processes. Constructor inputs are expected to be valid; YAML validation is not performed when constructing a runner directly.

```text
VisionRunner(
    source, pipeline, publisher, visualizer,
    *, source_id="vision", rate_hz=30, failure_limit=10,
    topic="vision/telemetry", monotonic=time.monotonic,
)
```

`initialize()` opens the source and initializes the pipeline. `step()` reads/processes/publishes/renders at most one frame and returns whether to continue. `cleanup()` attempts visualizer, pipeline, and source cleanup even after an earlier cleanup exception. It does not close the injected publisher. The runner does not sleep to enforce `rate_hz`; scheduling belongs to the worker runtime.

```text
ControllerRunner(
    controller, subscriber,
    *, deliveries=None, max_messages=100, receive_budget_ms=5,
    stale_after_s=1, monotonic=time.monotonic,
)
```

`deliveries` maps `(source, topic)` to `latest` or `ordered`. `subscriber` may be `None`. `initialize()` initializes the controller and timing state. `step()` performs one receive/dispatch/tick cycle. `cleanup()` cleans up the controller, not the injected subscriber.

For direct runner use, an unspecified route falls back to `latest` for message type `vision.telemetry`, otherwise `ordered`. The built-in worker supplies explicit policies resolved from YAML, whose default is based on the **topic string**. Prefer explicit delivery mappings in tests.

See [test components without hardware](../how-to/testing.md) for runnable examples.
