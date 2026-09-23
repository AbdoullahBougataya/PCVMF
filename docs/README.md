# PCVMF documentation

These guides help application developers run PCVMF from a repository checkout, install plugins, connect workers, and diagnose failures. Start with the quick start if you have not run the framework yet.

## Recommended path

1. [Install and run the packaged demo](../README.md#quick-start). Confirm that both workers and the application become ready.
2. [Build your first application](tutorials/first-application.md). Make detections visible and complete a finite run.
3. [Create a vision plugin](tutorials/vision-plugin.md). Install an application package and select its detector in YAML.
4. [Combine vision and temperature](tutorials/multiple-sensors.md). Connect two publishers to one controller.

You can stop after any tutorial with a working application. If you already have a specific task, use the guide below.

## Find the right guide

| Your task | Start here |
|---|---|
| Use a webcam, recorded video, or debug window | [Camera and video](how-to/camera-and-video.md) |
| Add a non-vision data source | [Add a sensor and message type](how-to/add-sensor.md) |
| Test an algorithm or application | [Test components without hardware](how-to/testing.md) |
| Embed PCVMF in another Python program | [Embed and stop an application](how-to/embedding.md) |
| Build a wheel or container | [Package an application](how-to/packaging.md) |
| Upgrade a 0.2 application | [Migrate to 0.3](how-to/migrate-to-0.3.md) |
| Diagnose startup, delivery, or shutdown | [Troubleshooting](how-to/troubleshooting.md) |
| Look up fields, methods, and message formats | [Reference](reference/README.md) |
| Understand architecture, timing, and lifecycle | [Explanation](explanation/README.md) |

## Before you begin

Runnable examples assume Linux, Python 3.10–3.12, `uv`, and a repository checkout. Run commands from the repository root unless a guide says otherwise. The tutorials use synthetic input and need no camera or graphical session. Plugin packages must be installed in the environment that launches PCVMF.

After installing a separate plugin package, use `uv run --no-sync` so automatic synchronization does not remove it. If you later run `uv sync`, install that package again. For a pip environment, follow the [README pip setup](../README.md#using-pip-instead-of-uv), then replace `uv run ... pcvmf ...` with `pcvmf ...` and use `python -m pip` to install plugins.

PCVMF uses best-effort scheduling and publish/subscribe messaging. It does not guarantee hard real-time deadlines or reliable message delivery. The examples do not operate actuators.

## Browse by documentation type

- [Tutorials](tutorials/README.md) teach through guided, runnable exercises.
- [How-to guides](how-to/README.md) solve specific development and operational tasks.
- [Reference](reference/README.md) lists configuration fields, component options, API contracts, and wire formats.
- [Explanation](explanation/README.md) describes architecture, delivery, timing, and failure policy.

The older `docs/` entry paths remain as links for existing bookmarks.
