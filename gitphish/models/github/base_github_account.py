"""
Base GitHub Account Model

This module provides a base model class for GitHub accounts,
shared between deployment accounts and compromised accounts.
"""

import json
import hashlib
import base64
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Type, TypeVar
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from gitphish.core.accounts.auth.token_validator import GitHubTokenInfo
from gitphish.models.base import Base

# Type variable for the account model
AccountModel = TypeVar("AccountModel", bound="BaseGitHubAccount")


class BaseGitHubAccount(Base):
    """
    Base model for storing GitHub account information and PATs.

    This abstract base class contains common fields and methods
    shared between deployment and compromised accounts.
    """

    __abstract__ = True

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # GitHub user information
    username = Column(String(255), nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    email = Column(String(255))
    name = Column(String(255))
    avatar_url = Column(String(500))

    # Token information (encrypted/masked for security)
    token_preview = Column(String(50), nullable=False)  # First 4 + last 4 chars
    token_hash = Column(String(64), nullable=False)  # SHA256 hash for identification
    encrypted_token = Column(Text)  # Encrypted token for actual use
    scopes = Column(JSON)  # List of token scopes

    # Token metadata
    token_created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_validated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_valid = Column(Boolean, default=True, nullable=False)
    validation_error = Column(Text)  # Last validation error if any

    # Rate limit information
    rate_limit_remaining = Column(Integer)
    rate_limit_reset = Column(DateTime)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    @property
    def account_type(self) -> str:
        """Return the account type for logging and display purposes."""
        return "base"

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id}, username='{self.username}', is_valid={self.is_valid})>"

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convert the account to a dictionary representation.

        Args:
            include_sensitive: Whether to include sensitive information like token hash

        Returns:
            Dictionary containing account information
        """
        # Handle scopes - could be JSON string or list
        scopes = self.scopes
        if isinstance(scopes, str):
            try:
                scopes = json.loads(scopes)
            except (json.JSONDecodeError, TypeError):
                scopes = []
        elif scopes is None:
            scopes = []

        data = {
            "id": self.id,
            "username": self.username,
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "token_preview": self.token_preview,
            "scopes": scopes,
            "token_created_at": (
                self.token_created_at.isoformat() if self.token_created_at else None
            ),
            "last_validated_at": (
                self.last_validated_at.isoformat() if self.last_validated_at else None
            ),
            "is_valid": self.is_valid,
            "validation_error": self.validation_error,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_reset": (
                self.rate_limit_reset.isoformat() if self.rate_limit_reset else None
            ),
            "is_active": self.is_active,
            "created_at": (self.created_at.isoformat() if self.created_at else None),
            "updated_at": (self.updated_at.isoformat() if self.updated_at else None),
        }

        if include_sensitive:
            data["token_hash"] = self.token_hash

        return data

    @classmethod
    def _get_encryption_key(cls) -> bytes:
        """
        Get or create the encryption key for token storage.

        For most users, the key and salt are hardcoded for convenience and basic
        security. Advanced users can override the key by setting the
        GITPHISH_TOKEN_KEY environment variable.
        """
        # Use environment variable if set, otherwise use a non-obvious default
        password = os.environ.get(
            "GITPHISH_TOKEN_KEY", "b7f3c2e1-4a5d-9e8f-2c3b-7a6e5d4c1b2a"
        )
        # Hardcoded random salt (16 bytes)
        salt = b"\x8f\x1a\x9c\x3d\x7e\x2b\x4c\x5d" b"\x6e\x7f\x8a\x9b\xac\xbd\xce\xdf"

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    @classmethod
    def _encrypt_token(cls, token: str) -> str:
        """
        Encrypt a token for secure storage.

        Args:
            token: GitHub Personal Access Token

        Returns:
            Encrypted token string (base64 encoded)
        """
        key = cls._get_encryption_key()
        f = Fernet(key)
        encrypted_token = f.encrypt(token.encode())
        return base64.urlsafe_b64encode(encrypted_token).decode()

    @classmethod
    def _decrypt_token(cls, encrypted_token: str) -> str:
        """
        Decrypt a stored token.

        Args:
            encrypted_token: Encrypted token string (base64 encoded)

        Returns:
            Decrypted token string
        """
        key = cls._get_encryption_key()
        f = Fernet(key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_token.encode())
        decrypted_token = f.decrypt(encrypted_bytes)
        return decrypted_token.decode()

    @classmethod
    def _create_token_hash(cls, token: str) -> str:
        """
        Create a SHA256 hash of the token for identification.

        Args:
            token: GitHub Personal Access Token

        Returns:
            SHA256 hash of the token
        """
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def _create_token_preview(cls, token: str) -> str:
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

    def get_decrypted_token(self) -> Optional[str]:
        """
        Get the decrypted token for this account.

        Returns:
            Decrypted token string or None if not available
        """
        if not self.encrypted_token:
            return None

        try:
            return self._decrypt_token(self.encrypted_token)
        except Exception:
            # Token decryption failed - possibly corrupted or key changed
            return None

    def set_encrypted_token(self, token: str):
        """
        Set the encrypted token for this account.

        Args:
            token: GitHub Personal Access Token to encrypt and store
        """
        self.encrypted_token = self._encrypt_token(token)

    def update_validation_status(self, token_info: "GitHubTokenInfo"):
        """
        Update the account's validation status.

        Args:
            token_info: Latest GitHubTokenInfo from validation
        """
        self.is_valid = token_info.is_valid
        self.last_validated_at = datetime.utcnow()

        if token_info.is_valid:
            self.validation_error = None
            self.rate_limit_remaining = token_info.rate_limit_remaining
            # Handle scopes storage - some models use JSON string, others use JSON column
            if (
                hasattr(self, "_store_scopes_as_json_string")
                and self._store_scopes_as_json_string
            ):
                self.scopes = (
                    json.dumps(token_info.scopes) if token_info.scopes else None
                )
            else:
                self.scopes = token_info.scopes
        else:
            self.validation_error = token_info.error_message

        self.updated_at = datetime.utcnow()

    def soft_delete(self):
        """Mark the account as inactive (soft delete)."""
        self.is_active = False
        self.updated_at = datetime.utcnow()

    @classmethod
    def get_by_username(
        cls: Type[AccountModel], session: Session, username: str
    ) -> Optional[AccountModel]:
        """
        Get an account by username.

        Args:
            session: Database session
            username: GitHub username

        Returns:
            Account instance or None
        """
        return (
            session.query(cls).filter(cls.username == username, cls.is_active).first()
        )

    @classmethod
    def get_by_token_hash(
        cls: Type[AccountModel], session: Session, token_hash: str
    ) -> Optional[AccountModel]:
        """
        Get an account by token hash.

        Args:
            session: Database session
            token_hash: SHA256 hash of the token

        Returns:
            Account instance or None
        """
        return (
            session.query(cls)
            .filter(cls.token_hash == token_hash, cls.is_active)
            .first()
        )

    @classmethod
    def get_all_active(cls: Type[AccountModel], session: Session) -> List[AccountModel]:
        """
        Get all active accounts.

        Args:
            session: Database session

        Returns:
            List of active account instances
        """
        return (
            session.query(cls)
            .filter(cls.is_active)
            .order_by(cls.created_at.desc())
            .all()
        )

    @classmethod
    def get_valid_accounts(
        cls: Type[AccountModel], session: Session
    ) -> List[AccountModel]:
        """
        Get all valid and active accounts.

        Args:
            session: Database session

        Returns:
            List of valid account instances
        """
        return (
            session.query(cls)
            .filter(cls.is_active, cls.is_valid)
            .order_by(cls.created_at.desc())
            .all()
        )
