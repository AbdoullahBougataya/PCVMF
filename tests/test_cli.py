import os
import selectors
import signal
import subprocess
import sys
import time

import pytest
import yaml
from mcap.reader import make_reader


@pytest.mark.parametrize("recording", [False, True])
@pytest.mark.parametrize("sig,group", [(signal.SIGTERM, False), (signal.SIGINT, True)])
def test_cli_ready_and_signal_shutdown(sig, group, recording, tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONUNBUFFERED"] = "1"
    command = [sys.executable, "-m", "pcvmf", "run"]
    if recording:
        from importlib.resources import files

        config = yaml.safe_load(files("pcvmf.defaults").joinpath("demo.yaml").read_text())
        config["logging"]["mcap"] = {"directory": str(tmp_path / "recordings")}
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(config))
        command += ["--config", str(path)]
    proc = subprocess.Popen(
        command,
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    output = b""
    try:
        deadline = time.monotonic() + 15
        while b"Application ready:" not in output and time.monotonic() < deadline:
            if selector.select(0.1):
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                output += chunk
        assert b"Application ready:" in output, output.decode()
        if group:
            os.killpg(proc.pid, sig)
        else:
            proc.send_signal(sig)
        rest, _ = proc.communicate(timeout=10)
        assert proc.returncode == 0, (output + rest).decode()
        if recording:
            [recording_path] = list((tmp_path / "recordings").glob("*.mcap"))
            with recording_path.open("rb") as stream:
                reader = make_reader(stream, validate_crcs=True)
                assert reader.get_summary() is not None
                assert list(reader.iter_messages(topics=["/pcvmf/logs"]))
    finally:
        selector.close()
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        proc.stdout.close()


def test_cli_validation_error(tmp_path):
    config = tmp_path / "invalid.yaml"
    config.write_text("workers: []")
    proc = subprocess.run(
        [sys.executable, "-m", "pcvmf", "config", "validate", str(config)], capture_output=True, text=True
    )
    assert proc.returncode == 2
    assert "workers" in proc.stderr
