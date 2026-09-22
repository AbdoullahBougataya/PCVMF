# Your first application

[Documentation home](../README.md) · [Tutorials](README.md)

**Outcome:** run two processes that exchange vision detections, observe the controller's output, and make the application finish automatically.

You need a Linux checkout, Python 3.10–3.12, and `uv`. Open a terminal in the repository root. This exercise needs no camera, GPU, or display.

## 1. Install the development environment

```bash
uv sync --frozen --extra dev
```

This creates `.venv` and installs the framework and development tools. Leave your terminal in the repository root.

## 2. Start the packaged demo

```bash
uv run --frozen pcvmf run
```

Look for the following log messages, with timestamps and process names around them:

```text
Worker vision ready
Worker controller ready
Application ready: 2 workers
```

The worker readiness order can differ. A synthetic source generates a moving green target, a pipeline detects it, and a controller receives the detections. No window opens. The default INFO log level does not print each detection.

Press **Ctrl+C**. Wait for the shell prompt to return. You have started and stopped a multiprocess application without hardware.

## 3. Make the application visible in the logs

Create `config/tutorial.yaml` with this complete configuration:

```yaml
logging:
  level: DEBUG
workers:
  - name: vision
    plugin:
      class: pcvmf.workers:VisionWorker
      options:
        source:
          class: pcvmf.vision.sources:SyntheticSource
          options: {width: 320, height: 240, frames: 60}
    rate_hz: 30
    publications: [vision/telemetry]
  - name: controller
    plugin: {class: 'pcvmf.workers:ControllerWorker'}
    rate_hz: 50
    subscriptions:
      - {source: vision, topic: vision/telemetry}
```

Validate before running:

```bash
uv run --frozen pcvmf config validate config/tutorial.yaml
```

Expected output:

```text
Valid configuration: 2 workers
```

Run it:

```bash
uv run --frozen pcvmf run --config config/tutorial.yaml
```

You should see DEBUG messages containing `Target offset:`. The values change as the target moves. The controller calculates the offset using the actual 320×240 dimensions.

After roughly two seconds of processing, plus startup and shutdown time, the application exits on its own. The `frames: 60` limit ends the synthetic stream; normal completion of the vision worker stops the controller too. The exact number of received messages is not guaranteed.

## 4. Confirm successful completion

Immediately after the command returns, run:

```bash
echo $?
```

The exit code should be `0`. Configuration validation did not open a camera or start workers; the run command did.

Change the vision worker's `rate_hz` from `30` to `15`, validate, and run again. The same 60-frame stream now takes roughly four seconds after startup. Leave the controller at 50 Hz.

You now have a configuration-controlled application with independent vision and controller rates. Continue with [your first vision plugin](vision-plugin.md), or learn [why the processes are separate](../explanation/architecture.md).
