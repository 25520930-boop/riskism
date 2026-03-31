"""
Riskism - FastAPI Main Application V3.0
Core backend server with REST API + WebSocket.
V3.0: Simplified endpoints, shared risk logic, global error handling.
"""
import json
import asyncio
import time as _time
import re
import hmac
import hashlib
import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from sqlalchemy import text
from backend.database import SyncSessionLocal

from backend.config import get_settings
from backend.agent.orchestrator import AgentOrchestrator
from backend.data.vnstock_client import VnstockClient
from backend.firebase_auth import get_firebase_public_config, verify_firebase_id_token
from backend.risk_engine.capital_aware import SECTOR_MAP

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    SLOWAPI_AVAILABLE = True
except ImportError:
    Limiter = None
    RateLimitExceeded = None
    SLOWAPI_AVAILABLE = False

settings = get_settings()

PASSWORD_ITERATIONS = 310000
PASSWORD_MIN_LENGTH = 8
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
LOCAL_USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,30}[a-z0-9])?$")
DEMO_USER_PASSWORD_HASH = "pbkdf2_sha256$310000$9c3f4ec51f8ae5ff27b1e978df3f98b0$e623f55994dab0705f4080292443eb20a0dbc2292fd62a675aafb4cdffe0bb0a"

# Global instances
agent = AgentOrchestrator()
vnstock = VnstockClient()
agent_execution_lock = asyncio.Lock()
auto_agent_tasks: Dict[Tuple[int, str], asyncio.Task] = {}


def _default_auto_agent_state() -> Dict:
    return {
        'running': None,
        'last_runs': {},
        'latest_execution_log': [],
        'latest_result': None,
    }


auto_agent_state = defaultdict(_default_auto_agent_state)
AGENT_AUTOMATION_COOLDOWN_SECONDS = 90
AUTO_MORNING_START_MINUTES = 8 * 60 + 30
AUTO_AFTERNOON_START_MINUTES = 15 * 60 + 30


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()


# ─── Lifespan ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Riskism Backend V3.0 starting...")
    price_task = asyncio.create_task(price_broadcast_loop())
    automation_task = asyncio.create_task(agent_automation_loop())
    yield
    price_task.cancel()
    automation_task.cancel()
    await asyncio.gather(price_task, automation_task, return_exceptions=True)
    print("👋 Riskism Backend shutting down")


# ─── App ─────────────────────────────────────────────────
app = FastAPI(
    title="Riskism API",
    description="🔷 Vietnamese Stock Market Risk Assessment Platform V3.0",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if SLOWAPI_AVAILABLE and RateLimitExceeded is not None:
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc):
        retry_after = None
        headers = getattr(exc, "headers", {}) or {}
        if headers.get("Retry-After") is not None:
            retry_after = headers.get("Retry-After")
        elif getattr(exc, "retry_after", None) is not None:
            retry_after = getattr(exc, "retry_after")

        try:
            retry_seconds = int(float(retry_after)) if retry_after is not None else 60
        except (TypeError, ValueError):
            retry_seconds = 60
        return _rate_limit_response(retry_seconds)


@app.middleware("http")
async def fallback_rate_limit_middleware(request: Request, call_next):
    if SLOWAPI_AVAILABLE:
        return await call_next(request)

    limiter_for_request = _fallback_rate_limiter_for_request(request)
    client_ip = request.client.host if request.client else "unknown"
    if not limiter_for_request.is_allowed(client_ip):
        return _rate_limit_response(limiter_for_request.retry_after(client_ip))
    return await call_next(request)


# ─── Global Error Handler ────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    print(f"[ERROR] Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


# ─── Pydantic Models ────────────────────────────────────
class AgentTriggerRequest(BaseModel):
    analysis_type: str = "morning"
    symbol: Optional[str] = None

class ChatMessageRequest(BaseModel):
    message: str
    history: List[dict] = Field(default_factory=list)
    app_context: Dict = Field(default_factory=dict)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── Rate Limiter ────────────────────────────────────────
