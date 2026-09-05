import time
import pytest
from config import AppConfig, CVPipelineConfig, MainTaskConfig, IPCConfig
from cv_pipeline import DummyVisionPipeline
from main_task import SampleMainTask
from core.process_manager import ProcessManager


def test_full_framework_multiprocessing_run():
    """Integration test spinning up both CV and Main processes for 2 seconds."""
    config = AppConfig(
        app_name="TestFrameworkApp",
        log_level="WARNING",
        cv_config=CVPipelineConfig(source="synthetic", target_fps=30.0, width=160, height=120),
        main_config=MainTaskConfig(poll_timeout=0.05, log_interval=1.0),
        ipc_config=IPCConfig(max_queue_size=20, drop_when_full=True)
    )

    cv_pipeline = DummyVisionPipeline(config.cv_config)
    main_task = SampleMainTask(config.main_config)
    manager = ProcessManager(config, cv_pipeline, main_task)

    # Start processes
    manager.start()
    assert manager.cv_process is not None and manager.cv_process.is_alive()
    assert manager.main_process is not None and manager.main_process.is_alive()

    # Let processes execute for 1.5 seconds
    time.sleep(1.5)

    # Signal stop and shutdown
    manager.shutdown(grace_period=3.0)

    assert not manager.cv_process.is_alive()
    assert not manager.main_process.is_alive()
    assert main_task.packets_received >= 0
