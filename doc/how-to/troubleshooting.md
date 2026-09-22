# Diagnose configuration and runtime failures

[Documentation home](../README.md) · [How-to guides](README.md)

Start with the exact environment and YAML used for the failing run:

```bash
uv run --no-sync pcvmf config validate config/my_app.yaml
uv run --no-sync pcvmf run --config config/my_app.yaml
```

Replace `config/my_app.yaml` with your file. Validation should finish before you investigate devices or transport. For extra detail, set top-level `logging: {level: DEBUG}`; effective configuration is included in DEBUG logs.

## Cannot import a plugin

Confirm the configured string is `module:Class`, the class is at module scope, and the package is installed in `.venv`:

```bash
uv pip list --python .venv/bin/python
```

For repository examples, reinstall them:

```bash
uv pip install --python .venv/bin/python --no-deps --editable ./examples/external_plugins
```

Then validate using `uv run --no-sync`. A later `uv sync` can remove packages that are not declared project dependencies. If import works but validation says the class must be concrete, implement all abstract methods of the expected contract. A worker entry expects `Worker`; a nested pipeline entry expects `VisionPipeline`.

## Unknown field or publication

Read the field path in the error. Framework keys are strict; a misspelling is not ignored. `rate_hz` belongs on the worker, while source dimensions belong under `plugin.options.source.options`. Subscriptions must reference an existing worker name and one of its declared publications.

For vision output, make `plugin.options.topic` match a declared publication if you change it from `vision/telemetry`. The parser validates routes but cannot infer all publication requirements from arbitrary plugin code.

## Application is ready but prints no detections

The demo is headless and target offsets are DEBUG logs. Set `logging.level` to `DEBUG`, or enable the [OpenCV visualizer](camera-and-video.md#display-processed-frames) in a graphical session.

Readiness confirms initialization, not data delivery. Check source availability, the exact topic/source route, and whether the pipeline actually detects the input. For custom messages, inspect decode warnings and confirm every worker has the required codec in top-level `codecs`.

## Camera or video will not open

Check the source plugin and options first. A camera uses a nonnegative integer `device`; video uses `path`. Validate does not open either source.

For a camera, verify device permissions, the correct index, and whether another application is using the device. For a video, verify the file exists and is readable from the launch working directory; prefer an absolute path. For a container, verify the resource is available inside it, not just on the host.

Try the synthetic source with the same pipeline to distinguish input problems from algorithm problems. A video that stops during a failed decode can look like EOF because that is how the built-in video source maps failed reads.

## Stale input or missed deadlines

A stale warning means the controller has not accepted a message for the configured interval. Inspect publisher health, codec errors, and routing before increasing the threshold. A low-rate sensor may simply require a `stale_after_s` longer than its normal sampling interval.

A missed deadline means a worker step took longer than its scheduling period. Measure capture and processing durations, reduce model cost or rate, and keep controller callbacks short. The receive budget bounds batching, not inference or callback runtime. Increasing queue sizes can increase backlog; it does not make the algorithm faster.

See [delivery and timing](../explanation/delivery-and-timing.md) before changing `latest`, `ordered`, or `hwm`.

## Startup or progress timeout

For startup timeout, look for slow initialization or a device/model operation that never returned. Set `startup_timeout` on the affected worker to accommodate a known bounded initialization cost.

For progress timeout, ensure `step()` performs bounded work and has no nested infinite loop. Configure I/O timeouts in the device API. Raise `progress_timeout` only when the legitimate step duration requires it, and keep it longer than the scheduling period. Heartbeats originate from the loop, so a blocked step must remain detectable.

## Endpoint already exists or permission denied

Prefer automatic endpoints by omitting `endpoint`. For an explicit IPC path, ensure the parent directory exists and is writable. A socket or `.lock` file may belong to an active process; do not delete it without checking ownership and stopping that application. An uncatchable supervisor crash may leave an explicit endpoint requiring manual cleanup.

An `Operation not permitted` while binding an otherwise valid local socket can come from a sandbox policy. Run integration checks in an environment that permits IPC sockets. Changing detector code will not resolve a denied bind operation.

## Nonzero exit during shutdown

Read all worker failure and cleanup messages. Cleanup failure, missing acknowledgement, abnormal worker exit, and forced termination make shutdown unsuccessful even after Ctrl+C. Ensure cleanup handles partial initialization and returns within `shutdown_timeout`; release every acquired resource even when another release operation fails.

Do not hide cleanup exceptions just to obtain exit code 0. The [lifecycle explanation](../explanation/lifecycle.md) describes why these failures are surfaced.
