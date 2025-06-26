"""
API endpoints for GitHub and compromised accounts management.
"""

import logging
from flask import request, jsonify

from gitphish.core.accounts.services.deployer_service import (
    DeployerGitHubAccountService,
)
from gitphish.core.accounts.services.compromised_service import (
    CompromisedGitHubAccountService,
)
from gitphish.core.accounts.clients.github_client import GitHubClient


class AccountsAPI:
    """API endpoints for account management."""

    def __init__(
        self,
        app,
        github_account_service: DeployerGitHubAccountService,
        compromised_account_service: CompromisedGitHubAccountService,
    ):
        self.app = app
        self.github_account_service = github_account_service
        self.compromised_account_service = compromised_account_service
        self.logger = logging.getLogger(__name__)
        self._setup_routes()

    def _setup_routes(self):
        """Setup Flask routes for accounts API."""

        @self.app.route("/api/github/validate-token", methods=["POST"])
        def validate_token():
            """API endpoint to validate a GitHub token."""
            try:
                data = request.get_json()

                if not data.get("github_token"):
                    return (
                        jsonify({"error": "Missing github_token field"}),
                        400,
                    )

                github_client = GitHubClient(data["github_token"])
                token_info = github_client.validate_token()
                return jsonify(token_info.to_dict())

            except Exception as e:
                self.logger.error(f"Failed to validate token: {str(e)}")
                return (
                    jsonify({"error": f"Failed to validate token: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/github/accounts", methods=["GET"])
        def get_github_accounts():
            """API endpoint to get all GitHub accounts."""
            try:
                accounts = self.github_account_service.get_all_accounts()
                return jsonify(accounts)
            except Exception as e:
                self.logger.error(f"Failed to get GitHub accounts: {str(e)}")
                return (
                    jsonify({"error": f"Failed to get accounts: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/github/accounts", methods=["POST"])
        def add_github_account():
            """API endpoint to add a new GitHub account."""
            try:
                data = request.get_json()

                if not data.get("token"):
                    return jsonify({"error": "Missing token field"}), 400

                result = self.github_account_service.add_account(data["token"])

                if result["success"]:
                    return jsonify(result)
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(f"Failed to add GitHub account: {str(e)}")
                return (
                    jsonify({"error": f"Failed to add account: {str(e)}"}),
                    500,
                )

        @self.app.route(
            "/api/github/accounts/<int:account_id>/repositories",
            methods=["GET"],
        )
        def get_account_repositories(account_id):
            """API endpoint to get repositories for a GitHub account."""
            try:
                result = self.github_account_service.get_account_repositories(
                    account_id
                )

                if result["success"]:
                    return jsonify(result)
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(
                    f"Failed to get repositories for account {account_id}: " f"{str(e)}"
                )
                return (
                    jsonify({"error": (f"Failed to get repositories: {str(e)}")}),
                    500,
                )

        @self.app.route(
            "/api/github/accounts/<int:account_id>/validate", methods=["POST"]
        )
        def validate_github_account(account_id):
            """API endpoint to validate a GitHub account."""
            try:
                result = self.github_account_service.validate_account(account_id)

                if result["success"]:
                    return jsonify(result)
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(f"Failed to validate account {account_id}: {str(e)}")
                return (
                    jsonify({"error": (f"Failed to validate account: {str(e)}")}),
                    500,
                )

        @self.app.route(
            "/api/github/accounts/<int:account_id>/primary", methods=["POST"]
        )
        def set_primary_github_account(account_id):
            """API endpoint to set a GitHub account as primary."""
            try:
                result = self.github_account_service.set_primary_account(account_id)

                if result["success"]:
                    return jsonify(result)
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(
                    f"Failed to set primary account {account_id}: {str(e)}"
                )
                return (
                    jsonify({"error": f"Failed to set primary account: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/github/accounts/<int:account_id>", methods=["DELETE"])
        def remove_github_account(account_id):
            """API endpoint to remove a GitHub account."""
            try:
                result = self.github_account_service.remove_account(account_id)

                if result["success"]:
                    return jsonify(result)
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(f"Failed to remove account {account_id}: {str(e)}")
                return (
                    jsonify({"error": (f"Failed to remove account: {str(e)}")}),
                    500,
                )

        # Compromised Account API Routes
        @self.app.route("/api/compromised/accounts", methods=["GET"])
        def get_compromised_accounts():
            """API endpoint to get all compromised accounts."""
            try:
                accounts = (
                    self.compromised_account_service.get_all_compromised_accounts()
                )
                return jsonify(accounts), 200
            except Exception as e:
                self.logger.error(f"Failed to get compromised accounts: {str(e)}")
                return (
                    jsonify(
                        {"error": (f"Failed to get compromised accounts: {str(e)}")}
                    ),
                    500,
                )

        @self.app.route("/api/compromised/accounts", methods=["POST"])
        def add_compromised_account():
            """API endpoint to add a compromised account."""
            try:
                data = request.get_json()

                if not data.get("token"):
                    return jsonify({"error": "Missing token field"}), 400

                # Extract victim information if provided
                victim_info = data.get("victim_info", {})

                result = self.compromised_account_service.add_compromised_account(
                    token=data["token"],
                    source="manual",
                    victim_info=victim_info,
                )

                if result["success"]:
                    return jsonify(result), 201
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(f"Failed to add compromised account: {str(e)}")
                return (
                    jsonify(
                        {"error": (f"Failed to add compromised account: {str(e)}")}
                    ),
                    500,
                )

        @self.app.route(
            "/api/compromised/accounts/<int:account_id>/repositories",
            methods=["GET"],
        )
        def get_compromised_account_repositories(account_id):
            """API endpoint to get repositories for a compromised account."""
            try:
                result = self.compromised_account_service.get_compromised_account_repositories(
                    account_id
                )

                if result["success"]:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(
                    f"Failed to get repositories for compromised account: {str(e)}"
                )
                return (
                    jsonify({"error": f"Failed to get repositories: {str(e)}"}),
                    500,
                )

        @self.app.route(
            "/api/compromised/accounts/<int:account_id>/validate",
            methods=["POST"],
        )
        def validate_compromised_account(account_id):
            """API endpoint to validate a compromised account."""
            try:
                result = self.compromised_account_service.validate_compromised_account(
                    account_id
                )

                if result["success"]:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(f"Failed to validate compromised account: {str(e)}")
                return (
                    jsonify(
                        {"error": f"Failed to validate compromised account: {str(e)}"}
                    ),
                    500,
                )

        @self.app.route(
            "/api/compromised/accounts/<int:account_id>/analyze",
            methods=["POST"],
        )
        def mark_compromised_account_analyzed(account_id):
            """API endpoint to mark a compromised account as analyzed."""
            try:
                result = self.compromised_account_service.mark_account_analyzed(
                    account_id
                )

                if result["success"]:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(
                    f"Failed to mark compromised account as analyzed: {str(e)}"
                )
                return (
                    jsonify({"error": f"Failed to mark as analyzed: {str(e)}"}),
                    500,
                )

        @self.app.route(
            "/api/compromised/accounts/<int:account_id>/unanalyze",
            methods=["POST"],
        )
        def unmark_compromised_account_analyzed(account_id):
            """API endpoint to unmark a compromised account as analyzed."""
            try:
                result = self.compromised_account_service.mark_account_unanalyzed(
                    account_id
                )

                if result["success"]:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(
                    f"Failed to unmark compromised account as analyzed: {str(e)}"
                )
                return (
                    jsonify({"error": f"Failed to unmark as analyzed: {str(e)}"}),
                    500,
                )

        @self.app.route(
            "/api/compromised/accounts/<int:account_id>", methods=["DELETE"]
        )
        def remove_compromised_account(account_id):
            """API endpoint to remove a compromised account."""
            try:
                result = self.compromised_account_service.remove_compromised_account(
                    account_id
                )

                if result["success"]:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400

            except Exception as e:
                self.logger.error(f"Failed to remove compromised account: {str(e)}")
                return (
                    jsonify(
                        {"error": f"Failed to remove compromised account: {str(e)}"}
                    ),
                    500,
                )

        @self.app.route("/api/compromised/statistics", methods=["GET"])
        def get_compromised_statistics():
            """API endpoint to get compromised account statistics."""
            try:
                stats = self.compromised_account_service.get_statistics()
                return jsonify(stats), 200
            except Exception as e:
                self.logger.error(
                    f"Failed to get compromised account statistics: {str(e)}"
                )
                return (
                    jsonify({"error": f"Failed to get statistics: {str(e)}"}),
                    500,
                )
