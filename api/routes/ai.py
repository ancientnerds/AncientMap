"""
AI Agent API Routes.

Provides endpoints for:
- PIN verification and session management
- Chat queries with RAG
- Server-Sent Events streaming
"""

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.config.ai_modes import DEFAULT_MODE, get_all_modes, get_mode_config
from api.services.access_control import get_access_control
from api.services.admin_auth import get_client_ip
from api.services.turnstile import verify_turnstile as _verify_turnstile

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session store (for production, use Redis)
_sessions: dict[str, dict] = {}

# Configuration
SESSION_TTL = int(os.getenv("AI_SESSION_TTL", "3600"))  # 1 hour default

# IP Lockout configuration
_failed_attempts: dict[str, dict] = {}  # {ip: {"count": int, "locked_until": datetime}}
LOCKOUT_THRESHOLD = 3  # Failed attempts before lockout
LOCKOUT_DURATION = 3600  # 1 hour in seconds


# ============================================================================
# Pydantic Models
# ============================================================================

class PinVerifyRequest(BaseModel):
    """Request to verify 4-digit PIN."""
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    turnstile_token: str = Field(..., description="Cloudflare Turnstile verification token")


class PinVerifyResponse(BaseModel):
    """Response from PIN verification."""
    verified: bool
    session_token: str | None = None
    expires_in: int | None = None
    error: str | None = None
    message: str | None = None
    connected: bool = False
    users_connected: int = 0


class ChatRequest(BaseModel):
    """Request for chat query."""
    session_token: str
    message: str = Field(..., min_length=1, max_length=2000)
    include_sites: bool = True


class SiteHighlightResponse(BaseModel):
    """Site data for highlighting on map."""
    id: str
    name: str
    lat: float
    lon: float
    site_type: str | None = None
    period_name: str | None = None


class ChatResponse(BaseModel):
    """Response from chat query."""
    response: str
    sites: list[SiteHighlightResponse] = []
    query_metadata: dict = {}


class HealthResponse(BaseModel):
    """AI service health status."""
    status: str
    vector_store: dict
    llm: dict


# ============================================================================
# Session Management
# ============================================================================

