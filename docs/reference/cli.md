# CLI and diagnostics reference

[Documentation home](../README.md) · [Reference](README.md)

Implementations: [cli.py](../../src/pcvmf/cli.py), [runtime.py](../../src/pcvmf/runtime.py).

## Commands

| Command | Behavior |
|---|---|
| `pcvmf` | Run the packaged headless demo |
| `pcvmf run` | Run the packaged headless demo |
| `pcvmf run --config PATH` | Load, validate, and run an application |
| `pcvmf config validate PATH` | Validate configuration and plugin imports/options, then exit |
| `pcvmf --help` | Show command help |
| `python -m pcvmf ...` | Equivalent module entry point |

`uv run --no-sync` is an environment-management prefix, not a PCVMF subcommand. Use it after separately installing application plugins.

The CLI has no `--headless`, `--fps`, `--duration`, or `--version` flag. Set component options in YAML. For the installed version use `python -c 'import pcvmf; print(pcvmf.__version__)'` in the appropriate environment. Finite synthetic frames and video EOF can provide automatic completion.

## Path behavior

Explicit configuration paths are relative to the launch working directory unless absolute. Video paths in plugin options also resolve from the working directory. Omitted configuration uses package resources, so the demo does not need the repository's `config/` directory.

## Exit codes and shutdown

| Code | Meaning |
|---|---|
| `0` | Validation succeeded, or application completed with successful cleanup |
| `1` | Runtime/supervision/cleanup failure or forced worker termination |
| `2` | CLI argument or handled configuration error |

SIGINT and SIGTERM received by the CLI request normal shutdown. Cleanup still must succeed for exit code 0. Completion by any worker, including a controller returning `False`, stops all workers. The embeddable `Application` does not install these signal handlers.

## Log messages

| Message/level | Interpretation |
|---|---|
| `Worker NAME ready` / INFO | That worker completed initialization |
| `Application ready: N workers` / INFO | Every worker initialized and the execution gate opened |
| `Effective configuration` / DEBUG | Validated settings used for the run |
| `Target offset` / DEBUG | Sample tracking controller's computed pixel offset |
| `Stale input` / WARNING | No accepted message on a route within its configured interval |
| `Input recovered` / INFO | A previously stale route received a message |
| `Discarded invalid message (decode_errors=N)` / WARNING | Incoming message failed decoding/validation |
| `missed scheduling deadline` / WARNING | A step exceeded its scheduling budget |
| `startup timeout` / ERROR | Worker did not report readiness in time |
| `progress timeout` / ERROR | Worker loop stopped reporting progress |
| `graceful shutdown timed out` / ERROR | Supervisor is forcing termination |

Deadline warnings are rate-limited to approximately once per second per worker. Staleness is logged once per stale transition, not on every tick. Neither metric is an automatic actuator policy.

## Lifecycle events

`Application(config, on_event=callback)` calls `callback(name, event)` synchronously in the parent. The event is a dictionary with a `kind` key.

| Name/kind | Additional data | Meaning |
|---|---|---|
| Worker / `ready` | None | Initialization completed |
| `application` / `ready` | `endpoints` mapping | All workers ready; resolved publisher endpoints |
| Worker / `heartbeat` | None | Progress reported by the execution loop |
| Worker / `complete` | None | Normal application completion requested |
| Worker / `failure` | `error`; sometimes `traceback` | Execution or cleanup failed |
| Worker / `exited` | `ok` boolean | Cleanup path finished; process exit is checked separately |
| Worker / `resources` | Ownership bookkeeping | Internal endpoint cleanup metadata; applications should ignore it |

Handle only events your application needs and ignore other kinds. Keep callbacks fast. A blocking callback can delay supervision; exceptions from callbacks cause failed shutdown. Call `request_stop()` to request completion rather than manipulating multiprocessing events directly.

For diagnosis steps rather than message definitions, see [troubleshooting](../how-to/troubleshooting.md).
