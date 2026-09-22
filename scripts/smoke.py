"""Smoke-test the installed CLI from an unrelated working directory."""

import argparse
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def smoke(config=None, duration=0.25):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONUNBUFFERED"] = "1"
    command = [sys.executable, "-m", "pcvmf", "run"]
    if config:
        command += ["--config", str(Path(config).resolve())]
    with tempfile.TemporaryDirectory(prefix="pcvmf-smoke-") as directory:
        process = subprocess.Popen(
            command, cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True
        )
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        output = b""
        deadline = time.monotonic() + 30
        try:
            while b"Application ready:" not in output and time.monotonic() < deadline:
                if selector.select(timeout=0.1):
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output += chunk
            if b"Application ready:" not in output:
                raise RuntimeError(f"application did not become ready:\n{output.decode()}")
            time.sleep(duration)
            if process.poll() is not None:
                raise RuntimeError("application exited unexpectedly")
            process.send_signal(signal.SIGTERM)
            rest, _ = process.communicate(timeout=10)
            output += rest
            if process.returncode != 0:
                raise RuntimeError(f"shutdown returned {process.returncode}:\n{output.decode()}")
            print(output.decode(), end="")
            print("Installed CLI smoke test passed")
        finally:
            selector.close()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process.stdout.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    smoke(parser.parse_args().config)
