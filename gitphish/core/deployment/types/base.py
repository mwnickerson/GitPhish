"""
Abstract base deployer for GitPhish deployment types.

This module provides the common interface that all deployment types must implement.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class DeploymentType(Enum):
    """Supported deployment types."""

    GITHUB_PAGES = "github_pages"


class BaseDeployer(ABC):
    """Abstract base class for all GitPhish deployers."""

    def __init__(self, config):
        """
        Initialize the deployer with configuration.

        Args:
            config: Deployment configuration object
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def deployment_type(self) -> DeploymentType:
        """Return the deployment type this deployer handles."""
        pass

    @abstractmethod
    def deploy(
        self, poll_deployment: bool = True, poll_timeout: int = 300, **kwargs
    ) -> Dict[str, Any]:
        """
        Deploy the landing page.

        Args:
            poll_deployment: Whether to poll for deployment completion
            poll_timeout: Maximum time to wait for deployment in seconds
            **kwargs: Additional deployment-specific parameters

        Returns:
            Dictionary with deployment results containing at minimum:
            {
                'status': 'success' | 'failed',
                'deployment_url': 'https://...',  # URL where the deployment is accessible
                'repo_name': 'repository-name',
                'username': 'github-username',
                'error': 'error message if failed'
            }
        """
        pass

    @abstractmethod
    def cleanup(self) -> Dict[str, Any]:
        """
        Clean up the deployment.

        Returns:
            Dictionary with cleanup results:
            {
                'success': True | False,
                'message': 'cleanup details',
                'error': 'error message if failed'
            }
        """
        pass

    @abstractmethod
    def get_deployment_status(self) -> Dict[str, Any]:
        """
        Get current deployment status.

        Returns:
            Dictionary with status information:
            {
                'deployed': True | False,
                'deployment_url': 'https://...' if deployed,
                'repo_name': 'repository-name',
                'username': 'github-username',
                'error': 'error message if applicable'
            }
        """
        pass

    def validate_config(self) -> Dict[str, Any]:
        """
        Validate the deployment configuration.

        Returns:
            Dictionary with validation results:
            {
                'valid': True | False,
                'errors': ['list of error messages'],
                'warnings': ['list of warning messages']
            }
        """
        errors = []
        warnings = []

        # Common validation that all deployers should perform
        if not hasattr(self.config, "github_token") or not self.config.github_token:
            errors.append("GitHub token is required")

        if not hasattr(self.config, "repo_name") or not self.config.repo_name:
            errors.append("Repository name is required")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def _log_deployment_start(self):
        """Log deployment start with common information."""
        self.logger.debug(
            f"Starting {self.deployment_type.value} deployment for {self.config.repo_name}"
        )

    def _log_deployment_success(self, deployment_url: str):
        """Log successful deployment."""
        self.logger.debug(
            f"{self.deployment_type.value} deployment completed successfully: {deployment_url}"
        )

    def _log_deployment_error(self, error: str):
        """Log deployment error."""
        self.logger.error(f"{self.deployment_type.value} deployment failed: {error}")
