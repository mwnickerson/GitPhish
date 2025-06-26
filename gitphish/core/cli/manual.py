from gitphish.core.manual.manual import ManualDeviceAuth


def run_manual(args):
    """Run the manual device code authentication flow or poll for token only."""
    auth = ManualDeviceAuth()
    if args.poll:
        return auth.poll_for_token_only(
            client_id=args.client_id,
            org_name=args.org_name,
            device_code=args.poll,
            email=args.email,
        )
    else:
        return auth.run_manual_device_code_flow(
            client_id=args.client_id,
            org_name=args.org_name,
            email=args.email,
            skip_wait=args.skip_wait,
        )


def setup_manual_subparser(subparsers):
    """Add the 'manual' subparser and its options to the main parser."""
    manual_parser = subparsers.add_parser(
        "manual",
        help="Manually generate a device code and poll for auth, or poll for a token using an existing device code.",
    )
    manual_parser.add_argument(
        "--client-id",
        default="178c6fc778ccc68e1d6a",
        help="GitHub OAuth app client ID (default: 178c6fc778ccc68e1d6a)",
    )
    manual_parser.add_argument(
        "--org-name",
        default="GitHub",
        help="Target organization name (default: GitHub)",
    )
    manual_parser.add_argument(
        "--email",
        help="Email for tracking (if omitted, token is saved with just a timestamp)",
    )
    manual_parser.add_argument(
        "--skip-wait",
        action="store_true",
        help="Skip polling for token (just print device code)",
    )
    manual_parser.add_argument(
        "--poll",
        metavar="DEVICE_CODE",
        help="Poll for a token using this device code instead of generating a "
        "new one. Use if you previously ran --skip-wait.",
    )
    manual_parser.set_defaults(func=run_manual)
    return manual_parser
