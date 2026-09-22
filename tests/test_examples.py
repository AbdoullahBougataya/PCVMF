from pathlib import Path

import pytest
import yaml

from pcvmf.config import load_config, parse_config
from pcvmf.messages import CodecRegistry
from pcvmf.runtime import Application
from pcvmf.vision.sources import SyntheticSource


@pytest.fixture
def plugins(monkeypatch):
    monkeypatch.syspath_prepend(str(Path("examples/external_plugins").resolve()))


def test_external_pipeline_and_codec(plugins):
    from robot_plugins.sensor import Temperature
    from robot_plugins.vision import BrightPixelPipeline

    pipeline = BrightPixelPipeline({})
    pipeline.initialize()
    source = SyntheticSource({})
    source.open("camera", 30)
    assert pipeline.process(source.read().frame).detections[0].label == "bright"
    registry = CodecRegistry(["robot_plugins.sensor:TemperatureCodec"])
    payload = Temperature(21.5)
    assert registry.decode("sensor/temperature", registry.encode("temp", 1, 1, payload)).payload == payload
    load_config("examples/vision.yaml")
    load_config("examples/sensor.yaml")


@pytest.mark.parametrize("filename", ["vision", "sensor"])
def test_external_examples_exchange_messages(plugins, filename, tmp_path):
    # A test controller completes only after observing a decoded typed message.
    raw = yaml.safe_load(Path(f"examples/{filename}.yaml").read_text())
    output = tmp_path / "received"
    raw["workers"][1]["plugin"] = {"class": "tests.plugins:PayloadProbeWorker", "options": {"output": str(output)}}
    result = Application(parse_config(raw)).run()
    assert result.exit_code == 0, result.errors
    assert output.read_text() == ("VisionTelemetry" if filename == "vision" else "Temperature")
