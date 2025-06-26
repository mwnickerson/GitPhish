"""
GitHub Account Management Service

This service provides high-level operations for managing GitHub accounts
and their associated Personal Access Tokens.
"""

import logging
import json
from typing import Dict, Any, Optional, Type
from datetime import datetime

from gitphish.models.github.github_account import DeployerGitHubAccount
from gitphish.models.database import db_session_scope
from gitphish.core.accounts.services.base_service import (
    BaseGitHubAccountService,
)

logger = logging.getLogger(__name__)


class DeployerGitHubAccountService(BaseGitHubAccountService):
    """Service for managing GitHub deployment accounts and tokens."""

    @property
    def account_model(self) -> Type[DeployerGitHubAccount]:
        """Return the DeployerGitHubAccount model class."""
        return DeployerGitHubAccount

    @property
    def account_type_name(self) -> str:
        """Return a human-readable name for this account type."""
        return "deployment"

    def add_account(self, token: str) -> Dict[str, Any]:
        """
        Add a new GitHub account by validating and storing the token.

        Args:
            token: GitHub Personal Access Token

        Returns:
            Dictionary with operation result
        """
        try:
            logger.debug(
                f"Adding new {self.account_type_name} GitHub account with "
                f"token: {token[:10]}...{token[-4:] if len(token) > 10 else ''}"
            )

            # Validate the token using base class method
            token_info = self._validate_token(token)

            if not token_info.is_valid:
                return {
                    "success": False,
                    "error": f"Invalid token: {token_info.error_message}",
                }

            # Create token hash for checking duplicates
            token_hash = self._create_token_hash(token)

            with db_session_scope() as session:
                # Check if account already exists by username (active or inactive)
                existing_by_username = self._check_duplicate_by_username(
                    session, token_info.username
                )

                if existing_by_username:
                    # Update existing account with new token info
                    logger.debug(
                        f"Updating existing {self.account_type_name} GitHub account: {token_info.username}"
                    )

                    # Update the account with new token information
                    existing_by_username.user_id = token_info.user_id
                    existing_by_username.email = token_info.email
                    existing_by_username.name = token_info.name
                    existing_by_username.avatar_url = token_info.avatar_url
                    existing_by_username.token_preview = self._create_token_preview(
                        token
                    )
                    existing_by_username.token_hash = token_hash
                    existing_by_username.set_encrypted_token(
                        token
                    )  # Store encrypted token
                    existing_by_username.scopes = (
                        json.dumps(token_info.scopes) if token_info.scopes else None
                    )
                    existing_by_username.token_created_at = datetime.utcnow()
                    existing_by_username.last_validated_at = datetime.utcnow()
                    existing_by_username.is_valid = True
                    existing_by_username.validation_error = None
                    existing_by_username.rate_limit_remaining = (
                        token_info.rate_limit_remaining
                    )
                    existing_by_username.is_active = True
                    existing_by_username.updated_at = datetime.utcnow()

                    session.commit()

                    # Cache the token for immediate use
                    self._cache_token(existing_by_username.id, token)

                    logger.debug(
                        f"Updated {self.account_type_name} GitHub account: {token_info.username}"
                    )

                    return {
                        "success": True,
                        "account": existing_by_username.to_dict(),
                        "message": f"Successfully updated {self.account_type_name} "
                        f"GitHub account for {token_info.username}",
                    }

                # Check if token already exists (different user)
                existing_by_token = self._check_duplicate_by_token_hash(
                    session, token_hash
                )
                if existing_by_token:
                    return {
                        "success": False,
                        "error": "This token is already registered to a different account",
                    }

                # Create new account
                account = DeployerGitHubAccount.create_from_token_info(
                    token_info, token
                )

                # If this is the first account, make it primary
                existing_accounts = DeployerGitHubAccount.get_all_active(session)
                if not existing_accounts:
                    account.is_primary = True

                session.add(account)
                session.commit()

                # Cache the token for immediate use
                self._cache_token(account.id, token)

                logger.debug(
                    f"Added {self.account_type_name} GitHub account: {token_info.username}"
                )

                return {
                    "success": True,
                    "account": account.to_dict(),
                    "message": f"Successfully added {self.account_type_name} GitHub account for {token_info.username}",
                }

        except Exception as e:
            logger.error(
                f"Failed to add {self.account_type_name} GitHub account: {str(e)}"
            )
            return {
                "success": False,
                "error": f"Failed to add account: {str(e)}",
            }

    def set_primary_account(self, account_id: int) -> Dict[str, Any]:
        """
        Set an account as the primary account for deployments.

        Args:
            account_id: ID of the GitHub account

        Returns:
            Dictionary with operation result
        """
        try:
            with db_session_scope() as session:
                account = session.get(DeployerGitHubAccount, account_id)
                if not account or not account.is_active:
                    return {"success": False, "error": "Account not found"}

                if not account.is_valid:
                    return {
                        "success": False,
                        "error": "Cannot set invalid account as primary",
                    }

                account.mark_as_primary(session)
                session.commit()

                logger.debug(f"Set account {account.username} as primary")

                return {
                    "success": True,
                    "account": account.to_dict(),
                    "message": f"Set {account.username} as primary account",
                }

        except Exception as e:
            logger.error(f"Failed to set primary account {account_id}: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_primary_account_token(self) -> Optional[str]:
        """
        Get the token for the primary account.

        Returns:
            Token string or None if no primary account
        """
        try:
            with db_session_scope() as session:
                primary_account = DeployerGitHubAccount.get_primary_account(session)
                if primary_account:
                    return self.get_account_token(primary_account.id)
                return None
        except Exception as e:
            logger.error(f"Failed to get primary account token: {str(e)}")
            return None
