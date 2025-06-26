"""
GitPhish Compromised Accounts Management CLI module.
Handles compromised account operations for accounts captured via OAuth flows.
"""

from datetime import datetime
from gitphish.core.accounts.services.compromised_service import (
    CompromisedGitHubAccountService,
)


def handle_list_command(args):
    """List compromised accounts."""
    print("👥 GitPhish Compromised Accounts")
    print("=" * 60)

    service = CompromisedGitHubAccountService()

    if args.source:
        accounts = service.get_compromised_accounts_by_source(args.source)
        print(f"📋 Compromised accounts from source: {args.source}")
    else:
        accounts = service.get_all_compromised_accounts()
        print("📋 All compromised accounts")

    if not accounts:
        print("📭 No compromised accounts found")
        return

    print(f"📊 Found {len(accounts)} compromised account(s)")
    print("-" * 60)
    for account in accounts:
        _display_account_summary(account)


def handle_show_command(args):
    """Show details for a compromised account."""
    print("👤 GitPhish Compromised Account Details")
    print("=" * 60)

    service = CompromisedGitHubAccountService()
    accounts = service.get_all_compromised_accounts()
    target_account = None

    if args.account_id:
        target_account = next(
            (acc for acc in accounts if acc["id"] == args.account_id), None
        )
    elif args.username:
        target_account = next(
            (
                acc
                for acc in accounts
                if acc["username"].lower() == args.username.lower()
            ),
            None,
        )

    if not target_account:
        identifier = (
            f"ID {args.account_id}"
            if args.account_id
            else f"username '{args.username}'"
        )
        print(f"❌ No compromised account found with {identifier}")
        return

    _display_account_details(target_account)


def handle_stats_command(args):
    """Show statistics for compromised accounts."""
    print("📊 GitPhish Compromised Accounts Statistics")
    print("=" * 60)

    service = CompromisedGitHubAccountService()
    stats = service.get_statistics()

    print("📈 Account Overview:")
    print(f"   Total Accounts: {stats['total_accounts']}")
    print(f"   Valid Tokens: {stats['valid_accounts']}")
    print(f"   Invalid Tokens: {stats['invalid_accounts']}")
    print()
    print("📥 Sources:")
    print(f"   Device Auth Flow: {stats['device_auth_accounts']}")
    print(f"   Manual Entry: {stats['manual_accounts']}")
    print()
    print("🔍 Analysis Status:")
    print(f"   Analyzed: {stats['analyzed_accounts']}")
    print(f"   Unanalyzed: {stats['unanalyzed_accounts']}")
    print()

    if stats["total_accounts"] > 0:
        valid_percentage = (stats["valid_accounts"] / stats["total_accounts"]) * 100
        device_percentage = (
            stats["device_auth_accounts"] / stats["total_accounts"]
        ) * 100
        print("📊 Metrics:")
        print(f"   Valid Token Rate: {valid_percentage:.1f}%")
        print(f"   Device Auth Capture Rate: {device_percentage:.1f}%")


def handle_validate_command(args):
    """Validate a compromised account token."""
    print("🔍 GitPhish Token Validation")
    print("=" * 60)

    service = CompromisedGitHubAccountService()

    if not args.account_id:
        print("❌ Account ID is required for validation")
        return

    print(f"🔍 Validating token for account ID: {args.account_id}")

    result = service.validate_compromised_account(args.account_id)
    if result["success"]:
        account = result["account"]

        print("✅ Token validation successful!")
        print(f"👤 Username: {account['username']}")
        print(f"🔑 Token Status: {'Valid' if account['is_valid'] else 'Invalid'}")
        print(f"📊 Rate Limit: {account.get('rate_limit_remaining', 'Unknown')}")

        if account.get("last_validated_at"):
            print(
                f"🕒 Last Validated: {_format_datetime(account['last_validated_at'])}"
            )
    else:
        print(f"❌ Token validation failed: {result['error']}")


def handle_repos_command(args):
    """Show repositories for a compromised account (DB only)."""
    print("📚 GitPhish Account Repositories (Database Only)")
    print("=" * 60)

    service = CompromisedGitHubAccountService()

    if not args.account_id:
        print("❌ Account ID is required to view repositories")
        return

    accounts = service.get_all_compromised_accounts()

    target_account = next(
        (acc for acc in accounts if acc["id"] == args.account_id), None
    )
    if not target_account:
        print(f"❌ No compromised account found with ID {args.account_id}")
        return

    print(f"📚 Checking stored repositories for account: {target_account['username']}")
    print("📊 Note: This only shows repositories already stored in the database")
    print("         Use the admin interface to fetch live repositories from GitHub")
    print("-" * 60)
    print("📭 No repositories stored in database for this account")


