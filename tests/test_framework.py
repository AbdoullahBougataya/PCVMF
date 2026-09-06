#!/usr/bin/env python3
import multiprocessing as mp
import time
import sys
import yaml
from src.vision.process import run_vision_process
from src.main_app.process import run_main_app_process
from src.common.messages import VisionTelemetry

def test_multiprocess_ipc():
    print("=== Starting Framework Multiprocess & ZeroMQ IPC Integration Test ===")
    
    with open("config/default_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    mp.set_start_method("spawn", force=True)
    stop_event = mp.Event()

    vision_proc = mp.Process(target=run_vision_process, args=(config, stop_event), name="VisionProcTest")
    main_proc = mp.Process(target=run_main_app_process, args=(config, stop_event), name="MainProcTest")

    vision_proc.start()
    main_proc.start()

    print("Processes spawned. Running for 3.5 seconds to observe IPC telemetry flow...")
    time.sleep(3.5)

    print("Signaling processes to shutdown via stop_event...")
    stop_event.set()

    vision_proc.join(timeout=3.0)
    main_proc.join(timeout=3.0)

    assert not vision_proc.is_alive(), "Vision process failed to shut down cleanly!"
    assert not main_proc.is_alive(), "Main process failed to shut down cleanly!"

    print("=== Integration Test SUCCESSFUL: Both processes ran, exchanged IPC telemetry, and exited cleanly! ===")

if __name__ == "__main__":
    test_multiprocess_ipc()
