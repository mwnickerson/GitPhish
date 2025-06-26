"""
Database model for GitHub accounts and Personal Access Tokens.

This module contains SQLAlchemy models for storing and managing
GitHub account information and their associated PATs.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import Session
from gitphish.models.github.base_github_account import BaseGitHubAccount
from gitphish.core.accounts.auth.token_validator import GitHubTokenInfo


class DeployerGitHubAccount(BaseGitHubAccount):
    """
    Model for storing GitHub deployment accounts and PATs.

    This model stores validated GitHub accounts with their tokens,
    user information, and metadata for deployment operations.
    """

    __tablename__ = "github_accounts"

    # Additional fields specific to deployment accounts
    username = Column(String(255), nullable=False, index=True)  # Removed unique=True
    user_id = Column(Integer, nullable=False)  # Removed unique=True
    is_primary = Column(
        Boolean, default=False, nullable=False
    )  # Primary account for deployments

    @property
    def account_type(self) -> str:
        """Return the account type for logging and display purposes."""
        return "deployment"

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convert the account to a dictionary representation.

        Args:
            include_sensitive: Whether to include sensitive information like token hash

        Returns:
            Dictionary containing account information
        """
        # Get base dictionary from parent class
        data = super().to_dict(include_sensitive)

        # Add deployment-specific fields
        data["is_primary"] = self.is_primary

        return data

    @classmethod
    def create_from_token_info(
        cls, token_info: "GitHubTokenInfo", token: str
    ) -> "DeployerGitHubAccount":
        """
        Create a DeployerGitHubAccount from validated token information.

        Args:
            token_info: Validated GitHubTokenInfo object
            token: The actual token (will be hashed and masked)

        Returns:
            DeployerGitHubAccount instance
        """
        # Create token hash and preview using base class methods
        token_hash = cls._create_token_hash(token)
        token_preview = cls._create_token_preview(token)
        encrypted_token = cls._encrypt_token(token)

        account = cls(
            username=token_info.username,
            user_id=token_info.user_id,
            email=token_info.email,
            name=token_info.name,
            avatar_url=token_info.avatar_url,
            token_preview=token_preview,
            token_hash=token_hash,
            encrypted_token=encrypted_token,
            scopes=token_info.scopes,
            is_valid=True,
            rate_limit_remaining=token_info.rate_limit_remaining,
        )

        return account

    def mark_as_primary(self, session: Session):
        """
        Mark this account as the primary account and unmark others.

        Args:
            session: Database session
        """
        # Unmark all other accounts as primary
        session.query(DeployerGitHubAccount).filter(
            DeployerGitHubAccount.id != self.id
        ).update({"is_primary": False})

        # Mark this account as primary
        self.is_primary = True
        self.updated_at = datetime.utcnow()

    @staticmethod
    def get_primary_account(
        session: Session,
    ) -> Optional["DeployerGitHubAccount"]:
        """
        Get the primary GitHub account.

        Args:
            session: Database session

        Returns:
            Primary DeployerGitHubAccount instance or None
        """
        return (
            session.query(DeployerGitHubAccount)
            .filter(
                DeployerGitHubAccount.is_primary,
                DeployerGitHubAccount.is_active,
                DeployerGitHubAccount.is_valid,
            )
            .first()
        )

    @staticmethod
    def get_all_active(session: Session) -> List["DeployerGitHubAccount"]:
        """
        Get all active GitHub accounts, ordered by primary status.

        Args:
            session: Database session

        Returns:
            List of active DeployerGitHubAccount instances
        """
        return (
            session.query(DeployerGitHubAccount)
            .filter(DeployerGitHubAccount.is_active)
            .order_by(
                DeployerGitHubAccount.is_primary.desc(),
                DeployerGitHubAccount.created_at.desc(),
            )
            .all()
        )

    @staticmethod
    def get_valid_accounts(session: Session) -> List["DeployerGitHubAccount"]:
        """
        Get all valid and active GitHub accounts, ordered by primary status.

        Args:
            session: Database session

        Returns:
            List of valid DeployerGitHubAccount instances
        """
        return (
            session.query(DeployerGitHubAccount)
            .filter(
                DeployerGitHubAccount.is_active,
                DeployerGitHubAccount.is_valid,
            )
            .order_by(
                DeployerGitHubAccount.is_primary.desc(),
                DeployerGitHubAccount.created_at.desc(),
            )
            .all()
        )

    def soft_delete(self):
        """Mark the account as inactive (soft delete) and remove primary status."""
        super().soft_delete()
        self.is_primary = False
