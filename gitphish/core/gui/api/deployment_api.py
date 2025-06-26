"""
API endpoints for deployment management.
"""

import logging
from datetime import datetime
from flask import request, jsonify
from threading import Thread
from typing import Dict, Any, Optional

from gitphish.config.deployment import DeploymentConfig
from gitphish.core.deployment.services.deployment_service import (
    DeploymentService,
)
from gitphish.core.accounts.services.deployer_service import (
    DeployerGitHubAccountService,
)
from gitphish.core.deployment.factory import create_deployer
from gitphish.core.accounts.clients.github_client import GitHubClient
from gitphish.models.github_pages.deployment import (
    GitHubDeployment,
    DeploymentStatus,
)
from gitphish.models.database import db_session_scope


class DeploymentAPI:
    """API endpoints for deployment management."""

    def __init__(
        self,
        app,
        deployment_service: DeploymentService,
        github_account_service: DeployerGitHubAccountService,
    ):
        self.app = app
        self.deployment_service = deployment_service
        self.github_account_service = github_account_service
        self.logger = logging.getLogger(__name__)
        self._setup_routes()

    def _setup_routes(self):
        """Setup Flask routes for deployment API."""

        @self.app.route("/api/deployment/deploy", methods=["POST"])
        def deploy_github_pages():
            """API endpoint to deploy a landing page to GitHub Pages."""
            try:
                data = request.get_json()

                # Validate required fields
                required_fields = ["account_id", "ingest_url", "repo_name"]
                for field in required_fields:
                    if not data.get(field):
                        return (
                            jsonify({"error": f"Missing required field: {field}"}),
                            400,
                        )

                # Get the GitHub token from the account service
                account_id = data["account_id"]
                github_token = self.github_account_service.get_account_token(account_id)

                if not github_token:
                    return (
                        jsonify(
                            {
                                "error": "GitHub account token not available. Please re-add the account."
                            }
                        ),
                        400,
                    )

                # Validate the GitHub token and get username first
                github_client = GitHubClient(github_token)
                token_info = github_client.validate_token()

                if not token_info.is_valid:
                    return (
                        jsonify(
                            {
                                "error": f"Invalid GitHub token: {token_info.error_message}"
                            }
                        ),
                        400,
                    )

                # Create deployment record first to get ID
                with db_session_scope() as session:
                    # Check if deployment already exists
                    existing = GitHubDeployment.get_by_repo_name(
                        session, data["repo_name"], token_info.username
                    )

                    if existing:
                        # Reactivate/update the existing deployment
                        existing.status = DeploymentStatus.PENDING
                        existing.updated_at = datetime.utcnow()
                        existing.repo_description = data.get(
                            "repo_description", "GitHub Verification Portal"
                        )
                        existing.account_id = account_id
                        existing.ingest_url = data["ingest_url"]
                        existing.template_preset = data.get(
                            "template_preset", "default"
                        )
                        existing.org_name = data.get("org_name")
                        existing.custom_title = data.get("custom_title")
                        existing.github_token_used = (
                            f"{github_token[:4]}...{github_token[-4:]}"
                            if len(github_token) > 8
                            else "***"
                        )
                        existing.is_active = True
                        existing.pages_enabled = False
                        existing.error_message = None
                        session.commit()
                        deployment_id = existing.id
                    else:
                        # Create new deployment record
                        deployment_record = GitHubDeployment(
                            repo_name=data["repo_name"],
                            repo_description=data.get(
                                "repo_description", "GitHub Verification Portal"
                            ),
                            github_username=token_info.username,
                            account_id=account_id,
                            ingest_url=data["ingest_url"],
                            template_preset=data.get("template_preset", "default"),
                            org_name=data.get("org_name"),
                            custom_title=data.get("custom_title"),
                            status=DeploymentStatus.PENDING,
                            github_token_used=(
                                f"{github_token[:4]}...{github_token[-4:]}"
                                if len(github_token) > 8
                                else "***"
                            ),
                        )
                        session.add(deployment_record)
                        session.commit()
                        deployment_id = deployment_record.id

                deployment_config = DeploymentConfig(
                    github_token=github_token,
                    ingest_url=data["ingest_url"],
                    repo_name=data["repo_name"],
                    repo_description=data.get(
                        "repo_description", "GitHub Verification Portal"
                    ),
                    username=data.get("username"),
                    template_preset=data.get("template_preset", "default"),
                    org_name=data.get("org_name"),
                    custom_title=data.get("custom_title"),
                )

                # Start deployment in background using the deployment service
                deployment_thread = Thread(
                    target=self._run_deployment_with_existing_record,
                    args=(
                        deployment_id,
                        deployment_config,
                        data.get("poll_deployment", True),
                        data.get("poll_timeout", 300),
                    ),
                    daemon=True,
                )
                deployment_thread.start()

                return jsonify(
                    {
                        "success": True,
                        "message": f'Deployment started for repository: {data["repo_name"]}',
                        "deployment_id": deployment_id,
                    }
                )

            except Exception as e:
                self.logger.error(f"Failed to start deployment: {str(e)}")
                return (
                    jsonify({"error": f"Failed to start deployment: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/deployment/delete/<repo_name>", methods=["DELETE"])
        def delete_deployment_by_repo(repo_name):
            """API endpoint to delete a GitHub Pages repository using stored account token."""
            try:
                # Use the method that looks up the stored account token
                result = self.deployment_service.delete_deployment(repo_name)

                if result["success"]:
                    return jsonify(result)
                else:
                    return jsonify({"error": result["error"]}), 400

            except Exception as e:
                self.logger.error(f"Failed to delete deployment: {str(e)}")
                return (
                    jsonify({"error": f"Failed to delete deployment: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/deployment/status")
        def get_deployment_status():
            """API endpoint to get deployment status."""
            return jsonify(self._get_deployment_status_from_db())

        @self.app.route("/api/deployment/progress/<int:deployment_id>")
        def get_deployment_progress(deployment_id):
            """API endpoint to get detailed deployment progress."""
            try:
                deployment = self.deployment_service.get_deployment_by_id(deployment_id)
                if not deployment:
                    return jsonify({"error": "Deployment not found"}), 404

                return jsonify(
                    {
                        "deployment": deployment,
                        "progress": self._calculate_deployment_progress(deployment),
                    }
                )
            except Exception as e:
                self.logger.error(f"Failed to get deployment progress: {str(e)}")
                return (
                    jsonify({"error": f"Failed to get deployment progress: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/deployment/latest")
        def get_latest_deployment():
            """API endpoint to get the latest deployment for progress monitoring."""
            try:
                recent_deployments = self.deployment_service.get_recent_deployments(
                    limit=1
                )
                if not recent_deployments:
                    return jsonify({"error": "No deployments found"}), 404

                latest = recent_deployments[0]
                return jsonify(
                    {
                        "deployment": latest,
                        "progress": self._calculate_deployment_progress(latest),
                    }
                )
            except Exception as e:
                self.logger.error(f"Failed to get latest deployment: {str(e)}")
                return (
                    jsonify({"error": f"Failed to get latest deployment: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/deployment/health/<int:deployment_id>", methods=["GET"])
        def check_deployment_health(deployment_id):
            """API endpoint to check the health of a deployment's GitHub Pages site (backend, reliable)."""
            try:
                # Get deployment info
                deployment = self.deployment_service.get_deployment_by_id(deployment_id)
                if not deployment:
                    return (
                        jsonify(
                            {
                                "status": "unknown",
                                "message": "Deployment not found",
                            }
                        ),
                        404,
                    )
                pages_url = deployment.get("pages_url")
                account_id = deployment.get("account_id")
                if not pages_url or not account_id:
                    return (
                        jsonify(
                            {
                                "status": "unknown",
                                "message": "Missing pages URL or account ID",
                            }
                        ),
                        400,
                    )

                # Get the GitHub token for the account
                token = self.github_account_service.get_account_token(account_id)
                if not token:
                    return (
                        jsonify(
                            {
                                "status": "unknown",
                                "message": "GitHub token not available for this account",
                            }
                        ),
                        400,
                    )

                # Use backend health check
                deployment_config = DeploymentConfig(
                    github_token=token,
                    repo_name=deployment.get("repo_name", ""),
                )
                deployer = create_deployer(deployment_config, cleanup_mode=True)
                is_live = deployer._test_page_accessibility(pages_url)
                if is_live:
                    return jsonify({"status": "live", "message": "Page is accessible"})
                else:
                    return jsonify(
                        {"status": "down", "message": "Page is not accessible"}
                    )
            except Exception as e:
                self.logger.error(
                    f"Health check failed for deployment {deployment_id}: {str(e)}"
                )
                return (
                    jsonify(
                        {
                            "status": "unknown",
                            "message": f"Health check error: {str(e)}",
                        }
                    ),
                    500,
                )

    def _run_deployment_with_existing_record(
        self,
        deployment_id: int,
        deployment_config: DeploymentConfig,
        poll_deployment: bool = True,
        poll_timeout: int = 300,
    ):
        """Run GitHub Pages deployment in background thread with existing deployment record."""
        try:
            self.logger.debug(
                f"Starting deployment for repository: {deployment_config.repo_name} (ID: {deployment_id})"
            )

            # Update status to in_progress
            self._update_deployment_status(deployment_id, DeploymentStatus.IN_PROGRESS)

            # Perform the actual deployment
            deployer = create_deployer(deployment_config)
            deployment_result = deployer.deploy(
                poll_deployment=poll_deployment, poll_timeout=poll_timeout
            )

            # Update deployment record with results
            with db_session_scope() as session:
                deployment_record = session.get(GitHubDeployment, deployment_id)
                if deployment_record:
                    # Update with deployment results
                    deployment_record.repo_url = deployment_result.get("repo_url")
                    deployment_record.pages_url = deployment_result.get("pages_url")
                    deployment_record.github_username = deployment_result.get(
                        "username"
                    )

                    # Update status based on result
                    if deployment_result.get("status") == "success":
                        deployment_record.update_status(DeploymentStatus.ACTIVE)
                        deployment_record.pages_enabled = True
                        deployment_record.deployed_at = datetime.utcnow()

                        # Store deployment timing if available
                        if "deployment_status" in deployment_result:
                            deployment_time = deployment_result[
                                "deployment_status"
                            ].get("deployment_time")
                            if deployment_time:
                                deployment_record.deployment_time_seconds = int(
                                    deployment_time
                                )

                        deployment_record.deployment_metadata = deployment_result.get(
                            "deployment_status"
                        )
                    else:
                        deployment_record.update_status(
                            DeploymentStatus.FAILED,
                            error_message="Deployment failed - check logs for details",
                        )

                    session.commit()
                    self.logger.debug(
                        f"Updated deployment record {deployment_id} with status: {deployment_record.status.value}"
                    )

            if deployment_result.get("status") == "success":
                self.logger.debug(
                    f"Deployment completed successfully for {deployment_config.repo_name}"
                )
            else:
                self.logger.error(
                    f"Deployment failed for {deployment_config.repo_name}: "
                    f"{deployment_result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            self.logger.error(
                f"Deployment failed for {deployment_config.repo_name}: {str(e)}"
            )

            # Update database record with failure
            try:
                self._update_deployment_status(
                    deployment_id,
                    DeploymentStatus.FAILED,
                    error_message=str(e),
                )
            except Exception as db_error:
                self.logger.error(
                    f"Failed to update deployment status in database: {str(db_error)}"
                )

    def _update_deployment_status(
        self,
        deployment_id: int,
        status: DeploymentStatus,
        error_message: Optional[str] = None,
    ):
        """Update deployment status in the database."""
        try:
            with db_session_scope() as session:
                deployment = session.get(GitHubDeployment, deployment_id)
                if deployment:
                    deployment.update_status(status, error_message)
                    session.commit()
                    self.logger.debug(
                        f"Updated deployment {deployment_id} status to {status.value}"
                    )
        except Exception as e:
            self.logger.error(f"Failed to update deployment status: {str(e)}")

    def _get_deployment_status_from_db(self) -> Dict:
        """Get deployment status information from database."""
        try:
            # Get deployment statistics
            stats = self.deployment_service.get_deployment_stats()

            # Get recent deployments
            recent_deployments = self.deployment_service.get_recent_deployments(
                limit=10
            )

            # Format all deployments for frontend
            formatted_deployments = []
            for deployment in recent_deployments:
                formatted_deployments.append(
                    {
                        "id": deployment["id"],
                        "timestamp": (
                            deployment["created_at"][:8]
                            if deployment["created_at"]
                            else "Unknown"
                        ),
                        "repo_name": deployment["repo_name"],
                        "preset": deployment["template_preset"],
                        "pages_url": deployment["pages_url"],
                        "status": deployment["status"],
                        "github_username": deployment["github_username"],
                        "deployed_at": deployment["deployed_at"],
                        "is_active": deployment["is_active"],
                    }
                )

            # Filter for active deployments (pending, in_progress, active)
            active_statuses = {"pending", "in_progress", "active"}
            active_deployments = [
                d
                for d in formatted_deployments
                if (d["status"] or "").lower() in active_statuses
            ]

            return {
                "recent_deployments": formatted_deployments,
                "active_deployments": active_deployments,
                "total_deployments": stats["total_deployments"],
                "successful_deployments": stats["successful_deployments"],
                "failed_deployments": stats["failed_deployments"],
                "success_rate": stats["success_rate"],
            }

        except Exception as e:
            self.logger.error(
                f"Error getting deployment status from database: {str(e)}"
            )
            return {
                "recent_deployments": [],
                "total_deployments": 0,
                "successful_deployments": 0,
                "failed_deployments": 0,
                "active_deployments": [],
                "success_rate": 0,
            }

    def _calculate_deployment_progress(
        self, deployment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate deployment progress based on status and timing.

        Args:
            deployment: Deployment dictionary

        Returns:
            Progress information dictionary
        """
        status = deployment.get("status", "pending")
        created_at = deployment.get("created_at")

        # Calculate elapsed time
        elapsed_seconds = 0
        if created_at:
            try:
                from datetime import datetime

                created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                current_time = datetime.utcnow()
                elapsed_seconds = (current_time - created_time).total_seconds()
            except Exception:
                elapsed_seconds = 0

        # Define progress stages and their typical durations
        stages = [
            {
                "id": "validation",
                "name": "Validating GitHub token",
                "duration": 5,
            },
            {
                "id": "repository",
                "name": "Creating repository",
                "duration": 10,
            },
            {"id": "content", "name": "Uploading content", "duration": 15},
            {"id": "pages", "name": "Enabling GitHub Pages", "duration": 10},
            {
                "id": "deployment",
                "name": "Deploying to GitHub Pages",
                "duration": 30,
            },
            {
                "id": "verification",
                "name": "Verifying deployment",
                "duration": 10,
            },
        ]

        # Calculate progress based on status and elapsed time
        if status == "pending":
            return {
                "percentage": 0,
                "current_stage": "validation",
                "stage_status": "pending",
                "message": "Deployment queued",
                "stages": stages,
                "elapsed_seconds": elapsed_seconds,
            }
        elif status == "in_progress":
            # Calculate progress based on elapsed time
            total_duration = sum(stage["duration"] for stage in stages)
            progress_percentage = min(85, (elapsed_seconds / total_duration) * 100)

            # Determine current stage
            cumulative_time = 0
            current_stage = "validation"
            for stage in stages[:-1]:  # Exclude verification stage for in_progress
                cumulative_time += stage["duration"]
                if elapsed_seconds <= cumulative_time:
                    current_stage = stage["id"]
                    break
                current_stage = stage["id"]

            return {
                "percentage": int(progress_percentage),
                "current_stage": current_stage,
                "stage_status": "in_progress",
                "message": f"Deployment in progress - {current_stage}",
                "stages": stages,
                "elapsed_seconds": elapsed_seconds,
            }
        elif status == "active":
            return {
                "percentage": 100,
                "current_stage": "verification",
                "stage_status": "completed",
                "message": "Deployment completed successfully",
                "stages": stages,
                "elapsed_seconds": elapsed_seconds,
                "pages_url": deployment.get("pages_url"),
            }
        elif status == "failed":
            # Determine which stage failed based on elapsed time
            cumulative_time = 0
            failed_stage = "validation"
            for stage in stages:
                cumulative_time += stage["duration"]
                if elapsed_seconds <= cumulative_time:
                    failed_stage = stage["id"]
                    break
                failed_stage = stage["id"]

            return {
                "percentage": 0,
                "current_stage": failed_stage,
                "stage_status": "failed",
                "message": f"Deployment failed during {failed_stage}",
                "stages": stages,
                "elapsed_seconds": elapsed_seconds,
                "error_message": deployment.get("error_message"),
            }
        else:
            return {
                "percentage": 0,
                "current_stage": "validation",
                "stage_status": "unknown",
                "message": f"Unknown status: {status}",
                "stages": stages,
                "elapsed_seconds": elapsed_seconds,
            }
