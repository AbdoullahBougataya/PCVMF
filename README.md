# Python Computer Vision Multiprocessing Framework

A production-grade, highly scalable Python boilerplate framework designed for computer vision (CV) projects. This framework decouples heavy video ingestion and AI model inference from application business logic into isolated, concurrent processes using Python's `multiprocessing` library.

---

## 💡 Why Multiprocessing in Python Computer Vision?

Python's Global Interpreter Lock (GIL) prevents multiple native threads from executing Python bytecode simultaneously on separate CPU cores. In real-time computer vision applications:
- Running video frame capture, deep learning inference (PyTorch/OpenCV/YOLO), business logic, database operations, and network APIs in a single thread causes **frame stuttering, high latency, and dropped video streams**.
- Using `threading` still suffers from GIL contention during CPU-heavy pre-processing and post-processing.
- **This Framework Solution**: Uses true multi-process execution (`multiprocessing`), bypassing the GIL completely. One process runs the CV pipeline on dedicated CPU/GPU compute, while a second process handles business logic, logging, database writes, and external communications without interfering with video processing.

---

## 🏛️ Architecture & Component Overview

```
                        ┌───────────────────────────────────────────────┐
                        │                 main.py                       │
                        │        (Process Manager / Orchestrator)       │
                        └───────────────────────┬───────────────────────┘
                                                │
                       ┌────────────────────────┴───────────────────────┐
                       │                                                │
         ┌─────────────▼──────────────┐                   ┌─────────────▼──────────────┐
         │     CV Pipeline Process    │                   │      Main Task Process     │
         │ (BaseVisionPipeline Worker)│                   │   (BaseMainTask Worker)    │
         └─────────────┬──────────────┘                   └─────────────▲──────────────┘
                       │                                                │
                       │             IPC Queue (DataPacket)             │
                       └────────────────────────────────────────────────┘
```

1. **CV Pipeline Process (`BaseVisionPipeline`)**:
   - Handles frame acquisition (Webcams, RTSP streams, Video files, or Synthetic generators).
   - Performs frame resizing, color transformations, and AI inference (OpenCV, PyTorch, MediaPipe, YOLO, TensorRT).
   - Packages detection metadata, performance metrics, and optional processed frames into `DataPacket`s.
   - Pushes packets into an IPC queue channel with backpressure control and frame-dropping metrics.

2. **Main Task Process (`BaseMainTask`)**:
   - Continuously receives and dequeues `DataPacket`s.
   - Executes domain-specific business rules (hardware actuation, webhooks, database writes, alert notifications).
   - Configurable processing rate (`--main-hz`) and logging frequency (`--log-every`).
   - Tracks metrics (packets processed, latency in ms, objects detected, queue depth).

3. **Orchestrator (`ProcessManager`)**:
   - Handles process creation (`spawn` start method for CUDA & OpenCV safety).
   - Traps operating system termination signals (`SIGINT`, `SIGTERM`).
   - Controls graceful shutdowns, ensuring no orphaned zombie processes or corrupted IPC queues remain.

---

## ⚡ Key Features

- **GIL Bypass**: Full multi-core CPU/GPU utilization via `multiprocessing.Process`.
- **Non-blocking IPC Queue**: Custom `IPCChannel` queue wrapper preventing process locks.
- **Configurable Backpressure & Frame-Dropping**: Automatically drops oldest frames when processing falls behind to maintain low real-time latency.
- **Target Rate Limiting**: Independent target FPS for CV Pipeline and target Hz for Main Task.
- **Process-Aware Logging**: Custom `FlushStreamHandler` ensuring real-time terminal output across un-pickled multiprocessing child boundaries.
- **Graceful Emergency Teardown**: Intercepts `Ctrl+C` and system kill signals to release hardware resources safely.
- **Modular Abstract Base Classes**: Standardized interfaces (`abc.ABC`) allowing effortless swapping of vision models or main logic.

---

## 📁 Repository Structure & Module Responsibilities