class SlidingWindowRateLimiter:
    """Simple in-memory sliding window rate limiter."""
    def __init__(self, max_calls: int = 3, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls = defaultdict(list)  # ip -> [timestamps]

    def is_allowed(self, key: str) -> bool:
        now = _time.time()
        # Prune old entries
        self._calls[key] = [t for t in self._calls[key] if now - t < self.window]
        if len(self._calls[key]) >= self.max_calls:
            return False
        self._calls[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        now = _time.time()
        self._calls[key] = [t for t in self._calls[key] if now - t < self.window]
        return max(0, self.max_calls - len(self._calls[key]))

    def retry_after(self, key: str) -> int:
        if not self._calls[key]:
            return 0
        oldest = min(self._calls[key])
        return max(0, int(self.window - (_time.time() - oldest)))


def _noop_limit(*args, **kwargs):
    def decorator(func):
        return func
    return decorator


limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"]) if SLOWAPI_AVAILABLE else None
limit_decorator = limiter.limit if limiter else _noop_limit
general_rate_limiter = SlidingWindowRateLimiter(max_calls=60, window_seconds=60)
auth_rate_limiter = SlidingWindowRateLimiter(max_calls=10, window_seconds=60)
agent_rate_limiter = SlidingWindowRateLimiter(max_calls=5, window_seconds=60)

if limiter:
    app.state.limiter = limiter


def _rate_limit_response(retry_after: int) -> JSONResponse:
    retry_seconds = max(1, int(retry_after or 1))
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded. Try again in {retry_seconds}s."},
        headers={"Retry-After": str(retry_seconds)},
    )


def _fallback_rate_limiter_for_request(request: Request) -> SlidingWindowRateLimiter:
    path = request.url.path
    method = request.method.upper()
    if method == "POST" and path == "/api/agent/trigger":
        return agent_rate_limiter
    if method == "POST" and path in {"/api/auth/login", "/api/auth/signup"}:
        return auth_rate_limiter
    return general_rate_limiter


# ─── Background Tasks ───────────────────────────────────
async def price_broadcast_loop():
    """Broadcast live prices via WebSocket every 10 seconds."""
    symbols = ['VCB', 'FPT', 'HPG', 'TCB', 'MWG']
    while True:
        try:
            if ws_manager.active_connections:
                prices = {}
                for symbol in symbols:
                    try:
                        data = await vnstock.get_historical_data_async(symbol, days=2)
                        if data and data.get('close'):
                            close = data['close']
                            if len(close) >= 2:
                                prices[symbol] = {
                                    'price': close[-1],
                                    'change_pct': round((close[-1] - close[-2]) / close[-2] * 100, 2)
                                }
                    except Exception:
                        pass

                if prices:
                    await ws_manager.broadcast({
                        'type': 'price_update',
                        'data': prices,
                        'timestamp': datetime.now().isoformat(),
                    })
        except Exception as e:
            print(f"[WS] Broadcast error: {e}")

        await asyncio.sleep(10)


def _coerce_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _parse_json_field(payload):
    if payload is None:
        return None
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
    return None


def _load_latest_insight_sync(user_id: int) -> Optional[Dict]:
    db = None
    try:
        db = SyncSessionLocal()
        row = db.execute(
            text(
                "SELECT title, content, risk_level, confidence_score, created_at "
                "FROM insights WHERE user_id = :uid ORDER BY created_at DESC LIMIT 1"
            ),
            {"uid": user_id}
        ).fetchone()
        if not row:
            return None

        insight = _parse_json_field(row[1]) or {}
        if not insight:
            insight = {
                "title": row[0],
                "summary": row[1],
                "risk_level": row[2],
                "confidence_score": float(row[3] or 0),
            }
        insight.setdefault("title", row[0] or "AI Insight")
        insight.setdefault("risk_level", row[2] or "medium")
        insight.setdefault("confidence_score", float(row[3] or 0))
        if row[4] and not insight.get("saved_at"):
            insight["saved_at"] = row[4].isoformat()
        return insight
    except Exception as e:
        print(f"[Agent] Failed to load latest insight for user {user_id}: {e}")
        return None
    finally:
        if db:
            db.close()


def _load_latest_morning_prediction_sync(user_id: int) -> Optional[Dict]:
    db = None
    try:
        db = SyncSessionLocal()
        row = db.execute(
            text(
                "SELECT content, predicted_at FROM morning_predictions "
                "WHERE user_id = :uid ORDER BY predicted_at DESC LIMIT 1"
            ),
            {"uid": user_id}
        ).fetchone()
        if not row:
            return None

        prediction = _parse_json_field(row[0]) or {}
        if row[1] and not prediction.get("predicted_at"):
            prediction["predicted_at"] = row[1].isoformat()
        return prediction
    except Exception as e:
        print(f"[Agent] Failed to load latest prediction for user {user_id}: {e}")
        return None
    finally:
        if db:
            db.close()


def _load_latest_reflection_sync(user_id: int) -> Optional[Dict]:
    db = None
    try:
        db = SyncSessionLocal()
        row = db.execute(
            text(
                "SELECT content, evaluated_at FROM reflections "
                "WHERE user_id = :uid ORDER BY evaluated_at DESC LIMIT 1"
            ),
            {"uid": user_id}
        ).fetchone()
        if not row:
            return None

        reflection = _parse_json_field(row[0]) or {}
        if row[1] and not reflection.get("evaluated_at"):
            reflection["evaluated_at"] = row[1].isoformat()
        return reflection
    except Exception as e:
        print(f"[Agent] Failed to load latest reflection for user {user_id}: {e}")
        return None
    finally:
        if db:
            db.close()


def _load_latest_agent_dates_sync(user_id: int) -> Dict[str, Optional[str]]:
    db = None
    try:
        db = SyncSessionLocal()
        morning = db.execute(
            text("SELECT predicted_at FROM morning_predictions WHERE user_id = :uid ORDER BY predicted_at DESC LIMIT 1"),
            {"uid": user_id}
        ).fetchone()
        reflection = db.execute(
            text("SELECT evaluated_at FROM reflections WHERE user_id = :uid ORDER BY evaluated_at DESC LIMIT 1"),
            {"uid": user_id}
        ).fetchone()
        return {
            "morning_date": morning[0].date().isoformat() if morning and morning[0] else None,
            "reflection_date": reflection[0].date().isoformat() if reflection and reflection[0] else None,
        }
    except Exception as e:
        print(f"[Agent] Failed to load agent dates for user {user_id}: {e}")
        return {"morning_date": None, "reflection_date": None}
    finally:
        if db:
            db.close()


def _list_users_with_holdings_sync() -> List[int]:
    db = None
    try:
        db = SyncSessionLocal()
        rows = db.execute(
            text("SELECT DISTINCT user_id FROM portfolios WHERE quantity > 0 ORDER BY user_id")
        ).fetchall()
        return [int(row[0]) for row in rows if row and row[0] is not None]
    except Exception as e:
        print(f"[Agent] Failed to list users with holdings: {e}")
        return []
    finally:
        if db:
            db.close()


def _user_has_holdings_sync(user_id: int) -> bool:
    db = None
    try:
        db = SyncSessionLocal()
        row = db.execute(
            text("SELECT 1 FROM portfolios WHERE user_id = :uid AND quantity > 0 LIMIT 1"),
            {"uid": user_id}
        ).fetchone()
        return bool(row)
    except Exception as e:
        print(f"[Agent] Failed to check holdings for user {user_id}: {e}")
        return False
    finally:
        if db:
            db.close()


def _minutes_since_midnight(now: datetime) -> int:
    return now.hour * 60 + now.minute


def _should_skip_agent_run(user_id: int, analysis_type: str, force: bool = False) -> bool:
    if force:
        return False

    state = auto_agent_state[user_id]
    last_run = state['last_runs'].get(analysis_type)
    completed_at = _coerce_datetime(last_run.get('completed_at')) if isinstance(last_run, dict) else None
    if not completed_at:
        return False
    return (datetime.now() - completed_at).total_seconds() < AGENT_AUTOMATION_COOLDOWN_SECONDS


async def _execute_agent_analysis(
    user_id: int,
    analysis_type: str,
    symbol: Optional[str] = None,
    trigger_source: str = "manual",
) -> Dict:
    async with agent_execution_lock:
        started_at = datetime.now()
        state = auto_agent_state[user_id]
        state['running'] = {
            'analysis_type': analysis_type,
            'trigger_source': trigger_source,
            'started_at': started_at.isoformat(),
        }

        if analysis_type == "morning":
            result = await agent.run_morning_analysis(user_id)
        elif analysis_type == "afternoon":
            result = await agent.run_afternoon_review(user_id)
        elif analysis_type == "quick" and symbol:
            result = await agent.run_quick_analysis(symbol.upper())
        else:
            state['running'] = None
            raise HTTPException(status_code=400, detail="Invalid analysis_type")

        completed_at = datetime.now()
        result = {
            **result,
            'analysis_type': analysis_type,
            'user_id': user_id,
            'trigger_source': trigger_source,
            'completed_at': completed_at.isoformat(),
        }
        if 'execution_log' not in result:
            result['execution_log'] = list(agent.execution_log)

        state['latest_execution_log'] = list(result.get('execution_log') or [])
        state['latest_result'] = result
        state['last_runs'][analysis_type] = {
            'status': result.get('status', 'unknown'),
            'started_at': started_at.isoformat(),
            'completed_at': completed_at.isoformat(),
            'trigger_source': trigger_source,
        }
        state['running'] = None
        agent.state['latest_agent_result'] = result

    await ws_manager.broadcast({
        'type': 'agent_result',
        'data': result,
        'timestamp': datetime.now().isoformat(),
    })
    return result


async def _queue_agent_analysis(
    user_id: int,
    analysis_type: str,
    trigger_source: str,
    delay_seconds: float = 0,
    force: bool = False,
) -> bool:
    if analysis_type not in {"morning", "afternoon"}:
        return False

    has_holdings = await asyncio.to_thread(_user_has_holdings_sync, user_id)
    if not has_holdings:
        return False

    key = (user_id, analysis_type)
    existing_task = auto_agent_tasks.get(key)
    if existing_task and not existing_task.done():
        return False
    if _should_skip_agent_run(user_id, analysis_type, force=force):
        return False

    async def _job():
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            still_has_holdings = await asyncio.to_thread(_user_has_holdings_sync, user_id)
            if not still_has_holdings:
                return
            await _execute_agent_analysis(user_id, analysis_type, trigger_source=trigger_source)
        except Exception as e:
            print(f"[Agent] Background {analysis_type} failed for user {user_id}: {e}")
            auto_agent_state[user_id]['running'] = None
        finally:
            auto_agent_tasks.pop(key, None)

    auto_agent_tasks[key] = asyncio.create_task(_job())
    return True


async def agent_automation_loop():
    """Run morning analysis and afternoon reflection automatically for active portfolios."""
    while True:
        try:
            now = datetime.now()
            if now.weekday() < 5:
                minutes = _minutes_since_midnight(now)
                user_ids = await asyncio.to_thread(_list_users_with_holdings_sync)
                for user_id in user_ids:
                    latest_dates = await asyncio.to_thread(_load_latest_agent_dates_sync, user_id)
                    today = now.date().isoformat()

                    if AUTO_MORNING_START_MINUTES <= minutes < AUTO_AFTERNOON_START_MINUTES:
                        if latest_dates.get('morning_date') != today:
                            await _queue_agent_analysis(
                                user_id,
                                'morning',
                                trigger_source='scheduled_morning',
                            )
                    elif minutes >= AUTO_AFTERNOON_START_MINUTES:
                        if latest_dates.get('morning_date') == today and latest_dates.get('reflection_date') != today:
                            await _queue_agent_analysis(
                                user_id,
                                'afternoon',
                                trigger_source='scheduled_reflection',
                            )
        except Exception as e:
            print(f"[Agent] Automation loop error: {e}")

        await asyncio.sleep(60)


# ─── API ROUTES ──────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """System health with diagnostics."""
    # Check DB connectivity
    db_ok = False
    try:
        db = SyncSessionLocal()
        db.execute(text("SELECT 1"))
        db_ok = True
        db.close()
    except Exception:
        pass

    return {
        "status": "healthy",
        "service": "Riskism API V3.1",
        "timestamp": datetime.now().isoformat(),
        "diagnostics": {
            "database": "connected" if db_ok else "unreachable",
            "vnstock": "available" if vnstock._stock_cache is not None else "unavailable",
            "llm_cache": {
                "size": agent.llm._cache.size,
                "hits": agent.llm._cache_hits,
                "misses": agent.llm._cache_misses,
                "hit_rate": f"{agent.llm._cache_hits / max(1, agent.llm._cache_hits + agent.llm._cache_misses) * 100:.1f}%",
            },
            "llm_runtime": agent.llm.runtime_status(),
            "market_data_cache": len(vnstock._memory_cache),
        },
    }


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str

class SignupRequest(BaseModel):
    username: str
    password: str

class FirebaseLoginRequest(BaseModel):
    id_token: str
    username_hint: Optional[str] = None

def _ensure_local_auth_columns(db):
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT"))
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(255)"))
    db.execute(
        text(
            "UPDATE users "
            "SET password_hash = :password_hash, updated_at = NOW() "
            "WHERE username = 'demo_user' AND password_hash IS NULL"
        ),
        {"password_hash": DEMO_USER_PASSWORD_HASH},
    )

def _ensure_firebase_user_columns(db):
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(255)"))
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)"))
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT"))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid) WHERE firebase_uid IS NOT NULL"))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL"))

