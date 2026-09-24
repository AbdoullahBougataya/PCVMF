import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from mcap.reader import make_reader

from pcvmf.config import parse_config
from pcvmf.messages import CodecRegistry
from pcvmf.runtime import Application


def recording_worker(name="probe", **options):
    return {
        "name": name,
        "plugin": {"class": "tests.plugins:RecordingWorker", "options": options},
        "publications": ["sample"],
        "rate_hz": 50,
        "startup_timeout": 5,
        "progress_timeout": 2,
        "shutdown_timeout": 2,
    }


def recording_config(tmp_path, workers=None, **kwargs):
    return parse_config(
        {
            "workers": workers or [recording_worker()],
            "logging": {"mcap": {"directory": str(tmp_path), "compression": "none"}},
            **kwargs,
        }
    )


def read_recording(result):
    assert result.recording_path is not None
    with Path(result.recording_path).open("rb") as stream:
        reader = make_reader(stream, validate_crcs=True)
        records = list(reader.iter_messages(log_time_order=False))
        summary = reader.get_summary()
    assert summary is not None
    assert summary.statistics.message_count == len(records)
    return records


def publications(records):
    return [(schema, channel, message) for schema, channel, message in records if channel.topic != "/pcvmf/logs"]


def log_records(records):
    return [json.loads(message.data) for _, channel, message in records if channel.topic == "/pcvmf/logs"]


def test_records_first_and_last_finite_frame_without_subscribers(tmp_path):
    worker = {
        "name": "vision",
        "plugin": {
            "class": "pcvmf.workers:VisionWorker",
            "options": {"source": {"class": "pcvmf.vision.sources:SyntheticSource", "options": {"frames": 5}}},
        },
        "publications": ["vision/telemetry"],
    }
    result = Application(recording_config(tmp_path, [worker])).run()
    assert result.exit_code == 0, result.errors
    records = publications(read_recording(result))
    assert len(records) == 5
    registry = CodecRegistry()
    decoded = [registry.decode(channel.topic, message.data) for _, channel, message in records]
    assert [message.sequence for message in decoded] == list(range(5))
    assert [message.payload.frame_id for message in decoded] == list(range(5))
    for schema, channel, message in records:
        envelope = json.loads(message.data)
        assert channel.topic == "vision/telemetry"
        assert channel.message_encoding == "json"
        assert channel.metadata["source"] == "vision"
        assert channel.metadata["message_type"] == "vision.telemetry"
        assert channel.metadata["schema_version"] == "1"
        assert schema.encoding == "jsonschema"
        assert json.loads(schema.data)["type"] == "object"
        assert message.publish_time == int(envelope["timestamp"] * 1_000_000_000)
        assert message.sequence == envelope["sequence"]
        assert message.log_time > 0


def test_records_lifecycle_publications_and_structured_logs(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="pcvmf.runtime")
    result = Application(recording_config(tmp_path)).run()
    assert result.exit_code == 0, result.errors
    records = read_recording(result)
    envelopes = [json.loads(message.data) for _, _, message in publications(records)]
    assert [envelope["payload"]["message"] for envelope in envelopes] == [
        "initialized",
        "step 0",
        "step 1",
        "cleaned",
    ]
    assert [envelope["sequence"] for envelope in envelopes] == list(range(4))
    logs = log_records(records)
    worker_logs = [record for record in logs if record["logger"] == "tests.plugins"]
    assert [record["message"] for record in worker_logs] == [
        "recording initialized",
        "recording step 0",
        "recording step 1",
        "recording cleaned",
    ]
    for record in worker_logs:
        assert record["source"] == "probe"
        assert record["level"] == "INFO"
        assert record["timestamp"] > 0
        assert record["process"] > 0
        assert record["process_name"] == "probe"
        assert Path(record["filename"]).name == "plugins.py"
        assert record["line"] > 0
        assert record["exception"] == ""
    assert any(record["source"] == "application" for record in logs)


def test_separates_producers_sharing_one_topic(tmp_path):
    workers = [recording_worker("alpha"), recording_worker("beta")]
    result = Application(recording_config(tmp_path, workers)).run()
    assert result.exit_code == 0, result.errors
    records = publications(read_recording(result))
    channels = {channel.id: channel for _, channel, _ in records}
    assert len(channels) == 2
    assert {channel.topic for channel in channels.values()} == {"sample"}
    assert {channel.metadata["source"] for channel in channels.values()} == {"alpha", "beta"}
    for source in ("alpha", "beta"):
        envelopes = [
            json.loads(message.data) for _, channel, message in records if channel.metadata["source"] == source
        ]
        assert envelopes[0]["payload"]["message"] == "initialized"
        assert envelopes[-1]["payload"]["message"] == "cleaned"
        assert [envelope["sequence"] for envelope in envelopes] == list(range(len(envelopes)))


