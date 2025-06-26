import requests
import logging
import threading
import time
from typing import Dict, Any, Optional
from urllib.parse import urljoin
from gitphish.models.auth_attempts.auth import DeviceAuthResult
from gitphish.config.auth import GitHubAuthConfig

logger = logging.getLogger(__name__)


class GitHubDeviceAuth:
    """Handles GitHub device code authentication flow."""

    def __init__(self, config: GitHubAuthConfig):
        self.config = config
        self.headers = {"Accept": "application/json"}
        self._auth_results = {}
        self._lock = threading.Lock()
        self._session = None

    def _create_session(self) -> requests.Session:
        """Create a requests session."""
        session = requests.Session()
        session.headers.update(self.headers)
        return session

    def _make_request(
        self,
        endpoint: str,
        method: str = "POST",
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to GitHub API."""
        url = urljoin(self.config.base_url, endpoint)

        # Create a new session or reuse existing one
        if not self._session:
            self._session = self._create_session()

        try:
            response = self._session.request(
                method=method, url=url, params=params, data=data, timeout=10
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            if response := getattr(e, "response", None):
                logger.error(f"Response content: {response.text}")
            raise

    def initiate_device_flow(self) -> Dict[str, str]:
        """Initiate the device code flow."""
        body = {
            "client_id": self.config.client_id,
            "scope": self.config.scopes,
        }

        results = self._make_request("/login/device/code", params=body)
        logger.debug(f"Device code expires in: {results.get('expires_in')} seconds")
        return results

    def poll_for_token(
        self, device_code: str, interval: int, email: str
    ) -> Optional[str]:
        """Poll for the access token with email tracking."""
        poll_params = {
            "client_id": self.config.client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }

        elapsed = 0
        current_interval = interval
        start_time = time.time()

        while elapsed < self.config.timeout:
            try:
                response = self._make_request(
                    "/login/oauth/access_token", data=poll_params
                )

                if "access_token" in response:
                    with self._lock:
                        self._auth_results[email] = DeviceAuthResult(
                            email=email,
                            access_token=response["access_token"],
                            status="SUCCESS",
                        )
                    logger.debug(f"Authentication successful for {email}!")
                    return response["access_token"]

                error = response.get("error")
                if error == "authorization_pending":
                    logger.debug(f"Waiting for device authorization for {email}...")
                elif error == "slow_down":
                    current_interval += 5
                    logger.debug(
                        f"Slowing down polling interval to {current_interval} seconds for {email}"
                    )
                else:
                    with self._lock:
                        self._auth_results[email] = DeviceAuthResult(
                            email=email,
                            access_token=None,
                            status="ERROR",
                            error=error,
                        )
                    logger.error(f"Authentication error for {email}: {error}")
                    return None

            except requests.RequestException as e:
                with self._lock:
                    self._auth_results[email] = DeviceAuthResult(
                        email=email,
                        access_token=None,
                        status="ERROR",
                        error=str(e),
                    )
                logger.error(f"Failed to poll for token for {email}", exc_info=True)
                return None

            time.sleep(current_interval)
            elapsed = time.time() - start_time

        with self._lock:
            self._auth_results[email] = DeviceAuthResult(
                email=email,
                access_token=None,
                status="TIMEOUT",
                error="Authentication timed out",
            )
        logger.error(f"Authentication timed out for {email}")
        return None

    def close(self):
        """Clean up resources."""
        if self._session:
            self._session.close()
            self._session = None