def _normalize_local_username(value: str) -> str:
    return (value or "").strip().lower()

def _validate_local_username(value: str) -> str:
    username = _normalize_local_username(value)
    if not LOCAL_USERNAME_RE.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail="Use 3-32 lowercase letters, numbers, dots, underscores, or hyphens.",
        )
    return username

def _validate_local_password(password: str) -> str:
    if len(password or "") < PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Use at least {PASSWORD_MIN_LENGTH} characters for your password.",
        )
    return password

def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"

def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except Exception:
        return False


auth_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _create_access_token(user_id: int, username: str, auth_provider: str = "local") -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "auth_provider": auth_provider,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def _build_token_response(user_id: int, username: str, auth_provider: str = "local") -> Dict[str, str]:
    return {
        "access_token": _create_access_token(user_id, username, auth_provider),
        "token_type": "bearer",
    }


def _load_current_user_sync(user_id: int) -> Optional[Dict]:
    db = None
    try:
        db = SyncSessionLocal()
        _ensure_local_auth_columns(db)
        _ensure_firebase_user_columns(db)
        db.commit()
        row = db.execute(
            text(
                "SELECT id, username, capital_amount, firebase_uid, email "
                "FROM users WHERE id = :uid"
            ),
            {"uid": user_id},
        ).fetchone()
        if not row:
            return None
        auth_provider = "firebase" if row[3] else "local"
        return {
            "user_id": int(row[0]),
            "username": row[1],
            "capital_amount": float(row[2] or 0),
            "auth_provider": auth_provider,
            "display_name": row[1],
            "email": row[4],
        }
    except Exception as e:
        print(f"[AUTH] Failed to load current user {user_id}: {e}")
        return None
    finally:
        if db:
            db.close()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> Dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise _unauthorized("Invalid or expired token")

    user = await asyncio.to_thread(_load_current_user_sync, user_id)
    if not user:
        raise _unauthorized("User not found")
    return user