def test_custom_codec_records_original_envelopes(tmp_path):
    codec_paths = ["tests.plugins:RecordingPayloadCodec"]
    result = Application(recording_config(tmp_path, [recording_worker(custom=True)], codecs=codec_paths)).run()
    assert result.exit_code == 0, result.errors
    registry = CodecRegistry(codec_paths)
    records = publications(read_recording(result))
    assert len(records) == 4
    assert {channel.metadata["message_type"] for _, channel, _ in records} == {"test.recording"}
    assert {channel.metadata["schema_version"] for _, channel, _ in records} == {"2"}
    assert [registry.decode(channel.topic, message.data).payload.phase for _, channel, message in records] == [
        "initialized",
        "step 0",
        "step 1",
        "cleaned",
    ]


@pytest.mark.parametrize("phase", ["initialized", "step 0", "cleaned"])
def test_failure_logs_are_flushed_and_file_is_readable(tmp_path, phase):
    result = Application(recording_config(tmp_path, [recording_worker(fail=phase)])).run()
    assert result.exit_code == 1
    expected = f"intentional recording {phase} failure"
    assert any(expected in error for error in result.errors), result.errors
    records = read_recording(result)
    assert any(expected in record["exception"] for record in log_records(records))
    envelopes = [json.loads(message.data) for _, _, message in publications(records)]
    assert envelopes[0]["payload"]["message"] == "initialized"
    assert envelopes[-1]["payload"]["message"] == "cleaned"


def test_disabled_recording_does_not_create_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = parse_config({"workers": [recording_worker()]})
    result = Application(config).run()
    assert result.exit_code == 0, result.errors
    assert result.recording_path is None
    assert not list(tmp_path.iterdir())


def test_unusable_output_directory_fails_before_workers_start(tmp_path):
    output = tmp_path / "existing-file"
    output.write_text("keep this content")
    events = []
    result = Application(recording_config(output), on_event=lambda name, event: events.append((name, event))).run()
    assert result.exit_code == 1
    assert result.errors
    assert not result.ready
    assert not any(event["kind"] == "ready" for _, event in events)
    assert output.read_text() == "keep this content"


def test_each_run_creates_a_distinct_recording(tmp_path):
    config = recording_config(tmp_path)
    results = [Application(config).run(), Application(config).run()]
    for result in results:
        assert result.exit_code == 0, result.errors
        assert publications(read_recording(result))
    assert results[0].recording_path != results[1].recording_path
    assert len(list(tmp_path.glob("*.mcap"))) == 2


def test_worker_named_recording_has_distinct_ipc_endpoint(tmp_path):
    result = Application(recording_config(tmp_path, [recording_worker("recording")])).run()
    assert result.exit_code == 0, result.errors
    assert len(publications(read_recording(result))) == 4


def test_concurrent_applications_keep_recordings_and_parent_logs_separate(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="pcvmf.runtime")

    def run_one(name):
        def mark_ready(source, event):
            if source == "application" and event["kind"] == "ready":
                logging.getLogger("pcvmf.runtime").info("application marker %s", name)

        result = Application(recording_config(tmp_path, [recording_worker(name)]), on_event=mark_ready).run()
        assert result.exit_code == 0, result.errors
        return name, result, read_recording(result)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_one, ("alpha", "beta")))
    assert len({result.recording_path for _, result, _ in results}) == 2
    for name, result, records in results:
        assert {channel.metadata["source"] for _, channel, _ in publications(records)} == {name}
        parent_logs = [record for record in log_records(records) if record["source"] == "application"]
        markers = [record["message"] for record in parent_logs if record["message"].startswith("application marker ")]
        assert markers == [f"application marker {name}"]
        paths = [record["message"] for record in parent_logs if record["message"].startswith("MCAP recording: ")]
        assert paths == [f"MCAP recording: {result.recording_path}"]


def test_log_level_does_not_filter_publications(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="pcvmf.runtime")
    config = recording_config(
        tmp_path,
        logging={"level": "WARNING", "mcap": {"directory": str(tmp_path), "compression": "none"}},
    )
    result = Application(config).run()
    assert result.exit_code == 0, result.errors
    records = read_recording(result)
    assert len(publications(records)) == 4
    assert all(record["level"] in ("WARNING", "ERROR", "CRITICAL") for record in log_records(records))
