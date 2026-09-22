"""Command-line entry point for the visible, non-persistent ASHBORNE agent."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from ashborne_agent import __version__
from ashborne_agent.client import (
    AgentAPIError,
    AshborneClient,
    AuthenticationError,
    enrollment_identity,
)
from ashborne_agent.config import AgentConfig, ConfigError, default_config_path
from ashborne_agent.heartbeat import AgentRunner
from ashborne_agent.logging import configure_logging
from ashborne_agent.models import ProtocolError
from ashborne_agent.outbox import OutboxError, ResultOutbox

LOG = logging.getLogger("ashborne_agent.main")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ashborne-agent",
        description="ASHBORNE - Adversary Emulation & Offensive Security Lab Platform",
    )
    parser.add_argument("--version", action="version", version=f"ashborne-agent {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    enroll = commands.add_parser("enroll", help="enroll using a one-time token")
    _add_config_argument(enroll)
    enroll.add_argument("--server", default=os.getenv("ASHBORNE_SERVER_URL"))
    enroll.add_argument("--token", default=os.getenv("ASHBORNE_ENROLLMENT_TOKEN"))
    enroll.add_argument("--name", default=os.getenv("ASHBORNE_AGENT_NAME"))
    enroll.add_argument("--ca-bundle", default=os.getenv("ASHBORNE_CA_BUNDLE"))
    enroll.add_argument(
        "--allow-insecure-http",
        action="store_true",
        default=_env_bool("ASHBORNE_ALLOW_INSECURE_HTTP", False),
        help="allow plain HTTP for an isolated local lab only",
    )
    enroll.add_argument(
        "--kali-controller",
        action="store_true",
        default=_env_bool("ASHBORNE_KALI_CONTROLLER", False),
        help="enroll this Linux host as the explicit Kali operation controller",
    )
    enroll.add_argument(
        "--max-parallel-hosts",
        type=int,
        default=_env_int("ASHBORNE_MAX_PARALLEL_HOSTS", 10),
    )
    enroll.add_argument("--force", action="store_true", help="replace an existing credential")
    _add_logging_arguments(enroll)

    run = commands.add_parser("run", help="send heartbeats and execute allowlisted tasks")
    _add_config_argument(run)
    run.add_argument("--server", default=os.getenv("ASHBORNE_SERVER_URL"))
    run.add_argument("--name", default=os.getenv("ASHBORNE_AGENT_NAME"))
    run.add_argument("--ca-bundle", default=os.getenv("ASHBORNE_CA_BUNDLE"))
    run.add_argument(
        "--allow-insecure-http",
        action="store_true",
        default=_env_bool("ASHBORNE_ALLOW_INSECURE_HTTP", False),
        help="allow plain HTTP for an isolated local lab only",
    )
    run.add_argument(
        "--heartbeat-interval",
        type=float,
        default=_env_float("ASHBORNE_HEARTBEAT_INTERVAL"),
    )
    run.add_argument("--poll-interval", type=float, default=_env_float("ASHBORNE_POLL_INTERVAL"))
    run.add_argument(
        "--kali-controller",
        action="store_true",
        default=_env_bool("ASHBORNE_KALI_CONTROLLER", False),
        help="enable Kali controller execution for this agent",
    )
    run.add_argument(
        "--max-parallel-hosts",
        type=int,
        default=_env_int("ASHBORNE_MAX_PARALLEL_HOSTS", 10),
    )
    run.add_argument("--once", action="store_true", help="perform one poll cycle and exit")
    _add_logging_arguments(run)

    status = commands.add_parser("status", help="show local enrollment status")
    _add_config_argument(status)
    status.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = build_parser()
    except ConfigError as exc:
        print(f"ASHBORNE configuration error: {exc}", file=sys.stderr)
        return 2
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "enroll":
            return _enroll(arguments)
        if arguments.command == "run":
            return _run(arguments)
        if arguments.command == "status":
            return _status(arguments)
    except (ConfigError, OutboxError, ValueError) as exc:
        print(f"ASHBORNE configuration error: {exc}", file=sys.stderr)
        return 2
    except AuthenticationError as exc:
        print(f"ASHBORNE authentication error: {exc}", file=sys.stderr)
        return 3
    except (AgentAPIError, ProtocolError) as exc:
        print(f"ASHBORNE API error: {exc}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        return 130
    return 2


def _enroll(arguments: argparse.Namespace) -> int:
    config_path = Path(arguments.config)
    _configure_cli_logging(arguments, config_path)
    existing: AgentConfig | None = None
    if config_path.exists():
        existing = AgentConfig.load(config_path)
        if existing.credential and not arguments.force:
            raise ConfigError("agent is already enrolled; use --force to replace its credential")
    server_url = arguments.server or (existing.server_url if existing else None)
    if not server_url:
        raise ConfigError("--server or ASHBORNE_SERVER_URL is required")
    if not arguments.token:
        raise ConfigError("--token or ASHBORNE_ENROLLMENT_TOKEN is required")

    if existing:
        config = replace(
            existing,
            server_url=server_url,
            name=arguments.name or existing.name,
            ca_bundle=arguments.ca_bundle or existing.ca_bundle,
            allow_insecure_http=arguments.allow_insecure_http or existing.allow_insecure_http,
            kali_controller=arguments.kali_controller or existing.kali_controller,
            max_parallel_hosts=arguments.max_parallel_hosts,
        )
    else:
        config = AgentConfig.new(
            server_url,
            name=arguments.name,
            ca_bundle=arguments.ca_bundle,
            allow_insecure_http=arguments.allow_insecure_http,
            kali_controller=arguments.kali_controller,
            max_parallel_hosts=arguments.max_parallel_hosts,
        )
        # Persist the UUID before using a one-time token so a retry keeps identity.
        config.save(config_path)

    with AshborneClient(config) as client:
        credential = client.enroll(arguments.token, enrollment_identity(config))
    config.credential = credential
    config.save(config_path)
    LOG.info(
        "Agent enrolled",
        extra={"event": "agent_enrolled", "agent_id": config.agent_id},
    )
    print(f"ASHBORNE agent enrolled: {config.agent_id}")
    return 0


def _run(arguments: argparse.Namespace) -> int:
    config_path = Path(arguments.config)
    _configure_cli_logging(arguments, config_path)
    config = _load_run_config(arguments, config_path)
    stop_event = threading.Event()
    _install_signal_handlers(stop_event)

    with AshborneClient(config) as client:
        if not config.credential:
            token = os.getenv("ASHBORNE_ENROLLMENT_TOKEN")
            demo_secret = os.getenv("ASHBORNE_DEMO_BOOTSTRAP_SECRET")
            if token:
                config.credential = client.enroll(token, enrollment_identity(config))
            elif demo_secret:
                config.credential = client.enroll_demo(demo_secret, enrollment_identity(config))
            else:
                raise ConfigError(
                    "agent is not enrolled; run `ashborne-agent enroll` or provide a demo secret"
                )
            config.save(config_path)
            LOG.info(
                "Agent enrolled during startup",
                extra={"event": "agent_enrolled", "agent_id": config.agent_id},
            )

        outbox = ResultOutbox.beside_config(config_path)
        runner = AgentRunner(config, client, outbox, stop_event=stop_event)
        if arguments.once:
            runner.run_cycle()
        else:
            runner.run_forever()
    return 0


def _load_run_config(arguments: argparse.Namespace, config_path: Path) -> AgentConfig:
    kali_controller = bool(getattr(arguments, "kali_controller", False))
    max_parallel_hosts = int(getattr(arguments, "max_parallel_hosts", 10))
    if config_path.exists():
        config = AgentConfig.load(config_path)
        if arguments.server and arguments.server.rstrip("/") != config.server_url:
            raise ConfigError("--server does not match the enrolled server")
        if arguments.heartbeat_interval is not None:
            config.heartbeat_interval = arguments.heartbeat_interval
        if arguments.poll_interval is not None:
            config.poll_interval = arguments.poll_interval
        if kali_controller:
            config.kali_controller = True
        config.max_parallel_hosts = max_parallel_hosts
        # Revalidate bounded command-line overrides.
        config.__post_init__()
        return config
    if not arguments.server:
        raise ConfigError("agent configuration is missing and no server URL was provided")
    config = AgentConfig.new(
        arguments.server,
        name=arguments.name,
        ca_bundle=arguments.ca_bundle,
        allow_insecure_http=arguments.allow_insecure_http,
        kali_controller=kali_controller,
        max_parallel_hosts=max_parallel_hosts,
    )
    if arguments.heartbeat_interval is not None:
        config.heartbeat_interval = arguments.heartbeat_interval
    if arguments.poll_interval is not None:
        config.poll_interval = arguments.poll_interval
    config.__post_init__()
    config.save(config_path)
    return config


def _status(arguments: argparse.Namespace) -> int:
    config_path = Path(arguments.config)
    config = AgentConfig.load(config_path)
    status = config.public_status(config_path)
    if arguments.json:
        print(json.dumps(status, sort_keys=True))
    else:
        print("ASHBORNE agent status")
        for key, value in status.items():
            print(f"  {key.replace('_', ' ').title()}: {value}")
    return 0 if config.credential else 1


def _install_signal_handlers(stop_event: threading.Event) -> None:
    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
    except (ValueError, AttributeError):
        # Signal registration is unavailable outside the main interpreter thread.
        pass


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=str(default_config_path()),
        help="path to the permission-restricted agent configuration",
    )


def _add_logging_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default=os.getenv("ASHBORNE_LOG_LEVEL", "INFO").upper(),
    )
    parser.add_argument("--log-file", default=os.getenv("ASHBORNE_LOG_FILE"))


def _configure_cli_logging(arguments: argparse.Namespace, config_path: Path) -> None:
    default_log = config_path.with_name("agent.log")
    log_file = Path(arguments.log_file) if arguments.log_file else default_log
    configure_logging(level=arguments.log_level, log_file=log_file, console=True)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean")


def _env_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


if __name__ == "__main__":
    raise SystemExit(main())