```text
framework/
├── config.py                 # Centralized configuration dataclasses (AppConfig, CVPipelineConfig, MainTaskConfig, IPCConfig)
├── main.py                   # Main application entry point with CLI parser and orchestrator setup
├── requirements.txt          # Minimal framework dependencies (numpy, opencv-python, pytest)
├── README.md                 # Framework documentation and user guide
│
├── core/                     # Core Framework Engine
│   ├── __init__.py
│   ├── base_pipeline.py      # Abstract Base Class for CV Pipeline worker
│   ├── base_main_task.py     # Abstract Base Class for Main Task worker
│   ├── ipc.py                # DataPacket dataclass and IPCChannel queue manager
│   ├── process_manager.py    # Process lifecycle management & signal handling
│   └── logger.py             # Process-aware real-time logging with stdout flushing
│
├── cv_pipeline/             # Computer Vision Pipeline Implementations
│   ├── __init__.py
│   └── dummy_cv_pipeline.py  # Sample CV pipeline with synthetic & OpenCV camera capture
│
├── main_task/                # Main Application Task Implementations
│   ├── __init__.py
│   └── sample_main_task.py   # Sample main task consuming vision results & metrics
│
└── tests/                    # Automated Test Suite
    ├── __init__.py
    ├── test_ipc.py           # Unit tests for queue IPC and packet serialization
    └── test_framework.py     # Integration tests for process lifecycle & communication
```

---

## 🚀 Quick Start Guide

### 1. Installation
Install core requirements:
```bash
pip install -r requirements.txt
```

### 2. Running the Default Application

Run with synthetic frame generation (no physical camera required):
```bash
python main.py
```

Run with camera index `0` at 30 FPS with an OpenCV live preview window:
```bash
python main.py --source 0 --fps 30 --show-preview
```

Run for a fixed duration of 10 seconds before auto-exiting:
```bash
python main.py --duration 10
```

---

## 🎛️ Complete Command Line Interface (CLI) Reference

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--source` | `str` | `"synthetic"` | Input source: `"synthetic"`, camera index (e.g. `"0"`), or video file path (`".mp4"`) |
| `--fps` | `float` | `30.0` | Target processing FPS limit for CV pipeline (`0.0` for uncapped max speed) |
| `--width` | `int` | `640` | Desired frame width resolution |
| `--height` | `int` | `480` | Desired frame height resolution |
| `--show-preview` | `flag` | `False` | Displays OpenCV `imshow` preview window in the CV process |
| `--duration` | `float` | `0.0` | Run duration in seconds before automatic graceful stop (`0.0` for infinite) |
| `--queue-size` | `int` | `50` | Maximum capacity of the IPC queue buffer |
| `--main-hz` | `float` | `0.0` | Execution rate limit for the Main Task in Hz (`0.0` for uncapped) |
| `--log-every` | `int` | `20` | Log frame details every Nth frame in the Main Task (`0` to disable) |
| `--stats-interval` | `float` | `5.0` | Interval in seconds to output summary queue statistics |

---

## 🎯 How to Tuning Framework Performance for Different Goals

Depending on your application domain, you can configure the framework to prioritize **real-time latency**, **zero frame loss**, or **resource usage**:

### Scenario 1: Prioritize Real-Time Ultra-Low Latency (Drones, Robotics, CCTV Tracking)
- **Goal**: Minimize delay between frame capture and action execution. Old frames are useless.
- **Configuration**:
  - Set `--queue-size 1` or `--queue-size 5`.
  - Ensure `drop_when_full = True` in `IPCConfig` (drops oldest queued frames).
  - Do NOT pass raw image arrays inside `DataPacket.frame` unless necessary (pass bounding box metadata only).
- **Command**:
  ```bash
  python main.py --source 0 --queue-size 2 --fps 30
  ```

### Scenario 2: Prioritize Zero Frame Loss (Video Analytics, Security Footage Archiving)
- **Goal**: Process every single frame without skipping, even if processing slows down.
- **Configuration**:
  - Set `drop_when_full = False` in `IPCConfig`.
  - Increase queue size (`--queue-size 200`).
  - Set `--main-hz 0.0` so the main task consumes packets as fast as possible.
- **Code snippet (`config.py`)**:
  ```python
  ipc_config = IPCConfig(max_queue_size=200, drop_when_full=False)
  ```

### Scenario 3: Prioritize Low CPU / Power Consumption (Edge Devices, Raspberry Pi)
- **Goal**: Avoid overheating and conserve CPU cycles on resource-constrained hardware.
- **Configuration**:
  - Lower the CV pipeline FPS limit (`--fps 15.0`).
  - Throttle Main Task execution (`--main-hz 5.0`).
  - Increase frame log step (`--log-every 50`).
- **Command**:
  ```bash
  python main.py --fps 15 --main-hz 5 --log-every 50
  ```

### Scenario 4: Prioritize Maximum AI Inference FPS (GPU PyTorch / YOLO)
- **Goal**: Run deep learning models at maximum possible GPU frame rate.
- **Configuration**:
  - Set `--fps 0.0` (uncapped).
  - Disable preview window (`--show-preview` omitted).
  - Perform CUDA model loading in `setup()` inside the CV process.

---

## 🛠️ Step-by-Step Extension Guide

### 1. Creating a Custom Computer Vision Pipeline

Create a new file under `cv_pipeline/` (e.g., `cv_pipeline/yolo_pipeline.py`), inherit from `BaseVisionPipeline`, and implement the required abstract methods:

```python
# cv_pipeline/yolo_pipeline.py
import cv2
import time
import torch
from typing import Optional
from config import CVPipelineConfig
from core.base_pipeline import BaseVisionPipeline
from core.ipc import DataPacket

