import argparse
import logging
import signal
import sys
from pathlib import Path

from .api import ConfigurationError, Worker
from .config import load_config
from .plugins import load_class
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
    yamcs = commands.add_parser("yamcs", help="Yamcs telemetry integration")
    yamcs_commands = yamcs.add_subparsers(dest="yamcs_command", required=True)
    mdb = yamcs_commands.add_parser("mdb", help="Generate the XTCE mission database for a YamcsExporter worker")
    mdb.add_argument("--config", required=True)
    mdb.add_argument("--worker", help="Exporter worker name when the configuration has several")
    mdb.add_argument("-o", "--output", help="Output file (default: standard output)")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.path if args.command == "config" else getattr(args, "config", None))
    except (ConfigurationError, ValueError, TypeError) as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    if args.command == "yamcs":
        return _yamcs_mdb(parser, config, args)
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


def _yamcs_mdb(parser, config, args):
    from .yamcs import YamcsExporter
    from .yamcs.mapping import parse_export_options, unsubscribed_routes
    from .yamcs.xtce import generate_xtce

    exporters = [
        w
        for w in config.workers
        if load_class(w.plugin["class"], Worker) is YamcsExporter and args.worker in (None, w.name)
    ]
    if len(exporters) != 1:
        found = "no" if not exporters else "several"
        parser.exit(2, f"Configuration error: {found} YamcsExporter workers match; use --worker NAME\n")
    [worker] = exporters
    spec = parse_export_options(worker.plugin.get("options", {}))
    for route in unsubscribed_routes(spec, worker.subscriptions):
        print(f"Warning: worker {worker.name} does not subscribe to {route}", file=sys.stderr)
    document = generate_xtce(spec)
    if args.output:
        Path(args.output).write_text(document)
        print(f"Wrote {args.output}: {len(spec.packets)} packets", file=sys.stderr)
    else:
        sys.stdout.write(document)
    return 0
