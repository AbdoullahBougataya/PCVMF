import socket
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from pcvmf.api import ConfigurationError, Message, TargetDetection, VisionTelemetry, WorkerContext
from pcvmf.cli import main
from pcvmf.config import Subscription
from pcvmf.yamcs import YamcsExporter
from pcvmf.yamcs.mapping import parse_export_options, unsubscribed_routes
from pcvmf.yamcs.packets import DATA_OFFSET, ExtractionError, encode, extract, layout
from pcvmf.yamcs.xtce import NAMESPACE, generate_xtce

EXAMPLE = Path("examples/yamcs.yaml")
MDB = Path("deploy/yamcs/mdb/pcvmf.xml")
NS = {"x": NAMESPACE}


def example_options():
    raw = yaml.safe_load(EXAMPLE.read_text())
    return next(w for w in raw["workers"] if w["name"] == "yamcs")["plugin"]["options"]


def telemetry(detections=(), status="OK"):
    return VisionTelemetry(1.0, 320, 240, 7, 1.5, 2.5, list(detections), status)


def options(**parameter):
    parameter.setdefault("name", "value")
    parameter.setdefault("type", "float64")
    return {"packets": [{"name": "p", "apid": 1, "source": "s", "topic": "t", "parameters": [parameter]}]}


@pytest.mark.parametrize(
    "raw,error",
    [
        ({"packets": []}, "nonempty list"),
        (options(type="int64"), "type"),
        (options(field="a..b"), "field"),
        (options(type="enum"), "values"),
        (options(type="enum", values={"A": 0, "B": 0}), "duplicate enumeration"),
        (options(type="float64", values={"A": 0}), "only valid for enum"),
        (options(reduce="count"), "count requires"),
        (options(type="uint32", default=-1), "at least"),
        (options(type="enum", values={"A": 0}, default="B"), "unknown enumeration"),
        (options(name="1bad"), "name"),
        ({**options(), "space_system": "bad name"}, "space_system"),
    ],
)
def test_invalid_mapping_options(raw, error):
    with pytest.raises(ConfigurationError, match=error):
        parse_export_options(raw)


def test_duplicate_packets_are_rejected():
    packet = options()["packets"][0]
    for change, error in (({}, "duplicate packet name"), ({"name": "q"}, "duplicate APID")):
        with pytest.raises(ConfigurationError, match=error):
            parse_export_options({"packets": [packet, {**packet, **change}]})
    with pytest.raises(ConfigurationError, match="apid"):
        parse_export_options({"packets": [{**packet, "apid": 2047}]})


def test_exporter_validates_connection_options():
    YamcsExporter.validate_options(example_options())
    with pytest.raises(ConfigurationError, match="port"):
        YamcsExporter.validate_options({**example_options(), "port": 70000})
    with pytest.raises(ConfigurationError, match="unknown keys"):
        YamcsExporter.validate_options({**example_options(), "extra": 1})


def test_unsubscribed_routes():
    spec = parse_export_options(example_options())
    assert unsubscribed_routes(spec, []) == ["vision/vision/telemetry"]
    assert unsubscribed_routes(spec, [Subscription("vision", "vision/telemetry")]) == []


def test_extract_paths_counts_and_defaults():
    [packet] = parse_export_options(example_options()).packets
    names = [p.name for p in packet.parameters]
    detection = TargetDetection("target", 0.75, [0, 0, 10, 10], [5, 6])
    values = dict(zip(names, extract(packet, telemetry([detection]))))
    assert values == {
        "frame_id": 7,
        "width": 320,
        "height": 240,
        "capture_time_ms": 1.5,
        "processing_time_ms": 2.5,
        "detection_count": 1,
        "target_confidence": 0.75,
        "target_x": 5,
        "target_y": 6,
        "status": 0,
    }
    empty = dict(zip(names, extract(packet, telemetry(status="NO_TARGETS"))))
    assert (empty["detection_count"], empty["target_confidence"], empty["target_x"], empty["status"]) == (0, 0, -1, 1)


@pytest.mark.parametrize(
    "parameter,payload,error",
    [
        ({"field": "missing"}, telemetry(), "missing attribute"),
        ({"field": "detections.0.confidence"}, telemetry(), "no default"),
        ({"field": "status", "type": "enum", "values": {"OK": 0}}, telemetry(status="LOST"), "unknown enumeration"),
        ({"field": "processing_time_ms", "type": "uint32"}, telemetry(), "not a valid uint32"),
        ({"field": "status"}, telemetry(), "expected a number"),
    ],
)
def test_extract_errors(parameter, payload, error):
    [packet] = parse_export_options(options(**parameter)).packets
    with pytest.raises(ExtractionError, match=error):
        extract(packet, payload)


