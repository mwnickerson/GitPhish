"""
Deployment factory for creating appropriate deployers.

This module provides a factory pattern for creating deployment instances
based on the deployment type specified in the configuration.
"""

import logging
from typing import Dict, Type

from gitphish.core.deployment.types.base import BaseDeployer, DeploymentType
from gitphish.core.deployment.types.github_pages.deployer import (
    GitHubPagesDeployer,
)


logger = logging.getLogger(__name__)


class DeploymentFactory:
    """Factory for creating deployment instances."""

    # Registry of available deployers
    _deployers: Dict[DeploymentType, Type[BaseDeployer]] = {
        DeploymentType.GITHUB_PAGES: GitHubPagesDeployer,
    }

    @classmethod
    def create_deployer(
        cls,
        deployment_type: DeploymentType,
        config,
        cleanup_mode: bool = False,
    ) -> BaseDeployer:
        """
        Create a deployer instance for the specified deployment type.

        Args:
            deployment_type: Type of deployment to create
            config: Deployment configuration object
            cleanup_mode: Whether this is for cleanup operations

        Returns:
            Appropriate deployer instance

        Raises:
            ValueError: If deployment type is not supported
        """
        if deployment_type not in cls._deployers:
            available_types = list(cls._deployers.keys())
            raise ValueError(
                f"Unsupported deployment type: {deployment_type}. "
                f"Available types: {[dt.value for dt in available_types]}"
            )

        deployer_class = cls._deployers[deployment_type]
        logger.debug(f"Creating {deployment_type.value} deployer")

        return deployer_class(config, cleanup_mode=cleanup_mode)

    @classmethod
    def create_from_config(cls, config, cleanup_mode: bool = False) -> BaseDeployer:
        """
        Create a deployer instance based on the deployment type in the config.

        Args:
            config: Deployment configuration object with deployment_type attribute
            cleanup_mode: Whether this is for cleanup operations

        Returns:
            Appropriate deployer instance

        Raises:
            ValueError: If deployment type is not specified or supported
        """
        # Default to GitHub Pages if no deployment type specified (backward compatibility)
        deployment_type_str = getattr(config, "deployment_type", "github_pages")

        try:
            deployment_type = DeploymentType(deployment_type_str)
        except ValueError:
            available_types = [dt.value for dt in DeploymentType]
            raise ValueError(
                f"Invalid deployment type '{deployment_type_str}'. "
                f"Available types: {available_types}"
            )

        return cls.create_deployer(deployment_type, config, cleanup_mode)

    @classmethod
    def get_supported_types(cls) -> Dict[str, str]:
        """
        Get a dictionary of supported deployment types and their descriptions.

        Returns:
            Dictionary mapping deployment type values to descriptions
        """
        return {
            DeploymentType.GITHUB_PAGES.value: "Deploy static landing page to GitHub Pages",
        }

    @classmethod
    def register_deployer(
        cls,
        deployment_type: DeploymentType,
        deployer_class: Type[BaseDeployer],
    ):
        """
        Register a new deployer type (for future extensibility).

        Args:
            deployment_type: The deployment type enum value
            deployer_class: The deployer class that implements BaseDeployer
        """
        if not issubclass(deployer_class, BaseDeployer):
            raise ValueError("Deployer class must inherit from BaseDeployer")

        cls._deployers[deployment_type] = deployer_class
        logger.debug(f"Registered new deployer: {deployment_type.value}")


# Convenience function for backward compatibility
def create_deployer(config, cleanup_mode: bool = False) -> BaseDeployer:
    """
    Create a deployer instance based on configuration.

    This is a convenience function that maintains backward compatibility
    with the old GitPhishDeployer interface.

    Args:
        config: Deployment configuration object
        cleanup_mode: Whether this is for cleanup operations

    Returns:
        Appropriate deployer instance
    """
    return DeploymentFactory.create_from_config(config, cleanup_mode)