def _create_session(ip_address: str) -> str:
    """Create a new session and return the token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "ip_address": ip_address,
        "message_count": 0,
        "history": []  # Conversation history for context awareness
    }
    return token


def _add_to_history(token: str, role: str, content: str, max_history: int = 10):
    """Add message to conversation history."""
    if token in _sessions:
        _sessions[token]["history"].append({
            "role": role,  # "user" or "assistant"
            "content": content[:500]  # Truncate long messages
        })
        # Keep only last N messages
        if len(_sessions[token]["history"]) > max_history:
            _sessions[token]["history"] = _sessions[token]["history"][-max_history:]


def _get_history(token: str) -> list[dict]:
    """Get conversation history for session."""
    if token in _sessions:
        return _sessions[token].get("history", [])
    return []


def _validate_session(token: str) -> bool:
    """Validate session token and check expiry. Returns True if valid, False otherwise."""
    if token not in _sessions:
        return False

    session = _sessions[token]
    now = datetime.utcnow()

    # Check expiry
    if now - session["created_at"] > timedelta(seconds=SESSION_TTL):
        del _sessions[token]
        return False

    # Update last activity
    session["last_activity"] = now
    return True


def _cleanup_sessions():
    """Remove expired sessions."""
    now = datetime.utcnow()
    expired = [
        token for token, session in _sessions.items()
        if now - session["created_at"] > timedelta(seconds=SESSION_TTL)
    ]
    for token in expired:
        del _sessions[token]


# ============================================================================
# IP Lockout Management
# ============================================================================

def _check_ip_lockout(ip: str) -> tuple[bool, int]:
    """Check if IP is locked out. Returns (is_locked, seconds_remaining)."""
    if ip not in _failed_attempts:
        return False, 0

    data = _failed_attempts[ip]
    if "locked_until" in data:
        remaining = (data["locked_until"] - datetime.utcnow()).total_seconds()
        if remaining > 0:
            return True, int(remaining)
        else:
            # Lockout expired, reset
            del _failed_attempts[ip]
            return False, 0
    return False, 0


def _record_failed_attempt(ip: str) -> bool:
    """Record a failed attempt. Returns True if IP is now locked out."""
    if ip not in _failed_attempts:
        _failed_attempts[ip] = {"count": 0}

    _failed_attempts[ip]["count"] += 1

    logger.warning(f"Failed PIN attempt from {ip} (attempt {_failed_attempts[ip]['count']}/{LOCKOUT_THRESHOLD})")

    if _failed_attempts[ip]["count"] >= LOCKOUT_THRESHOLD:
        _failed_attempts[ip]["locked_until"] = datetime.utcnow() + timedelta(seconds=LOCKOUT_DURATION)
        logger.warning(f"IP {ip} locked out for {LOCKOUT_DURATION} seconds after {LOCKOUT_THRESHOLD} failed attempts")
        return True
    return False  # Not locked out yet


def _clear_failed_attempts(ip: str):
    """Clear failed attempts on successful PIN entry."""
    if ip in _failed_attempts:
        del _failed_attempts[ip]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/modes")
async def get_modes():
    """
    Get available AI modes and their configurations.

    Returns all mode configs for frontend display.
    """
    return get_all_modes()


@router.post("/verify", response_model=PinVerifyResponse)
async def verify_pin(request: PinVerifyRequest, req: Request):
    """
    Verify 4-digit PIN and try to connect.

    Security layers:
    1. IP lockout check (3 failed attempts = 1 hour ban)
    2. Cloudflare Turnstile verification (bot protection)
    3. PIN validation

    Each PIN can only be used by one person at a time.
    Returns a session token if PIN is valid and not in use.
    """
    # Cleanup old sessions periodically
    _cleanup_sessions()

    ip_address = get_client_ip(req)

    # 1. Check IP lockout first (before any expensive operations)
    is_locked, seconds_remaining = _check_ip_lockout(ip_address)
    if is_locked:
        minutes = max(1, seconds_remaining // 60)
        return PinVerifyResponse(
            verified=False,
            error="ip_locked",
            message=f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes > 1 else ''}."
        )

    # 2. Verify Cloudflare Turnstile token (bot protection)
    if not await _verify_turnstile(request.turnstile_token, ip_address):
        return PinVerifyResponse(
            verified=False,
            error="captcha_failed",
            message="Verification failed. Please complete the captcha and try again."
        )

    # 3. Create session token
    token = _create_session(ip_address)

    # 4. Try to connect with this PIN
    access_control = get_access_control()
    result = access_control.try_connect(token, request.pin)

    if not result.get("connected"):
        error_type = result.get("error", "unknown")

        # Only track failed attempts for invalid PINs (not for "pin_in_use")
        if error_type == "invalid_pin":
            is_now_locked = _record_failed_attempt(ip_address)
            if is_now_locked:
                return PinVerifyResponse(
                    verified=False,
                    error="ip_locked",
                    message="Too many failed attempts. Try again in 60 minutes."
                )
            # Show remaining attempts
            attempts_left = LOCKOUT_THRESHOLD - _failed_attempts.get(ip_address, {}).get("count", 0)
            return PinVerifyResponse(
                verified=False,
                error="invalid_pin",
                message=f"Invalid PIN. {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining."
            )

        # PIN in use or other errors - don't track as failed attempt
        logger.warning(f"PIN connection failed from {ip_address}: {error_type}")
        return PinVerifyResponse(
            verified=False,
            error=error_type,
            message=result.get("message", "Connection failed")
        )

    # Success - clear any failed attempts for this IP
    _clear_failed_attempts(ip_address)

    logger.info(f"AI session created for {ip_address} ({result.get('users_connected')} users online)")

    return PinVerifyResponse(
        verified=True,
        session_token=token,
        expires_in=SESSION_TTL,
        connected=True,
        users_connected=result.get("users_connected", 0)
    )


@router.post("/disconnect")
async def disconnect(session_token: str = Query(...)):
    """
    Disconnect user and free up slot.

    Call this when user closes the chat modal.
    """
    access_control = get_access_control()
    was_connected = access_control.disconnect(session_token)

    # Also clean up session
    if session_token in _sessions:
        del _sessions[session_token]

    return {"success": True, "was_connected": was_connected}


@router.get("/access-status")
async def access_status():
    """
    Get current access control status.

    Returns connected users count and queue info.
    """
    access_control = get_access_control()
    return access_control.get_status()


def _extract_bearer_token(authorization: str | None) -> str:
    """Extract token from Authorization: Bearer <token> header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must use Bearer scheme")
    return authorization[7:]  # Remove "Bearer " prefix