def test_encode_ccsds_layout():
    spec = parse_export_options(
        {
            "packets": [
                {
                    "name": "p",
                    "apid": 0x123,
                    "source": "s",
                    "topic": "t",
                    "parameters": [{"name": "a", "type": "uint32"}, {"name": "b", "type": "float32"}],
                }
            ]
        }
    )
    [packet] = spec.packets
    data = encode(packet, 0x4001, 1.2506, (9, 0.5))
    word1, word2, length, millis, sequence = struct.unpack(">HHHQI", data[:DATA_OFFSET])
    assert word1 == 0x0800 | 0x123  # version 0, telemetry, secondary header flag
    assert word2 == 0xC001  # unsegmented, 14-bit wrapped count
    assert length == len(data) - 7
    assert (millis, sequence) == (1251, 0x4001)
    assert struct.unpack(">If", data[DATA_OFFSET:]) == (9, 0.5)


def _entries(container):
    return [entry.get("parameterRef") for entry in container.iterfind("x:EntryList/x:ParameterRefEntry", NS)]


def test_xtce_matches_packet_layout():
    spec = parse_export_options(example_options())
    root = ET.fromstring(generate_xtce(spec))
    assert root.get("name") == "PCVMF"
    sizes = {}
    for ptype in root.iter():
        encoding = ptype.find("x:IntegerDataEncoding", NS)
        encoding = ptype.find("x:FloatDataEncoding", NS) if encoding is None else encoding
        encoding = ptype.find("x:Encoding/x:IntegerDataEncoding", NS) if encoding is None else encoding
        if ptype.get("name", "").endswith("_t") and encoding is not None:
            sizes[ptype.get("name")[:-2]] = int(encoding.get("sizeInBits"))
    header = root.find("x:TelemetryMetaData/x:ContainerSet/x:SequenceContainer", NS)
    assert sum(sizes[name] for name in _entries(header)) == DATA_OFFSET * 8
    for packet in spec.packets:
        system = root.find(f"x:SpaceSystem[@name='{packet.name}']", NS)
        container = system.find("x:TelemetryMetaData/x:ContainerSet/x:SequenceContainer", NS)
        comparison = container.find("x:BaseContainer/x:RestrictionCriteria/x:Comparison", NS)
        assert comparison.get("value") == str(packet.apid)
        offset = DATA_OFFSET * 8
        for name, field in zip(_entries(container), layout(packet)):
            assert (name, offset, sizes[name]) == (field.name, field.bit_offset, field.size_bits)
            offset += field.size_bits
        assert offset // 8 == len(encode(packet, 0, 0, extract(packet, telemetry())))


def test_committed_mdb_matches_example():
    assert MDB.read_text() == generate_xtce(parse_export_options(example_options()))


def test_cli_writes_mdb(tmp_path, capsys):
    output = tmp_path / "mdb.xml"
    assert main(["yamcs", "mdb", "--config", str(EXAMPLE), "-o", str(output)]) == 0
    assert output.read_text() == MDB.read_text()
    with pytest.raises(SystemExit) as exit_info:
        main(["yamcs", "mdb", "--config", str(EXAMPLE), "--worker", "vision"])
    assert exit_info.value.code == 2
    assert "no YamcsExporter workers" in capsys.readouterr().err


class Queue:
    def __init__(self, messages):
        self.messages = list(messages)

    def receive(self, timeout_ms=0):
        return self.messages.pop(0) if self.messages else None

    def close(self):
        pass


def test_exporter_sends_udp_packets(caplog):
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2)
    port = receiver.getsockname()[1]
    sent = [
        Message("vision/telemetry", "vision.telemetry", 1, "vision", i, 100.0 + i, telemetry(status=status))
        for i, status in enumerate(["OK", "LOST", "NO_TARGETS"])
    ]
    other = Message("other", "vision.telemetry", 1, "vision", 0, 0.0, telemetry())
    exporter = YamcsExporter({**example_options(), "port": port})
    try:
        exporter.initialize(WorkerContext("yamcs", 10, subscriber=Queue([*sent, other])))
        assert exporter.step() is None
        packets = [receiver.recv(4096) for _ in range(2)]
    finally:
        exporter.cleanup()
        exporter.cleanup()
        receiver.close()
    assert [struct.unpack(">QI", p[6:DATA_OFFSET]) for p in packets] == [(100000, 0), (102000, 1)]
    assert "unknown enumeration label 'LOST'" in caplog.text
    assert "No Yamcs packet for vision/other" in caplog.text


def test_exporter_requires_subscriptions():
    exporter = YamcsExporter(example_options())
    with pytest.raises(ValueError, match="subscriptions"):
        exporter.initialize(WorkerContext("yamcs", 10))
    exporter.cleanup()


def test_example_application_streams_to_udp():
    from pcvmf.config import parse_config
    from pcvmf.runtime import Application

    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(5)
    raw = yaml.safe_load(EXAMPLE.read_text())
    raw["workers"][0]["plugin"]["options"]["source"]["options"]["frames"] = 20
    raw["workers"][1]["plugin"]["options"]["port"] = receiver.getsockname()[1]
    try:
        result = Application(parse_config(raw)).run()
        assert result.exit_code == 0, result.errors
        packet = receiver.recv(4096)
    finally:
        receiver.close()
    assert struct.unpack(">H", packet[:2])[0] & 0x7FF == 100