def _slugify_username(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:40] or "riskism_user"

def _pick_username_seed(decoded: dict, username_hint: Optional[str] = None) -> str:
    email = (decoded.get("email") or "").strip()
    name = (decoded.get("name") or "").strip()
    preferred = (username_hint or "").strip()

    candidates = [
        preferred,
        name,
        email.split("@")[0] if email else "",
        f"user_{str(decoded.get('uid', 'firebase'))[:8]}",
    ]
    for candidate in candidates:
        slug = _slugify_username(candidate)
        if slug:
            return slug
    return "riskism_user"

def _ensure_unique_username(db, base_username: str) -> str:
    username = base_username
    suffix = 1
    while db.execute(
        text("SELECT 1 FROM users WHERE username = :u"),
        {"u": username},
    ).fetchone():
        suffix += 1
        username = f"{base_username}_{suffix}"
    return username

@app.post("/api/auth/login")
@limit_decorator("10/minute")
async def login(request: Request, credentials: LoginRequest):
    """Authenticate a local account using username + password."""
    username = _validate_local_username(credentials.username)
    password = _validate_local_password(credentials.password)

    db = SyncSessionLocal()
    try:
        _ensure_local_auth_columns(db)
        db.commit()
        user_query = text(
            "SELECT id, username, capital_amount, password_hash, firebase_uid "
            "FROM users WHERE username = :u"
        )
        user = db.execute(user_query, {"u": username}).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="Account not found. Create an account to get started.")

        if user[4]:
            raise HTTPException(
                status_code=409,
                detail="This username is linked to Google sign-in. Use Google to continue.",
            )

        if not user[3]:
            raise HTTPException(
                status_code=409,
                detail="This account does not have a password yet. Create it again to finish setup.",
            )

        if not _verify_password(password, user[3]):
            raise HTTPException(status_code=401, detail="Incorrect password.")

        return _build_token_response(user[0], user[1], auth_provider="local")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[AUTH] Local login failed: {e}")
        raise HTTPException(status_code=500, detail="Unable to sign in right now.")
    finally:
        db.close()

@app.post("/api/auth/signup")
@limit_decorator("10/minute")
async def signup(request: Request, credentials: SignupRequest):
    """Create a local account using username + password."""
    username = _validate_local_username(credentials.username)
    password = _validate_local_password(credentials.password)

    db = SyncSessionLocal()
    try:
        _ensure_local_auth_columns(db)
        db.commit()

        user_query = text(
            "SELECT id, username, capital_amount, password_hash, firebase_uid "
            "FROM users WHERE username = :u"
        )
        existing_user = db.execute(user_query, {"u": username}).fetchone()

        if existing_user and existing_user[4]:
            raise HTTPException(
                status_code=409,
                detail="This username is reserved by a Google account. Choose another username.",
            )

        password_hash = _hash_password(password)

        if existing_user and existing_user[3]:
            raise HTTPException(status_code=409, detail="Username already exists. Sign in instead.")

        if existing_user:
            db.execute(
                text(
                    "UPDATE users SET password_hash = :password_hash, updated_at = NOW() "
                    "WHERE id = :user_id"
                ),
                {"password_hash": password_hash, "user_id": existing_user[0]},
            )
            db.commit()
            return _build_token_response(existing_user[0], existing_user[1], auth_provider="local")

        result = db.execute(
            text(
                "INSERT INTO users (username, password_hash, risk_appetite, capital_amount) "
                "VALUES (:username, :password_hash, 'moderate', 0) RETURNING id"
            ),
            {"username": username, "password_hash": password_hash},
        )
        user_id = result.fetchone()[0]
        db.commit()
        return _build_token_response(user_id, username, auth_provider="local")
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"[AUTH] Signup failed: {e}")
        raise HTTPException(status_code=500, detail="Unable to create your account right now.")
    finally:
        db.close()

@app.get("/api/auth/firebase/config")
async def firebase_config():
    """Return client-safe Firebase config when Firebase Auth is enabled."""
    return get_firebase_public_config()

