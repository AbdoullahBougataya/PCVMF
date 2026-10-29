# Stream telemetry to Yamcs

[Documentation home](../README.md) · [How-to guides](README.md)

Send live PCVMF telemetry to [Yamcs](https://yamcs.org), a mission control server that archives, plots and alarms on parameters. The `YamcsExporter` worker subscribes to PCVMF topics. It converts the message fields you choose into CCSDS packets and sends them to a Yamcs UDP link. The `pcvmf yamcs mdb` command generates the matching XTCE mission database (MDB), the file that tells Yamcs how to decode each packet.

This guide assumes a Linux repository checkout, Python 3.10–3.12, `uv`, and Docker with Compose. Run the commands from the repository root.

## Start Yamcs

The repository includes a Yamcs 5.13.6 server configured for PCVMF in [`deploy/yamcs`](../../deploy/yamcs). Build and start it:

```bash
docker compose -f deploy/yamcs/docker-compose.yml up -d --build
```

The first build downloads the Yamcs release archive and checks its SHA-256 digest. Yamcs is ready when `http://localhost:8090` opens the Yamcs web interface and shows the `pcvmf` instance. Both ports are bound to `127.0.0.1` only:

| Port | Purpose |
|---|---|
| `8090/tcp` | Web interface and HTTP/WebSocket API |
| `10015/udp` | Telemetry link `udp-in`, which receives PCVMF packets |

## Run the example

[`examples/yamcs.yaml`](../../examples/yamcs.yaml) runs a synthetic vision worker and a `YamcsExporter` worker that forwards `vision/telemetry`:

```bash
uv sync --frozen --extra dev
uv run --frozen pcvmf config validate examples/yamcs.yaml
uv run --frozen pcvmf run --config examples/yamcs.yaml
```

Validation prints `Valid configuration: 2 workers`. The run logs `Application ready: 2 workers` and streams until you press Ctrl+C.

Check the result in the Yamcs web interface at `http://localhost:8090`, instance `pcvmf`:

1. Open **Links**. The `udp-in` link counts received packets.
2. Open **Telemetry > Parameters** and select `/PCVMF/vision_telemetry/processing_time_ms`. The value updates about ten times per second.
3. Open **Archive** after you stop PCVMF. The `/PCVMF/vision_telemetry/Packet` packets remain available for replay and plotting.

## Export your own topic

You can export any topic whose payload fields are numbers, booleans, or strings with a fixed set of values. This also covers payloads from [custom codecs](add-sensor.md).

1. Add a `YamcsExporter` worker with one packet per `(source, topic)` route. Subscribe the worker to every route it exports:

   ```yaml
   - name: yamcs
     plugin:
       class: pcvmf.yamcs:YamcsExporter
       options:
         packets:
           - name: temperature
             apid: 101
             source: temperature
             topic: sensor/temperature
             parameters:
               - {name: celsius, type: float64, units: degC}
     subscriptions:
       - {source: temperature, topic: sensor/temperature, delivery: ordered}
   ```

   Each packet needs a unique `apid` from 0 to 2046. Use `delivery: ordered` so Yamcs receives every message the exporter gets, not only the newest one. The [YamcsExporter reference](../reference/components.md#yamcsexporter) lists every option and parameter type.

2. Regenerate the mission database from the same configuration:

   ```bash
   uv run --frozen pcvmf yamcs mdb --config my-app.yaml -o deploy/yamcs/mdb/pcvmf.xml
   ```

   The command warns on standard error when a packet route has no matching subscription.

3. Restart Yamcs so it loads the new MDB:

   ```bash
   docker compose -f deploy/yamcs/docker-compose.yml restart yamcs
   ```

Parameters appear in Yamcs as `/<space_system>/<packet name>/<parameter name>`, for example `/PCVMF/temperature/celsius`.

> **Important:** Regenerate the MDB and restart Yamcs every time you change `packets`. Yamcs decodes packets by byte position. A stale MDB shows wrong values without reporting an error.

## Select nested values

The `field` path reads attributes, mapping keys, and list indexes separated by dots. Without `field`, the parameter name is used as the path.

| Goal | Parameter |
|---|---|
| Top-level field | `{name: frame_id, type: uint32}` |
| Number of list items | `{name: detection_count, field: detections, reduce: count, type: uint32}` |
| First list item, when one exists | `{name: target_confidence, field: detections.0.confidence, type: float64, default: 0.0}` |
| String status | `{name: status, type: enum, values: {OK: 0, NO_TARGETS: 1}}` |

`default` is used only when a list index is out of range. If any other path is missing or a value does not fit the type, the exporter skips that message and logs one warning for the packet.

## Connect Open MCT

Open MCT can display the same parameters through the [openmct-yamcs](https://github.com/akhenry/openmct-yamcs) plugin. The plugin reads the Yamcs mission database, so PCVMF needs no further changes. Configure the plugin with:

| Setting | Value |
|---|---|
| Yamcs URL | `http://localhost:8090` (or `http://yamcs:8090` from another Compose service) |
| Instance | `pcvmf` |
| Processor | `realtime` |

The Yamcs server in `deploy/yamcs` allows cross-origin requests from any origin so a separately served Open MCT page can call the API during development. The Compose file has a commented-out `openmct` service as a starting point.

## Troubleshoot

| Symptom | Cause and fix |
|---|---|
| `udp-in` count stays at 0 | Yamcs is not running, or `host`/`port` in the exporter options do not point to the link. Check `docker compose -f deploy/yamcs/docker-compose.yml ps` and the default `127.0.0.1:10015`. |
| Packets arrive but parameters are missing or wrong | The MDB does not match the configuration. Regenerate it with `pcvmf yamcs mdb` and restart Yamcs. |
| `Skipped Yamcs packet NAME: ...` warning | A field path is missing, a string has no `enum` label, or a value is outside its integer range. Fix the mapping or add a `default`. |
| `No Yamcs packet for SOURCE/TOPIC` warning | The exporter subscribes to a route with no packet definition. Add a packet or remove the subscription. |
| `Yamcs send to HOST:PORT failed` warning | The operating system rejected the datagram. The exporter keeps running and keeps trying. |

UDP delivery is best-effort. Yamcs does not acknowledge packets, and the exporter does not retry them. Compare `PACKET_SEQUENCE` values in Yamcs to find gaps.
