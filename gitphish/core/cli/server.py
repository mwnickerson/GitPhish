import os

from gitphish.core.server.server import start_github_auth_server


def run_server(args):
    """Run the GitPhish authentication server."""
    if not (args.dev or (args.cert_path and args.key_path)):
        args._parser.error(
            "You must specify either --dev or both --cert-path " "and --key-path."
        )
        return 1

    print("🔐 GitPhish Authentication Server")
    print(f"🌐 Host: {args.host}")
    print(f"🔌 Port: {args.port}")
    print(f"🏢 Organization: {args.org_name}")
    print(f"🔑 Client ID: {args.client_id}")
    print("ℹ️  Use Ctrl+C to stop the server")
    print()

    start_github_auth_server(
        client_id=args.client_id,
        org_name=args.org_name,
        host=args.host,
        port=args.port,
        cert_path=args.cert_path,
        key_path=args.key_path,
        dev_mode=args.dev,
    )


def setup_server_subparser(subparsers):
    """Add the 'server' subparser and its options to the main parser."""
    server_parser = subparsers.add_parser("server", help="Run authentication server")

    server_parser.add_argument(
        "--port", type=int, default=443, help="Server port (default: 443)"
    )
    server_parser.add_argument(
        "--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)"
    )
    server_parser.add_argument(
        "--client-id",
        default=os.getenv("GITHUB_CLIENT_ID") or "178c6fc778ccc68e1d6a",
        help=("GitHub client ID (env: GITHUB_CLIENT_ID)"),
    )
    server_parser.add_argument(
        "--org-name",
        default=os.getenv("GITHUB_ORG_NAME") or "GitHub",
        help=("Target organization name (env: GITHUB_ORG_NAME)"),
    )
    server_parser.add_argument(
        "--dev",
        action="store_true",
        help="Development mode (HTTP + self-signed certs)",
    )
    server_parser.add_argument(
        "--cert-path",
        default=os.getenv("SSL_CERT_PATH"),
        help=("Path to SSL certificate file (env: SSL_CERT_PATH)"),
    )
    server_parser.add_argument(
        "--key-path",
        default=os.getenv("SSL_KEY_PATH"),
        help=("Path to SSL private key file (env: SSL_KEY_PATH)"),
    )

    server_parser.set_defaults(func=run_server, _parser=server_parser)

    return server_parser
