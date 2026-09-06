import time
import importlib
from multiprocessing.synchronize import Event
from typing import Dict, Any, Type

from src.common.logger import setup_logger
from src.common.ipc import ZMQSubscriber
from src.common.messages import VisionTelemetry, VisionStatusMessage
from src.main_app.base_controller import BaseMainController

logger = setup_logger("MainAppProcess")


def _load_controller_class(controller_name: str) -> Type[BaseMainController]:
    """Dynamically loads controller class from src.main_app.controllers."""
    try:
        module = importlib.import_module("src.main_app.controllers.sample_controller")
        controller_cls = getattr(module, controller_name)
        return controller_cls
    except Exception as e:
        logger.error(f"Failed to load controller class '{controller_name}': {e}")
        raise RuntimeError(f"Could not load controller {controller_name}") from e


def run_main_app_process(config: Dict[str, Any], stop_event: Event):
    """
    Main Application Worker Process.
    
    CRITICAL: This function runs inside the dedicated child process.
    ZeroMQ context and subscriber sockets are created strictly within this function.
    """
    logger.info("Main Application process started.")

    ipc_cfg = config.get("ipc", {})
    main_cfg = config.get("main_app", {})
    ctrl_cfg = main_cfg.get("controller", {})

    endpoint = ipc_cfg.get("endpoint", "ipc:///tmp/cv_telemetry.ipc")
    topic_telemetry = ipc_cfg.get("topics", {}).get("telemetry", "vision/telemetry")
    topic_status = ipc_cfg.get("topics", {}).get("status", "vision/status")
    loop_rate_hz = main_cfg.get("loop_rate_hz", 50)
    loop_period = 1.0 / float(loop_rate_hz)

    # 1. Initialize process-isolated ZeroMQ IPC Subscriber
    subscriber = ZMQSubscriber(
        endpoint=endpoint,
        topics=[topic_telemetry, topic_status],
        rcvhwm=ipc_cfg.get("rcvhwm", 10),
    )

    # 2. Instantiate Robotics Controller
    controller_name = ctrl_cfg.get("name", "SampleRoboticsController")
    try:
        controller_cls = _load_controller_class(controller_name)
        controller = controller_cls(ctrl_cfg)
        controller.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize controller: {e}")
        subscriber.close()
        return

    logger.info(f"Main App loop starting with controller: {controller_name} @ {loop_rate_hz} Hz")

    last_tick_time = time.time()

    # 3. Main Application Loop
    try:
        while not stop_event.is_set():
            t_now = time.time()
            dt = t_now - last_tick_time
            last_tick_time = t_now

            # Drain ZMQ IPC socket for incoming telemetry/status messages
            while True:
                msg = subscriber.receive(timeout_ms=1)
                if msg is None:
                    break

                topic, payload = msg
                try:
                    if topic == topic_telemetry:
                        telemetry = VisionTelemetry.from_json(payload)
                        controller.on_vision_telemetry(telemetry)
                    elif topic == topic_status:
                        status_msg = VisionStatusMessage.from_json(payload)
                        controller.on_vision_status(status_msg)
                except Exception as e:
                    logger.error(f"Error parsing received message on topic '{topic}': {e}")

            # Execute controller periodic logic tick
            controller.tick(dt)

            # Maintain constant control loop frequency
            t_elapsed = time.time() - t_now
            sleep_time = loop_period - t_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error(f"Unhandled exception in main app process loop: {e}", exc_info=True)
    finally:
        logger.info("Shutting down Main Application process...")
        try:
            controller.cleanup()
        except Exception:
            pass
        subscriber.close()
        logger.info("Main Application process shutdown complete.")
