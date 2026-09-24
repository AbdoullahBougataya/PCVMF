"""Embeddable fail-fast application supervision. Signals are a CLI concern."""

import logging
import multiprocessing as mp
import tempfile
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .api import Worker, WorkerContext
from .messages import CodecRegistry
from .plugins import instantiate
from .recording import McapLogHandler, McapRecorder, RecordingClient
from .runners import cleanup_all
from .transport import ZMQPublisher, ZMQSubscriber

logger = logging.getLogger(__name__)


def configure_logging(config):
    logging.basicConfig(
        level=config.get("level", "INFO"),
        format=config.get(
            "format",
            "%(asctime)s %(levelname)s [%(processName)s] %(name)s: %(message)s",
        ),
        force=True,
    )


def _worker_main(spec, config, endpoints, stop, start, channel, recording_endpoint=None):
    configure_logging(config.logging)
    worker = None
    publisher = None
    subscriber = None
    recorder = None
    log_handler = None
    failed = False
    try:
        if recording_endpoint is not None:
            recorder = RecordingClient(
                recording_endpoint, spec.name, config.logging["mcap"]["queue_size"], spec.startup_timeout
            )
            log_handler = McapLogHandler(recorder, spec.name, config.logging.get("level", "INFO"))
            logging.getLogger().addHandler(log_handler)
        registry = CodecRegistry(config.codecs)
        if spec.publications:
            publisher = ZMQPublisher(
                endpoints[spec.name], spec.name, spec.publications, registry, config.hwm, recorder=recorder
            )
            channel.send({"kind": "resources", "owned": publisher.owned_paths()})
        if spec.subscriptions:
            subscriber = ZMQSubscriber(spec.subscriptions, endpoints, registry, config.hwm)
        worker = instantiate(spec.plugin, Worker)
        worker.initialize(WorkerContext(spec.name, spec.rate_hz, publisher, subscriber))
        channel.send({"kind": "ready"})
        while not start.is_set() and not stop.wait(0.05):
            pass
        period = 1 / spec.rate_hz
        deadline = time.monotonic()
        last_heartbeat = deadline
        last_warning = float("-inf")
        while not stop.is_set():
            if recorder is not None:
                recorder.check()
            if worker.step() is False:
                channel.send({"kind": "complete"})
                break
            now = time.monotonic()
            if now - last_heartbeat >= min(0.25, spec.progress_timeout / 3):
                channel.send({"kind": "heartbeat"})
                last_heartbeat = now
            deadline += period
            delay = deadline - now
            if delay < 0:
                if now - last_warning >= 1:
                    logger.warning(
                        "Worker %s missed scheduling deadline by %.3fs",
                        spec.name,
                        -delay,
                    )
                    last_warning = now
                deadline = now
            else:
                stop.wait(delay)
    except KeyboardInterrupt:
        # Terminal Ctrl+C reaches the whole foreground process group. The CLI
        # signals the shared event; no child signal handler is installed.
        if not stop.wait(0.5):
            failed = True
            channel.send({"kind": "failure", "error": "unexpected KeyboardInterrupt"})
    except BaseException as exc:
        failed = True
        logger.exception("Worker %s failed", spec.name)
        channel.send({"kind": "failure", "error": str(exc), "traceback": traceback.format_exc()})
    finally:
        callbacks = []
        if worker is not None:
            callbacks.append(worker.cleanup)
        if subscriber is not None:
            callbacks.append(subscriber.close)
        if publisher is not None:
            callbacks.append(publisher.close)
        try:
            cleanup_all(callbacks)
        except BaseException as exc:
            failed = True
            logger.exception("Worker %s cleanup failed", spec.name)
            channel.send({"kind": "failure", "error": str(exc)})
        if log_handler is not None:
            logging.getLogger().removeHandler(log_handler)
            log_handler.close()
        if recorder is not None:
            try:
                recorder.flush(spec.shutdown_timeout)
            except BaseException as exc:
                failed = True
                channel.send({"kind": "failure", "error": str(exc)})
            finally:
                recorder.close()
        channel.send({"kind": "exited", "ok": not failed})
        channel.close()
    if failed:
        raise SystemExit(1)


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    errors: tuple[str, ...]
    ready: bool
    recording_path: str | None = None


