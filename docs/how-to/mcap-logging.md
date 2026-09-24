# Record messages and diagnostic logs in MCAP

[Documentation home](../README.md) · [How-to guides](README.md)

Enable MCAP recording to inspect published messages and diagnostic logs from one application run in a single file. This guide assumes a Linux repository checkout, Python 3.10–3.12, and `uv`. Run the commands from the repository root. The example uses ten synthetic frames and needs no camera, GPU, or display.

## Run the recording example

Install the framework, validate the example, and run it:

```bash
uv sync --frozen --extra dev
uv run --frozen pcvmf config validate examples/recording.yaml
uv run --frozen pcvmf run --config examples/recording.yaml
```

Validation prints `Valid configuration: 1 workers`. The run logs `Application ready: 1 workers`, publishes ten `vision/telemetry` messages, and exits automatically. A successful run returns exit code `0` and creates one `recordings/pcvmf-<UTC timestamp>-<unique ID>.mcap` file. Each run creates a new file without overwriting earlier recordings.

The [example configuration](../../examples/recording.yaml) has no subscriber. Recording captures publications at the publisher, independently of whether a subscriber receives them.

## Enable recording in your application

Add `mcap` under your configuration's `logging` mapping:

```yaml
logging:
  level: INFO
  mcap: {}
```

Merge this setting into any existing `logging` mapping. An empty mapping enables the defaults. Omit `logging.mcap` to disable recording; `false` and `null` are not accepted. The `mcap` package is a core dependency; no recording extra is required.

To choose the output directory or compression:

```yaml
logging:
  level: DEBUG
  mcap:
    directory: recordings
    compression: zstd
    queue_size: 1000
```

| Field | Default | Meaning |
|---|---|---|
| `directory` | `recordings` | Nonempty path string. Relative paths resolve from the launch working directory. Missing directories are created when the application runs. |
| `compression` | `zstd` | `zstd`, `lz4`, or `none` |
| `queue_size` | `1000` | Positive integer high-water mark for each worker's recording transport, and the parent log buffer limit. This approximates a queued record count, not a byte or total-memory limit. |

`logging.level` filters diagnostic logs. It does not filter published messages. `logging.format` controls console formatting; the recording stores structured log fields.

Configuration validation checks recording options without creating directories or files. See the [configuration reference](../reference/configuration.md#logging-fields) for all logging fields.

## Inspect the newest recording

Run this after the example completes. `--no-sync` also preserves separately installed plugins when inspecting recordings from your own application:

```bash
uv run --no-sync python - <<'PY'
import json
from collections import Counter
from pathlib import Path

from mcap.reader import make_reader

path = max(Path("recordings").glob("*.mcap"), key=lambda p: p.stat().st_mtime_ns)
counts = Counter()
with path.open("rb") as stream:
    reader = make_reader(stream)
    for schema, channel, message in reader.iter_messages():
        counts[channel.topic] += 1
        record = json.loads(message.data)
        if channel.topic == "/pcvmf/logs":
            print(record["level"], record["source"], record["message"])
print("Recording:", path.resolve())
print("Records per topic:", dict(counts))
PY
```

For the example, expect `vision/telemetry: 10` and one or more records on `/pcvmf/logs`. The diagnostic log count can vary. If you already have recordings from other applications, replace the `path = ...` line with `path = Path("path/to/your/file.mcap")` to select a specific run.

To inspect just published messages, pass `topics=["vision/telemetry"]` to `iter_messages()` and print `record`. The [MCAP Python reader reference](https://mcap.dev/docs/python/mcap-apidoc/mcap.reader) documents topic and timestamp filters.

## Interpret published messages

PCVMF uses the original publication topic as the MCAP channel topic. Channel metadata identifies `source`, `message_type`, and `schema_version`, so different publishers or message types can use separate channels with the same topic.

Each record contains the exact JSON envelope produced by the publisher: message type, schema version, source, sequence, timestamp, and payload. Custom codecs use the same path. The embedded JSON schema describes the envelope and allows arbitrary object fields within `payload`; it does not describe each custom payload's structure. See the [message wire format](../reference/messages.md) for envelope fields.

Channels use `json` message encoding and schemas use `jsonschema`, as defined in the [MCAP format registry](https://mcap.dev/spec/registry).

| MCAP field | Meaning |
|---|---|
| `publish_time` | Envelope `timestamp`, converted from wall-clock seconds to integer nanoseconds |
| `log_time` | Wall-clock time when the record enters the recording path, in nanoseconds |
| `sequence` | Publisher sequence modulo `2**32`, to fit MCAP's sequence field |

The original unbounded sequence remains in the JSON envelope. A publisher shares one sequence counter across its topics, so gaps within one topic can simply indicate publication on another topic. Recording a publication does not prove that a subscriber received it.

## Interpret diagnostic logs

Framework and worker diagnostics share `/pcvmf/logs`. Parent-process capture covers the thread running `Application.run()`; unrelated host threads are excluded so concurrent embedded applications keep separate recordings. Worker capture includes Python logs that reach the worker root logger. Each JSON record has these fields:

| Field | Meaning |
|---|---|
| `timestamp` | Log creation time in wall-clock seconds |
| `level` | Level name, such as `INFO` or `ERROR` |
| `message` | Formatted log message |
| `logger` | Python logger name |
| `source` | `application` for application-thread logs, or the configured worker name |
| `process` | Process ID |
| `process_name` | Python process name |
| `filename`, `line` | Logging call location |
| `exception` | Formatted exception traceback, or an empty string |

Logs emitted during worker initialization and cleanup are included after the recorder connection is established. Logs from configuration loading or earlier process setup are outside the recording lifetime. Plain `print()` output and direct writes to stdout or stderr are not captured as diagnostic records.

## Get the recording path from Python

The embedding application owns its parent-process logger configuration. Configure logging before running if you want INFO diagnostics from the parent, or use your existing logging setup with suitable logger levels. The recording handler applies `logging.level`, but cannot recover records already filtered by a logger.

Save this as `run_recording.py` in the repository root:

```python
from pcvmf.config import load_config
from pcvmf.runtime import Application, configure_logging


def main():
    config = load_config("examples/recording.yaml")
    configure_logging(config.logging)
    result = Application(config).run()
    print("Recording:", result.recording_path)
    for error in result.errors:
        print("Application error:", error)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
```

Run it with `uv run --no-sync python run_recording.py`. `RunResult.recording_path` is an absolute path when the recorder started, or `None` when recording is disabled or recorder startup failed. A path alone does not prove the run succeeded; also check `result.exit_code` and `result.errors`. See [embedding an application](embedding.md) for signal handling and cancellation.

## Handle recording failures and shutdown

The parent process owns the writer and drains a separate recording transport while supervising workers and shutting down. During normal shutdown, producers wait for their queued records to be acknowledged before the writer finishes the file and its indexes. Startup and cleanup publications follow the same recording path.

A recording queue overflow, write error, or flush timeout fails the application and produces a nonzero run result. Recording does not silently discard records to keep a run successful. Slow storage can delay supervision; use a suitable local output directory and size `queue_size` for short bursts. Increasing the queue size cannot fix sustained disk throughput limits.

Forced process termination can lose buffered records. Abrupt parent termination can leave a file without its final indexes. Successful finalization is not an `fsync` durability guarantee against machine failure. Capture covers published JSON messages and Python diagnostic logs; raw image buffers and video are not recorded unless your application explicitly publishes suitable payloads. PCVMF does not provide a replay command.
