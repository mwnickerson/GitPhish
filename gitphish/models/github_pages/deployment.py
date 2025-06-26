"""
Database models for GitHub Pages deployments.

This module contains SQLAlchemy models for storing and managing
GitHub Pages deployment information.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Boolean,
    JSON,
    Enum as SQLEnum,
    UniqueConstraint,
)
from sqlalchemy.orm import Session
from gitphish.models.base import Base


class DeploymentStatus(Enum):
    """Enumeration of possible deployment statuses."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ACTIVE = "active"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INACTIVE = "inactive"


class GitHubDeployment(Base):
    """
    Model for storing GitHub Pages deployment information.

    This model tracks all deployments made through GitPhish, including
    their configuration, status, and metadata.
    """

    __tablename__ = "github_deployments"
    __table_args__ = (
        UniqueConstraint("repo_name", "github_username", name="_repo_user_uc"),
    )

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Basic deployment information
    repo_name = Column(String(255), nullable=False, index=True)
    repo_description = Column(Text)
    github_username = Column(
        String(255), nullable=True, index=True
    )  # Can be null initially, filled after deployment
    account_id = Column(
        Integer, nullable=True, index=True
    )  # ID of the GitHub account used for deployment

    # URLs
    repo_url = Column(String(500))
    pages_url = Column(String(500))
    ingest_url = Column(String(500))

    # Template and configuration
    template_preset = Column(String(100), default="default")
    org_name = Column(String(255))
    custom_title = Column(String(255))

    # Status and timing
    status = Column(
        SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    deployed_at = Column(DateTime)

    # Deployment metadata
    deployment_time_seconds = Column(Integer)  # Time taken for deployment
    github_token_used = Column(String(50))  # First/last few chars for identification

    # Additional metadata stored as JSON
    deployment_metadata = Column(JSON)  # Stores additional deployment info
    error_message = Column(Text)  # Error details if deployment failed

    # Flags
    is_active = Column(Boolean, default=True)  # Whether the deployment is still active
    pages_enabled = Column(Boolean, default=False)  # Whether GitHub Pages is enabled

    def __repr__(self):
        return (
            f"<GitHubDeployment(id={self.id}, repo='{self.repo_name}', "
            f"status='{self.status.value}')>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the deployment to a dictionary representation.

        Returns:
            Dictionary containing all deployment information
        """
        return {
            "id": self.id,
            "repo_name": self.repo_name,
            "repo_description": self.repo_description,
            "github_username": self.github_username,
            "account_id": self.account_id,
            "repo_url": self.repo_url,
            "pages_url": self.pages_url,
            "ingest_url": self.ingest_url,
            "template_preset": self.template_preset,
            "org_name": self.org_name,
            "custom_title": self.custom_title,
            "status": self.status.value,
            "created_at": (self.created_at.isoformat() if self.created_at else None),
            "updated_at": (self.updated_at.isoformat() if self.updated_at else None),
            "deployed_at": (self.deployed_at.isoformat() if self.deployed_at else None),
            "deployment_time_seconds": self.deployment_time_seconds,
            "deployment_metadata": self.deployment_metadata,
            "error_message": self.error_message,
            "is_active": self.is_active,
            "pages_enabled": self.pages_enabled,
        }

    @classmethod
    def create_from_deployment_result(
        cls,
        deployment_result: Dict[str, Any],
        config,
        github_token: str,
    ) -> "GitHubDeployment":
        """
        Create a GitHubDeployment instance from deployment result and config.

        Args:
            deployment_result: Result from deployment (dict)
            config: DeploymentConfig used for the deployment
            github_token: GitHub token used (will be masked for storage)

        Returns:
            GitHubDeployment instance
        """
        # Mask the GitHub token for storage (keep first 4 and last 4 chars)
        masked_token = (
            f"{github_token[:4]}...{github_token[-4:]}"
            if len(github_token) > 8
            else "***"
        )

        # Determine status based on deployment result
        status = (
            DeploymentStatus.ACTIVE
            if deployment_result.get("status") == "active"
            else DeploymentStatus.FAILED
        )

        # Extract deployment timing if available
        deployment_time = None
        if "deployment_status" in deployment_result:
            deployment_time = deployment_result["deployment_status"].get(
                "deployment_time"
            )

        deployment = cls(
            repo_name=config.repo_name,
            repo_description=config.repo_description,
            github_username=deployment_result.get("username"),
            repo_url=deployment_result.get("repo_url"),
            pages_url=deployment_result.get("pages_url"),
            ingest_url=config.ingest_url,
            template_preset=config.template_preset,
            org_name=config.org_name,
            custom_title=config.custom_title,
            status=status,
            deployed_at=(
                datetime.utcnow() if status == DeploymentStatus.ACTIVE else None
            ),
            deployment_time_seconds=(int(deployment_time) if deployment_time else None),
            github_token_used=masked_token,
            deployment_metadata=deployment_result.get("deployment_status"),
            pages_enabled=(status == DeploymentStatus.ACTIVE),
        )

        return deployment

    def update_status(
        self, status: DeploymentStatus, error_message: Optional[str] = None
    ):
        """
        Update the deployment status.

        Args:
            status: New deployment status
            error_message: Error message if status is FAILED
        """
        self.status = status
        self.updated_at = datetime.utcnow()

        if status == DeploymentStatus.ACTIVE and not self.deployed_at:
            self.deployed_at = datetime.utcnow()
            self.pages_enabled = True
        elif status == DeploymentStatus.FAILED:
            self.error_message = error_message
            self.pages_enabled = False

    @staticmethod
    def get_by_repo_name(
        session: Session, repo_name: str, github_username: Optional[str] = None
    ) -> Optional["GitHubDeployment"]:
        """
        Get a deployment by repository name.

        Args:
            session: Database session
            repo_name: Repository name to search for
            github_username: Optional username filter

        Returns:
            GitHubDeployment instance or None
        """
        query = session.query(GitHubDeployment).filter(
            GitHubDeployment.repo_name == repo_name
        )
        if github_username:
            query = query.filter(GitHubDeployment.github_username == github_username)
        return query.first()

    @staticmethod
    def get_recent_deployments(
        session: Session, limit: int = 10
    ) -> List["GitHubDeployment"]:
        """
        Get recent deployments ordered by creation date.

        Args:
            session: Database session
            limit: Maximum number of deployments to return

        Returns:
            List of GitHubDeployment instances
        """
        return (
            session.query(GitHubDeployment)
            .order_by(GitHubDeployment.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_active_deployments(session: Session) -> List["GitHubDeployment"]:
        """
        Get all active deployments.

        Args:
            session: Database session

        Returns:
            List of active GitHubDeployment instances
        """
        return (
            session.query(GitHubDeployment)
            .filter(GitHubDeployment.is_active.is_(True))
            .filter(GitHubDeployment.status == DeploymentStatus.ACTIVE)
            .order_by(GitHubDeployment.created_at.desc())
            .all()
        )

    @staticmethod
    def get_deployment_stats(session: Session) -> Dict[str, Any]:
        """
        Get deployment statistics.

        Args:
            session: Database session

        Returns:
            Dictionary containing deployment statistics
        """
        total_deployments = session.query(GitHubDeployment).count()
        successful_deployments = (
            session.query(GitHubDeployment)
            .filter(GitHubDeployment.status == DeploymentStatus.ACTIVE)
            .count()
        )
        failed_deployments = (
            session.query(GitHubDeployment)
            .filter(GitHubDeployment.status == DeploymentStatus.FAILED)
            .count()
        )
        active_deployments = (
            session.query(GitHubDeployment)
            .filter(GitHubDeployment.is_active.is_(True))
            .filter(GitHubDeployment.status == DeploymentStatus.ACTIVE)
            .count()
        )

        return {
            "total_deployments": total_deployments,
            "successful_deployments": successful_deployments,
            "failed_deployments": failed_deployments,
            "active_deployments": active_deployments,
            "success_rate": (
                (successful_deployments / total_deployments * 100)
                if total_deployments > 0
                else 0
            ),
        }
