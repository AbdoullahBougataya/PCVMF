# Explanation

[Documentation home](../README.md)

These pages explain the design and tradeoffs behind the API. They are useful when choosing boundaries for a larger application or interpreting runtime behavior.

- [Architecture and extension boundaries](architecture.md): why components and workers are separate, and who owns resources.
- [Message delivery and timing](delivery-and-timing.md): what freshness, ordering, timestamps, and scheduling actually mean.
- [Lifecycle and failure policy](lifecycle.md): readiness, progress reporting, application-wide shutdown, and cleanup guarantees.

For concrete operations, use the [how-to guides](../how-to/README.md). For exact fields and defaults, use [reference](../reference/README.md).
