# Use a camera, video file, or debug window

[Documentation home](../README.md) · [How-to guides](README.md)

Use this guide to replace synthetic input while keeping your pipeline and controller. You need the [quick-start environment](../../README.md#quick-start) and, for a webcam, an accessible OpenCV camera device. Run commands from the repository root. `uv run --no-sync` preserves a separately installed pipeline plugin if your configuration uses one.

## Use a webcam

Create `config/camera.yaml` from the repository root:

```yaml
workers:
  - name: vision
    plugin:
      class: pcvmf.workers:VisionWorker
      options:
        source:
          class: pcvmf.vision.sources:OpenCVCamera
          options: {device: 0, width: 640, height: 480}
        failure_limit: 10
    rate_hz: 30
    publications: [vision/telemetry]
  - name: controller
    plugin: {class: 'pcvmf.workers:ControllerWorker'}
    rate_hz: 50
    subscriptions:
      - {source: vision, topic: vision/telemetry, delivery: latest}
```

```bash
uv run --no-sync pcvmf config validate config/camera.yaml
uv run --no-sync pcvmf run --config config/camera.yaml
```

Validation checks configuration, not device access. A successful run reports both workers ready. The default detector looks for green regions; point the camera at a suitable object or configure a different pipeline. Ctrl+C stops the application.

Change `device` if the desired camera uses another index. Requested width, height, and FPS are backend requests, not guarantees. Use telemetry dimensions in control calculations. A single unavailable frame does not immediately fail the worker; `failure_limit` counts consecutive failed reads, while a blocking read is governed by the supervisor's progress timeout.

## Use a recorded video

In the vision worker's `plugin.options`, replace the entire `source` specification with:

```yaml
source:
  class: pcvmf.vision.sources:VideoFileSource
  options:
    path: /absolute/path/to/recording.mp4
```

Set the worker's `rate_hz` to your desired playback rate. Validate and run the edited configuration as above. Do not keep `device`, `width`, or `height` in the video source's options; that source accepts only `path`.

The application stops normally at end-of-stream. Relative video paths resolve from the directory where you launch the command. Use an absolute path if you launch from different directories. A failed video read is treated as EOF; this backend cannot reliably distinguish EOF from every decode failure.

## Display processed frames

In a graphical desktop session, add this alongside `source` under the vision worker's `plugin.options`:

```yaml
visualizer:
  class: pcvmf.vision.visualizers:OpenCVVisualizer
```

Run the configuration and look for the `PCVMF` window with boxes and labels. Press Escape or Q while that window is focused to request normal application completion. Use Ctrl+C in the terminal otherwise.

For a server or container without a graphical session, omit the visualizer or explicitly select `pcvmf.vision.visualizers:DisabledVisualizer`. The CLI has no `--show-window` switch.

## Verify what changed

Set top-level `logging: {level: DEBUG}` to see target offsets from the sample controller. Verify the reported dimensions in your own controller if resolution is important. If opening the device fails, use the [camera troubleshooting steps](troubleshooting.md#camera-or-video-will-not-open). See [component reference](../reference/components.md) for all source options.
