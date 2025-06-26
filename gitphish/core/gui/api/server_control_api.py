"""
API endpoints for server control.
"""

import os
import logging
from flask import request, jsonify
from typing import Dict, List, Optional
import json
import datetime

import multiprocessing
import signal
import time
import threading

from gitphish.core.server.server import start_github_auth_server


class ServerControlAPI:
    """API endpoints for server control and email campaigns."""

    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger(__name__)

        # Server instance
        self.auth_server_process: Optional[multiprocessing.Process] = None

        self._setup_routes()

    def _setup_routes(self):
        """Setup Flask routes for server control API."""

        @self.app.route("/api/server/start", methods=["POST"])
        def start_server():
            """API endpoint to start the auth server."""
            try:
                data = request.get_json()

                client_id = data.get(
                    "client_id",
                    os.getenv("GITHUB_CLIENT_ID", "178c6fc778ccc68e1d6a"),
                )
                org_name = data.get(
                    "org_name",
                    os.getenv("GITHUB_ORG_NAME", "GitHub"),
                )
                host = data.get("host", "0.0.0.0")
                port = int(data.get("port", 443))
                cert_path = data.get("ssl_cert", "fullchain.pem")
                key_path = data.get("ssl_key", "privkey.pem")
                dev_mode = data.get("dev_mode", False)

                if self.auth_server_process and self.auth_server_process.is_alive():
                    return jsonify({"error": "Server is already running"}), 400

                self.auth_server_process = multiprocessing.Process(
                    target=start_github_auth_server,
                    kwargs={
                        "client_id": client_id,
                        "org_name": org_name,
                        "host": host,
                        "port": port,
                        "cert_path": cert_path,
                        "key_path": key_path,
                        "dev_mode": dev_mode,
                    },
                    daemon=True,
                )
                self.auth_server_process.start()

                # Wait briefly to verify the process actually started
                time.sleep(1)
                if not self.auth_server_process.is_alive():
                    self.logger.error("Auth server process failed to start.")
                    self.auth_server_process = None
                    return (
                        jsonify(
                            {
                                "error": (
                                    "Server failed to start. Check logs for details."
                                )
                            }
                        ),
                        500,
                    )

                self.logger.debug(f"Auth server started on {host}:{port}")
                return jsonify(
                    {"success": True, "message": "Server started successfully"}
                )

            except Exception as e:
                self.logger.error(f"Failed to start server: {str(e)}")
                return (
                    jsonify({"error": f"Failed to start server: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/server/stop", methods=["POST"])
        def stop_server():
            """API endpoint to stop the auth server."""
            try:
                if self.auth_server_process and self.auth_server_process.is_alive():
                    os.kill(self.auth_server_process.pid, signal.SIGINT)
                    self.auth_server_process.join(timeout=5)
                    self.auth_server_process = None
                    return jsonify(
                        {"success": True, "message": "Server stop initiated"}
                    )
                else:
                    return jsonify({"error": "No server running"}), 400
            except Exception as e:
                return (
                    jsonify({"error": f"Failed to stop server: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/stats")
        def get_gui_stats():
            """API endpoint to get GUI statistics."""
            return jsonify(self._get_gui_stats())

        @self.app.route("/api/logs")
        def get_logs():
            """API endpoint to get recent logs."""
            return jsonify({"logs": self._get_recent_logs()})

        @self.app.route("/api/allowlist", methods=["GET"])
        def get_allowlist():
            """Return the current allowlist as a JSON list."""
            try:
                allowlist = self._read_allowlist()
                return jsonify({"allowlist": sorted(list(allowlist))})
            except Exception as e:
                self.logger.error(f"Failed to read allowlist: {str(e)}")
                return jsonify({"error": f"Failed to read allowlist: {str(e)}"}), 500

        @self.app.route("/api/allowlist", methods=["POST"])
        def add_to_allowlist():
            """Add an email to the allowlist."""
            try:
                data = request.get_json()
                email = (data.get("email") or "").strip().lower()
                if not email or "@" not in email:
                    return jsonify({"error": "Invalid email address."}), 400
                allowlist = self._read_allowlist()
                if email in allowlist:
                    return jsonify({"error": "Email already in allowlist."}), 400
                allowlist.add(email)
                self._write_allowlist(allowlist)
                return jsonify({"success": True, "allowlist": sorted(list(allowlist))})
            except Exception as e:
                self.logger.error(f"Failed to add to allowlist: {str(e)}")
                return jsonify({"error": f"Failed to add to allowlist: {str(e)}"}), 500

        @self.app.route("/api/allowlist", methods=["DELETE"])
        def remove_from_allowlist():
            """Remove an email from the allowlist."""
            try:
                data = request.get_json()
                email = (data.get("email") or "").strip().lower()
                allowlist = self._read_allowlist()
                if email not in allowlist:
                    return jsonify({"error": "Email not in allowlist."}), 400
                allowlist.remove(email)
                self._write_allowlist(allowlist)
                return jsonify({"success": True, "allowlist": sorted(list(allowlist))})
            except Exception as e:
                self.logger.error(f"Failed to remove from allowlist: {str(e)}")
                return (
                    jsonify({"error": f"Failed to remove from allowlist: {str(e)}"}),
                    500,
                )

        @self.app.route("/api/active_sessions")
        def get_active_sessions():
            """API endpoint to get active authentication sessions."""
            sessions = []
            try:
                attempts_dir = "data/auth_attempts"
                tokens_dir = "data/successful_tokens"
                if not os.path.exists(attempts_dir):
                    return jsonify({"active_sessions": []})
                now = datetime.datetime.now(datetime.timezone.utc)
                for fname in os.listdir(attempts_dir):
                    if not fname.endswith(".json"):
                        continue
                    fpath = os.path.join(attempts_dir, fname)
                    with open(fpath, "r") as f:
                        data = json.load(f)
                    # Skip timed out
                    if data.get("timed_out"):
                        continue
                    email = data.get("email")
                    timestamp = data.get("timestamp")
                    tzname = data.get("timeZone", "UTC")
                    ip = data.get("ip_address")

                    if timestamp:
                        t = datetime.datetime.fromisoformat(timestamp)
                        if t.tzinfo is None:
                            try:
                                from zoneinfo import ZoneInfo

                                t = t.replace(tzinfo=ZoneInfo(tzname))
                            except Exception:
                                t = t.replace(tzinfo=datetime.timezone.utc)
                        t_utc = t.astimezone(datetime.timezone.utc)
                        if (now - t_utc).total_seconds() > 1200:
                            continue

                    # Check for corresponding successful token
                    found = False
                    if os.path.exists(tokens_dir):
                        for tname in os.listdir(tokens_dir):
                            if not tname.endswith(".json"):
                                continue
                            if (
                                email
                                and email in tname
                                and timestamp
                                and timestamp[:10] in tname
                            ):
                                found = True
                                break
                    if not found:
                        sessions.append(
                            {"email": email, "timestamp": timestamp, "ip_address": ip}
                        )
                return jsonify({"active_sessions": sessions})
            except Exception as e:
                self.logger.error(f"Failed to get active sessions: {e}")
                return jsonify({"active_sessions": [], "error": str(e)}), 500

    def _get_gui_stats(self) -> Dict:
        """Get statistics for GUI."""
        stats = {
            "server_running": (
                self.auth_server_process is not None
                and self.auth_server_process.is_alive()
            ),
            "total_attempts": 0,
            "successful_auths": 0,
            "recent_activity": [],
        }

        try:
            # Count auth attempts
            if os.path.exists("data/auth_attempts"):
                stats["total_attempts"] = len(os.listdir("data/auth_attempts"))

            # Count successful auths
            if os.path.exists("data/successful_tokens"):
                stats["successful_auths"] = len(os.listdir("data/successful_tokens"))

            # Get recent activity from logs
            stats["recent_activity"] = self._get_recent_logs(limit=5)

        except Exception as e:
            self.logger.error(f"Error getting stats: {str(e)}")

        return stats

    def _get_server_config(self) -> Dict:
        """Get current server configuration."""
        if not self.auth_server:
            return {}

        return {
            "host": self.auth_server.host,
            "port": self.auth_server.port,
            "cert_path": self.auth_server.cert_path,
            "key_path": self.auth_server.key_path,
        }

    def _get_recent_logs(self, limit: int = 50) -> List[Dict]:
        """Get recent log entries."""
        logs = []
        try:
            log_file = "data/logs/visitor_data.log"
            if os.path.exists(log_file):
                with open(log_file, "r") as f:
                    lines = f.readlines()
                    for line in lines[-limit:]:
                        if line.strip():
                            logs.append(
                                {
                                    "timestamp": (
                                        line.split(" - ")[0]
                                        if " - " in line
                                        else "Unknown"
                                    ),
                                    "message": line.strip(),
                                }
                            )
        except Exception as e:
            self.logger.error(f"Error reading logs: {str(e)}")

        return logs

    def get_server_status(self) -> Dict:
        """Get current server status for templates."""
        return {
            "running": (
                self.auth_server_process is not None
                and self.auth_server_process.is_alive()
            ),
            "config": (
                self._get_server_config()
                if (
                    self.auth_server_process is not None
                    and self.auth_server_process.is_alive()
                )
                else None
            ),
        }

    _allowlist_lock = threading.Lock()

    def _read_allowlist(self) -> set:
        """Read the allowlist from file."""
        allowlist_file = "data/allowlist.txt"
        emails = set()
        if not os.path.exists(allowlist_file):
            return emails
        with self._allowlist_lock, open(allowlist_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    emails.add(line.lower())
        return emails

    def _write_allowlist(self, allowlist: set):
        """Write the allowlist to file."""
        allowlist_file = "data/allowlist.txt"
        with self._allowlist_lock, open(allowlist_file, "w") as f:
            f.write("# One email per line\n")
            for email in sorted(allowlist):
                f.write(email + "\n")
