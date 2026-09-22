# Add a sensor and message type

[Documentation home](../README.md) · [How-to guides](README.md)

Use this guide when adding a non-vision data source to an existing application. You need an installable application package and a controller that can consume the new payload. The [temperature example](../../examples/external_plugins/robot_plugins/sensor.py) is a complete implementation to copy into your own package and adapt.

## Define the payload and codec

Keep the payload focused on the measurement, including explicit units in field names. Subclass `MessageCodec` and set a unique message type, schema version, and payload type. Implement validation in both directions; reject booleans masquerading as numbers and non-finite values when those are invalid for your domain.

For the existing example, the Python payload is `Temperature(celsius: float)`, the message type is `sensor.temperature`, and the version is 1. `TemperatureCodec.encode()` returns `{"celsius": value}` after validation; `decode()` creates a validated `Temperature` instance.

When adapting it, change the payload, message type, codec, and controller together. Register the codec in the application, not just in the publishing worker:

```yaml
codecs: ['robot_plugins.sensor:TemperatureCodec']
```

The registry is shared as configuration and constructed separately in every process. It selects outgoing codecs by exact Python payload type. Do not register two codecs for the same payload class. See [codec reference](../reference/messages.md#custom-messagecodec-contract).

## Implement bounded acquisition

Subclass `Worker` in your package. Its lifecycle should do the following:

1. Validate options without opening a device.
2. In `initialize(context)`, store the context and open the hardware handle.
3. In `step()`, read at most a bounded amount of data and call `context.publisher.publish(topic, payload)`.
4. In `cleanup()`, release a handle if initialization created one, including after a partial initialization failure.

Use the device API's timeout where available. Do not start an infinite acquisition loop inside `step()`; the runtime already provides the loop and rate control. A blocked step prevents progress reporting and eventually fails the application. Do not open a device at import time or create ZeroMQ sockets in your plugin constructor.

The example worker increments a synthetic sample index once per step and publishes `Temperature` on `sensor/temperature`. It returns `None` to keep running. Return `False` only when you intend the entire application to finish.

## Connect the worker to a controller

Install the example package if trying this recipe unchanged:

```bash
uv pip install --python .venv/bin/python --no-deps --editable ./examples/external_plugins
```

The following complete configuration starts the example publisher and its consumer:

```yaml
codecs: ['robot_plugins.sensor:TemperatureCodec']
workers:
  - name: temperature
    plugin: {class: 'robot_plugins.sensor:TemperatureWorker'}
    rate_hz: 10
    publications: [sensor/temperature]
  - name: controller
    plugin:
      class: pcvmf.workers:ControllerWorker
      options:
        controller: {class: 'robot_plugins.sensor:TemperatureController'}
    subscriptions:
      - {source: temperature, topic: sensor/temperature, delivery: ordered}
```

Save it as `config/my_sensor.yaml`, validate, and run:

```bash
uv run --no-sync pcvmf config validate config/my_sensor.yaml
uv run --no-sync pcvmf run --config config/my_sensor.yaml
```

Expected result: readiness followed by a single `Received temperature from temperature:` log entry. Stop with Ctrl+C. In an existing application, add the worker and codec and merge the subscription into your existing controller instead of adding a second controller blindly.

## Handle the typed message

In `on_message(message)`, distinguish payloads with `isinstance(message.payload, Temperature)` and use `message.source` if multiple sensors publish the same type. Keep callbacks short and store state for the next `tick(dt)`.

Select `latest` when intermediate readings may be replaced by fresher readings within a batch. Select `ordered` when you want callbacks for every message the consumer actually receives. Neither mode prevents PUB/SUB loss or startup drops. For required acknowledgements or replay, this transport is not sufficient.

Before connecting hardware, verify codec round trips and rejected inputs, then verify that the synthetic worker delivers a decoded payload to your controller. The [testing guide](testing.md) separates component checks from process integration checks.
