"""
Deployment service for managing deployments with database integration.

This service provides a high-level interface for managing deployments,
including database persistence and status tracking.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import os

from gitphish.models.github_pages.deployment import (
    GitHubDeployment,
    DeploymentStatus,
)
from gitphish.models.database import db_session_scope
from gitphish.config.deployment import DeploymentConfig
from gitphish.core.deployment.factory import create_deployer
from gitphish.core.accounts.clients.github_client import GitHubClient
from gitphish.core.accounts.services.deployer_service import (
    DeployerGitHubAccountService,
)
from gitphish.core.server.server import GitHubAuthServer

logger = logging.getLogger(__name__)


class DeploymentService:
    """
    Service for managing deployments with database persistence.

    This service acts as a bridge between the deployment logic and the database,
    providing a clean interface for deployment operations that supports multiple
    deployment types.
    """

    def __init__(self):
        """Initialize the deployment service."""
        pass

    def create_deployment(
        self,
        config: DeploymentConfig,
        poll_deployment: bool = True,
        poll_timeout: int = 300,
        account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a new deployment and store it in the database.
        """
        deployment_record = None
        deployment_record_dict = None  # Store dict version for error handling

        try:
            # First, validate the GitHub token and get username
            github_client = GitHubClient(config.github_token)
            token_info = github_client.validate_token()

            if not token_info.is_valid:
                logger.error(f"Invalid GitHub token: {token_info.error_message}")
                return {
                    "success": False,
                    "error": f"Invalid GitHub token: {token_info.error_message}",
                }

            # Use the validated username from the token
            actual_username = token_info.username
            logger.debug(f"Validated GitHub token for user: {actual_username}")

            # Create initial database record
            with db_session_scope() as session:
                # Check if deployment already exists
                existing = GitHubDeployment.get_by_repo_name(
                    session, config.repo_name, actual_username
                )
                if existing and existing.is_active:
                    # Check if the repo actually exists on GitHub
                    github_client = GitHubClient(config.github_token)
                    repo_exists = github_client.repository_exists(
                        config.repo_name, actual_username
                    )
                    if not repo_exists:
                        # Mark DB record as inactive and proceed
                        existing.is_active = False
                        session.commit()
                        logger.warning(
                            f"Stale DB record for {config.repo_name} marked inactive; "
                            "repo not found on GitHub."
                        )
                    else:
                        logger.warning(
                            f"Active deployment already exists for "
                            f"{config.repo_name}"
                        )
                        return {
                            "success": False,
                            "error": (
                                f"Active deployment already exists for repository "
                                f"{config.repo_name}"
                            ),
                            "existing_deployment": existing.to_dict(),
                        }
                if existing and not existing.is_active:
                    deployment_record = existing
                    deployment_record.repo_description = config.repo_description
                    deployment_record.account_id = account_id
                    deployment_record.ingest_url = config.ingest_url
                    deployment_record.template_preset = getattr(
                        config, "template_preset", None
                    )
                    deployment_record.org_name = getattr(config, "org_name", None)
                    deployment_record.custom_title = getattr(
                        config, "custom_title", None
                    )
                    deployment_record.status = DeploymentStatus.PENDING
                    deployment_record.github_token_used = (
                        f"{config.github_token[:4]}...{config.github_token[-4:]}"
                        if len(config.github_token) > 8
                        else "***"
                    )
                    deployment_record.is_active = True
                    deployment_record.pages_enabled = False
                    deployment_record.repo_url = None
                    deployment_record.pages_url = None
                    deployment_record.deployed_at = None
                    deployment_record.deployment_time_seconds = None
                    deployment_record.deployment_metadata = None
                    deployment_record.error_message = None
                    session.commit()
                    deployment_id = deployment_record.id
                    logger.debug(
                        f"Reused inactive deployment record with ID: {deployment_id}"
                    )
                else:
                    deployment_record = GitHubDeployment(
                        repo_name=config.repo_name,
                        repo_description=config.repo_description,
                        github_username=actual_username,  # Use validated username
                        account_id=account_id,  # Store the account ID for future reference
                        ingest_url=config.ingest_url,
                        template_preset=getattr(config, "template_preset", None),
                        org_name=getattr(config, "org_name", None),
                        custom_title=getattr(config, "custom_title", None),
                        status=DeploymentStatus.PENDING,
                        github_token_used=(
                            f"{config.github_token[:4]}...{config.github_token[-4:]}"
                            if len(config.github_token) > 8
                            else "***"
                        ),
                    )
                    session.add(deployment_record)
                    session.commit()
                    deployment_id = deployment_record.id
                    logger.debug(f"Created deployment record with ID: {deployment_id}")
                # Save dict version for error handling
                deployment_record_dict = deployment_record.to_dict()

            # Update status to in progress
            self._update_deployment_status(deployment_id, DeploymentStatus.IN_PROGRESS)

            # Create the appropriate deployer using the factory
            deployer = create_deployer(config)

            # Perform the actual deployment
            deployment_result = deployer.deploy(
                poll_deployment=poll_deployment, poll_timeout=poll_timeout
            )

            # Update deployment record with results
            with db_session_scope() as session:
                deployment_record = session.get(GitHubDeployment, deployment_id)
                if deployment_record:
                    # Update with deployment results
                    deployment_record.repo_url = deployment_result.get("repo_url")
                    pages_url = deployment_result.get(
                        "deployment_url"
                    ) or deployment_result.get("pages_url")
                    deployment_record.pages_url = pages_url
                    deployment_record.github_username = deployment_result.get(
                        "username"
                    )

                    # Update status based on result
                    if deployment_result.get("status") == "success":
                        deployment_record.update_status(DeploymentStatus.ACTIVE)
                        deployment_record.pages_enabled = True
                        deployment_record.deployed_at = datetime.utcnow()

                        # Store deployment timing if available
                        deployment_status = deployment_result.get("deployment_status")
                        if deployment_status and deployment_status.get(
                            "deployment_time"
                        ):
                            deployment_record.deployment_time_seconds = int(
                                deployment_status["deployment_time"]
                            )

                        deployment_record.deployment_metadata = deployment_status
                    else:
                        error_message = deployment_result.get(
                            "error",
                            "Deployment failed - check logs for details",
                        )
                        deployment_record.update_status(
                            DeploymentStatus.FAILED,
                            error_message=error_message,
                        )

                    session.commit()

                    logger.debug(
                        f"Updated deployment record {deployment_id} with status: {deployment_record.status.value}"
                    )
                    deployment_record_dict = deployment_record.to_dict()
                    return {
                        "success": deployment_result.get("status") == "success",
                        "deployment_result": deployment_result,
                        "database_record": deployment_record_dict,
                    }

        except Exception as e:
            logger.error(f"Deployment failed: {str(e)}")

            # Update database record with failure
            if deployment_record_dict:
                return {
                    "success": False,
                    "error": str(e),
                    "database_record": deployment_record_dict,
                }
            else:
                return {
                    "success": False,
                    "error": str(e),
                    "database_record": None,
                }

    def delete_deployment(
        self,
        repo_name: str,
        github_username: Optional[str] = None,
        github_token: Optional[str] = None,
        hard: bool = False,
    ) -> Dict[str, Any]:
        """
        Delete a deployment using the appropriate deployer and mark it as inactive, or hard delete if requested.

        Args:
            repo_name: Name of the repository to delete
            github_username: Optional username filter
            github_token: Optional GitHub token to use for deletion
            hard: If True, hard delete the record from the DB

        Returns:
            Dictionary containing deletion result
        """
        try:
            with db_session_scope() as session:
                # Find the deployment record
                deployment = GitHubDeployment.get_by_repo_name(
                    session, repo_name, github_username
                )

                # If deployment record exists, try to get token from stored account
                if deployment and not github_token and deployment.account_id:
                    account_service = DeployerGitHubAccountService()
                    try:
                        account = account_service.get_account_by_id(
                            deployment.account_id
                        )
                        if account:
                            logger.debug(
                                f"Found account for ID {deployment.account_id}: {account.get('username', 'Unknown')}"
                            )
                        else:
                            logger.warning(
                                f"No account found for ID {deployment.account_id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error checking account {deployment.account_id}: {str(e)}"
                        )

                    stored_token = account_service.get_account_token(
                        deployment.account_id
                    )
                    logger.debug(
                        f"Retrieved token for account {deployment.account_id}: "
                        f"{'Found' if stored_token else 'Not found'}"
                    )

                    if stored_token:
                        github_token = stored_token
                    else:
                        # Try to find account by username as fallback
                        logger.debug(
                            "Attempting fallback: looking for account by "
                            f"username '{deployment.github_username}'"
                        )
                        try:
                            accounts = account_service.get_all_accounts()
                            matching_account = None
                            for acc in accounts:
                                if acc.get("username") == deployment.github_username:
                                    matching_account = acc
                                    logger.debug(
                                        "Found matching account by username: "
                                        f"{acc.get('username')} (ID: {acc.get('id')})"
                                    )
                                    break

                            if matching_account:
                                fallback_token = account_service.get_account_token(
                                    matching_account["id"]
                                )
                                logger.debug(
                                    f"Fallback token retrieval for account {matching_account['id']}: "
                                    f"{'Found' if fallback_token else 'Not found'}"
                                )
                                if fallback_token:
                                    github_token = fallback_token
                                    logger.debug(
                                        "Successfully retrieved token using "
                                        f"fallback method for {deployment.github_username}"
                                    )
                                    # Update deployment record with correct account_id
                                    deployment.account_id = matching_account["id"]
                                    session.commit()
                                    logger.debug(
                                        f"Updated deployment {repo_name} account_id "
                                        f"from {deployment.account_id} to {matching_account['id']}"
                                    )
                                else:
                                    logger.warning(
                                        "Fallback failed: Token not in cache "
                                        f"for account {matching_account['id']} ({matching_account['username']})"
                                    )
                        except Exception as e:
                            logger.error(f"Fallback account lookup failed: {str(e)}")

                # Check if we have a token to proceed
                if not github_token:
                    if deployment and deployment.account_id:
                        return {
                            "success": False,
                            "error": "GitHub account token not available for "
                            f"deployment {repo_name}. The token cache was "
                            "cleared when the server restarted. Please re-add "
                            f'the GitHub account "{deployment.github_username}" '
                            "to restore the token, then try deleting again. "
                            f"Original account_id: {deployment.account_id}",
                        }
                    else:
                        return {
                            "success": False,
                            "error": "No GitHub token available for deletion. "
                            "Please provide a GitHub token via --github-token "
                            "or GITHUB_DEPLOY_TOKEN environment variable.",
                        }

                # Create a minimal config for the deployer
                cleanup_config = DeploymentConfig(
                    github_token=github_token, repo_name=repo_name
                )

                # Create the appropriate deployer for cleanup
                deployer = create_deployer(cleanup_config, cleanup_mode=True)

                # Perform cleanup
                cleanup_result = deployer.cleanup()
                repo_not_found = (
                    not cleanup_result.get("success")
                    and "not found" in cleanup_result.get("error", "").lower()
                )

                message = ""
                if deployment:
                    if hard:
                        session.delete(deployment)
                        session.commit()
                        message = f"Deployment record for {repo_name} hard deleted from database."
                        return {"success": True, "message": message}
                    deployment.is_active = False
                    deployment.status = DeploymentStatus.INACTIVE
                    deployment.pages_enabled = False
                    session.commit()
                    if repo_not_found:
                        logger.debug(
                            f"Repo not found on GitHub, marked deployment as inactive: "
                            f"{repo_name}"
                        )
                        message = (
                            f"Repository {repo_name} not found on GitHub; "
                            "deployment marked as inactive."
                        )
                    else:
                        logger.debug(
                            f"Successfully marked deployment as inactive: {repo_name}"
                        )
                        message = cleanup_result.get(
                            "message",
                            f"Repository {repo_name} deleted and marked as inactive.",
                        )
                else:
                    if repo_not_found:
                        logger.debug(
                            f"Repo not found on GitHub, no deployment record to mark inactive: "
                            f"{repo_name}"
                        )
                        message = (
                            f"Repository {repo_name} not found on GitHub and "
                            "no deployment record found."
                        )
                    else:
                        logger.debug(
                            f"Successfully deleted repository without deployment record: "
                            f"{repo_name}"
                        )
                        message = cleanup_result.get(
                            "message",
                            f"Repository {repo_name} deleted successfully",
                        )

                return {"success": True, "message": message}

        except Exception as e:
            logger.error(f"Failed to delete deployment: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_deployment_by_repo(
        self, repo_name: str, github_username: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get deployment information by repository name.

        Args:
            repo_name: Repository name
            github_username: Optional username filter

        Returns:
            Deployment dictionary or None
        """
        try:
            with db_session_scope() as session:
                deployment = GitHubDeployment.get_by_repo_name(
                    session, repo_name, github_username
                )
                return deployment.to_dict() if deployment else None
        except Exception as e:
            logger.error(f"Failed to get deployment for {repo_name}: {str(e)}")
            return None

    def get_deployment_by_id(self, deployment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get deployment information by ID.

        Args:
            deployment_id: Deployment ID

        Returns:
            Deployment dictionary or None
        """
        try:
            with db_session_scope() as session:
                deployment = session.get(GitHubDeployment, deployment_id)
                return deployment.to_dict() if deployment else None
        except Exception as e:
            logger.error(f"Failed to get deployment {deployment_id}: {str(e)}")
            return None

    def get_recent_deployments(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent deployments.

        Args:
            limit: Maximum number of deployments to return

        Returns:
            List of deployment dictionaries
        """
        try:
            with db_session_scope() as session:
                deployments = GitHubDeployment.get_recent_deployments(session, limit)
                return [deployment.to_dict() for deployment in deployments]
        except Exception as e:
            logger.error(f"Failed to get recent deployments: {str(e)}")
            return []

    def get_active_deployments(self) -> List[Dict[str, Any]]:
        """
        Get all active deployments.

        Returns:
            List of active deployment dictionaries
        """
        try:
            with db_session_scope() as session:
                deployments = GitHubDeployment.get_active_deployments(session)
                return [deployment.to_dict() for deployment in deployments]
        except Exception as e:
            logger.error(f"Failed to get active deployments: {str(e)}")
            return []

    def get_deployment_stats(self) -> Dict[str, Any]:
        """
        Get deployment statistics.

        Returns:
            Dictionary containing deployment statistics
        """
        try:
            with db_session_scope() as session:
                return GitHubDeployment.get_deployment_stats(session)
        except Exception as e:
            logger.error(f"Failed to get deployment stats: {str(e)}")
            return {
                "total_deployments": 0,
                "successful_deployments": 0,
                "failed_deployments": 0,
                "active_deployments": 0,
                "success_rate": 0,
            }

    def _update_deployment_status(
        self,
        deployment_id: int,
        status: DeploymentStatus,
        error_message: Optional[str] = None,
    ):
        """
        Update deployment status in the database.

        Args:
            deployment_id: ID of the deployment to update
            status: New status
            error_message: Optional error message
        """
        try:
            with db_session_scope() as session:
                deployment = session.get(GitHubDeployment, deployment_id)
                if deployment:
                    deployment.update_status(status, error_message)
                    session.commit()
                    logger.debug(
                        f"Updated deployment {deployment_id} status to {status.value}"
                    )
        except Exception as e:
            logger.error(f"Failed to update deployment status: {str(e)}")

    def get_deployments_by_type(self, deployment_type: str) -> List[Dict[str, Any]]:
        """
        Get deployments filtered by deployment type.

        Args:
            deployment_type: Type of deployment ('github_pages')

        Returns:
            List of deployment dictionaries
        """
        try:

            # Default to GitHub Pages deployments
            with db_session_scope() as session:
                deployments = (
                    session.query(GitHubDeployment)
                    .order_by(GitHubDeployment.created_at.desc())
                    .all()
                )
                result = []
                for deployment in deployments:
                    try:
                        result.append(deployment.to_dict())
                    except Exception as e:
                        logger.error(
                            f"Error converting GitHub Pages deployment {deployment.id} to dict: {str(e)}"
                        )
                        # Add a minimal dict for GitHub Pages deployments too
                        try:
                            result.append(
                                {
                                    "id": deployment.id,
                                    "repo_name": getattr(
                                        deployment, "repo_name", "Unknown"
                                    ),
                                    "status": "error",
                                    "created_at": getattr(
                                        deployment,
                                        "created_at",
                                        datetime.utcnow(),
                                    ).isoformat(),
                                    "error": f"Serialization error: {str(e)}",
                                }
                            )
                        except Exception as inner_e:
                            logger.error(
                                f"Failed to create minimal dict for GitHub Pages deployment {deployment.id}: {inner_e}"
                            )
                            continue
                return result
        except Exception as e:
            logger.error(
                f"Failed to get deployments by type {deployment_type}: {str(e)}"
            )
            return []

    def save_deployment(
        self,
        repo_name: str,
        deployment_type: str,
        status: str,
        config_data: Dict[str, Any],
        deployment_metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Save a deployment record in the database.

        Args:
            repo_name: Repository name
            deployment_type: Type of deployment
            status: Deployment status
            config_data: Configuration data used for deployment
            deployment_metadata: Additional metadata

        Returns:
            Dictionary with result information
        """
        try:
            # Handle GitHub Pages deployments (existing logic)
            logger.warning(
                f"save_deployment called for unsupported type: {deployment_type}"
            )
            return {
                "success": False,
                "error": f"Unsupported deployment type: {deployment_type}",
            }

        except Exception as e:
            logger.error(f"Failed to save deployment {repo_name}: {str(e)}")
            return {"success": False, "error": str(e)}

    def update_deployment_status(self, repo_name: str, status: str) -> Dict[str, Any]:
        """
        Update deployment status by repository name.

        Args:
            repo_name: Repository name
            status: New status

        Returns:
            Dictionary with result information
        """
        try:
            with db_session_scope() as session:
                # Try GitHub Pages deployment
                pages_deployment = GitHubDeployment.get_by_repo_name(session, repo_name)
                if pages_deployment:
                    # Map string status to DeploymentStatus enum
                    status_map = {
                        "stopped": DeploymentStatus.FAILED,  # No direct "stopped" status for pages
                        "running": DeploymentStatus.ACTIVE,
                        "failed": DeploymentStatus.FAILED,
                    }
                    deployment_status = status_map.get(status, DeploymentStatus.FAILED)
                    pages_deployment.update_status(deployment_status)
                    session.commit()

                    logger.debug(
                        f"Updated GitHub Pages deployment {repo_name} status to {status}"
                    )
                    return {
                        "success": True,
                        "message": f"Updated deployment {repo_name} status to {status}",
                    }

                return {
                    "success": False,
                    "error": f"Deployment {repo_name} not found",
                }

        except Exception as e:
            logger.error(
                f"Failed to update deployment status for {repo_name}: {str(e)}"
            )
            return {"success": False, "error": str(e)}

    def deploy_github_pages(
        self,
        repo_name,
        preset,
        ingest_url,
        custom_title=None,
        github_token=None,
        poll_deployment=True,
        poll_timeout=300,
    ):
        """Encapsulates GitHub Pages deployment logic (no CLI printing)."""
        if not github_token:
            github_token = os.getenv("GITHUB_DEPLOY_TOKEN")
        if not github_token:
            return {
                "success": False,
                "error": "GITHUB_DEPLOY_TOKEN environment variable required",
            }
        deployment_config = DeploymentConfig(
            github_token=github_token,
            ingest_url=ingest_url,
            repo_name=repo_name,
            template_preset=preset,
            custom_title=custom_title,
        )
        return self.create_deployment(
            config=deployment_config,
            poll_deployment=poll_deployment,
            poll_timeout=poll_timeout,
        )

    def start_auth_server(
        self, github_config, host, port, cert_path, key_path, dev_mode
    ):
        """Encapsulates Auth Server startup logic (no CLI printing). Returns the server and thread."""
        import threading
        import time

        try:
            server = GitHubAuthServer(
                github_config=github_config,
                host=host,
                port=port,
                cert_path=cert_path,
                key_path=key_path,
                dev_mode=dev_mode,
            )
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            time.sleep(3)  # Give server time to start
            return {"success": True, "server": server, "thread": thread}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cleanup_deployment(self, auth_server=None):
        """Encapsulates cleanup logic for deployment (no CLI printing)."""
        # Placeholder for future resource cleanup logic
        # If auth_server is provided, stop it (implement stop logic if available)
        # Currently just returns success
        return {"success": True}

    def get_all_deployments(self) -> List[Dict[str, Any]]:
        """
        Get all deployments, regardless of type or status.

        Returns:
            List of deployment dictionaries
        """
        try:
            with db_session_scope() as session:
                deployments = (
                    session.query(GitHubDeployment)
                    .order_by(GitHubDeployment.created_at.desc())
                    .all()
                )
                return [deployment.to_dict() for deployment in deployments]
        except Exception as e:
            logger.error(f"Failed to get all deployments: {str(e)}")
            return []

    def get_deployment_status(
        self, repo_name: str, github_username: str = None, github_token: str = None
    ):
        """
        Get the live deployment status from the deployer and update DB if needed.
        """
        try:
            with db_session_scope() as session:
                deployment = GitHubDeployment.get_by_repo_name(
                    session, repo_name, github_username
                )
                if not deployment:
                    return None

                config = DeploymentConfig(
                    github_token=github_token,
                    repo_name=deployment.repo_name,
                    username=deployment.github_username,
                    ingest_url=deployment.ingest_url,
                    template_preset=deployment.template_preset,
                    org_name=deployment.org_name,
                    custom_title=deployment.custom_title,
                )
                deployer = create_deployer(config)

                live_status = deployer.get_deployment_status().get("deployed")
                db_status = deployment.status.value if deployment.status else None

                if db_status == "active" and not live_status:
                    deployment.update_status(DeploymentStatus.INACTIVE)
                    session.commit()
                elif db_status != "active" and live_status:
                    deployment.update_status(DeploymentStatus.ACTIVE)
                    session.commit()
                return deployment.to_dict()
        except Exception as e:
            logger.error(f"Failed to get deployment status: {str(e)}")
            return None
