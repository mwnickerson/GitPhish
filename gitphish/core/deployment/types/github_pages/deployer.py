"""
GitHub Pages deployment implementation for GitPhish.

This module handles deployment of landing pages to GitHub Pages.
"""

import logging
import time
import requests
from typing import Dict, Any
from github import Github, GithubException
from github.Repository import Repository

from gitphish.core.deployment.types.base import BaseDeployer, DeploymentType
from gitphish.core.deployment.types.github_pages.templates.renderer import (
    TemplateRenderer,
)

logger = logging.getLogger(__name__)


class GitHubPagesDeployer(BaseDeployer):
    """GitHub Pages deployment implementation."""

    def __init__(self, config, cleanup_mode: bool = False):
        """
        Initialize the GitHub Pages deployer.

        Args:
            config: DeploymentConfig instance
            cleanup_mode: If True, skip deployment-specific validation
        """
        super().__init__(config)

        # Validate config unless in cleanup mode
        if not cleanup_mode:
            config.validate(cleanup_mode=cleanup_mode)

        # Initialize GitHub client
        try:
            self.token = config.github_token
            self.github = Github(self.token)
            # Test authentication
            self.user = self.github.get_user()
            self.logger.debug(
                f"GitHub Pages deployer initialized for user: {self.user.login}"
            )
        except Exception as e:
            self.logger.error(f"Failed to authenticate with GitHub: {str(e)}")
            raise

        # Initialize template renderer (only for non-cleanup operations)
        if not cleanup_mode:
            self.template_renderer = TemplateRenderer()

    @property
    def deployment_type(self) -> DeploymentType:
        """Return the deployment type this deployer handles."""
        return DeploymentType.GITHUB_PAGES

    def deploy(
        self,
        poll_deployment: bool = True,
        poll_timeout: int = 300,
        **template_kwargs,
    ) -> Dict[str, Any]:
        """
        Deploy the landing page to GitHub Pages.

        Args:
            poll_deployment: Whether to poll for deployment completion
            poll_timeout: Maximum time to wait for deployment in seconds
            **template_kwargs: Additional template variables

        Returns:
            Dictionary with deployment results
        """
        try:
            self._log_deployment_start()

            # Step 1: Render the template
            self.logger.debug(
                f"Rendering landing page template with preset: {self.config.template_preset}"
            )

            # Prepare template variables from config
            template_vars = {}
            if self.config.org_name:
                template_vars["org_name"] = self.config.org_name
            if self.config.custom_title:
                template_vars["page_title"] = self.config.custom_title
                template_vars["portal_title"] = self.config.custom_title

            # Merge with any additional kwargs
            template_vars.update(template_kwargs)

            html_content = self.template_renderer.render_with_preset(
                ingest_url=self.config.ingest_url,
                preset_name=self.config.template_preset,
                **template_vars,
            )

            # Step 2: Deploy to GitHub Pages
            self.logger.debug("Deploying to GitHub Pages...")

            # Use authenticated user if no username specified
            target_user = (
                self.config.username if self.config.username else self.user.login
            )

            self.logger.debug(
                f"Starting deployment to {target_user}/{self.config.repo_name}"
            )

            # Create repository
            repo = self._create_repository(
                self.config.repo_name,
                self.config.repo_description,
                target_user,
            )

            # Upload index.html
            self._upload_index_html(repo, html_content)

            # Enable GitHub Pages
            pages_url = self._enable_github_pages(repo)

            # Poll GitHub Actions to check deployment status (optional)
            deployment_status = None
            if poll_deployment:
                deployment_status = self._poll_pages_deployment(
                    repo, pages_url, poll_timeout
                )
            else:
                self.logger.debug(
                    "⏭️  Skipping deployment polling (--no-wait specified)"
                )

            self._log_deployment_success(pages_url)

            return {
                "status": "success",
                "deployment_url": pages_url,
                "repo_url": repo.html_url,
                "pages_url": pages_url,  # Keep for backward compatibility
                "repo_name": self.config.repo_name,
                "username": target_user,
                "deployment_status": deployment_status,
            }

        except Exception as e:
            self._log_deployment_error(str(e))
            return {
                "status": "failed",
                "error": str(e),
                "repo_name": self.config.repo_name,
                "username": getattr(self.config, "username", None),
            }

    def cleanup(self) -> Dict[str, Any]:
        """
        Clean up deployment by deleting the repository.

        Returns:
            Dictionary with cleanup results
        """
        try:
            self.logger.debug(f"Cleaning up repository: {self.config.repo_name}")
            success = self.delete_repository(self.config.repo_name)

            if success:
                return {
                    "success": True,
                    "message": f"Repository {self.config.repo_name} deleted successfully",
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to delete repository",
                }

        except Exception as e:
            self.logger.error(f"Cleanup failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_deployment_status(self) -> Dict[str, Any]:
        """
        Get current deployment status.

        Returns:
            Dictionary with status information
        """
        try:
            repos = self.list_repositories()
            repo_exists = self.config.repo_name in repos

            if repo_exists:
                deployment_url = (
                    f"https://{self.user.login}.github.io/{self.config.repo_name}"
                )
                return {
                    "deployed": True,
                    "deployment_url": deployment_url,
                    "repo_name": self.config.repo_name,
                    "username": self.user.login,
                }
            else:
                return {"deployed": False, "repo_name": self.config.repo_name}

        except Exception as e:
            self.logger.error(f"Failed to get deployment status: {str(e)}")
            return {"deployed": False, "error": str(e)}

    def validate_config(self) -> Dict[str, Any]:
        """
        Validate the GitHub Pages deployment configuration.

        Returns:
            Dictionary with validation results
        """
        result = super().validate_config()

        # GitHub Pages specific validation
        if (
            not hasattr(self.config, "template_preset")
            or not self.config.template_preset
        ):
            result["errors"].append(
                "Template preset is required for GitHub Pages deployment"
            )

        if not hasattr(self.config, "ingest_url") or not self.config.ingest_url:
            result["errors"].append(
                "Ingest URL is required for GitHub Pages deployment"
            )

        result["valid"] = len(result["errors"]) == 0
        return result

    # === Original GitHub Pages implementation methods ===

    def _create_repository(
        self, repo_name: str, description: str, username: str
    ) -> Repository:
        """
        Create a new GitHub repository.

        Args:
            repo_name: Name for the repository
            description: Repository description
            username: Username (for validation)

        Returns:
            Created Repository object
        """
        try:
            # Check if repo already exists
            try:
                existing_repo = self.user.get_repo(repo_name)
                self.logger.warning(
                    f"Repository {repo_name} already exists, using existing repo"
                )
                return existing_repo
            except GithubException as e:
                if e.status != 404:  # Not found is expected for new repos
                    raise

            # Create new repository
            repo = self.user.create_repo(
                name=repo_name,
                description=description,
                private=False,  # Must be public for GitHub Pages
                auto_init=False,  # We'll add our own content
            )

            self.logger.debug(f"Created repository: {repo.html_url}")
            return repo

        except Exception as e:
            self.logger.error(f"Failed to create repository {repo_name}: {str(e)}")
            raise

    def _upload_index_html(self, repo: Repository, html_content: str) -> None:
        """
        Upload index.html to the repository.

        Args:
            repo: GitHub Repository object
            html_content: HTML content to upload
        """
        try:
            # Check if index.html already exists
            try:
                existing_file = repo.get_contents("index.html")
                # Update existing file
                repo.update_file(
                    path="index.html",
                    message="Update landing page",
                    content=html_content,
                    sha=existing_file.sha,
                )
                self.logger.debug("Updated existing index.html")
            except GithubException as e:
                if e.status == 404:  # File doesn't exist, create it
                    repo.create_file(
                        path="index.html",
                        message="Add landing page",
                        content=html_content,
                    )
                    self.logger.debug("Created new index.html")
                else:
                    raise

        except Exception as e:
            self.logger.error(f"Failed to upload index.html: {str(e)}")
            raise

    def _enable_github_pages(self, repo: Repository) -> str:
        """
        Enable GitHub Pages for the repository using direct REST API calls.

        Args:
            repo: GitHub Repository object

        Returns:
            GitHub Pages URL
        """
        pages_url = f"https://{repo.owner.login}.github.io/{repo.name}"

        try:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            }

            # Create Pages configuration
            pages_config = {"source": {"branch": "main", "path": "/"}}

            # Enable GitHub Pages
            response = requests.post(
                f"https://api.github.com/repos/{repo.full_name}/pages",
                headers=headers,
                json=pages_config,
                timeout=30,
            )

            if response.status_code == 201:
                self.logger.debug(f"✅ GitHub Pages enabled for {repo.full_name}")
                self.logger.debug(f"🌐 Pages URL: {pages_url}")
            elif response.status_code == 409:
                self.logger.debug(
                    f"✅ GitHub Pages already enabled for {repo.full_name}"
                )
                self.logger.debug(f"🌐 Pages URL: {pages_url}")
            else:
                self.logger.warning(
                    f"⚠️  Unexpected response from GitHub Pages API: {response.status_code}"
                )
                self.logger.warning(f"Response: {response.text}")
                # Don't fail deployment for this

            return pages_url

        except Exception as e:
            self.logger.error(f"Failed to enable GitHub Pages: {str(e)}")
            raise

    def delete_repository(self, repo_name: str) -> bool:
        """
        Delete a GitHub repository.

        Args:
            repo_name: Name of the repository to delete

        Returns:
            True if deletion successful, False otherwise
        """
        try:
            repo = self.user.get_repo(repo_name)
            repo.delete()
            self.logger.debug(f"Successfully deleted repository: {repo_name}")
            return True
        except GithubException as e:
            if e.status == 404:
                self.logger.warning(
                    f"Repository {repo_name} not found (may already be deleted)"
                )
                return True  # Consider this success
            else:
                self.logger.error(f"Failed to delete repository {repo_name}: {str(e)}")
                return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error deleting repository {repo_name}: {str(e)}"
            )
            return False

    def list_repositories(self) -> list:
        """
        List all repositories for the authenticated user.

        Returns:
            List of repository names
        """
        try:
            repos = [repo.name for repo in self.user.get_repos()]
            return repos
        except Exception as e:
            self.logger.error(f"Failed to list repositories: {str(e)}")
            return []

    def _poll_pages_deployment(
        self, repo: Repository, pages_url: str, timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Poll GitHub Actions to check Pages deployment status.

        Args:
            repo: GitHub Repository object
            pages_url: Expected Pages URL
            timeout: Maximum time to wait in seconds

        Returns:
            Dictionary with deployment status information
        """
        start_time = time.time()

        self.logger.debug(
            f"🔄 Polling GitHub Pages deployment status (timeout: {timeout}s)..."
        )

        while time.time() - start_time < timeout:
            try:
                # Method 1: Check if the page is accessible
                if self._test_page_accessibility(pages_url):
                    deployment_time = time.time() - start_time
                    self.logger.debug(
                        f"🚀 GitHub Pages is now LIVE! (took {deployment_time:.1f}s)"
                    )
                    return {
                        "status": "live",
                        "deployment_time": deployment_time,
                        "pages_url": pages_url,
                        "message": f"Page deployed successfully in {deployment_time:.1f} seconds",
                    }

                # Wait before next check
                time.sleep(10)

            except Exception as e:
                self.logger.debug(f"Polling error (will retry): {str(e)}")
                time.sleep(5)

        # Timeout reached
        deployment_time = time.time() - start_time
        self.logger.warning(
            f"⏰ Deployment polling timed out after {deployment_time:.1f}s"
        )
        self.logger.debug(f"💡 The page may still be deploying. Check: {pages_url}")

        return {
            "status": "timeout",
            "deployment_time": deployment_time,
            "pages_url": pages_url,
            "message": f"Polling timed out after {deployment_time:.1f} seconds. Page may still be deploying.",
        }

    def _test_page_accessibility(self, pages_url: str) -> bool:
        """
        Test if the GitHub Pages URL is accessible.

        Args:
            pages_url: URL to test

        Returns:
            True if accessible, False otherwise
        """
        try:
            headers = {
                "User-Agent": "GitPhish-Deployment-Checker/1.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

            response = requests.get(
                pages_url, headers=headers, timeout=10, allow_redirects=True
            )

            if response.status_code == 200:
                # Additional check: ensure it's not a generic GitHub 404 page
                if "github" in response.text.lower() and "404" in response.text:
                    return False
                return True
            else:
                return False

        except Exception:
            return False