@app.post("/api/auth/firebase/login")
async def firebase_login(request: FirebaseLoginRequest):
    """Authenticate via Firebase ID token and map to local user record."""
    decoded = verify_firebase_id_token(request.id_token)
    if not decoded:
        raise HTTPException(status_code=400, detail="Firebase authentication is not configured or token is invalid")

    firebase_uid = str(decoded.get("uid") or "").strip()
    if not firebase_uid:
        raise HTTPException(status_code=400, detail="Firebase token missing uid")

    email = (decoded.get("email") or "").strip().lower() or None
    display_name = (decoded.get("name") or request.username_hint or "").strip()
    picture = (decoded.get("picture") or "").strip() or None

    db = SyncSessionLocal()
    try:
        _ensure_local_auth_columns(db)
        _ensure_firebase_user_columns(db)
        db.commit()

        user = db.execute(
            text(
                "SELECT id, username, capital_amount FROM users "
                "WHERE firebase_uid = :uid OR (:email IS NOT NULL AND email = :email) "
                "ORDER BY id ASC LIMIT 1"
            ),
            {"uid": firebase_uid, "email": email},
        ).fetchone()

        if user:
            db.execute(
                text(
                    "UPDATE users SET firebase_uid = :uid, email = COALESCE(:email, email), "
                    "avatar_url = COALESCE(:avatar, avatar_url), updated_at = NOW() "
                    "WHERE id = :user_id"
                ),
                {
                    "uid": firebase_uid,
                    "email": email,
                    "avatar": picture,
                    "user_id": user[0],
                },
            )
            db.commit()
            return _build_token_response(user[0], user[1], auth_provider="firebase")

        username = _ensure_unique_username(db, _pick_username_seed(decoded, request.username_hint))
        result = db.execute(
            text(
                "INSERT INTO users (username, firebase_uid, email, avatar_url, risk_appetite, capital_amount) "
                "VALUES (:username, :uid, :email, :avatar, 'moderate', 0) RETURNING id"
            ),
            {
                "username": username,
                "uid": firebase_uid,
                "email": email,
                "avatar": picture,
            },
        )
        user_id = result.fetchone()[0]
        db.commit()
        return _build_token_response(user_id, username, auth_provider="firebase")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[FIREBASE AUTH] Login failed: {e}")
        raise HTTPException(status_code=500, detail="Firebase login failed")
    finally:
        db.close()


@app.get("/api/auth/me")
async def auth_me(current_user: Dict = Depends(get_current_user)):
    return current_user


# --- Market Data ---
def _build_vnindex_snapshot(index_data: Optional[dict]) -> Optional[dict]:
    """Build a latest-price style snapshot for VNINDEX from recent closes."""
    if not index_data:
        return None

    closes = index_data.get('close') or []
    opens = index_data.get('open') or []
    highs = index_data.get('high') or []
    lows = index_data.get('low') or []
    if not closes:
        return None

    latest_close = float(closes[-1])
    previous_close = float(closes[-2]) if len(closes) > 1 else latest_close
    change = latest_close - previous_close
    volume_series = index_data.get('volume') or []
    latest_volume = int(volume_series[-1]) if volume_series else 0

    return {
        'symbol': 'VNINDEX',
        'price': latest_close,
        'previous_close': previous_close,
        'open': float(opens[-1]) if opens else previous_close,
        'high': float(highs[-1]) if highs else latest_close,
        'low': float(lows[-1]) if lows else latest_close,
        'volume': latest_volume,
        'change': round(change, 2),
        'change_pct': round((change / previous_close) * 100, 2) if previous_close > 0 else 0,
        'timestamp': datetime.now().isoformat(),
    }


def _normalize_stock_price(raw_price: Optional[float]) -> Optional[float]:
    if raw_price is None:
        return None
    price = float(raw_price)
    return price * 1000 if price < 1000 else price


async def _get_stock_reference_snapshot(symbol: str) -> Optional[dict]:
    intraday = None
    try:
        intraday = await asyncio.wait_for(
            asyncio.to_thread(vnstock.get_intraday_price, symbol),
            timeout=3.5,
        )
    except asyncio.TimeoutError:
        print(f"[Market] Intraday timeout for {symbol}, falling back to historical close")
    except Exception as e:
        print(f"[Market] Intraday snapshot error for {symbol}: {e}")

    if intraday and intraday.get('price') is not None:
        price = _normalize_stock_price(intraday.get('price'))
        previous_close = _normalize_stock_price(intraday.get('previous_close'))
        open_price = _normalize_stock_price(intraday.get('open'))
        high_price = _normalize_stock_price(intraday.get('high'))
        low_price = _normalize_stock_price(intraday.get('low'))
        change = intraday.get('change')
        if change is not None:
            change = round(float(change) * (1000 if abs(float(change)) < 1000 else 1), 2)
        return {
            **intraday,
            'symbol': symbol,
            'price': price,
            'previous_close': previous_close,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'change': change,
        }

    historical = None
    try:
        historical = await asyncio.wait_for(
            vnstock.get_historical_data_async(symbol, days=2),
            timeout=5,
        )
    except asyncio.TimeoutError:
        print(f"[Market] Historical fallback timeout for {symbol}")
    except Exception as e:
        print(f"[Market] Historical fallback error for {symbol}: {e}")

    closes = historical.get('close', []) if historical else []
    if not closes:
        return None

    latest_close = _normalize_stock_price(closes[-1])
    previous_close = _normalize_stock_price(closes[-2]) if len(closes) > 1 else latest_close
    if latest_close is None or previous_close is None:
        return None

    volumes = historical.get('volume', []) if historical else []
    latest_volume = int(volumes[-1]) if volumes else 0
    change = latest_close - previous_close
    return {
        'symbol': symbol,
        'price': latest_close,
        'previous_close': previous_close,
        'open': previous_close,
        'high': latest_close,
        'low': latest_close,
        'volume': latest_volume,
        'change': round(change, 2),
        'change_pct': round((change / previous_close) * 100, 2) if previous_close > 0 else 0,
        'timestamp': datetime.now().isoformat(),
    }


