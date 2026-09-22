# Reference

[Documentation home](../README.md)

Use these pages to look up the implemented PCVMF 0.3 API. For a worked example, start with the [tutorials](../tutorials/README.md).

- [Configuration](configuration.md): application, worker, subscription, endpoint, and logging fields.
- [Built-in components](components.md): worker options, frame sources, detector, controller, and visualizers.
- [Python API](api.md): public plugin contracts, context, configuration loading, application execution, and component runners.
- [Messages](messages.md): Python data types, codecs, envelope fields, validation, and topic routing.
- [CLI and diagnostics](cli.md): commands, paths, exit codes, logs, and lifecycle event callbacks.

Source links identify implementations for maintainers. Import extension contracts from `pcvmf.api`; use documented built-in import paths in configuration. Internal transport, registry, and loader modules are not extension APIs.
