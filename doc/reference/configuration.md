# Configuration reference

[Documentation home](../README.md) · [Reference](README.md)

Implementation: [config.py](../../src/pcvmf/config.py), [plugins.py](../../src/pcvmf/plugins.py). Configuration is YAML with a mapping at its root. `load_config()` returns an `AppConfig`; `parse_config()` validates an already parsed mapping.

## Application fields

| Field | Type | Default | Constraint or meaning |
|---|---|---|---|
| `workers` | List of worker mappings | Required | Must contain at least one worker |
| `codecs` | List of import-path strings | `[]` | Adds custom codecs to the two built-ins |
| `hwm` | Integer | `100` | Positive send and receive high-water mark |
| `logging` | Mapping | `{}` | Logging configuration applied in CLI and child processes |

Unknown application fields are rejected. Numeric rate/timeout values must be finite, strictly positive numbers; booleans are not accepted as numbers. Integer fields require actual integers.

## Worker fields

| Field | Type | Default | Constraint or meaning |
|---|---|---|---|
| `name` | String | Required | Unique; pattern `[A-Za-z][A-Za-z0-9_-]{0,39}` |
| `plugin` | Plugin specification | Required | Concrete `Worker` subclass |
| `publications` | List of strings | `[]` | Nonempty topic strings; no duplicates |
| `subscriptions` | List of subscription mappings | `[]` | No duplicate source/topic pairs |
| `endpoint` | String | Allocated | Allowed only if publications are declared |
| `rate_hz` | Number | `30` | Target worker step rate |
| `startup_timeout` | Number | `30` | Seconds from process startup until readiness |
| `progress_timeout` | Number | `10` | Seconds without reported progress after application readiness |
| `shutdown_timeout` | Number | `3` | Graceful shutdown allowance in seconds |

`progress_timeout` must be strictly greater than `1 / rate_hz`. All workers are required; there is no optional-worker or restart setting.

The runtime schedules steps using `rate_hz`. This is not a guarantee of achieved frequency. A long `step()` delays the next iteration; the supervisor detects an unresponsive step through `progress_timeout`.

## Plugin specification

```yaml
class: my_package.module:MyPlugin
options:
  threshold: 0.7
```

Only `class` and `options` are allowed. `class` must resolve to a concrete subclass of the expected contract. Import paths use one module path and one top-level class name, separated by `:`; nested attribute expressions are not supported. Omitted `options` becomes `{}` and must otherwise be a string-keyed mapping.

The loader imports the class and calls `validate_options(options)` during configuration validation. Plugin constructors receive those options; plugin code is responsible for validating their keys and values. Imports, validation, and constructors must not open hardware or acquire resources. Configuration selects executable Python code and should come from a trusted source.

## Subscription fields

| Field | Type | Default | Constraint or meaning |
|---|---|---|---|
| `source` | String | Required | Name of an existing worker |
| `topic` | String | Required | Exact topic in that worker's publications |
| `delivery` | String | Topic-dependent | `latest` or `ordered` |

The default is `latest` when the topic string is exactly `vision/telemetry`, and `ordered` otherwise. If you rename a vision topic, specify `delivery: latest` explicitly to retain that behavior.

Delivery mode is applied by the built-in `ControllerWorker`/`ControllerRunner`. A custom worker reading `context.subscriber` directly receives individual decoded messages and must implement its own batching/coalescing policy.

## Endpoint fields and ownership

Omitting `endpoint` allocates `ipc:///tmp/pcvmf-<unique>/<worker>.ipc` in a per-run directory. Each publisher binds one endpoint; subscribers connect to every named upstream publisher. Topics do not create separate sockets.

Supported explicit forms:

```yaml
endpoint: ipc:///tmp/my-robot/vision.ipc
```

```yaml
endpoint: tcp://127.0.0.1:5555
```

IPC paths must be absolute, and the supplied path must be at most 100 bytes. Create the parent directory before running. TCP accepts loopback IPv4 or `localhost`, normalized to `127.0.0.1`, with a port from 1 to 65535. Wildcard binds and remote-host endpoints are not accepted by this configuration parser.

Normalized endpoints must be unique. IPC publishers create an ownership lock and reject an existing lock or socket path. Cleanup removes owned files; the supervisor also records file identities for cleanup after a forced worker exit. A crash of the supervisor itself can leave explicit endpoints behind. Automatic per-run paths avoid accidental sharing between applications.

## Logging fields

| Field | Default | Accepted values |
|---|---|---|
| `level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `format` | See below | Python logging percent-style format string |

Default format:

```text
%(asctime)s %(levelname)s [%(processName)s] %(name)s: %(message)s
```

DEBUG logging includes the effective configuration. Configuration validation checks format syntax; it does not prove that arbitrary custom LogRecord field names exist at runtime.

## Validation boundaries

Validation rejects malformed YAML, unknown framework keys, missing or duplicate worker names, invalid plugin imports/types/options, undeclared subscription targets, invalid endpoint declarations, and duplicate codec registrations. It does **not** open a device, verify model files by loading them, prove an endpoint is free, or establish a subscriber connection. Those operations happen in child initialization.

The parser cannot infer a plugin's publication needs from arbitrary code. For example, a vision worker needs its configured output topic declared in `publications`; an omitted publisher fails initialization and a mismatched publication fails when publishing.

See [built-in component options](components.md) for the contents of `plugin.options` and [troubleshooting](../how-to/troubleshooting.md) for common errors.
