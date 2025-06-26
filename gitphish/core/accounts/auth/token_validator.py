"""
GitHub Authentication and Token Validation

This module provides utilities for validating GitHub Personal Access Tokens
and retrieving associated user information.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GitHubTokenInfo:
    """Information about a GitHub token and associated user."""

    is_valid: bool
    username: Optional[str] = None
    user_id: Optional[int] = None
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    scopes: Optional[List[str]] = None
    rate_limit_remaining: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "is_valid": self.is_valid,
            "username": self.username,
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "scopes": self.scopes,
            "rate_limit_remaining": self.rate_limit_remaining,
            "error_message": self.error_message,
        }