class YoloVisionPipeline(BaseVisionPipeline):
    """Custom CV Pipeline running YOLO object detection."""

    def setup(self) -> None:
        self.logger.info("Loading YOLOv8 PyTorch model...")
        # Initialize video capture hardware
        self.cap = cv2.VideoCapture(self.config.source if isinstance(self.config.source, int) else str(self.config.source))
        # Load AI model
        self.model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
        self.model.to(self.config.device)

    def process_frame(self, frame_id: int) -> Optional[DataPacket]:
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None

        # Resize if specified in config
        if self.config.width and self.config.height:
            frame = cv2.resize(frame, (self.config.width, self.config.height))

        # Run AI Inference
        results = self.model(frame)
        detections = results.pandas().xyxy[0].to_dict(orient="records")

        # Return structured DataPacket
        return DataPacket(
            frame_id=frame_id,
            timestamp=time.time(),
            data={"detections": detections, "count": len(detections)},
            frame=frame if self.config.show_preview else None,
            metadata={"device": self.config.device}
        )

    def teardown(self) -> None:
        self.logger.info("Releasing camera resources...")
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
```

---

### 2. Creating a Custom Main Application Task

Create a new file under `main_task/` (e.g., `main_task/mqtt_logger_task.py`), inherit from `BaseMainTask`, and implement the abstract methods:

```python
# main_task/mqtt_logger_task.py
from config import MainTaskConfig
from core.base_main_task import BaseMainTask
from core.ipc import DataPacket

class MQTTLoggerTask(BaseMainTask):
    """Custom Main Task publishing vision events to an MQTT Broker or Database."""

    def setup(self) -> None:
        self.logger.info("Connecting to Database / MQTT Broker...")
        # Initialize database pool, MQTT client, or hardware serial connection
        self.client = self._connect_mqtt()

    def _connect_mqtt(self):
        # Placeholder for MQTT / DB connection logic
        return None

    def handle_packet(self, packet: DataPacket) -> None:
        detections = packet.data.get("detections", [])
        count = packet.data.get("count", 0)

        # Execute custom business logic rules
        if count > 0:
            self.logger.info(f"Target Detected at Frame #{packet.frame_id}! Detections: {count}")
            # Example: Publish detection alert payload over network
            # self.client.publish("vision/alerts", str(detections))

    def teardown(self) -> None:
        self.logger.info("Closing MQTT connections...")
        # Graceful cleanup
```

---

### 3. Wiring Custom Components into `main.py`

Update `main.py` to instantiate your custom pipeline and task:

```python
# main.py
from cv_pipeline.yolo_pipeline import YoloVisionPipeline
from main_task.mqtt_logger_task import MQTTLoggerTask

def main():
    config = AppConfig(...)
    
    # Instantiate custom components
    cv_pipeline = YoloVisionPipeline(config.cv_config)
    main_task = MQTTLoggerTask(config.main_config)

    # Launch process manager
    manager = ProcessManager(config, cv_pipeline, main_task)
    manager.run_until_complete()
```

---

## 🧪 Running the Test Suite

The project includes unit tests for the IPC channel and integration tests for process spawning.

To run tests:
```bash
pytest tests/ -v
```

Expected output:
```text
============================= test session starts ==============================
collected 5 items

tests/test_framework.py::test_full_framework_multiprocessing_run PASSED  [ 20%]
tests/test_ipc.py::test_data_packet_creation PASSED                      [ 40%]
tests/test_ipc.py::test_ipc_channel_send_receive PASSED                  [ 60%]
tests/test_ipc.py::test_ipc_channel_drop_when_full PASSED                [ 80%]
tests/test_ipc.py::test_ipc_channel_timeout PASSED                       [100%]

============================== 5 passed in 2.05s ===============================
```
