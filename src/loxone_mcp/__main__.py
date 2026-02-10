"""Entry point for the Loxone MCP Server.

Usage:
    python -m loxone_mcp                           # Default: env vars, HTTP transport
    python -m loxone_mcp --config config.yaml      # YAML config file
    python -m loxone_mcp --transport stdio          # stdio transport for local AI
    python -m loxone_mcp --transport both           # Both HTTP and stdio
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys

import structlog

from loxone_mcp.config import RootConfig, TransportType, setup_logging
from loxone_mcp.server import LoxoneMCPServer

logger = structlog.get_logger()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="loxone-mcp",
        description="Loxone MCP Server - Bridge AI systems with Loxone home automation",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["http", "stdio", "both"],
        default=None,
        help="Transport type (overrides config)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="HTTP server bind address (overrides config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP server port (overrides config)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug mode with verbose logging",
    )
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> RootConfig:
    """Load configuration from YAML file or environment variables."""
    config = RootConfig.from_yaml(args.config) if args.config else RootConfig.from_env()

    # Apply CLI overrides
    if args.transport:
        config.server.transport = TransportType(args.transport)
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port
    if args.debug:
        config.server.debug = True
        config.server.log_level = "DEBUG"

    return config


async def run_stdio(server: LoxoneMCPServer) -> None:
    """Run the MCP server over stdio transport."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        init_options = server.mcp_server.create_initialization_options()
        await server.mcp_server.run(read_stream, write_stream, init_options)


async def run_http(server: LoxoneMCPServer) -> None:
    """Run the MCP server over HTTP+SSE transport."""
    from loxone_mcp.transport.http_sse import create_http_app, run_http_server

    app = create_http_app(server)
    await run_http_server(
        app,
        host=server.config.server.host,
        port=server.config.server.port,
        tls_cert=server.config.server.tls_cert,
        tls_key=server.config.server.tls_key,
    )


async def run_both(server: LoxoneMCPServer) -> None:
    """Run both stdio and HTTP transports concurrently."""
    await asyncio.gather(
        run_stdio(server),
        run_http(server),
    )


async def async_main(config: RootConfig) -> None:
    """Main async entry point."""
    server = LoxoneMCPServer(config)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("shutdown_signal_received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Initialize Loxone connection and state
        await server.initialize()

        # Select transport and run
        transport = config.server.transport

        if transport == TransportType.STDIO:
            # For stdio, run until EOF or signal
            transport_task = asyncio.create_task(run_stdio(server))
        elif transport == TransportType.BOTH:
            transport_task = asyncio.create_task(run_both(server))
        else:
            transport_task = asyncio.create_task(run_http(server))

        # Wait for either transport completion or shutdown signal
        _done, pending = await asyncio.wait(
            [transport_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except Exception:
        logger.exception("server_error")
    finally:
        await server.shutdown()


def main() -> None:
    """Synchronous entry point."""
    args = parse_args()

    try:
        config = load_config(args)
    except (ValueError, FileNotFoundError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    setup_logging(
        log_level=config.server.log_level,
        debug=config.server.debug,
    )

    logger.info(
        "starting_loxone_mcp_server",
        transport=config.server.transport.value,
        host=config.server.host,
        port=config.server.port,
        access_mode=config.access_control.mode.value,
    )

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(async_main(config))


if __name__ == "__main__":
    main()
