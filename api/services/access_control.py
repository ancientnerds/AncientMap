"""
Fair Use Access Control.

Manages concurrent user connections and inference queue for Lyra AI.
- Each PIN can only be used by one person at a time
- Inference requests queued FIFO
- One inference at a time
"""

import json
import time
import logging
from collections import deque
from typing import Optional
import threading
import os

logger = logging.getLogger(__name__)

# Configuration
STALE_TIMEOUT = int(os.getenv("AI_STALE_TIMEOUT", "300"))  # 5 minutes

# Valid PINs mapped to usernames - loaded from environment variable
# Format in .env: AI_VALID_PINS={"1234": "Alice", "5678": "Bob"}
def _load_valid_pins() -> dict[str, str]:
    """Load valid PINs from environment variable."""
    pins_json = os.getenv("AI_VALID_PINS", "{}")
    try:
        pins = json.loads(pins_json)
        if not pins:
            logger.warning("No AI_VALID_PINS configured - AI access will be disabled")
        return pins
    except json.JSONDecodeError as e:
        logger.error(f"Invalid AI_VALID_PINS format (must be JSON): {e}")
        return {}

VALID_PINS: dict[str, str] = _load_valid_pins()


class AccessControlService:
    """Manages user connections and inference queue."""

    def __init__(self):
        self._connected_users: dict[str, dict] = {}  # token → {pin, last_activity}
        self._pins_in_use: dict[str, str] = {}  # pin → token
        self._inference_queue: deque[str] = deque()   # tokens waiting
        self._current_inference: Optional[str] = None
        self._lock = threading.Lock()

    def is_valid_pin(self, pin: str) -> bool:
        """Check if PIN is in the valid list."""
        return pin in VALID_PINS

    def try_connect(self, token: str, pin: str) -> dict:
        """
        Connect a user with their PIN.

        Returns:
            dict with keys:
            - connected: bool
            - error: str (if failed)
            - message: str (user-friendly message)
            - users_connected: int
        """
        with self._lock:
            self._cleanup_stale()

            # Check if PIN is valid
            if pin not in VALID_PINS:
                return {
                    "connected": False,
                    "error": "invalid_pin",
                    "message": "Invalid PIN"
                }

            # Check if this token is already connected (reconnecting)
            if token in self._connected_users:
                user_data = self._connected_users[token]
                if user_data["pin"] == pin:
                    user_data["last_activity"] = time.time()
                    return {
                        "connected": True,
                        "reconnected": True,
                        "users_connected": len(self._connected_users)
                    }

            # Check if PIN is already in use by someone else - take over the session
            if pin in self._pins_in_use:
                existing_token = self._pins_in_use[pin]
                if existing_token != token and existing_token in self._connected_users:
                    # Kick the old session and allow this one to take over
                    del self._connected_users[existing_token]
                    del self._pins_in_use[pin]

            # Connect new user
            self._connected_users[token] = {
                "pin": pin,
                "last_activity": time.time()
            }
            self._pins_in_use[pin] = token

            return {
                "connected": True,
                "users_connected": len(self._connected_users)
            }

    def disconnect(self, token: str) -> bool:
        """
        User disconnected (closed modal, left page).

        Returns True if user was connected.
        """
        with self._lock:
            was_connected = token in self._connected_users

            # Free up the PIN
            if token in self._connected_users:
                pin = self._connected_users[token].get("pin")
                if pin and self._pins_in_use.get(pin) == token:
                    del self._pins_in_use[pin]

            self._connected_users.pop(token, None)

            # Remove from queue if waiting
            self._inference_queue = deque(
                t for t in self._inference_queue if t != token
            )

            # Clear current inference if this user was running
            if self._current_inference == token:
                self._current_inference = None
                # Promote next in queue
                if self._inference_queue:
                    self._current_inference = self._inference_queue.popleft()

            return was_connected

    def request_inference(self, token: str) -> dict:
        """
        Request to run inference. Returns queue position.

        Position 0 = your turn, go ahead.
        Position > 0 = waiting in queue.

        Returns:
            dict with keys:
            - position: int (0 = processing, >0 = waiting)
            - status: str ("processing", "waiting", "error")
            - error: str (if not connected)
        """
        with self._lock:
            if token not in self._connected_users:
                return {"error": "not_connected", "status": "error"}

            # Update activity timestamp
            self._connected_users[token]["last_activity"] = time.time()

            # If no one running and queue empty, go ahead
            if self._current_inference is None and len(self._inference_queue) == 0:
                self._current_inference = token
                return {"position": 0, "status": "processing"}

            # If we're already the current one, continue
            if self._current_inference == token:
                return {"position": 0, "status": "processing"}

            # If already in queue, return position
            if token in self._inference_queue:
                position = list(self._inference_queue).index(token) + 1
                return {"position": position, "status": "waiting"}

            # Add to queue
            self._inference_queue.append(token)
            position = len(self._inference_queue)
            return {"position": position, "status": "waiting"}

    def finish_inference(self, token: str) -> Optional[str]:
        """
        Called when inference completes.

        Returns the next token that should process (if any).
        """
        with self._lock:
            if self._current_inference == token:
                self._current_inference = None
                # Promote next in queue
                if self._inference_queue:
                    self._current_inference = self._inference_queue.popleft()
                    return self._current_inference
            return None

    def get_queue_position(self, token: str) -> dict:
        """
        Get current queue status for a token.

        Returns:
            dict with keys:
            - position: int (-1 = idle, 0 = processing, >0 = waiting)
            - status: str ("idle", "processing", "waiting")
        """
        with self._lock:
            if self._current_inference == token:
                return {"position": 0, "status": "processing"}

            if token in self._inference_queue:
                position = list(self._inference_queue).index(token) + 1
                return {"position": position, "status": "waiting"}

            return {"position": -1, "status": "idle"}

    def get_status(self) -> dict:
        """Get overall system status."""
        with self._lock:
            return {
                "connected_users": len(self._connected_users),
                "pins_in_use": len(self._pins_in_use),
                "queue_length": len(self._inference_queue),
                "inference_active": self._current_inference is not None
            }

    def update_activity(self, token: str) -> bool:
        """Update last activity time for a token. Returns True if token exists."""
        with self._lock:
            if token in self._connected_users:
                self._connected_users[token]["last_activity"] = time.time()
                return True
            return False

    def _cleanup_stale(self):
        """Remove users inactive for > STALE_TIMEOUT seconds."""
        now = time.time()
        stale = [
            token for token, data in self._connected_users.items()
            if now - data.get("last_activity", 0) > STALE_TIMEOUT
        ]
        for token in stale:
            # Free up the PIN
            if token in self._connected_users:
                pin = self._connected_users[token].get("pin")
                if pin and self._pins_in_use.get(pin) == token:
                    del self._pins_in_use[pin]
            self._connected_users.pop(token, None)
            # Also remove from queue
            self._inference_queue = deque(
                t for t in self._inference_queue if t != token
            )
            # Clear current inference if stale
            if self._current_inference == token:
                self._current_inference = None


# Singleton instance
_access_control: Optional[AccessControlService] = None


def get_access_control() -> AccessControlService:
    """Get the singleton AccessControlService instance."""
    global _access_control
    if _access_control is None:
        _access_control = AccessControlService()
    return _access_control