class Application:
    def __init__(self, config, *, on_event: Callable[[str, dict], None] | None = None):
        self.config = config
        self.on_event = on_event
        self.context = mp.get_context("spawn")
        self.stop = self.context.Event()
        self.start = self.context.Event()
        self._ran = False
        self._stop_requested = False

    def request_stop(self):
        # A signal may interrupt Event.wait() while its non-reentrant lock is
        # held. Defer touching multiprocessing synchronization to the run loop.
        self._stop_requested = True

    def run(self) -> RunResult:
        if self._ran:
            raise RuntimeError("Application instances are single-use")
        self._ran = True
        errors = []
        states = {}
        ready = False
        recorder = None
        log_handler = None
        recording_path = None
        recording_failed = False

        def error(name, message):
            detail = f"{name}: {message}"
            errors.append(detail)
            logger.error(detail)
            self.stop.set()

        def receive(name, state):
            if state["closed"]:
                return
            while state["channel"].poll():
                try:
                    event = state["channel"].recv()
                except EOFError:
                    state["closed"] = True
                    break
                if self.on_event:
                    self.on_event(name, event)
                kind = event["kind"]
                if kind == "resources":
                    state["owned"] = event["owned"]
                elif kind == "ready":
                    state["ready"] = True
                    logger.info("Worker %s ready", name)
                elif kind == "failure":
                    error(name, event["error"])
                elif kind == "complete":
                    self.stop.set()
                elif kind == "exited":
                    state["exited"] = True
                    if not event["ok"]:
                        error(name, "unsuccessful cleanup or execution")
                state["last_progress"] = time.monotonic()

        def poll_recording():
            nonlocal recording_failed
            if recorder is not None:
                try:
                    recorder.poll()
                except Exception as exc:
                    recorder._failed(exc)
                if recorder.error and not recording_failed:
                    recording_failed = True
                    error("recorder", recorder.error)

        with tempfile.TemporaryDirectory(prefix="pcvmf-", dir="/tmp") as directory:
            endpoints = {
                w.name: w.endpoint or f"ipc://{directory}/{w.name}.ipc" for w in self.config.workers if w.publications
            }
            try:
                recording_endpoint = None
                if "mcap" in self.config.logging:
                    recording_endpoint = f"ipc://{directory}/.recording.ipc"
                    recorder = McapRecorder(self.config.logging["mcap"], recording_endpoint)
                    recording_path = recorder.path
                    log_handler = McapLogHandler(recorder, "application", self.config.logging.get("level", "INFO"))
                    owner_thread = threading.get_ident()
                    log_handler.addFilter(lambda record: record.thread == owner_thread)
                    logging.getLogger().addHandler(log_handler)
                    logger.info("MCAP recording: %s", recording_path)
                logger.debug("Effective configuration: %s", asdict(self.config))
                for spec in self.config.workers:
                    parent, child = self.context.Pipe(duplex=False)
                    process = self.context.Process(
                        target=_worker_main,
                        name=spec.name,
                        args=(
                            spec,
                            self.config,
                            endpoints,
                            self.stop,
                            self.start,
                            child,
                            recording_endpoint,
                        ),
                    )
                    state = {
                        "spec": spec,
                        "process": process,
                        "channel": parent,
                        "ready": False,
                        "exited": False,
                        "closed": False,
                        "owned": [],
                        "started": time.monotonic(),
                        "last_progress": time.monotonic(),
                    }
                    try:
                        process.start()
                    except BaseException:
                        parent.close()
                        raise
                    finally:
                        child.close()
                    states[spec.name] = state
                while not self.stop.is_set() and not self._stop_requested:
                    poll_recording()
                    for name, state in states.items():
                        receive(name, state)
                        if not state["process"].is_alive() and not self.stop.is_set():
                            # A final completion/error may arrive between the
                            # first poll and observing the process exit.
                            receive(name, state)
                            if not self.stop.is_set():
                                error(name, f"unexpected exit ({state['process'].exitcode})")
                        now = time.monotonic()
                        if not state["ready"] and now - state["started"] > state["spec"].startup_timeout:
                            error(name, "startup timeout")
                        elif ready and now - state["last_progress"] > state["spec"].progress_timeout:
                            error(name, "progress timeout (step may be blocked)")
                    if not ready and not self.stop.is_set() and all(s["ready"] for s in states.values()):
                        ready = True
                        now = time.monotonic()
                        for state in states.values():
                            state["last_progress"] = now
                        self.start.set()
                        logger.info("Application ready: %d workers", len(states))
                        if self.on_event:
                            self.on_event(
                                "application",
                                {"kind": "ready", "endpoints": endpoints.copy()},
                            )
                    self.stop.wait(0.02)
            except BaseException as exc:
                error("supervisor", str(exc))
            finally:
                self.stop.set()
                shutdown_started = time.monotonic()
                pending = set(states)
                while pending:
                    poll_recording()
                    for name in list(pending):
                        state = states[name]
                        # Continue draining lifecycle events while children release resources.
                        try:
                            receive(name, state)
                        except Exception as exc:
                            error(name, f"lifecycle event handler failed: {exc}")
                        proc = state["process"]
                        proc.join(timeout=0)
                        if not proc.is_alive():
                            pending.remove(name)
                            continue
                        if time.monotonic() - shutdown_started >= state["spec"].shutdown_timeout:
                            error(name, "graceful shutdown timed out; terminating")
                            proc.terminate()
                            proc.join(timeout=0.5)
                            if proc.is_alive():
                                proc.kill()
                                proc.join(timeout=0.5)
                            if proc.is_alive():
                                error(name, "could not kill worker")
                            pending.remove(name)
                    if pending:
                        time.sleep(0.01)
                for name, state in states.items():
                    try:
                        receive(name, state)
                    except Exception as exc:
                        error(name, f"lifecycle event handler failed: {exc}")
                    proc = state["process"]
                    if proc.exitcode != 0:
                        error(name, f"exit code {proc.exitcode}")
                    if not state["exited"]:
                        error(name, "worker exited without cleanup acknowledgement")
                    state["channel"].close()
                    if not proc.is_alive():
                        proc.close()
                        for path_string, identity in state["owned"]:
                            path = Path(path_string)
                            try:
                                stat = path.lstat()
                                if (stat.st_dev, stat.st_ino) == tuple(identity):
                                    path.unlink()
                            except FileNotFoundError:
                                pass
                            except OSError as exc:
                                error(name, f"endpoint cleanup failed: {exc}")
                poll_recording()
                if log_handler is not None:
                    logging.getLogger().removeHandler(log_handler)
                    log_handler.close()
                if recorder is not None:
                    recorder.close()
                    if recorder.error and not recording_failed:
                        error("recorder", recorder.error)
                # Temporary directory cleanup covers auto-allocated endpoints even after kill.
        # Completion callbacks commonly capture the Application to request a
        # stop. Break that cycle so multiprocessing semaphores are finalized
        # promptly instead of during a later resource-tracker operation.
        self.on_event = None
        return RunResult(1 if errors else 0, tuple(errors), ready, recording_path)