@router.get("/pins")
async def list_pins(authorization: str | None = Header(None, description="Bearer token for admin authentication")):
    """
    List all PINs and their assigned usernames.

    Requires admin key for access via Authorization: Bearer header.
    Admin key must be set via AI_ADMIN_KEY environment variable.
    """
    from api.services.access_control import VALID_PINS

    # Verify admin key from Authorization header
    admin_key = _extract_bearer_token(authorization)
    configured_admin_key = os.getenv("AI_ADMIN_KEY", "")
    if not configured_admin_key:
        logger.warning("AI_ADMIN_KEY not configured - /pins endpoint disabled")
        raise HTTPException(status_code=503, detail="Admin access not configured")

    if not secrets.compare_digest(admin_key, configured_admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    return {
        "pins": [
            {"pin": pin, "username": username}
            for pin, username in VALID_PINS.items()
        ]
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a chat query through the RAG pipeline.

    Requires a valid session token from /verify.
    Returns the response text and any sites to highlight.
    """
    # Validate session
    if not _validate_session(request.session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Update message count
    _sessions[request.session_token]["message_count"] += 1

    try:
        # Import here to avoid circular imports and lazy loading
        from api.services.rag_service import get_rag_service

        rag_service = get_rag_service()
        result = await rag_service.process_query(
            query=request.message,
            include_site_details=request.include_sites
        )

        return ChatResponse(
            response=result.text,
            sites=[
                SiteHighlightResponse(
                    id=s.id,
                    name=s.name,
                    lat=s.lat,
                    lon=s.lon,
                    site_type=s.site_type,
                    period_name=s.period_name
                )
                for s in result.sites
            ],
            query_metadata=result.metadata
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your query. Please try again."
        ) from e


@router.get("/stream")
async def stream_chat(
    session_token: str = Query(...),
    message: str = Query(..., min_length=1, max_length=2000),
    sources: str = Query(default="ancient_nerds", description="Comma-separated source IDs"),
    mode: str = Query(default=DEFAULT_MODE, description="AI mode: chat or research")
):
    """
    Stream chat response using Server-Sent Events.

    Args:
        session_token: Valid session token from /verify
        message: User's query
        sources: Comma-separated source IDs (default: ancient_nerds)
        mode: AI mode - 'chat' for fast responses, 'research' for detailed analysis

    Events:
    - queued: {"position": N}    - Waiting in queue at position N
    - processing: {}             - Started processing (queue turn)
    - token: {"content": "..."}  - Generated text tokens
    - sites: {"sites": [...]}    - Sites to highlight
    - done: {"metadata": {...}}  - Completion with metadata
    - error: {"error": "..."}    - Error message
    """
    # Get mode configuration
    mode_config = get_mode_config(mode)

    # Validate session
    if not _validate_session(session_token):
        async def error_stream():
            yield f"event: error\ndata: {json.dumps({'error': 'Invalid or expired session'})}\n\n"
        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream"
        )

    # Parse source IDs
    source_ids = [s.strip() for s in sources.split(",") if s.strip()]
    if not source_ids:
        source_ids = ["ancient_nerds"]  # Default

    # Update message count
    _sessions[session_token]["message_count"] += 1

    # Get conversation history for context
    conversation_history = _get_history(session_token)

    # Add user message to history
    _add_to_history(session_token, "user", message)

    # Get access control for queue management
    access_control = get_access_control()

    async def generate():
        full_response = ""  # Collect full response for history
        try:
            # Request inference slot
            queue_result = access_control.request_inference(session_token)

            if queue_result.get("error"):
                yield f"event: error\ndata: {json.dumps({'error': 'Not connected'})}\n\n"
                return

            # If queued, wait for our turn
            if queue_result.get("position", 0) > 0:
                position = queue_result["position"]
                yield f"event: queued\ndata: {json.dumps({'position': position})}\n\n"

                # Poll until our turn
                while True:
                    await asyncio.sleep(0.5)
                    status = access_control.get_queue_position(session_token)
                    new_position = status.get("position", -1)

                    if new_position == 0:
                        # Our turn!
                        yield f"event: processing\ndata: {json.dumps({'status': 'starting'})}\n\n"
                        break
                    elif new_position == -1:
                        # Something went wrong
                        yield f"event: error\ndata: {json.dumps({'error': 'Lost queue position'})}\n\n"
                        return
                    elif new_position != position:
                        # Position changed
                        position = new_position
                        yield f"event: queued\ndata: {json.dumps({'position': position})}\n\n"

            # Now we're processing - do the actual inference
            from api.services.rag_service import get_rag_service

            rag_service = get_rag_service()

            async for chunk in rag_service.process_query_stream(
                query=message,
                source_ids=source_ids,
                conversation_history=conversation_history,
                model_override=mode_config["model"],
                max_tokens=mode_config["max_tokens"]
            ):
                if chunk["type"] == "token":
                    full_response += chunk["content"]  # Collect for history
                    yield f"event: token\ndata: {json.dumps({'content': chunk['content']})}\n\n"
                elif chunk["type"] == "sites":
                    yield f"event: sites\ndata: {json.dumps({'sites': chunk['sites']})}\n\n"
                elif chunk["type"] == "done":
                    # Store assistant response in history
                    if full_response:
                        _add_to_history(session_token, "assistant", full_response)
                    # Add model and mode info to metadata
                    metadata = chunk.get("metadata", {})
                    metadata["model"] = mode_config["model"]
                    metadata["mode"] = mode
                    yield f"event: done\ndata: {json.dumps({'metadata': metadata})}\n\n"

                # Allow other tasks to run
                await asyncio.sleep(0)

            # Finished - release inference slot
            access_control.finish_inference(session_token)

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            # Make sure to release slot on error
            access_control.finish_inference(session_token)
            yield f"event: error\ndata: {json.dumps({'error': 'An error occurred. Please try again.'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check health of AI services.

    Returns status of vector store and LLM service.
    """
    try:
        from api.services.rag_service import get_rag_service

        rag_service = get_rag_service()
        health = rag_service.health_check()

        return HealthResponse(
            status=health["status"],
            vector_store=health["vector_store"],
            llm=health["llm"]
        )

    except Exception as e:
        return HealthResponse(
            status="error",
            vector_store={"status": "unknown"},
            llm={"status": "unknown", "error": str(e)}
        )


@router.get("/session-info")
async def session_info(session_token: str = Query(...)):
    """
    Get information about current session.

    Useful for debugging and showing session status in UI.
    """
    if not _validate_session(session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    session = _sessions[session_token]
    now = datetime.utcnow()
    remaining = SESSION_TTL - (now - session["created_at"]).total_seconds()

    return {
        "valid": True,
        "message_count": session["message_count"],
        "created_at": session["created_at"].isoformat(),
        "expires_in_seconds": max(0, int(remaining))
    }
