import argparse
import logging
import signal

from .api import ConfigurationError
from .config import load_config
from .runtime import Application, configure_logging


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pcvmf")
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser("run", help="Run an application (packaged headless demo by default)")
    run.add_argument("--config")
    config = commands.add_parser("config", help="Inspect configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    validate = config_commands.add_parser("validate")
    validate.add_argument("path")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.path if args.command == "config" else getattr(args, "config", None))
    except (ConfigurationError, ValueError, TypeError) as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    if args.command == "config":
        print(f"Valid configuration: {len(config.workers)} workers")
        return 0
    configure_logging(config.logging)
    app = Application(config)

    def stop(signum, frame):
        logging.getLogger(__name__).info("Received %s; stopping", signal.Signals(signum).name)
        app.request_stop()

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        return app.run().exit_code
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
