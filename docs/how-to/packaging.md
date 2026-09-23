# Build and run a distributable application

[Documentation home](../README.md) · [How-to guides](README.md)

Use this guide to verify that an application works without importing from a development checkout. You need `uv`; Docker steps additionally require an available Docker daemon.

## Build and install the framework wheel

Run the following commands from the repository root in one shell. A fresh temporary directory keeps old build artifacts out of the wheel selection:

```bash
pcvmf_check_dir="$(mktemp -d)"
uv build --out-dir "$pcvmf_check_dir/dist"
uv venv "$pcvmf_check_dir/venv"
uv pip install --python "$pcvmf_check_dir/venv/bin/python" -r requirements.txt "$pcvmf_check_dir"/dist/*.whl
```

Keep this shell open for the checks below; they use `pcvmf_check_dir`. `requirements.txt` contains locked runtime dependencies, not an editable installation of PCVMF. The wheel provides the framework and packaged demo configuration.

Verify that it runs from outside the checkout:

```bash
"$pcvmf_check_dir/venv/bin/python" scripts/smoke.py
```

Expected result: readiness logs, successful SIGTERM shutdown, and `Installed CLI smoke test passed`. The script launches its child from a temporary working directory and removes `PYTHONPATH` from that child's environment.

## Install and verify application plugins

```bash
uv pip install --python "$pcvmf_check_dir/venv/bin/python" --no-deps ./examples/external_plugins
"$pcvmf_check_dir/venv/bin/python" scripts/smoke.py --config examples/vision.yaml
"$pcvmf_check_dir/venv/bin/python" scripts/smoke.py --config examples/sensor.yaml
```

For your application, replace the example package and YAML with your own. A deployed plugin package should declare its PCVMF and model/runtime dependencies. `--no-deps` is appropriate here because the example needs only the already installed framework.

Use an editable installation during development, and a built/installed package when checking distribution behavior. Do not depend on a manually modified `sys.path` or on running from a particular source directory.

## Build and smoke-test the container

```bash
docker build -t pcvmf:local .
docker run --rm pcvmf:local python /opt/pcvmf-smoke.py
docker run --rm pcvmf:local
```

The Dockerfile installs a wheel into a virtual environment, includes required OpenCV runtime libraries, and runs the headless CLI as a non-root user. It does not require an editable source checkout at runtime. Use a separate terminal to stop a long-running container with `docker stop CONTAINER`, or run it interactively if appropriate for your workflow.

For custom plugins, create a derived image that installs their package and copies or mounts a configuration file, then launch `pcvmf run --config /path/in/container.yaml`. Ensure any device or file paths refer to resources actually accessible inside the container. GUI display and hardware access require additional environment-specific setup; they are not exercised by the headless smoke test.

## Keep dependency artifacts consistent

After changing framework dependencies:

```bash
uv lock
uv export --frozen --format requirements-txt --no-hashes --no-dev --no-emit-project -o requirements.txt
uv sync --frozen --extra dev
```

Then rerun tests and rebuild the wheel. The GitHub and GitLab workflows define Python 3.10–3.12 tests, clean wheel/example smoke checks, and Docker checks. A configured CI job is not proof it has run; inspect its results for your revision. The release publishing workflow is separate from these checks.
