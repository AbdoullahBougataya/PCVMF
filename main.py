#!/usr/bin/env python3
"""
Computer Vision Robotics Framework - Main Entry Point

Orchestrates two independent Python processes:
1. Computer Vision Process: Frame capture, CV pipeline, ZeroMQ IPC Publisher
2. Main Application Process: Robotics controller, ZeroMQ IPC Subscriber

Usage:
    python main.py [--config config/default_config.yaml]
"""

import argparse
import multiprocessing as mp
import os
import signal
import sys
import time
import yaml

from src.common.logger import setup_logger
from src.vision.process import run_vision_process
from src.main_app.process import run_main_app_process

logger = setup_logger("Orchestrator")


def load_config(config_path: str) -> dict:
    """Loads YAML configuration file."""
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at: {config_path}")
        sys.exit(1)
        
    with open(config_path, "r") as f:
        try:
            config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to parse YAML config file {config_path}: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Computer Vision Robotics Multiprocess Framework")
    parser.add_argument(
        "--config",
        type=str,
        default="config/default_config.yaml",
        help="Path to YAML configuration file (default: config/default_config.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    # Use 'spawn' start method for clean, isolated process state (cross-platform best practice)
    mp.set_start_method("spawn", force=True)

    # Inter-process stop signal event
    stop_event = mp.Event()

    # Create processes
    logger.info("Initializing child processes...")
    vision_process = mp.Process(
        target=run_vision_process,
        args=(config, stop_event),
        name="VisionProcess",
    )

    main_app_process = mp.Process(
        target=run_main_app_process,
        args=(config, stop_event),
        name="MainAppProcess",
    )

    def shutdown_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal {sig_name}. Initiating graceful shutdown...")
        stop_event.set()

    # Register signal handlers for graceful shutdown (Ctrl+C / SIGTERM)
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start processes
    logger.info("Starting Vision Process...")
    vision_process.start()

    logger.info("Starting Main Application Process...")
    main_app_process.start()

    logger.info("Both processes running smoothly. Press Ctrl+C to terminate.")

    # Orchestrator monitoring loop
    try:
        while not stop_event.is_set():
            # Check if any child process died unexpectedly
            if not vision_process.is_alive():
                logger.error("VisionProcess terminated unexpectedly! Shutting down system.")
                stop_event.set()
                break
            if not main_app_process.is_alive():
                logger.error("MainAppProcess terminated unexpectedly! Shutting down system.")
                stop_event.set()
                break

            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught in main orchestrator loop.")
        stop_event.set()

    # Gracefully join processes with timeout
    logger.info("Waiting for processes to exit...")
    for proc in [vision_process, main_app_process]:
        proc.join(timeout=3.0)
        if proc.is_alive():
            logger.warning(f"Process {proc.name} did not exit in time. Forcefully terminating...")
            proc.terminate()
            proc.join()

    logger.info("System shutdown complete.")


if __name__ == "__main__":
    main()
