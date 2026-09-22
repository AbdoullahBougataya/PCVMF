from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from pcvmf.api import ConfigurationError, Worker
from pcvmf.config import load_config, parse_config
from pcvmf.plugins import load_class


def valid():
    return yaml.safe_load(Path("config/default_config.yaml").read_text())


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda c: c.update(typo=True), "unknown keys"),
        (lambda c: c.update(workers=[]), "nonempty list"),
        (lambda c: c["workers"].append(deepcopy(c["workers"][0])), "duplicate worker"),
        (lambda c: c["workers"][0].update(rate_hz=0), "rate_hz"),
        (lambda c: c["workers"][0].update(startup_timeout=-1), "startup_timeout"),
        (lambda c: c["workers"][0].update(rate_hz=float("nan")), "finite"),
        (lambda c: c["workers"][0].update(rate_hz=True), "finite"),
        (lambda c: c["workers"][1]["subscriptions"][0].update(source="absent"), "unknown publication"),
        (lambda c: c["workers"][1]["subscriptions"][0].update(delivery="bad"), "delivery"),
        (lambda c: c["workers"][0]["plugin"]["options"].update(unused=1), "unknown keys"),
        (lambda c: c["workers"][1].update(endpoint="ipc:///tmp/no-publisher"), "requires publications"),
        (lambda c: c["workers"][0].update(endpoint="tcp://127.0.0.1:0"), "invalid port"),
        (lambda c: c["workers"][0].update(endpoint="ipc://relative"), "absolute"),
        (lambda c: c.update(logging={"level": "VERBOSE"}), "logging.level"),
        (lambda c: c.update(codecs=["does_not_exist:Codec"]), "cannot import"),
    ],
)
def test_invalid_config(mutate, match):
    config = valid()
    mutate(config)
    with pytest.raises(ConfigurationError, match=match):
        parse_config(config)


def test_duplicate_endpoints():
    config = valid()
    config["workers"][0]["endpoint"] = "ipc:///tmp/a/../same"
    config["workers"][1].update(publications=["other"], endpoint="ipc:///tmp/same")
    with pytest.raises(ConfigurationError, match="duplicate endpoint"):
        parse_config(config)


def test_bad_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("workers: [")
    with pytest.raises(ConfigurationError):
        load_config(path)
    path.write_text("")
    with pytest.raises(ConfigurationError, match="mapping"):
        load_config(path)


@pytest.mark.parametrize("path", ["bad", "nothing_exists:Absent", "pcvmf.api:Worker", "builtins:dict"])
def test_plugin_errors(path):
    with pytest.raises(ConfigurationError):
        load_class(path, Worker)


def test_packaged_default_outside_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert len(config.workers) == 2
    assert config.workers[1].subscriptions[0].delivery == "latest"
