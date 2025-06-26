"""
GitHub Client Wrapper

This module provides a high-level wrapper around the PyGithub library
for common GitHub operations used throughout GitPhish.
"""

import logging
from typing import Optional, Dict, Any, List
from github import Github, GithubException
from github.Repository import Repository
from github.AuthenticatedUser import AuthenticatedUser
import requests

from gitphish.core.accounts.auth.token_validator import GitHubTokenInfo

logger = logging.getLogger(__name__)


class GitHubClient:
    """High-level GitHub API client for GitPhish operations."""

    def __init__(self, token: str, timeout: int = 30):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub Personal Access Token
            timeout: Request timeout in seconds
        """
        self.token = token
        self.timeout = timeout
        self._github = None
        self._user_info = None
        self._validated = False

    @property
    def github(self) -> Github:
        """Get the underlying PyGithub client."""
        if self._github is None:
            self._github = Github(self.token, timeout=self.timeout)
        return self._github

    @property
    def user_info(self) -> Optional[GitHubTokenInfo]:
        """Get cached user information."""
        if not self._validated:
            self.validate_token()
        return self._user_info

    def _is_valid_token_format(self, token: str) -> bool:
        """
        Check if token has a valid GitHub PAT format.
        """
        if token.startswith("ghp_"):
            return 40 <= len(token) <= 44
        elif token.startswith("github_pat_"):
            return len(token) >= 50
        else:
            return len(token) >= 20

    def _get_token_scopes(
        self, github_client: Github, token: str = None
    ) -> Optional[List[str]]:
        """
        Get the scopes associated with the token.
        """
        try:
            # Method 1: Try to get scopes from the requester's last response
            try:
                last_response = (
                    github_client._Github__requester._Requester__last_response
                )
                if last_response and hasattr(last_response, "headers"):
                    scopes_header = last_response.headers.get("X-OAuth-Scopes", "")
                    if scopes_header:
                        scopes = [
                            scope.strip()
                            for scope in scopes_header.split(",")
                            if scope.strip()
                        ]
                        return scopes
            except Exception:
                pass
            # Method 2: Make a direct request to get scopes
            try:
                request_token = token
                if not request_token:
                    if hasattr(github_client, "_Github__auth") and hasattr(
                        github_client._Github__auth, "token"
                    ):
                        request_token = github_client._Github__auth.token
                    elif hasattr(github_client, "_Github__auth") and hasattr(
                        github_client._Github__auth, "_token"
                    ):
                        request_token = github_client._Github__auth._token
                if request_token:
                    headers = {
                        "Authorization": f"token {request_token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "GitPhish/1.0",
                    }
                    response = requests.get(
                        "https://api.github.com/user",
                        headers=headers,
                        timeout=10,
                    )
                    scopes_header = response.headers.get("X-OAuth-Scopes", "")
                    if scopes_header:
                        scopes = [
                            scope.strip()
                            for scope in scopes_header.split(",")
                            if scope.strip()
                        ]
                        return scopes
            except Exception:
                pass
            # Method 3: Try using the internal requester
            try:
                status, headers, data = (
                    github_client._Github__requester.requestJsonAndCheck("GET", "/user")
                )
                scopes_header = headers.get("X-OAuth-Scopes", "")
                if scopes_header:
                    scopes = [
                        scope.strip()
                        for scope in scopes_header.split(",")
                        if scope.strip()
                    ]
                    return scopes
            except Exception:
                pass
            return None
        except Exception:
            return None

    def _parse_github_error(self, error: GithubException) -> str:
        if error.status == 401:
            return "Invalid or expired token"
        elif error.status == 403:
            if "rate limit" in str(error).lower():
                return "Rate limit exceeded"
            else:
                return "Access forbidden - check token permissions"
        elif error.status == 404:
            return "Resource not found - token may lack required permissions"
        elif error.status >= 500:
            return "GitHub API server error - please try again later"
        else:
            return f"GitHub API error: {getattr(error, 'data', {}).get('message', str(error))}"

    def validate_token(self) -> GitHubTokenInfo:
        """
        Validate the token and cache user information.
        Returns:
            GitHubTokenInfo object with validation results
        """
        if not self._validated:
            token = self.token
            if not token or not isinstance(token, str):
                self._user_info = GitHubTokenInfo(
                    is_valid=False,
                    error_message="Token is empty or invalid format",
                )
                self._validated = True
                return self._user_info
            token = token.strip()
            if not self._is_valid_token_format(token):
                self._user_info = GitHubTokenInfo(
                    is_valid=False, error_message="Token format is invalid"
                )
                self._validated = True
                return self._user_info
            try:
                github_client = Github(token, timeout=self.timeout)
                user = github_client.get_user()
                rate_limit = github_client.get_rate_limit()
                scopes = self._get_token_scopes(github_client, token)
                self._user_info = GitHubTokenInfo(
                    is_valid=True,
                    username=user.login,
                    user_id=user.id,
                    email=user.email,
                    name=user.name,
                    avatar_url=user.avatar_url,
                    scopes=scopes,
                    rate_limit_remaining=rate_limit.core.remaining,
                )
            except GithubException as e:
                error_msg = self._parse_github_error(e)
                self._user_info = GitHubTokenInfo(
                    is_valid=False, error_message=error_msg
                )
            except Exception as e:
                error_msg = f"Unexpected error during token validation: {str(e)}"
                self._user_info = GitHubTokenInfo(
                    is_valid=False, error_message=error_msg
                )
            self._validated = True
        return self._user_info

    def is_valid(self) -> bool:
        """
        Check if the token is valid.

        Returns:
            True if token is valid, False otherwise
        """
        token_info = self.validate_token()
        return token_info.is_valid

    def get_username(self) -> Optional[str]:
        """
        Get the username associated with the token.

        Returns:
            Username or None if token is invalid
        """
        token_info = self.validate_token()
        return token_info.username if token_info.is_valid else None

    def get_user(self) -> Optional[AuthenticatedUser]:
        """
        Get the authenticated user object.

        Returns:
            AuthenticatedUser object or None if token is invalid
        """
        if not self.is_valid():
            return None

        try:
            return self.github.get_user()
        except GithubException as e:
            logger.error(f"Failed to get user: {str(e)}")
            return None

    def get_repository(
        self, repo_name: str, owner: Optional[str] = None
    ) -> Optional[Repository]:
        """
        Get a repository by name.

        Args:
            repo_name: Repository name
            owner: Repository owner (defaults to authenticated user)

        Returns:
            Repository object or None if not found
        """
        if not self.is_valid():
            return None

        try:
            if owner:
                full_name = f"{owner}/{repo_name}"
            else:
                username = self.get_username()
                if not username:
                    return None
                full_name = f"{username}/{repo_name}"

            return self.github.get_repo(full_name)

        except GithubException as e:
            if e.status == 404:
                logger.debug(f"Repository {full_name} not found")
            else:
                logger.error(f"Failed to get repository {full_name}: {str(e)}")
            return None

    def repository_exists(self, repo_name: str, owner: Optional[str] = None) -> bool:
        """
        Check if a repository exists.

        Args:
            repo_name: Repository name
            owner: Repository owner (defaults to authenticated user)

        Returns:
            True if repository exists, False otherwise
        """
        repo = self.get_repository(repo_name, owner)
        return repo is not None

    def create_repository(
        self,
        repo_name: str,
        description: Optional[str] = None,
        private: bool = False,
        auto_init: bool = True,
    ) -> Optional[Repository]:
        """
        Create a new repository.

        Args:
            repo_name: Repository name
            description: Repository description
            private: Whether repository should be private
            auto_init: Whether to initialize with README

        Returns:
            Repository object or None if creation failed
        """
        if not self.is_valid():
            return None

        try:
            user = self.get_user()
            if not user:
                return None

            repo = user.create_repo(
                name=repo_name,
                description=description,
                private=private,
                auto_init=auto_init,
            )

            logger.debug(f"Created repository: {repo.full_name}")
            return repo

        except GithubException as e:
            logger.error(f"Failed to create repository {repo_name}: {str(e)}")
            return None

    def delete_repository(self, repo_name: str, owner: Optional[str] = None) -> bool:
        """
        Delete a repository.

        Args:
            repo_name: Repository name
            owner: Repository owner (defaults to authenticated user)

        Returns:
            True if deletion successful, False otherwise
        """
        repo = self.get_repository(repo_name, owner)
        if not repo:
            logger.warning(f"Repository {repo_name} not found for deletion")
            return False

        try:
            repo.delete()
            logger.debug(f"Deleted repository: {repo.full_name}")
            return True

        except GithubException as e:
            logger.error(f"Failed to delete repository {repo.full_name}: {str(e)}")
            return False

    def enable_pages(self, repo_name: str, source_branch: str = "main") -> bool:
        """
        Enable GitHub Pages for a repository.

        Args:
            repo_name: Repository name
            source_branch: Source branch for Pages

        Returns:
            True if Pages enabled successfully, False otherwise
        """
        repo = self.get_repository(repo_name)
        if not repo:
            return False

        try:
            # Enable Pages
            repo.create_pages_site(source="branch", source_branch=source_branch)
            logger.debug(f"Enabled GitHub Pages for {repo.full_name}")
            return True

        except GithubException as e:
            if "already exists" in str(e).lower():
                logger.debug(f"GitHub Pages already enabled for {repo.full_name}")
                return True
            else:
                logger.error(f"Failed to enable Pages for {repo.full_name}: {str(e)}")
                return False

    def get_pages_url(
        self, repo_name: str, owner: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the GitHub Pages URL for a repository.

        Args:
            repo_name: Repository name
            owner: Repository owner (defaults to authenticated user)

        Returns:
            Pages URL or None if not available
        """
        repo = self.get_repository(repo_name, owner)
        if not repo:
            return None

        try:
            pages = repo.get_pages()
            return pages.html_url

        except GithubException as e:
            if e.status == 404:
                logger.debug(f"GitHub Pages not enabled for {repo.full_name}")
            else:
                logger.error(f"Failed to get Pages URL for {repo.full_name}: {str(e)}")
            return None

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Get current rate limit information.

        Returns:
            Dictionary with rate limit information
        """
        if not self.is_valid():
            return {"error": "Invalid token"}

        try:
            rate_limit = self.github.get_rate_limit()
            return {
                "core": {
                    "limit": rate_limit.core.limit,
                    "remaining": rate_limit.core.remaining,
                    "reset": rate_limit.core.reset.isoformat(),
                },
                "search": {
                    "limit": rate_limit.search.limit,
                    "remaining": rate_limit.search.remaining,
                    "reset": rate_limit.search.reset.isoformat(),
                },
            }

        except GithubException as e:
            logger.error(f"Failed to get rate limit info: {str(e)}")
            return {"error": str(e)}

    def check_required_permissions(self, required_scopes: List[str]) -> Dict[str, Any]:
        """
        Check if the token has required permissions.
        Args:
            required_scopes: List of required scopes
        Returns:
            Dictionary with permission check results
        """
        token_info = self.validate_token()
        if not token_info.is_valid:
            return {
                "has_permissions": False,
                "error": token_info.error_message,
                "missing_scopes": required_scopes,
            }
        if not token_info.scopes:
            return {
                "has_permissions": True,
                "warning": "Could not verify specific scopes - assuming sufficient permissions",
            }
        missing_scopes = [
            scope for scope in required_scopes if scope not in token_info.scopes
        ]
        return {
            "has_permissions": len(missing_scopes) == 0,
            "available_scopes": token_info.scopes,
            "missing_scopes": missing_scopes,
        }