@app.get("/api/market/symbols/search")
async def search_market_symbols(
    q: str = Query(default="", min_length=1),
    limit: int = Query(default=8, ge=1, le=20),
):
    items = await vnstock.search_symbols_async(q, limit)
    return {
        'items': items,
        'query': q,
        'total': len(items),
    }


@app.get("/api/market/{symbol}")
async def get_market_data(symbol: str, days: int = Query(default=180, le=365)):
    """Get historical market data for a symbol."""
    symbol = symbol.upper()
    if symbol == 'VNINDEX':
        data = await vnstock.get_market_index_async(days)
    else:
        data = await vnstock.get_historical_data_async(symbol, days)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
    return data


@app.get("/api/market/{symbol}/risk")
async def get_stock_risk(symbol: str):
    """Get risk metrics for a single stock."""
    result = await agent.run_quick_analysis(symbol.upper())
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.get("/api/market/{symbol}/price")
async def get_latest_price(symbol: str):
    """Get latest intraday price."""
    symbol = symbol.upper()
    if symbol == 'VNINDEX':
        try:
            data = await asyncio.wait_for(
                vnstock.get_market_index_snapshot_async(),
                timeout=3.5,
            )
        except asyncio.TimeoutError:
            print("[Market] VNINDEX snapshot timeout, falling back to historical close")
            data = None
        if not data:
            try:
                index_data = await asyncio.wait_for(
                    vnstock.get_market_index_async(days=2),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                index_data = None
            data = _build_vnindex_snapshot(index_data)
    else:
        data = await _get_stock_reference_snapshot(symbol)
    if not data:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    return data


# --- Portfolio ---
class HoldingInput(BaseModel):
    symbol: str
    quantity: int
    avg_price: Optional[float] = None

class PortfolioUpdateRequest(BaseModel):
    capital_amount: float
    holdings: List[HoldingInput]

@app.post("/api/portfolio/update")
async def update_portfolio(
    request: PortfolioUpdateRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Update user capital and portfolio holdings."""
    user_id = int(current_user["user_id"])
    db = SyncSessionLocal()
    try:
        # Check user exists
        check = db.execute(text("SELECT id FROM users WHERE id = :uid"), {"uid": user_id}).fetchone()
        if not check:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Update capital
        db.execute(
            text("UPDATE users SET capital_amount = :cap WHERE id = :uid"), 
            {"cap": request.capital_amount, "uid": user_id}
        )
        
        # Clear old holdings
        db.execute(text("DELETE FROM portfolios WHERE user_id = :uid"), {"uid": user_id})

        normalized_holdings = {}
        for h in request.holdings:
            symbol = h.symbol.upper().strip()
            if symbol and h.quantity > 0:
                existing = normalized_holdings.get(symbol, {"quantity": 0, "avg_price": None})
                fallback_price = existing["avg_price"]
                if h.avg_price is not None and float(h.avg_price) > 0:
                    fallback_price = float(h.avg_price)
                normalized_holdings[symbol] = {
                    "quantity": existing["quantity"] + h.quantity,
                    "avg_price": fallback_price,
                }

        # Insert new holdings
        if normalized_holdings:
            symbols = list(normalized_holdings.keys())
            unresolved_symbols = [
                symbol for symbol, meta in normalized_holdings.items()
                if not meta.get("avg_price")
            ]
            snapshots_by_symbol = {}
            if unresolved_symbols:
                snapshots = await asyncio.gather(
                    *[_get_stock_reference_snapshot(symbol) for symbol in unresolved_symbols]
                )
                snapshots_by_symbol = dict(zip(unresolved_symbols, snapshots))

            for symbol in symbols:
                snapshot = snapshots_by_symbol.get(symbol)
                fallback_price = normalized_holdings[symbol]["avg_price"]
                if snapshot and snapshot.get('price') is not None:
                    resolved_price = float(snapshot['price'])
                elif fallback_price is not None and fallback_price > 0:
                    resolved_price = float(fallback_price)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Không lấy được giá hiện tại cho mã {symbol}"
                    )
                sector = SECTOR_MAP.get(symbol, 'Unknown')
                db.execute(text(
                    "INSERT INTO portfolios (user_id, symbol, quantity, avg_price, sector) "
                    "VALUES (:uid, :sym, :qty, :prc, :sector)"
                ), {
                    "uid": user_id,
                    "sym": symbol,
                    "qty": normalized_holdings[symbol]["quantity"],
                    "prc": resolved_price,
                    "sector": sector,
                })
        
        db.commit()
        queued = await _queue_agent_analysis(
            user_id,
            'morning',
            trigger_source='portfolio_update',
            delay_seconds=1,
            force=True,
        )
        return {
            "status": "success",
            "automation": {
                "queued": queued,
                "analysis_type": "morning",
            },
        }
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        print(f"[PORTFOLIO ERROR] Failed to persist portfolio update for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not save portfolio right now. Please try again shortly.",
        )
    finally:
        db.close()

@app.get("/api/portfolio")
async def get_portfolio(current_user: Dict = Depends(get_current_user)):
    user_id = int(current_user["user_id"])
    return await agent.tool_get_portfolio(user_id)


@app.get("/api/portfolio/risk")
async def get_portfolio_risk(current_user: Dict = Depends(get_current_user)):
    """
    Get comprehensive portfolio risk analysis with REAL market prices.
    V3.1: Enriches holdings with latest prices from vnstock for real PnL.
    """
    import numpy as np
    from backend.risk_engine import (
        compute_portfolio_metrics, generate_capital_advice,
        calculate_returns, compute_portfolio_risk_summary,
        build_sector_benchmark_exposure,
    )

    user_id = int(current_user["user_id"])
    portfolio = await agent.tool_get_portfolio(user_id)
    symbols = [h['symbol'] for h in portfolio['holdings']]

    # Fetch all data concurrently (fast!)
    market_data = await vnstock.fetch_multiple_async(symbols)

    # Enrich holdings with REAL latest prices
    enriched_holdings = []
    for h in portfolio['holdings']:
        sym = h['symbol']
        data = market_data.get(sym, {})
        close_prices = data.get('close', [])
        latest_price = close_prices[-1] * 1000 if close_prices else h['avg_price']  # vnstock returns in 1000 VND
        prev_price = close_prices[-2] * 1000 if len(close_prices) >= 2 else latest_price
        market_value = h['quantity'] * latest_price
        cost_value = h['quantity'] * h['avg_price']
        pnl_value = market_value - cost_value
        pnl_pct = ((latest_price - h['avg_price']) / h['avg_price'] * 100) if h['avg_price'] > 0 else 0
        daily_change_pct = ((latest_price - prev_price) / prev_price * 100) if prev_price > 0 else 0

        enriched_holdings.append({
            **h,
            'latest_price': latest_price,
            'market_value': market_value,
            'cost_value': cost_value,
            'pnl_value': round(pnl_value),
            'pnl_pct': round(pnl_pct, 2),
            'daily_change_pct': round(daily_change_pct, 2),
        })

    # Update portfolio with enriched data
    total_market_value = sum(h['market_value'] for h in enriched_holdings)
    total_cost = sum(h['cost_value'] for h in enriched_holdings)
    portfolio['holdings'] = enriched_holdings
    portfolio['total_market_value'] = total_market_value
    portfolio['total_cost'] = total_cost
    portfolio['total_pnl'] = round(total_market_value - total_cost)
    portfolio['total_pnl_pct'] = round((total_market_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0

    # Build returns dict
    returns_dict = {}
    for symbol in symbols:
        data = market_data.get(symbol, {})
        prices = np.array(data.get('close', []))
        if len(prices) > 1:
            returns_dict[symbol] = calculate_returns(prices)

    market_returns = None
    vnindex = market_data.get('VNINDEX', {})
    if vnindex.get('close'):
        market_returns = calculate_returns(np.array(vnindex['close']))

    benchmark_returns = None
    vn30 = market_data.get('VN30', {})
    if vn30.get('close'):
        benchmark_returns = calculate_returns(np.array(vn30['close']))

    vn30_symbols = await vnstock.get_vn30_constituents_async()
    vn30_sector_exposure = build_sector_benchmark_exposure(vn30_symbols)

    portfolio_metrics = compute_portfolio_metrics(
        portfolio['holdings'],
        returns_dict,
        market_returns=market_returns,
        benchmark_returns=benchmark_returns,
        benchmark_sector_exposure=vn30_sector_exposure,
    )
    capital_advice = generate_capital_advice(
        portfolio['capital_amount'], portfolio['holdings'], returns_dict,
    )

    # Shared risk summary (DRY — same function used by orchestrator)
    risk_summary = compute_portfolio_risk_summary(
        portfolio['holdings'], returns_dict, market_data
    )

    # Anomaly detection (auto-scan from real data)
    from backend.risk_engine.anomaly_detector import scan_all_anomalies
    anomalies = []
    for sym in symbols:
        data = market_data.get(sym, {})
        prices = np.array(data.get('close', []))
        volumes = np.array(data.get('volume', []))
        rets = returns_dict.get(sym, np.array([]))
        if len(prices) > 5:
            detected = scan_all_anomalies(sym, prices, volumes, rets)
            anomalies.extend([a.to_dict() for a in detected])

    # Correlation matrix (from real returns)
    from backend.risk_engine.capital_aware import find_hidden_correlations
    correlation_matrix = {}
    for i, s1 in enumerate(symbols):
        row = {}
        for j, s2 in enumerate(symbols):
            if s1 in returns_dict and s2 in returns_dict:
                r1, r2 = returns_dict[s1], returns_dict[s2]
                min_len = min(len(r1), len(r2))
                if min_len > 5:
                    corr = float(np.corrcoef(r1[-min_len:], r2[-min_len:])[0, 1])
                    row[s2] = round(corr, 3)
                else:
                    row[s2] = 0
            else:
                row[s2] = 0
        correlation_matrix[s1] = row
    corr_warnings = find_hidden_correlations(symbols, returns_dict)

    return {
        'portfolio': portfolio,
        'portfolio_metrics': portfolio_metrics.to_dict(),
        'portfolio_risk': risk_summary['current_risk'],
        'capital_advice': capital_advice.to_dict(),
        'stock_risks': risk_summary['stock_metrics'],
        'metrics_history': risk_summary['metrics_history'],
        'anomalies': anomalies,
        'correlation_matrix': correlation_matrix,
        'correlation_warnings': [w['warning'] for w in corr_warnings],
    }


# --- Insights ---
@app.get("/api/insights")
async def get_latest_insights(current_user: Dict = Depends(get_current_user)):
    user_id = int(current_user["user_id"])
    state = auto_agent_state[user_id]
    latest_result = state.get('latest_result') or {}
    insight = latest_result.get('insight') or latest_result.get('afternoon_insight')
    if not insight:
        insight = await asyncio.to_thread(_load_latest_insight_sync, user_id)
    return {
        'insight': insight,
        'generated_at': insight.get('saved_at') if insight else None,
    }


# --- News ---
FALLBACK_NEWS = [
    {'title': 'VN-Index biến động nhẹ phiên đầu tuần, khối ngoại mua ròng', 'source': 'cafef_stock', 'summary': 'Thị trường chứng khoán giao dịch tích cực, thanh khoản cải thiện rõ rệt.', 'published_at': None, 'sentiment': {'score': 0.35, 'label': 'tích cực', 'reasoning': 'Thị trường có tín hiệu phục hồi'}, 'related_symbols': ['VNINDEX']},
    {'title': 'FPT báo lãi quý tăng 25% nhờ mảng AI và chuyển đổi số', 'source': 'cafef_enterprise', 'summary': 'Tập đoàn FPT ghi nhận kết quả kinh doanh ấn tượng trong Q1.', 'published_at': None, 'sentiment': {'score': 0.72, 'label': 'rất tích cực', 'reasoning': 'KQ vượt kỳ vọng'}, 'related_symbols': ['FPT']},
    {'title': 'Khối ngoại bán ròng phiên thứ 5 liên tiếp trên HOSE', 'source': 'cafef_market', 'summary': 'Nhà đầu tư nước ngoài tiếp tục rút vốn khỏi thị trường.', 'published_at': None, 'sentiment': {'score': -0.45, 'label': 'tiêu cực', 'reasoning': 'Áp lực bán ròng kéo dài'}, 'related_symbols': ['VNINDEX', 'VCB', 'HPG']},
    {'title': 'Ngân hàng Nhà nước giữ nguyên lãi suất điều hành', 'source': 'cafef_macro', 'summary': 'NHNN quyết định giữ nguyên các mức lãi suất chính sách.', 'published_at': None, 'sentiment': {'score': 0.1, 'label': 'trung tính', 'reasoning': 'Chính sách ổn định'}, 'related_symbols': ['VCB', 'BID', 'CTG']},
    {'title': 'Hòa Phát: Sản lượng thép tháng 2 giảm 8% do nhu cầu yếu', 'source': 'cafef_enterprise', 'summary': 'HPG công bố sản lượng tháng 2 sụt giảm đáng kể.', 'published_at': None, 'sentiment': {'score': -0.3, 'label': 'tiêu cực', 'reasoning': 'Sản lượng sụt giảm'}, 'related_symbols': ['HPG']},
]

@app.get("/api/news/latest")
async def get_latest_news(limit: int = Query(default=20, le=50)):
    """Get latest news with sentiment scores."""
    try:
        raw_news = await asyncio.wait_for(agent.tool_fetch_news(), timeout=8)
    except Exception as e:
        print(f"[NEWS] Live fetch fallback: {e}")
        raw_news = []

    total = len(raw_news)

    if raw_news:
        news = []
        for article in raw_news[:limit]:
            item = dict(article)
            item['sentiment'] = agent.llm._heuristic_sentiment(
                item.get('title', ''),
                item.get('summary', ''),
            )
            news.append(item)
    else:
        news = [dict(article) for article in FALLBACK_NEWS[:limit]]
        total = len(news)

    return {
        'articles': news,
        'total': total,
        'fetched_at': datetime.now().isoformat(),
    }


# --- Agent ---
@app.post("/api/agent/trigger")
@limit_decorator("5/minute")
async def trigger_agent(
    request: Request,
    payload: AgentTriggerRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Manually trigger agent analysis."""
    try:
        user_id = int(current_user["user_id"])
        result = await _execute_agent_analysis(
            user_id,
            payload.analysis_type,
            symbol=payload.symbol,
            trigger_source='manual',
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent analysis timed out")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Agent] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/status")
async def get_agent_status(current_user: Dict = Depends(get_current_user)):
    user_id = int(current_user["user_id"])
    state = auto_agent_state[user_id]
    return {
        'status': 'running' if state.get('running') else 'ready',
        'last_run': state.get('latest_result'),
        'total_runs': len(state.get('last_runs', {})),
        'state_keys': list(agent.state.keys()),
        'execution_log': state.get('latest_execution_log', []),
        'automation': {
            'running': state.get('running'),
            'last_runs': state.get('last_runs', {}),
        },
    }


# --- Predictions ---
@app.get("/api/predictions")
async def get_predictions(current_user: Dict = Depends(get_current_user)):
    user_id = int(current_user["user_id"])
    state = auto_agent_state[user_id]
    latest_result = state.get('latest_result') or {}
    morning_prediction = latest_result.get('prediction')
    reflection = latest_result.get('reflection')

    db_prediction, db_reflection = await asyncio.gather(
        asyncio.to_thread(_load_latest_morning_prediction_sync, user_id),
        asyncio.to_thread(_load_latest_reflection_sync, user_id),
    )

    if not morning_prediction:
        morning_prediction = db_prediction
    if not reflection:
        reflection = db_reflection

    return {
        'morning_prediction': morning_prediction,
        'reflection': reflection,
    }

@app.get("/api/predictions/history")
async def get_predictions_history(
    limit: int = 10,
    current_user: Dict = Depends(get_current_user),
):
    user_id = int(current_user["user_id"])
    db = None
    try:
        db = SyncSessionLocal()
        rows = db.execute(
            text(
                "SELECT content, evaluated_at FROM reflections "
                "WHERE user_id = :uid ORDER BY evaluated_at DESC LIMIT :limit"
            ),
            {"uid": user_id, "limit": limit}
        ).fetchall()
        
        history = []
        for row in rows:
            reflection = _parse_json_field(row[0]) or {}
            if row[1] and not reflection.get("evaluated_at"):
                reflection["evaluated_at"] = row[1].isoformat()
            history.append(reflection)
            
        return {"history": history}
    except Exception as e:
        print(f"[Agent] Failed to load history for user {user_id}: {e}")
        return {"history": []}
    finally:
        if db:
            db.close()


# --- Chatbot Assistance ---
@app.post("/api/chat")
async def chat_endpoint(
    request: ChatMessageRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Handle newbie chat requests from frontend."""
    try:
        if not request.message.strip():
            return {"reply": "Vui lòng nhập câu hỏi nhé!"}
        
        reply = await asyncio.to_thread(
            agent.llm.chat_assistant, 
            request.message, 
            request.history,
            request.app_context,
        )
        return {"reply": reply}
    except Exception as e:
        print(f"[chat_endpoint] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── WebSocket ───────────────────────────────────────────

@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data:
                try:
                    msg = json.loads(data)
                    if msg.get('type') == 'subscribe':
                        pass  # Could filter broadcasts per client
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