def _display_account_summary(account):
    status_emoji = "✅" if account.get("is_valid") else "❌"
    source_emoji = "🔄" if account.get("source") == "device_auth" else "✋"
    analyzed_emoji = "🔍" if account.get("is_analyzed") else "⏳"

    print(
        status_emoji, source_emoji, analyzed_emoji, account["id"], account["username"]
    )

    if account.get("email"):
        print(f"    📧 {account['email']}")

    if account.get("victim_ip"):
        print(f"    🌐 {account['victim_ip']}")

    if account.get("created_at"):
        created_time = _format_datetime(account["created_at"])
        print(f"    🕒 {created_time}")

    if account.get("device_auth_session_id"):
        print(f"    🔗 Session: {account['device_auth_session_id']}")

    print()


def _display_account_details(account):
    print(f"👤 Account: {account['username']}")
    print(f"🆔 ID: {account['id']}")
    print(f"📧 Email: {account.get('email', 'N/A')}")
    print(f"🔑 Token Status: {'Valid' if account.get('is_valid') else 'Invalid'}")
    print(f"📊 Rate Limit: {account.get('rate_limit_remaining', 'Unknown')}")
    print(f"📍 Source: {account.get('source', 'Unknown')}")
    print(f"🔍 Analyzed: {'Yes' if account.get('is_analyzed') else 'No'}")
    print()

    print("🎯 Victim Information:")
    print(f"   🌐 IP Address: {account.get('victim_ip', 'N/A')}")
    if account.get("victim_user_agent"):
        print(f"   🖥️  User Agent: {account['victim_user_agent'][:80]}...")
    print()

    if account.get("device_auth_session_id"):
        print("🔗 Session Information:")
        print(f"   Session ID: {account['device_auth_session_id']}")
    print()

    print("🔐 Token Information:")
    # Get the full token from the service
    # (Not shown here for security reasons)
    if account.get("scopes"):
        scopes = account["scopes"] if isinstance(account["scopes"], list) else []
        print(f"   Scopes: {', '.join(scopes) if scopes else 'N/A'}")
    print()

    print("🕒 Timestamps:")
    if account.get("created_at"):
        print(f"   Created: {_format_datetime(account['created_at'])}")
    if account.get("last_validated_at"):
        print(f"   Last Validated: {_format_datetime(account['last_validated_at'])}")
    if account.get("updated_at"):
        print(f"   Updated: {_format_datetime(account['updated_at'])}")


def _format_datetime(dt_string: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return dt_string


def setup_postex_subparser(subparsers):
    """Add the 'postex' subparser and its subcommands to the main parser."""
    postex_parser = subparsers.add_parser(
        "postex", help="Manage post-exploitation (compromised) GitHub accounts"
    )
    postex_subparsers = postex_parser.add_subparsers(
        dest="postex_command", help="PostEx commands"
    )

    # List command
    list_parser = postex_subparsers.add_parser("list", help="List compromised accounts")
    list_parser.add_argument("--source", help="Filter by source (manual/device_auth)")
    list_parser.set_defaults(func=handle_list_command)

    # Show command
    show_parser = postex_subparsers.add_parser(
        "show", help="Show compromised account details"
    )
    show_parser.add_argument("--account-id", type=int, help="Account ID")
    show_parser.add_argument("--username", help="GitHub username")
    show_parser.set_defaults(func=handle_show_command)

    # Stats command
    stats_parser = postex_subparsers.add_parser(
        "stats", help="Show compromised account statistics"
    )
    stats_parser.set_defaults(func=handle_stats_command)

    # Validate command
    validate_parser = postex_subparsers.add_parser(
        "validate", help="Validate a compromised account token"
    )
    validate_parser.add_argument(
        "--account-id", type=int, required=True, help="Account ID to validate"
    )
    validate_parser.set_defaults(func=handle_validate_command)

    # Repos command
    repos_parser = postex_subparsers.add_parser(
        "repos", help="Show repositories for a compromised account (DB only)"
    )
    repos_parser.add_argument(
        "--account-id", type=int, required=True, help="Account ID to show repos for"
    )
    repos_parser.set_defaults(func=handle_repos_command)

    return postex_parser
