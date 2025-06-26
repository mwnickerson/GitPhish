from gitphish.core.gui.server import GitPhishGuiServer


def run_gui(args):
    """Run the GitPhish GUI (admin portal)."""
    gui_server = GitPhishGuiServer(host=args.host, port=args.port)

    print("🎛️  GitPhish GUI")
    print(f"📊 GUI: http://{args.host}:{args.port}")
    print("🔧 Access the web interface to manage GitPhish operations")
    print("ℹ️  Use Ctrl+C to stop the server")
    print()

    gui_server.run(debug=args.debug)


def setup_gui_subparser(subparsers):
    """Add the 'gui' subparser and its options to the main parser."""
    gui_parser = subparsers.add_parser("gui", help="Run GUI (admin portal)")

    gui_parser.add_argument(
        "--port", type=int, default=8080, help="GUI port (default: 8080)"
    )
    gui_parser.add_argument(
        "--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)"
    )
    gui_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    gui_parser.set_defaults(func=run_gui)

    return gui_parser
