"""
Configuration module for GitHub Pages deployment.
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class DeploymentConfig:
    """Configuration for GitHub Pages deployment."""

    github_token: str
    ingest_url: Optional[str] = None
    repo_name: str = "verification-portal"
    repo_description: str = "GitHub Verification Portal"
    username: Optional[str] = None
    template_preset: str = "default"
    org_name: Optional[str] = None
    custom_title: Optional[str] = None
    deployment_type: str = "github_pages"

    ssh_key_id: Optional[int] = None
    deployment_metadata: Optional[Dict[str, Any]] = None
    delete_repo_on_cleanup: bool = True
    expires_at: Optional[str] = None

    @classmethod
    def from_env(cls, **kwargs):
        """
        Create configuration from environment variables.
        Args:
            **kwargs: Override any configuration values
        Returns:
            DeploymentConfig instance
        """
        return cls(
            github_token=kwargs.get("github_token"),
            ingest_url=kwargs.get("ingest_url") or os.getenv("INGEST_URL"),
            repo_name=kwargs.get("repo_name")
            or os.getenv("DEPLOY_REPO_NAME", "verification-portal"),
            repo_description=kwargs.get("repo_description")
            or os.getenv("DEPLOY_REPO_DESCRIPTION", "GitHub Verification Portal"),
            username=kwargs.get("username") or os.getenv("DEPLOY_USERNAME"),
            template_preset=kwargs.get("template_preset")
            or os.getenv("TEMPLATE_PRESET", "default"),
            org_name=kwargs.get("org_name") or os.getenv("ORG_NAME"),
            custom_title=kwargs.get("custom_title") or os.getenv("CUSTOM_TITLE"),
            deployment_type=kwargs.get("deployment_type")
            or os.getenv("DEPLOYMENT_TYPE", "github_pages"),
            deployment_metadata=kwargs.get("deployment_metadata"),
            delete_repo_on_cleanup=kwargs.get("delete_repo_on_cleanup", True),
            expires_at=kwargs.get("expires_at"),
        )

    def validate(self, cleanup_mode: bool = False) -> bool:
        """
        Validate that required configuration is present.

        Args:
            cleanup_mode: If True, skip validation of deployment-specific
            fields

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If required configuration is missing
        """
        if not self.github_token:
            raise ValueError(
                "GitHub token is required. Set GITHUB_DEPLOY_TOKEN environment "
                "variable or provide --github-token"
            )

        # Only require ingest URL for GitHub Pages deployments
        if (
            not cleanup_mode
            and self.deployment_type == "github_pages"
            and not self.ingest_url
        ):
            raise ValueError(
                "Ingest URL is required for GitHub Pages deployment. Provide "
                "--ingest-url argument"
            )

        if not self.repo_name:
            raise ValueError("Repository name is required")

        return True
