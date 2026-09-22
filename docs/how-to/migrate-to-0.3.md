# Migrate a 0.2 application to 0.3

[Documentation home](../README.md) · [How-to guides](README.md)

Use this guide when upgrading existing application code and YAML. Upgrade all communicating components together; the old imports and wire messages are intentionally incompatible.

This release intentionally replaces the 0.2 API without deprecated aliases.

| Before | After |
|---|---|
| `python main.py` | `pcvmf run` or `python -m pcvmf` |
| Imports from `src.*` | Public contracts from `pcvmf.api` |
| Fixed `vision` and `main_app` sections | Named `workers` list with explicit routes |
| Pipeline/controller class name alone | `{class: 'your_package.module:Class', options: {...}}` |
| `initialize() -> bool` | `initialize()` succeeds or raises |
| `process_frame(array, frame_id)` | `process(Frame) -> PipelineResult` |
| Separate vision callbacks | `Controller.on_message(Message)` with typed payload |
| `cleanup` may assume successful initialization | Cleanup must handle partial initialization |
| Shared publisher endpoint | One endpoint per publisher; automatic per-run allocation |
| Messages serialize themselves | Shared versioned `MessageCodec` registry |
| `vision.target_fps` and camera FPS | Worker `rate_hz` |
| `target_color` string | Explicit `lower_hsv` and `upper_hsv` |
| GUI enabled by default | Disabled by default; explicit visualizer plugin |

Start with `config/default_config.yaml` and port your component options into plugin specifications. Install your plugins as a separate package before validating the configuration. Add every published topic to `publications`; each subscription must reference an existing worker and declared topic.

Replace old telemetry deserialization with the framework-provided `Message.payload`. For vision messages, use `isinstance(message.payload, VisionTelemetry)` and use its width/height instead of hard-coded image dimensions. Capture and processing durations are reported separately. Old JSON payloads are not wire-compatible; upgrade all connected components together.

The requirements export now contains runtime dependencies only. `pip install -r requirements.txt` alone does not install the framework: use `pip install .` or install a built wheel as described in the README.

Upgrade application plugins and configuration together, validate them, and run the external-plugin and integration tests before deployment. This release does not add automatic worker restart or reliable message delivery.

## Validate the migrated application

1. Install PCVMF 0.3 and your migrated plugin package into the same environment.
2. Run `pcvmf config validate application.yaml` and fix every import, option, and route error before starting devices.
3. Exercise the pipeline and controller synchronously with known inputs.
4. Run a synthetic integration configuration and assert receipt of a known typed message, successful completion, and cleanup.
5. Re-enable hardware and verify timeouts and shutdown behavior under the actual workload.

Keep the previous application package and configuration available as a matched rollback pair. Do not mix a 0.2 publisher with a 0.3 subscriber.

See the [configuration reference](../reference/configuration.md), [Python API](../reference/api.md), and [testing guide](testing.md) for the replacement contracts and checks.
