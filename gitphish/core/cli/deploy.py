from gitphish.config.deployment import DeploymentConfig
from gitphish.core.deployment.services.deployment_service import (
    DeploymentService,
)
from tabulate import tabulate
import json


def create_deployment(args):
    """Deploy a new GitHub Pages landing page."""
    if not args.github_token:
        args._parser.error(
            "A GitHub token must be provided via --github-token or the GITHUB_DEPLOY_TOKEN environment variable."
        )

    config = DeploymentConfig.from_env(**{**args.__dict__})
    service = DeploymentService()
    result = service.create_deployment(
        config=config,
        poll_deployment=not args.no_wait,
        poll_timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(result, default=str))
    elif result.get("success"):
        deployment = result.get("deployment_result", {})
        url = deployment.get("deployment_url", deployment.get("pages_url", ""))
        print(f"✅ Deployed: {url}")
        print(f"📂 Repo: {deployment.get('repo_url', '')}")
    else:
        print(f"❌ Deployment failed: {result.get('error', 'Unknown error')}")


def cleanup_deployment(args):
    """Delete a GitHub Pages deployment repository and update DB."""
    if not args.github_token:
        args._parser.error(
            "A GitHub token must be provided via --github-token or the GITHUB_DEPLOY_TOKEN environment variable."
        )

    service = DeploymentService()
    result = service.delete_deployment(
        repo_name=args.repo_name,
        github_username=args.username,
        github_token=args.github_token,
        hard=args.hard,
    )
    if args.json:
        print(json.dumps(result, default=str))
    elif result.get("success"):
        print(f"✅ {result.get('message', 'Repository deleted successfully')}")
    else:
        print(f"❌ Cleanup failed: {result.get('error', 'Unknown error')}")


def status_deployment(args):
    """Check deployment status using DeploymentService."""
    if not args.github_token:
        args._parser.error(
            "A GitHub token must be provided via --github-token or the GITHUB_DEPLOY_TOKEN environment variable."
        )

    service = DeploymentService()
    deployment = service.get_deployment_status(
        repo_name=args.repo_name,
        github_username=args.username,
        github_token=args.github_token,
    )
    if args.json:
        print(json.dumps(deployment, default=str))
    elif deployment and deployment["status"] == "active":
        url = deployment["pages_url"] or deployment["repo_url"] or ""
        print(f"✅ Deployed: {url}")
    elif deployment:
        status = deployment["status"] if deployment["status"] else "unknown"
        print(
            f"❌ Deployment record exists but the deployment is not active. "
            f"Status: {status.upper()}"
        )
    else:
        print(f"❌ Not deployed. Repo: {args.repo_name}")


def list_deployments(args):
    """List deployment history from the database."""
    if not args.github_token and args.refresh:
        args._parser.error(
            "A GitHub token must be provided via --github-token or the GITHUB_DEPLOY_TOKEN environment variable."
        )

    service = DeploymentService()
    if args.all:
        deployments = service.get_all_deployments()
    else:
        deployments = service.get_active_deployments()

    if args.refresh and deployments:
        refreshed = []
        for d in deployments:
            updated = service.get_deployment_status(
                repo_name=d["repo_name"],
                github_username=d["github_username"],
                github_token=args.github_token,
            )
            refreshed.append(updated)
        deployments = refreshed

    if args.json:
        print(json.dumps(deployments, default=str))
    elif not deployments:
        print("No deployments found." if args.all else "No active deployments found.")
    else:
        headers = [
            "Repo Name",
            "Status",
            "Username",
            "Created",
            "Pages URL",
            "Deployed",
            "Preset",
            "Title",
        ]
        rows = []
        for d in deployments:
            rows.append(
                [
                    d["repo_name"],
                    d["status"],
                    d["github_username"],
                    d["created_at"],
                    d["pages_url"],
                    d["deployed_at"],
                    d["template_preset"],
                    d["custom_title"],
                ]
            )
        print(tabulate(rows, headers=headers, tablefmt="mixed_grid"))


