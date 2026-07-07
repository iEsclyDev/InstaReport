#!/usr/bin/env python3
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

parser = argparse.ArgumentParser(description="InstaReport CLI")
parser.add_argument("--target", type=str, default="", help="Target username")
parser.add_argument("--targets", type=str, nargs="*", default=[], help="Multiple target usernames")
parser.add_argument("--platform", type=str, default="", help="Platform key")
parser.add_argument("--reason", type=str, default="spam", help="Report reason key")
parser.add_argument("--accounts", type=str, default="", help="Comma-sep accounts user:pw")
parser.add_argument("--accounts-file", type=str, default="", help="Path to accounts file")
parser.add_argument("--workers", type=int, default=0, help="Worker count")
parser.add_argument("--cooldown", type=int, default=0, help="Cooldown seconds")
parser.add_argument("--json", action="store_true", help="JSON output")
parser.add_argument("--output-format", choices=["json", "csv"], default="json", help="Output format")
parser.add_argument("--headless", action="store_true", help="Browser headless mode")
parser.add_argument("--debug", action="store_true", help="Debug logging")
parser.add_argument("--api", action="store_true", help="Run as REST API server")
parser.add_argument("--api-host", type=str, default="0.0.0.0", help="API server host")
parser.add_argument("--api-port", type=int, default=8765, help="API server port")
parser.add_argument("--version", action="store_true", help="Print version and exit")
args = parser.parse_args()

if args.version:
    from instareport.utils.constants import VERSION
    print(f"InstaReport CLI v{VERSION}")
    sys.exit(0)

if args.api:
    from instareport.api import run_api
    sys.exit(run_api(host=args.api_host, port=args.api_port))

if sys.platform == "win32" and sys.version_info >= (3, 8):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from instareport.cli import run_cli
sys.exit(run_cli(args))
