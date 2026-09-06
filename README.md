# 🚀 PCVMF - Python Computer Vision Multiprocessing Framework

**PCVMF** is a modular, scalable, and high-performance Python framework boilerplate engineered specifically for **Computer Vision (CV) based Robotics, Autonomous Systems, and Multi-Sensor Platforms**.

This framework solves the classic Python concurrency bottleneck—where heavy image processing blocks high-frequency motor control loops—by isolating the **Computer Vision Pipeline** and **Main Control Application** (plus optional sensor/device workers) into **independent Python processes** communicating asynchronously over **ZeroMQ IPC (`ipc://`)**.

---

## 📋 Table of Contents
1. [Executive Architectural Overview](#-executive-architectural-overview)
2. [Key Features](#-key-features)
3. [Deep-Dive Architecture & Data Flow](#-deep-dive-architecture--data-flow)
4. [Directory Layout & File Responsibilities](#-directory-layout--file-responsibilities)
5. [Configuration Reference (`config/default_config.yaml`)](#-configuration-reference)
6. [Step-by-Step Usage Guide](#-step-by-step-usage-guide)
7. [Extending the Framework](#-extending-the-framework)
   - [1. Creating Custom Vision Pipelines](#1-creating-custom-vision-pipelines)
   - [2. Creating Custom Robotics Controllers](#2-creating-custom-robotics-controllers)
   - [3. Defining Custom IPC Message Schemas](#3-defining-custom-ipc-message-schemas)
   - [4. Scaling to Multi-Process Architectures (LiDAR, IMU, Web Dashboard)](#4-scaling-to-multi-process-architectures-lidar-imu-web-dashboard)
8. [Performance Tuning & Prioritization Guide](#-performance-tuning--prioritization-guide)
   - [Prioritizing Ultra-Low Latency](#a-prioritizing-ultra-low-latency)
   - [Prioritizing High Frame Rates (FPS)](#b-prioritizing-high-frame-rates-fps)
   - [Scaling to Multi-Node Networked Systems (TCP)](#c-scaling-to-multi-node-networked-systems-tcp)
9. [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## 🏗️ Executive Architectural Overview

```
                                  +---------------------------------------+
                                  |               main.py                 |
                                  |        (Process Orchestrator)         |
                                  +-------------------+-------------------+
                                                      |
                             +------------------------+------------------------+
                             |                                                 |
                             v                                                 v
              +------------------------------+                  +------------------------------+
              |      Vision Process          |                  |         Main Process         |
              |   (src/vision/process.py)    |                  |   (src/main_app/process.py)  |
              +------------------------------+                  +------------------------------+
              | - Camera Capture Abstraction |                  | - Robotics Control Loop /    |
              |   (Physical / Synthetic Mock)|                  |   State Machine (50Hz)       |
              | - BaseVisionPipeline Plugin  |                  | - BaseMainController Plugin  |
              | - ZeroMQ IPC Publisher       |                  | - ZeroMQ IPC Subscriber      |
              +--------------+---------------+                  +--------------^---------------+
                             |                                                 |
                             |       ZeroMQ IPC (ipc:///tmp/cv_telemetry.ipc) |
                             +-------------------------------------------------+
```

### Problem Solved: Why Not Multithreading?
Python's **Global Interpreter Lock (GIL)** prevents true parallel execution of CPU-bound threads. In robotics, running heavy vision tasks (like YOLO object detection, ArUco tracking, or color segmentation) in Python threads causes latency spikes and starves motor/PID control loops.

### Solution: Multi-Process Isolation + ZeroMQ IPC
- **True Multi-Core Execution**: Operating System schedules `VisionProcess` and `MainAppProcess` on separate physical CPU cores.
- **Zero-Lock IPC**: ZeroMQ inter-process sockets (`ipc://`) write directly to kernel memory buffers without Python GIL contention or queue locking overhead.
- **ZeroMQ Context Isolation**: Every worker process instantiates its **own private `zmq.Context()`**. ZeroMQ contexts are **never shared across process boundaries**, guaranteeing thread safety and eliminating memory race conditions.

---

## ✨ Key Features

- ⚡ **Asynchronous ZeroMQ IPC**: High-throughput Pub/Sub messaging pattern (`ipc:///tmp/cv_telemetry.ipc`).
- 📷 **Hardware Abstraction Layer (`CameraDevice`)**: Seamlessly switch between physical USB/CSI webcams, video files, or a built-in **synthetic mock frame generator** (for development without physical hardware).
- 🧩 **Plugin Architecture**: Swap vision algorithms (`BaseVisionPipeline`) or robotics controllers (`BaseMainController`) dynamically via YAML config without modifying core process loops.
- ⏱️ **Real-Time FPS & Latency Metrics**: Tracks frame processing times (ms) and actual frame rates (FPS) in published telemetry.
- 🖥️ **Optional Debug GUI Window**: Configurable live OpenCV visualization with bounding boxes and centroid overlays (`vision.show_window`).
- 🛑 **Robust Lifecycle & Signal Management**: Inter-process `multiprocessing.Event` traps `SIGINT` (Ctrl+C) and `SIGTERM`, ensuring clean process termination and ZMQ socket unbinding without zombie process leaks or stale lockfiles.

---

## 🔄 Deep-Dive Architecture & Data Flow

```
[CameraDevice / Mock]
         |
    (BGR Frame)
         v
[BaseVisionPipeline] ---> [TargetDetections]
                                 |
                          (JSON Serialized)
                                 |
                       [ZMQPublisher (PUB)]
                                 |
                     (ipc:///tmp/cv_telemetry.ipc)
                                 |
                      [ZMQSubscriber (SUB)]
                                 |
                          (Deserialized)
                                 |
                       [BaseMainController] ---> [Motor / Motion Commands]
```

1. **Frame Capture**: `CameraDevice` reads the raw BGR frame from OpenCV or synthesizes a dynamic test target frame.
2. **Inference**: `BaseVisionPipeline.process_frame()` processes the frame, extracting bounding boxes, centroid coordinates, and labels into `TargetDetection` objects.
3. **Telemetry Serialization**: The vision worker constructs a `VisionTelemetry` dataclass (containing timestamp, frame ID, FPS, latency, and detections) and serializes it to JSON.
4. **IPC Publish**: `ZMQPublisher` broadcasts the message over topic `vision/telemetry`.
5. **IPC Receive**: `ZMQSubscriber` in the Main process receives the multipart message and deserializes it.
6. **Controller Tick**: `BaseMainController.on_vision_telemetry()` updates state, and `BaseMainController.tick(dt)` executes periodic control logic (e.g. 50 Hz PID control loop).

---

## 📁 Directory Layout & File Responsibilities

```
PCVMF/
├── config/
│   └── default_config.yaml         # Central YAML configuration settings
├── src/
│   ├── common/
│   │   ├── ipc.py                  # ZMQPublisher & ZMQSubscriber process-isolated classes
│   │   ├── messages.py             # Telemetry, Detection, & Status message schemas
│   │   └── logger.py               # Multiprocess-aware logging formatter
│   ├── vision/
│   │   ├── base_pipeline.py        # Abstract interface for CV algorithms (BaseVisionPipeline)
│   │   ├── camera.py               # Camera capture module (Physical camera & Synthetic mock)
│   │   ├── process.py              # Vision worker process main loop & ZMQ Publisher
│   │   └── pipelines/
│   │       ├── __init__.py
│   │       └── sample_pipeline.py  # Sample green blob tracker implementation
│   └── main_app/
│       ├── base_controller.py      # Abstract interface for control logic (BaseMainController)
│       ├── process.py              # Main app worker process main loop & ZMQ Subscriber
│       └── controllers/
│           ├── __init__.py
│           └── sample_controller.py# Sample robotics controller implementation
├── tests/
│   └── test_framework.py           # Automated multiprocess integration test
├── main.py                         # Framework CLI & top-level process orchestrator
├── requirements.txt                # Python dependencies
└── README.md                       # Framework documentation
```

### Module Responsibilities:
- **`main.py`**: Loads config, sets spawn start method, creates `multiprocessing.Event()`, launches worker processes, handles shutdown signals (`SIGINT`/`SIGTERM`), and monitors process health.
- **`src/common/ipc.py`**: Encapsulates PyZMQ socket management. Creates a process-private `zmq.Context()` on initialization.
- **`src/common/messages.py`**: Dataclass definitions for structured messaging (`VisionTelemetry`, `TargetDetection`, `VisionStatusMessage`).
- **`src/vision/process.py`**: Executes the high-frequency camera capture and CV processing loop in a child process.
- **`src/main_app/process.py`**: Executes the main robotics control loop at a fixed frequency (`loop_rate_hz`) in a child process.

---

## ⚙️ Configuration Reference

All PCVMF parameters are controlled via `config/default_config.yaml`:

```yaml
# ZeroMQ IPC Network Settings
ipc:
  endpoint: "ipc:///tmp/cv_telemetry.ipc"  # Linux IPC socket path
  topics:
    telemetry: "vision/telemetry"           # Main detection telemetry topic
    detections: "vision/detections"          # Secondary detection topic
    status: "vision/status"                # System pipeline status topic
  sndhwm: 10                                # Send High Water Mark (prevents queue buildup)
  rcvhwm: 10                                # Receive High Water Mark

# Computer Vision Process Settings
vision:
  camera:
    source: "mock"        # "mock" for synthetic test generator, 0 for webcam, or "video.mp4"
    width: 640            # Frame capture width
    height: 480           # Frame capture height
    fps: 30               # Target camera frame rate
  
  pipeline:
    name: "SampleColorTrackerPipeline" # Class name inside src/vision/pipelines/
    target_color: "green"
    min_area: 500         # Minimum area threshold for detection
    
  target_fps: 30          # Desired CV loop rate
  show_window: false      # true = display live OpenCV GUI debug window; false = headless mode

# Main Application / Robotics Controller Settings
main_app:
  controller:
    name: "SampleRoboticsController"   # Class name inside src/main_app/controllers/
  
  loop_rate_hz: 50        # Control loop frequency in Hz (e.g. 50Hz = 20ms tick)

# Logging Settings
logging:
  level: "INFO"           # DEBUG, INFO, WARNING, ERROR
  format: "[%(asctime)s] [%(levelname)s] [%(processName)s] %(message)s"
```

---

## 🚀 Step-by-Step Usage Guide

### 1. Installation
Install requirements:
```bash
pip install -r requirements.txt
```

### 2. Basic Execution
Run the main orchestrator script:
```bash
python main.py
```
Outputs from both processes will be logged to stdout:
```text
[11:47:08.901] [INFO] [MainAppProcess] CV Telemetry | Frame: #53 | FPS: 27.5 | Latency: 35.5ms | Target: green_target at (386, 130) | Offset Error: dx=+66, dy=-110
```

### 3. Custom Configuration File
Specify a custom YAML config file using `--config`:
```bash
python main.py --config config/my_robot_config.yaml
```

### 4. Stopping the Framework
Press `Ctrl+C`. The orchestrator catches `SIGINT`, sets `stop_event`, cleanly closes ZeroMQ sockets, releases camera resources, and joins all processes.

---

## 🛠️ Extending the Framework

### 1. Creating Custom Vision Pipelines

To add a new vision model (e.g., YOLO object detector, ArUco marker tracker, or OpenCV optical flow):

1. Create a new Python file in `src/vision/pipelines/` (e.g., `aruco_pipeline.py`).
2. Subclass `BaseVisionPipeline` and implement `initialize()`, `process_frame()`, and `cleanup()`:

```python
# src/vision/pipelines/aruco_pipeline.py
import cv2
import numpy as np
from typing import List, Tuple, Dict, Any
from src.vision.base_pipeline import BaseVisionPipeline
from src.common.messages import TargetDetection

class ArucoMarkerPipeline(BaseVisionPipeline):
    def initialize(self) -> bool:
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.parameters = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, self.parameters)
        return True

    def process_frame(self, frame: np.ndarray, frame_id: int) -> Tuple[List[TargetDetection], str]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        
        detections = []
        if ids is not None:
            for marker_id, corner in zip(ids.flatten(), corners):
                pts = corner[0]
                cx = int(np.mean(pts[:, 0]))
                cy = int(np.mean(pts[:, 1]))
                x, y, w, h = cv2.boundingRect(pts.astype(np.int32))
                
                detections.append(TargetDetection(
                    label=f"aruco_id_{marker_id}",
                    confidence=1.0,
                    bbox=[int(x), int(y), int(w), int(h)],
                    centroid=[cx, cy],
                    extra_attributes={"marker_id": int(marker_id)}
                ))
        
        status = "OK" if len(detections) > 0 else "NO_MARKERS"
        return detections, status

    def cleanup(self):
        pass
```

3. Update `config/default_config.yaml`:
```yaml
vision:
  pipeline:
    name: "ArucoMarkerPipeline"
```

---

### 2. Creating Custom Robotics Controllers

To add custom motor control logic, state machines, or ROS bridge nodes:

1. Create a new Python file in `src/main_app/controllers/` (e.g., `diff_drive_controller.py`).
2. Subclass `BaseMainController` and implement `initialize()`, `on_vision_telemetry()`, `tick()`, and `cleanup()`:

```python
# src/main_app/controllers/diff_drive_controller.py
from typing import Dict, Any
from src.main_app.base_controller import BaseMainController
from src.common.messages import VisionTelemetry, VisionStatusMessage
from src.common.logger import setup_logger

logger = setup_logger("DiffDriveController")

class DifferentialDriveController(BaseMainController):
    def initialize(self) -> bool:
        self.kp = 0.5
        self.latest_telemetry = None
        logger.info("DifferentialDriveController initialized.")
        return True

    def on_vision_telemetry(self, telemetry: VisionTelemetry):
        self.latest_telemetry = telemetry

    def on_vision_status(self, status_msg: VisionStatusMessage):
        pass

    def tick(self, dt: float):
        if self.latest_telemetry is None or not self.latest_telemetry.detections:
            self.send_motor_command(0.0, 0.0)
            return

        target = self.latest_telemetry.detections[0]
        cx, _ = target.centroid
        error_x = cx - 320  # Frame center at 320px
        
        angular_vel = -self.kp * (error_x / 320.0)
        linear_vel = 0.5  # m/s
        
        self.send_motor_command(linear_vel, angular_vel)

    def send_motor_command(self, v: float, w: float):
        logger.info(f"Robot Command -> Linear: {v:.2f} m/s | Angular: {w:.2f} rad/s")

    def cleanup(self):
        self.send_motor_command(0.0, 0.0)
```

3. Update `config/default_config.yaml`:
```yaml
main_app:
  controller:
    name: "DifferentialDriveController"
```

---

### 3. Defining Custom IPC Message Schemas

If your project requires sending raw depth maps, 3D point clouds, or pose vectors, add custom dataclasses to `src/common/messages.py`:

```python
@dataclass
class Pose3DMessage:
    timestamp: float
    x: float
    y: float
    z: float
    roll: float
    pitch: float
    yaw: float

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str) -> "Pose3DMessage":
        return cls(**json.loads(json_str))
```

---

### 4. Scaling to Multi-Process Architectures (LiDAR, IMU, Web Dashboard)

PCVMF is designed to scale beyond two processes. In complex robotics systems, you may have multiple hardware devices or background tasks running concurrently:
- **`VisionProcess`**: Camera acquisition and vision processing.
- **`LidarProcess`**: LiDAR point-cloud obstacle scanning (3D/2D).
- **`IMUSensorProcess`**: 9-DOF IMU accelerometer/gyroscope readings (100Hz+).
- **`MainAppProcess`**: Sensor fusion state machine and motor control loop.
- **`WebDashboardProcess`**: Real-time telemetry monitoring server (e.g. WebSocket/Flask).

#### Multi-Process Architecture Diagram

```
                             +----------------------------------------+
                             |                main.py                 |
                             |         (Process Orchestrator)         |
                             +-------------------+--------------------+
                                                 |
         +-------------------+-------------------+-------------------+-------------------+
         |                   |                   |                   |                   |
         v                   v                   v                   v                   v
+-----------------+ +-----------------+ +-----------------+ +-----------------+ +------------------+
| Vision Process  | |  Lidar Process  | |   IMU Process   | |   Main Process  | | Web Dashboard    |
| (ZMQ Pub: CV)   | | (ZMQ Pub: Lidar)| | (ZMQ Pub: IMU)  | | (ZMQ Sub: All)  | | (ZMQ Sub: Telem) |
+--------+--------+ +--------+--------+ +--------+--------+ +--------^--------+ +--------^---------+
         |                   |                   |                   |                   |
         +-------------------+---------+---------+-------------------+-------------------+
                                       |
                   ZeroMQ IPC Bus (ipc:///tmp/pcvmf_bus.ipc)
                   Topics: "vision/telemetry", "lidar/scan", "imu/data"
```

#### Step-by-Step Guide to Adding a New Process (e.g. `LidarProcess`):

1. **Create the Worker Script (`src/sensors/lidar_process.py`)**:
   ```python
   # src/sensors/lidar_process.py
   import time
   from multiprocessing.synchronize import Event
   from typing import Dict, Any
   from src.common.ipc import ZMQPublisher
   from src.common.logger import setup_logger

   logger = setup_logger("LidarProcess")

   def run_lidar_process(config: Dict[str, Any], stop_event: Event):
       endpoint = config.get("ipc", {}).get("endpoint", "ipc:///tmp/cv_telemetry.ipc")
       publisher = ZMQPublisher(endpoint=endpoint)
       logger.info("LiDAR Process started.")

       try:
           while not stop_event.is_set():
               # Read LiDAR hardware sensor data...
               scan_payload = '{"timestamp": %f, "min_distance_m": 0.45}' % time.time()
               publisher.publish("lidar/scan", scan_payload)
               time.sleep(0.05)  # 20 Hz scan rate
       finally:
           publisher.close()
           logger.info("LiDAR Process shut down.")
   ```

2. **Subscribe to the New Topic in Main Controller (`src/main_app/process.py`)**:
   Pass the new topic `"lidar/scan"` into `ZMQSubscriber`:
   ```python
   subscriber = ZMQSubscriber(
       endpoint=endpoint,
       topics=["vision/telemetry", "vision/status", "lidar/scan"],
   )
   ```

3. **Register the New Process in `main.py`**:
   ```python
   # In main.py
   from src.sensors.lidar_process import run_lidar_process

   # Instantiate additional process
   lidar_process = mp.Process(
       target=run_lidar_process,
       args=(config, stop_event),
       name="LidarProcess",
   )

   # Start process
   lidar_process.start()

   # Include in graceful shutdown loop
   for proc in [vision_process, main_app_process, lidar_process]:
       proc.join(timeout=3.0)
       if proc.is_alive():
           proc.terminate()
   ```

---

## ⚡ Performance Tuning & Prioritization Guide

### A. Prioritizing Ultra-Low Latency
If your robot requires sub-10ms response times (e.g., high-speed drone tracking or reactive obstacle avoidance):

1. **Disable Debug GUI Window**: Set `vision.show_window: false` in `default_config.yaml` to avoid OpenCV GUI render delays.
2. **Reduce High Water Marks**: Set `sndhwm: 2` and `rcvhwm: 2` in `config/default_config.yaml` to discard stale visual frames immediately if processing slows.
3. **Downscale Resolution**: Use lower resolution frames in `vision.camera` (`320x240` or `640x480`).
4. **Use MsgPack or Protocol Buffers**: For large payloads, replace JSON serialization in `messages.py` with `msgpack` or PyArrow.

---

### B. Prioritizing High Frame Rates (FPS)
If your application uses heavy deep learning models (YOLO / TensorRT):

1. **Inference Threading**: Run GPU inference asynchronously inside `process_frame()`.
2. **Decouple Camera Read**: `CameraDevice` can be expanded with an internal frame buffer thread so OpenCV frame capture never waits for model inference.
3. **Adjust Target Loop Rate**: Increase `vision.target_fps` to `60` or `120` when using high-speed global shutter cameras.

---

### C. Scaling to Multi-Node Networked Systems (TCP)
To separate the vision computer (e.g. NVIDIA Jetson mounted on a drone) from the ground control station or central robot controller:

Change the ZeroMQ endpoint protocol in `config/default_config.yaml` from `ipc://` to `tcp://`:
```yaml
ipc:
  # Bind on all interfaces on Jetson compute node (Port 5555)
  endpoint: "tcp://0.0.0.0:5555"
```
On the receiving ground control node, set subscriber endpoint to the Jetson IP:
```yaml
ipc:
  endpoint: "tcp://192.168.1.100:5555"
```

---

## ❓ Troubleshooting & FAQs

### Q1: "Address already in use" or ZMQ bind errors on startup
**Cause**: A previous crashed process left a stale socket file `/tmp/cv_telemetry.ipc`.  
**Solution**: PCVMF automatically removes stale socket files in `ZMQPublisher.__init__`. If needed, manually remove the file: `rm /tmp/cv_telemetry.ipc`.

---

### Q2: "Can't touch ZMQ context created in parent process" exception
**Cause**: Instantiating `zmq.Context()` in `main.py` before spawning child processes.  
**Solution**: Always instantiate `ZMQPublisher` and `ZMQSubscriber` inside the process target function (`run_vision_process` / `run_main_app_process`).

---

### Q3: OpenCV camera fails to open (`/dev/video0`)
**Cause**: Linux user permission issue for camera devices.  
**Solution**: Add your Linux user to the `video` group:
```bash
sudo usermod -aG video $USER
```
Then log out and log back in.

---

## 📜 License & Citation

PCVMF (Python Computer Vision Multiprocessing Framework) is designed for scalable robotics research, autonomous systems, and computer vision engineering.
