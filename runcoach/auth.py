"""JWT authentication for RunCoach API."""

from __future__ import annotations

import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify
from typing import Callable, Any
from werkzeug.security import check_password_hash, generate_password_hash


# Token expiry times
ACCESS_TOKEN_EXPIRY = timedelta(hours=1)
REFRESH_TOKEN_EXPIRY = timedelta(days=30)


def create_access_token(user_id: int, secret_key: str) -> str:
    """Create a JWT access token valid for 1 hour."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": "access",
        "exp": now + ACCESS_TOKEN_EXPIRY,
        "iat": now,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def create_refresh_token(user_id: int, secret_key: str) -> str:
    """Create a JWT refresh token valid for 30 days."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "exp": now + REFRESH_TOKEN_EXPIRY,
        "iat": now,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def verify_token(token: str, secret_key: str, expected_type: str = "access") -> dict | None:
    """
    Verify a JWT token and return the payload.

    Args:
        token: The JWT token string
        secret_key: Secret key for verification
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        Token payload dict if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])

        # Verify token type
        if payload.get("type") != expected_type:
            return None

        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_auth(f: Callable) -> Callable:
    """
    Decorator to require JWT authentication for API endpoints.

    Usage:
        @require_auth
        def my_endpoint():
            user_id = request.user_id  # Available after successful auth
            ...
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header"}), 401

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Verify token
        from flask import current_app
        secret_key = current_app.config["SECRET_KEY"]
        payload = verify_token(token, secret_key, "access")

        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Add user_id to request context
        request.user_id = payload["user_id"]

        return f(*args, **kwargs)

    return decorated_function


def hash_password(password: str) -> str:
    """Hash a password using werkzeug's secure method."""
    return generate_password_hash(password, method='pbkdf2:sha256')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return check_password_hash(password_hash, password)
