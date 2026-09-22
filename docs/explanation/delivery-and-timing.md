# Message delivery and timing

[Documentation home](../README.md) · [Explanation](README.md)

An asynchronous vision application must choose what to do when production and consumption rates differ. PCVMF exposes some of that policy through routes and batching, while leaving domain decisions to the application.

## Receiving every available sample versus using a fresher state

For an image-derived target location, processing many old positions may be less useful than acting on a newer one. For an event stream, each received event may matter individually. The built-in controller runner supports two delivery modes for these cases.

`ordered` delivers each received message in the batch to the controller. `latest` replaces earlier messages with the final message for the same source/topic **within that batch**. Sources and topics are distinct keys, so one camera cannot replace another camera's observation.

Suppose a batch contains:

```text
camera-a/frame-10
camera-b/frame-20
camera-a/frame-11
```

With latest delivery for both routes, callbacks receive camera B's frame 20 and camera A's frame 11, in the order of those retained messages. Camera A's frame 10 is discarded by the batch policy. This says nothing about messages still waiting in the transport queue.

Queue high-water marks bound transport queues, but do not make `latest` a global “jump to the newest sample” operation. If the consumer cannot keep up, a bounded batch may still contain old messages. Reducing publication rate, processing cost, or unnecessary payload size may be more useful than increasing queue depth.

## PUB/SUB has no delivery guarantee

The transport has no replay, acknowledgements, or durable storage. Initial publications can be missed while subscriptions connect, and queue pressure can drop messages. `ordered` means the order of messages received and dispatched, not proof that every sent message arrived. Sequence numbers can help an application observe gaps, but the framework does not repair them.

Readiness uses a separate lifecycle channel and means workers have initialized. It does not establish a delivery barrier for the data plane. This is why tests should wait for a known payload rather than infer message exchange from readiness or elapsed time alone.

A control command that requires confirmation needs a different communication contract. PCVMF's current telemetry transport does not implement that contract.

## Bounded receiving protects opportunities to tick

The controller runner stops receiving when it reaches either `max_messages` or `receive_budget_ms`. It then dispatches the retained messages and calls `tick(dt)`. A continuously busy publisher therefore cannot keep the built-in runner in an unlimited drain loop.

This budget covers the receive phase, not arbitrary controller code. A callback that blocks for a second still delays the tick by a second. Keep callbacks short, store state, and put periodic control logic in `tick()`. Even then, Python scheduling and operating-system load prevent hard real-time guarantees.

Custom `Worker` implementations reading the subscriber directly must implement their own batching policy. A YAML delivery setting does not rewrite a custom worker's loop.

## Three different time concepts

**Wall-clock timestamps** record capture and publication events. They are useful in logs and recordings but can jump when the system clock changes. They do not establish synchronization between hosts.

**Monotonic elapsed time** drives scheduling, progress detection, controller deltas, and local staleness checks. It measures intervals without depending on wall-clock corrections. It should not be serialized as a universally comparable timestamp.

**Processing measurements** separate source-read duration from pipeline duration. Neither includes transport residence, callback cost, or visualization. A small `processing_time_ms` does not prove that a controller is acting on a recent frame.

`rate_hz` is a target scheduling rate. When a step overruns, the runtime reports a missed deadline and avoids accumulating catch-up work indefinitely. It cannot make slow inference meet a faster target simply by increasing the rate value.

## Staleness is a diagnostic, not an action policy

The built-in controller runner tracks how long each route has gone without an accepted message and logs stale/recovered transitions. It starts that clock at controller initialization for configured routes. A sparse sensor may need a longer threshold than a fast camera.

The framework does not automatically clear a controller's last value, stop an actuator, or mark a typed payload invalid when a route becomes stale. Those are application decisions. The example tracking controller only demonstrates offsets and does not implement a physical control policy.

Use the [configuration reference](../reference/configuration.md) for delivery defaults, and [troubleshooting](../how-to/troubleshooting.md#stale-input-or-missed-deadlines) when investigating timing symptoms.
