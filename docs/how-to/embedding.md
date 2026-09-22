# Embed and stop an application

[Documentation home](../README.md) · [How-to guides](README.md)

Use the application runner when PCVMF is part of a larger Python program. The embedding process controls its own logging and signals.

## Run a configuration from Python

Save this as `run_robot.py` in your application directory:

```python
import logging
import signal

from pcvmf.config import load_config
from pcvmf.runtime import Application


def main():
    logging.basicConfig(level=logging.INFO)
    app = Application(load_config())

    def stop(signum, frame):
        app.request_stop()

    previous = {
        sig: signal.signal(sig, stop)
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        result = app.run()
        for error in result.errors:
            logging.error("Application failure: %s", error)
        return result.exit_code
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
```

```bash
uv run --no-sync python run_robot.py
```

This runs packaged defaults. Pass an explicit filename to `load_config()` to use your application configuration. Press Ctrl+C to request shutdown; the program returns the runtime's exit code.

The main guard is required for multiprocessing spawn. Install signal handlers only in the main thread. If a host application already owns signals or runs PCVMF supervision in another thread, omit this handler setup and call `request_stop()` from the host's shutdown path.

## Observe readiness without blocking supervision

Pass `on_event=callback` when constructing `Application`. The callback receives `(name, event)`. For application-level readiness, check `name == "application"` and `event["kind"] == "ready"`; `event["endpoints"]` contains resolved publisher endpoints.

Keep callbacks short. Forward information to your own queue if it needs slow processing. Do not wait for another event inside the callback: the supervisor cannot deliver it until the current callback returns. Callback exceptions make the run unsuccessful.

## Choose a completion policy

Use `request_stop()` for parent-requested shutdown. A plugin should instead return `False` from `Worker.step()` or `Controller.tick()` when its task is complete. Either mechanism finishes the whole application, including other workers.

Inspect `RunResult.exit_code` after `run()` returns. `ready=True` only means initialization succeeded at some point; runtime or cleanup failure can still produce exit code 1. Create a new `Application` for another run; instances are single-use and do not provide automatic restart.

See [lifecycle explanation](../explanation/lifecycle.md) for what happens during shutdown and [API reference](../reference/api.md#application-api) for signatures.
