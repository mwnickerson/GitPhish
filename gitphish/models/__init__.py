"""
GitPhish Models Package

This package contains all data models for GitPhish, including:
- Authentication models
- Deployment models
- Database configuration
"""

from gitphish.models.auth_attempts.auth import DeviceAuthResult, AuthAttempt
from gitphish.models.github_pages.deployment import (
    GitHubDeployment,
    DeploymentStatus,
)

from gitphish.models.github.base_github_account import BaseGitHubAccount
from gitphish.models.github.github_account import DeployerGitHubAccount
from gitphish.models.github.compromised_account import CompromisedGitHubAccount
from gitphish.models.database import DatabaseManager, get_db_session

__all__ = [
    "DeviceAuthResult",
    "AuthAttempt",
    "GitHubDeployment",
    "DeploymentStatus",
    "BaseGitHubAccount",
    "DeployerGitHubAccount",
    "CompromisedGitHubAccount",
    "DatabaseManager",
    "get_db_session",
]
