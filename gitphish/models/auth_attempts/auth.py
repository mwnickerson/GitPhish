from dataclasses import dataclass
from typing import Optional, NamedTuple


class DeviceAuthResult(NamedTuple):
    """Stores the result of a device authentication attempt."""

    email: str
    access_token: Optional[str]
    status: str
    error: Optional[str] = None


@dataclass
class AuthAttempt:
    """Represents a single authentication attempt with all its associated data."""

    email: str
    device_code: Optional[str] = None
    user_code: Optional[str] = None
    verification_uri: Optional[str] = None
    expires_in: Optional[int] = None
    access_token: Optional[str] = None
    status: str = "PENDING"
    error: Optional[str] = None
    email_sent: bool = False
