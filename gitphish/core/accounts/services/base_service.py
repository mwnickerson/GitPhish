"""
Base GitHub Account Service

This module provides common functionality for managing GitHub accounts,
shared between deployment accounts and compromised accounts.
"""

import logging
import hashlib
from typing import Dict, Any, List, Optional, Type, TypeVar
from abc import ABC, abstractmethod

from gitphish.models.database import db_session_scope, Base
from gitphish.core.accounts.clients.github_client import GitHubClient

logger = logging.getLogger(__name__)

# Type variable for the account model
AccountModel = TypeVar("AccountModel", bound=Base)


class BaseGitHubAccountService(ABC):
    """Base service for managing GitHub accounts with common functionality."""

    def __init__(self):
        """Initialize the base GitHub account service."""
        # Store tokens temporarily for operations
        self._token_cache = {}

    @property
    @abstractmethod
    def account_model(self) -> Type[AccountModel]:
        """Return the SQLAlchemy model class for this service."""
        pass

    @property
    @abstractmethod
    def account_type_name(self) -> str:
        """Return a human-readable name for this account type."""
        pass

    def _validate_token(self, token: str):
        """
        Validate a GitHub token and return token information using GitHubClient.
        """
        logger.debug(f"Validating {self.account_type_name} GitHub token...")
        github_client = GitHubClient(token)
        token_info = github_client.validate_token()
        logger.debug(
            f"Token validation result: is_valid={token_info.is_valid}, "
            f"error={token_info.error_message}"
        )
        if not token_info.is_valid:
            logger.warning(
                f"{self.account_type_name} token validation failed: "
                f"{token_info.error_message}"
            )
        return token_info

    def _create_token_hash(self, token: str) -> str:
        """
        Create a SHA256 hash of the token for identification.

        Args:
            token: GitHub Personal Access Token

        Returns:
            SHA256 hash of the token
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def _create_token_preview(self, token: str) -> str:
        """
        Create a preview of the token for display purposes.

        Args:
            token: GitHub Personal Access Token

        Returns:
            Token preview string
        """
        if len(token) > 8:
            return f"{token[:4]}...{token[-4:]}"
        else:
            return "***"

    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """
        Get all active accounts.

        Returns:
            List of account dictionaries
        """
        try:
            with db_session_scope() as session:
                accounts = self.account_model.get_all_active(session)
                return [account.to_dict() for account in accounts]
        except Exception as e:
            logger.error(f"Failed to get {self.account_type_name} accounts: {str(e)}")
            return []

    def get_account_repositories(self, account_id: int) -> Dict[str, Any]:
        """
        Get repositories for a specific GitHub account.

        Args:
            account_id: ID of the GitHub account

        Returns:
            Dictionary with repositories or error
        """
        try:
            with db_session_scope() as session:
                account = session.get(self.account_model, account_id)
                if not account or not account.is_active:
                    return {
                        "success": False,
                        "error": f"{self.account_type_name} account not found",
                    }

                # Always try to get token from cache or database
                token = self.get_account_token(account_id)
                if not token:
                    return {
                        "success": False,
                        "error": (
                            f"Token not available. Please re-add the "
                            f"{self.account_type_name} account."
                        ),
                    }

                # Get repositories using GitHub client
                github_client = GitHubClient(token)
                if not github_client.is_valid():
                    return {
                        "success": False,
                        "error": ("Token is no longer valid"),
                    }

                user = github_client.get_user()
                if not user:
                    return {
                        "success": False,
                        "error": ("Failed to get user information"),
                    }

                # Get repositories
                repos = []
                try:
                    for repo in user.get_repos():
                        repo_data = {
                            "name": repo.name,
                            "full_name": repo.full_name,
                            "description": repo.description,
                            "private": repo.private,
                            "html_url": repo.html_url,
                            "created_at": (
                                repo.created_at.isoformat() if repo.created_at else None
                            ),
                            "updated_at": (
                                repo.updated_at.isoformat() if repo.updated_at else None
                            ),
                            "language": repo.language,
                            "stargazers_count": repo.stargazers_count,
                            "forks_count": repo.forks_count,
                            "has_pages": repo.has_pages,
                        }

                        # Add additional fields for compromised accounts
                        if hasattr(repo, "size"):
                            repo_data["size"] = repo.size
                        if hasattr(repo, "default_branch"):
                            repo_data["default_branch"] = repo.default_branch

                        repos.append(repo_data)

                        # Limit to prevent API rate limiting
                        if len(repos) >= 100:
                            break

                except Exception as e:
                    logger.error(
                        f"Failed to fetch repositories for "
                        f"{self.account_type_name} account: {str(e)}"
                    )
                    return {
                        "success": False,
                        "error": f"Failed to fetch repositories: {str(e)}",
                    }

                return {
                    "success": True,
                    "repositories": repos,
                    "total_count": len(repos),
                }

        except Exception as e:
            logger.error(
                f"Failed to get repositories for {self.account_type_name} "
                f"account {account_id}: {str(e)}"
            )
            return {"success": False, "error": str(e)}

    def validate_account(self, account_id: int) -> Dict[str, Any]:
        """
        Re-validate a GitHub account's token.

        Args:
            account_id: ID of the GitHub account

        Returns:
            Dictionary with validation result
        """
        try:
            with db_session_scope() as session:
                account = session.get(self.account_model, account_id)
                if not account:
                    return {
                        "success": False,
                        "error": f"{self.account_type_name} account not found",
                    }

                # Get token from cache or database
                token = self.get_account_token(account_id)
                if not token:
                    return {
                        "success": False,
                        "error": "Token not available for validation",
                    }

                # Validate token
                token_info = self._validate_token(token)

                # Update account validation status
                account.update_validation_status(token_info)
                session.commit()

                return {
                    "success": True,
                    "is_valid": token_info.is_valid,
                    "account": account.to_dict(),
                    "error_message": token_info.error_message,
                }

        except Exception as e:
            logger.error(
                f"Failed to validate {self.account_type_name} account "
                f"{account_id}: {str(e)}"
            )
            return {"success": False, "error": str(e)}

    def remove_account(self, account_id: int) -> Dict[str, Any]:
        """
        Remove (hard delete) a GitHub account from the database.
        Args:
            account_id: ID of the GitHub account
        Returns:
            Dictionary with operation result
        """
        try:
            with db_session_scope() as session:
                account = session.get(self.account_model, account_id)
                if not account:
                    return {
                        "success": False,
                        "error": f"{self.account_type_name} account not found",
                    }
                username = account.username
                session.delete(account)
                session.commit()
                # Remove from token cache
                if account_id in self._token_cache:
                    del self._token_cache[account_id]
                logger.debug(
                    f"Hard deleted {self.account_type_name} GitHub account: "
                    f"{username}"
                )
                return {
                    "success": True,
                    "message": (
                        f"Deleted {self.account_type_name} account for " f"{username}"
                    ),
                }
        except Exception as e:
            logger.error(
                f"Failed to delete {self.account_type_name} account "
                f"{account_id}: {str(e)}"
            )
            return {"success": False, "error": str(e)}

    def get_account_token(self, account_id: int) -> Optional[str]:
        """
        Get the token for a specific account.

        Args:
            account_id: ID of the GitHub account

        Returns:
            Token string or None if not found
        """
        # First try the cache for performance
        cached_token = self._token_cache.get(account_id)
        if cached_token:
            return cached_token

        # If not in cache, get from database
        try:
            with db_session_scope() as session:
                account = session.get(self.account_model, account_id)
                if account and account.is_active and account.encrypted_token:
                    decrypted_token = account.get_decrypted_token()
                    if decrypted_token:
                        # Cache the token for future use
                        self._token_cache[account_id] = decrypted_token
                        return decrypted_token
        except Exception as e:
            logger.error(
                f"Failed to retrieve token for account {account_id}: " f"{str(e)}"
            )

        return None

    def get_account_by_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a GitHub account by ID.

        Args:
            account_id: Account ID

        Returns:
            Account dictionary or None if not found
        """
        try:
            with db_session_scope() as session:
                account = session.get(self.account_model, account_id)
                if account and account.is_active:
                    return account.to_dict()
                return None
        except Exception as e:
            logger.error(
                f"Failed to get {self.account_type_name} account by ID {account_id}: {str(e)}"
            )
            return None

    def _cache_token(self, account_id: int, token: str):
        """
        Cache a token for an account.

        Args:
            account_id: ID of the GitHub account
            token: GitHub Personal Access Token
        """
        self._token_cache[account_id] = token

    def _check_duplicate_by_token_hash(
        self, session, token_hash: str, exclude_account_id: int = None
    ):
        """
        Check if a token hash already exists.

        Args:
            session: Database session
            token_hash: SHA256 hash of the token
            exclude_account_id: Account ID to exclude from the check

        Returns:
            Existing account or None
        """
        query = session.query(self.account_model).filter(
            self.account_model.token_hash == token_hash,
            self.account_model.is_active,
        )

        if exclude_account_id:
            query = query.filter(self.account_model.id != exclude_account_id)

        return query.first()

    def _check_duplicate_by_username(
        self, session, username: str, exclude_account_id: int = None
    ):
        """
        Check if a username already exists.

        Args:
            session: Database session
            username: GitHub username
            exclude_account_id: Account ID to exclude from the check

        Returns:
            Existing account or None
        """
        query = session.query(self.account_model).filter(
            self.account_model.username == username,
            self.account_model.is_active,
        )

        if exclude_account_id:
            query = query.filter(self.account_model.id != exclude_account_id)

        return query.first()