def stats_deployments(args):
    """Show deployment statistics."""
    service = DeploymentService()
    stats = service.get_deployment_stats()
    if args.json:
        print(json.dumps(stats, default=str))
    else:
        print("📊 Deployment Statistics:")
        print(f"  Total deployments: {stats.get('total_deployments', 0)}")
        print(f"  Successful: {stats.get('successful_deployments', 0)}")
        print(f"  Failed: {stats.get('failed_deployments', 0)}")
        print(f"  Active: {stats.get('active_deployments', 0)}")
        print(f"  Success rate: {stats.get('success_rate', 0):.2f}%")


def setup_deploy_subparser(subparsers):
    """Add the 'deploy' subparser and its subcommands to the main parser."""
    deploy_parser = subparsers.add_parser(
        "deploy", help="Manage GitHub Pages deployments"
    )
    deploy_subparsers = deploy_parser.add_subparsers(
        dest="deploy_command", help="Deploy commands"
    )

    # Create command
    create_parser = deploy_subparsers.add_parser(
        "create", help="Create a new GitHub Pages deployment"
    )
    create_parser.add_argument(
        "--ingest-url", required=True, help="URL for form submissions"
    )
    create_parser.add_argument(
        "--repo-name",
        default="verification-portal",
        help="Repository name (default: verification-portal)",
    )
    create_parser.add_argument(
        "--repo-description",
        default="GitHub Verification Portal",
        help="Repository description",
    )
    create_parser.add_argument(
        "--github-token",
        help="GitHub Personal Access Token (env: GITHUB_DEPLOY_TOKEN)",
    )
    create_parser.add_argument(
        "--preset",
        choices=["default", "enterprise", "urgent", "security"],
        default="default",
        help="Template preset to use",
    )
    create_parser.add_argument("--custom-title", help="Custom page title")
    create_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Skip polling for deployment completion",
    )
    create_parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Deployment polling timeout in seconds (default: 600)",
    )
    create_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for easier processing.",
    )
    create_parser.add_argument(
        "--username", help="Target GitHub username (defaults to token owner)"
    )
    create_parser.set_defaults(func=create_deployment)

    # Cleanup command
    cleanup_parser = deploy_subparsers.add_parser(
        "cleanup", help="Delete a deployment repository"
    )
    cleanup_parser.add_argument(
        "--repo-name",
        default="verification-portal",
        help="Repository name to delete",
    )
    cleanup_parser.add_argument(
        "--github-token",
        help="GitHub Personal Access Token (env: GITHUB_DEPLOY_TOKEN)",
    )
    cleanup_parser.add_argument(
        "--username", help="Target GitHub username (defaults to token owner)"
    )
    cleanup_parser.add_argument(
        "--hard",
        action="store_true",
        help="Hard delete the deployment record from the database.",
    )
    cleanup_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for easier processing.",
    )
    cleanup_parser.set_defaults(func=cleanup_deployment)

    # Status command
    status_parser = deploy_subparsers.add_parser(
        "status", help="Check deployment status"
    )
    status_parser.add_argument("--repo-name", help="Specific repository name to check")
    status_parser.add_argument(
        "--github-token",
        help="GitHub Personal Access Token (env: GITHUB_DEPLOY_TOKEN)",
    )
    status_parser.add_argument(
        "--username", help="Target GitHub username (defaults to token owner)"
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for easier processing.",
    )
    status_parser.set_defaults(func=status_deployment)

    # List command
    list_parser = deploy_subparsers.add_parser("list", help="List deployment history")
    list_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh deployment statuses from GitHub (slower)",
    )
    list_parser.add_argument(
        "--all", action="store_true", help="List all deployments, even inactive ones."
    )
    list_parser.add_argument(
        "--github-token",
        help="GitHub Personal Access Token (env: GITHUB_DEPLOY_TOKEN)",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for easier processing.",
    )
    list_parser.set_defaults(func=list_deployments)

    # Stats command
    stats_parser = deploy_subparsers.add_parser(
        "stats", help="Show deployment statistics"
    )
    stats_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for easier processing.",
    )
    stats_parser.set_defaults(func=stats_deployments)

    return deploy_parser
