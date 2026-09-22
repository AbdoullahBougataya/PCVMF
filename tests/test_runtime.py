import json
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from pcvmf.config import parse_config
from pcvmf.runtime import Application


def worker(name="probe", action=None, **kwargs):
    options = kwargs.pop("options", {})
    if action:
        options["action"] = action
    return {
        "name": name,
        "plugin": {"class": "tests.plugins:ProbeWorker", "options": options},
        "rate_hz": 50,
        "progress_timeout": 1,
        "shutdown_timeout": 0.3,
        **kwargs,
    }


def test_two_publishers_deliver_and_clean_up(tmp_path):
    output = tmp_path / "received.json"
    config = parse_config(
        {
            "workers": [
                worker("a", publications=["sample"]),
                worker("b", publications=["sample"]),
                worker(
                    "sink",
                    options={"output": str(output), "expected_sources": 2},
                    subscriptions=[{"source": "a", "topic": "sample"}, {"source": "b", "topic": "sample"}],
                ),
            ]
        }
    )
    endpoints = []

    def event(name, data):
        if name == "application":
            endpoints.extend(data["endpoints"].values())

    before = {p.pid for p in mp.active_children()}
    result = Application(config, on_event=event).run()
    assert result.exit_code == 0, result.errors
    assert result.ready
    assert json.loads(output.read_text()) == {"a": "a", "b": "b"}
    assert all(not Path(endpoint[6:]).exists() for endpoint in endpoints)
    assert {p.pid for p in mp.active_children()} == before


@pytest.mark.parametrize(
    "action,expected",
    [
        ("init_fail", "initialization failure"),
        ("fail", "step failure"),
        ("exit", "exit"),
        ("block", "progress timeout"),
        ("ignore_term", "progress timeout"),
        ("init_block", "startup timeout"),
    ],
)
def test_failures_report_and_stop(action, expected, tmp_path):
    clean = tmp_path / "cleaned"
    spec = worker(action=action, options={"cleanup_file": str(clean)})
    if action == "init_block":
        spec["startup_timeout"] = 1
    result = Application(parse_config({"workers": [spec]})).run()
    assert result.exit_code == 1
    assert any(expected in error for error in result.errors), result.errors
    if action in ("init_fail", "fail"):
        assert clean.read_text() == "cleaned"


def test_normal_completion_and_cleanup_failure():
    result = Application(parse_config({"workers": [worker(action="complete")]})).run()
    assert result.exit_code == 0, result.errors
    app = None

    def stop_on_ready(name, event):
        if name == "application":
            app.request_stop()

    app = Application(parse_config({"workers": [worker(action="cleanup_fail")]}), on_event=stop_on_ready)
    result = app.run()
    assert result.exit_code == 1
    assert any("cleanup failure" in e for e in result.errors)


def test_shutdown_timeout():
    app = None

    def stop_on_ready(name, event):
        if name == "application":
            app.request_stop()

    app = Application(parse_config({"workers": [worker(action="cleanup_block")]}), on_event=stop_on_ready)
    result = app.run()
    assert result.exit_code == 1
    assert any("shutdown timed out" in e for e in result.errors)


def test_callback_failure_is_worker_failure():
    controller = {
        "name": "controller",
        "plugin": {
            "class": "pcvmf.workers:ControllerWorker",
            "options": {"controller": {"class": "tests.plugins:FailingController"}},
        },
        "subscriptions": [{"source": "source", "topic": "sample"}],
    }
    result = Application(parse_config({"workers": [worker("source", publications=["sample"]), controller]})).run()
    assert result.exit_code == 1
    assert any("callback failure" in e for e in result.errors)


def test_concurrent_instances_have_distinct_endpoints():
    def run_one():
        endpoints = []
        app = None

        def event(name, data):
            if name == "application":
                endpoints.extend(data["endpoints"].values())
                app.request_stop()

        app = Application(parse_config({"workers": [worker(publications=["sample"])]}), on_event=event)
        result = app.run()
        assert result.exit_code == 0, result.errors
        return endpoints[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_one(), range(2)))
    assert results[0] != results[1]


def test_finite_vision_completes():
    config = parse_config(
        {
            "workers": [
                {
                    "name": "vision",
                    "plugin": {
                        "class": "pcvmf.workers:VisionWorker",
                        "options": {
                            "source": {"class": "pcvmf.vision.sources:SyntheticSource", "options": {"frames": 3}}
                        },
                    },
                    "publications": ["vision/telemetry"],
                }
            ]
        }
    )
    assert Application(config).run().exit_code == 0


def test_forced_exit_cleans_explicit_owned_endpoint(tmp_path):
    endpoint = tmp_path / "explicit.ipc"
    result = Application(
        parse_config({"workers": [worker(action="block", publications=["sample"], endpoint=f"ipc://{endpoint}")]})
    ).run()
    assert result.exit_code == 1
    assert not endpoint.exists()
    assert not Path(str(endpoint) + ".lock").exists()
