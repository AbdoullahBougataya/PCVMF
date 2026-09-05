#!/usr/bin/env python3
"""Main entry point for the Python Computer Vision Multiprocessing Framework."""

import argparse
import time
import multiprocessing as mp
from config import AppConfig, CVPipelineConfig, MainTaskConfig, IPCConfig
from core.process_manager import ProcessManager
from cv_pipeline import DummyVisionPipeline
from main_task import SampleMainTask


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scalable Multiprocessing Computer Vision Framework Boilerplate"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="synthetic",
        help="Input source: 'synthetic', camera index (e.g., '0'), or video path"
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Target processing FPS limit (default: 30.0)"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=640,
        help="Frame width resolution (default: 640)"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=480,
        help="Frame height resolution (default: 480)"
    )
    parser.add_argument(
        "--show-preview",
        action="store_true",
        help="Display OpenCV live preview window in CV pipeline"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Automatically stop after N seconds (0 for indefinite run)"
    )
    parser.add_argument(
        "--queue-size",
        type=int,
        default=50,
        help="Maximum IPC queue buffer size (default: 50)"
    )
    parser.add_argument(
        "--main-hz",
        type=float,
        default=0.0,
        help="Main task processing rate limit in Hz (0.0 for uncapped)"
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=20,
        help="Log every Nth frame in main task (default: 20)"
    )
    parser.add_argument(
        "--stats-interval",
        type=float,
        default=5.0,
        help="Frequency in seconds to print summary statistics (default: 5.0)"
    )
    return parser.parse_args()


def main():
    # Force 'spawn' start method for cross-platform stability (CUDA & OpenCV friendly)
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

    args = parse_args()

    # Process camera source arg
    source_val = args.source
    if source_val.isdigit():
        source_val = int(source_val)

    # Initialize configuration
    config = AppConfig(
        app_name="VisionMultiprocessingApp",
        log_level="INFO",
        cv_config=CVPipelineConfig(
            source=source_val,
            target_fps=args.fps,
            width=args.width,
            height=args.height,
            show_preview=args.show_preview
        ),
        main_config=MainTaskConfig(
            poll_timeout=0.1,
            target_hz=args.main_hz,
            log_interval=args.stats_interval,
            log_every_n_frames=args.log_every
        ),
        ipc_config=IPCConfig(
            max_queue_size=args.queue_size,
            drop_when_full=True
        )
    )

    # Instantiate CV Pipeline and Main Task workers
    cv_pipeline = DummyVisionPipeline(config.cv_config)
    main_task = SampleMainTask(config.main_config)

    # Initialize Process Manager
    manager = ProcessManager(config, cv_pipeline, main_task)

    if args.duration > 0:
        # Run for specified duration in background thread / timer
        def auto_stopper():
            time.sleep(args.duration)
            manager.stop_event.set()

        import threading
        timer_thread = threading.Thread(target=auto_stopper, daemon=True)
        timer_thread.start()

    # Start processes and run loop until complete or interrupted
    manager.run_until_complete()


if __name__ == "__main__":
    main()
