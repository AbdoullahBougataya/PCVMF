import time
import importlib
import cv2
from multiprocessing.synchronize import Event
from typing import Dict, Any, Type

from src.common.logger import setup_logger
from src.common.ipc import ZMQPublisher
from src.common.messages import VisionTelemetry, VisionStatusMessage
from src.vision.camera import CameraDevice
from src.vision.base_pipeline import BaseVisionPipeline

logger = setup_logger("VisionProcess")


def _load_pipeline_class(pipeline_name: str) -> Type[BaseVisionPipeline]:
    """Dynamically loads pipeline class from src.vision.pipelines."""
    try:
        module = importlib.import_module("src.vision.pipelines.sample_pipeline")
        pipeline_cls = getattr(module, pipeline_name)
        return pipeline_cls
    except Exception as e:
        logger.error(f"Failed to load vision pipeline class '{pipeline_name}': {e}")
        raise RuntimeError(f"Could not load pipeline {pipeline_name}") from e


def run_vision_process(config: Dict[str, Any], stop_event: Event):
    """
    Computer Vision Worker Process.
    
    CRITICAL: This function runs inside the dedicated child process.
    ZeroMQ context and publisher sockets are created strictly within this function.
    """
    logger.info("Computer Vision process started.")

    ipc_cfg = config.get("ipc", {})
    vision_cfg = config.get("vision", {})
    cam_cfg = vision_cfg.get("camera", {})
    pipe_cfg = vision_cfg.get("pipeline", {})

    endpoint = ipc_cfg.get("endpoint", "ipc:///tmp/cv_telemetry.ipc")
    topic_telemetry = ipc_cfg.get("topics", {}).get("telemetry", "vision/telemetry")
    topic_status = ipc_cfg.get("topics", {}).get("status", "vision/status")
    show_window = vision_cfg.get("show_window", False)

    # 1. Initialize process-isolated ZeroMQ IPC Publisher
    publisher = ZMQPublisher(endpoint=endpoint, sndhwm=ipc_cfg.get("sndhwm", 10))

    # 2. Initialize Camera device
    camera = CameraDevice(
        source=cam_cfg.get("source", "mock"),
        width=cam_cfg.get("width", 640),
        height=cam_cfg.get("height", 480),
        target_fps=cam_cfg.get("fps", 30),
    )

    if not camera.open():
        logger.error("Camera initialization failed. Exiting vision process.")
        publisher.publish(topic_status, VisionStatusMessage(time.time(), "ERROR", "Camera open failed").to_json())
        publisher.close()
        return

    # 3. Instantiate CV Pipeline
    pipeline_name = pipe_cfg.get("name", "SampleColorTrackerPipeline")
    try:
        pipeline_cls = _load_pipeline_class(pipeline_name)
        pipeline = pipeline_cls(pipe_cfg)
        pipeline.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize vision pipeline: {e}")
        publisher.close()
        camera.release()
        return

    logger.info(f"Vision process loop starting with pipeline: {pipeline_name} (show_window={show_window})")
    publisher.publish(topic_status, VisionStatusMessage(time.time(), "RUNNING", f"Pipeline {pipeline_name} active").to_json())

    frame_id = 0
    fps_counter = 0
    fps_start_time = time.time()
    current_fps = 0.0

    # 4. Main Vision Loop
    try:
        while not stop_event.is_set():
            t_start = time.time()

            ret, frame = camera.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            frame_id += 1
            fps_counter += 1

            # Process frame using pipeline
            detections, status = pipeline.process_frame(frame, frame_id)

            t_end = time.time()
            proc_time_ms = (t_end - t_start) * 1000.0

            # Calculate actual frame rate every 30 frames
            if time.time() - fps_start_time >= 1.0:
                current_fps = fps_counter / (time.time() - fps_start_time)
                fps_counter = 0
                fps_start_time = time.time()

            # Optional OpenCV GUI Debug Window
            if show_window:
                debug_frame = frame.copy()
                for det in detections:
                    x, y, w, h = det.bbox
                    cx, cy = det.centroid
                    cv2.rectangle(debug_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.circle(debug_frame, (cx, cy), 4, (0, 0, 255), -1)
                    cv2.putText(
                        debug_frame,
                        f"{det.label} ({det.confidence:.2f})",
                        (x, max(y - 5, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        1,
                    )
                cv2.imshow("Computer Vision Pipeline Debug Window", debug_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord("q"):  # Press ESC or 'q' to stop
                    logger.info("GUI window closed by user request (ESC/q key).")
                    stop_event.set()
                    break

            # Construct telemetry message
            telemetry = VisionTelemetry(
                timestamp=t_end,
                frame_id=frame_id,
                fps=round(current_fps, 1),
                processing_time_ms=round(proc_time_ms, 2),
                detections=detections,
                status=status,
            )

            # Publish message over ZeroMQ IPC
            publisher.publish(topic_telemetry, telemetry.to_json())

    except Exception as e:
        logger.error(f"Unhandled exception in vision process loop: {e}", exc_info=True)
    finally:
        logger.info("Shutting down Vision process...")
        if show_window:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        try:
            pipeline.cleanup()
        except Exception:
            pass
        camera.release()
        publisher.close()
        logger.info("Vision process shutdown complete.")

