"""
Riskism - FastAPI Main Application V3.0
Core backend server with REST API + WebSocket.
V3.0: Simplified endpoints, shared risk logic, global error handling.
"""
import json
import asyncio
import time as _time
from collections import defaultdict
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from backend.database import SyncSessionLocal

from backend.config import get_settings
from backend.agent.orchestrator import AgentOrchestrator
from backend.data.vnstock_client import VnstockClient

settings = get_settings()

# Global instances
agent = AgentOrchestrator()
vnstock = VnstockClient()


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
    task = asyncio.create_task(price_broadcast_loop())
    yield
    task.cancel()
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
    user_id: int = 1
    analysis_type: str = "morning"
    symbol: Optional[str] = None


# ─── Rate Limiter ────────────────────────────────────────
class RateLimiter:
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

agent_rate_limiter = RateLimiter(max_calls=3, window_seconds=60)


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
            "market_data_cache": len(vnstock._memory_cache),
        },
    }


# --- Auth ---
class LoginRequest(BaseModel):
    username: str

@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Simple demo login/signup."""
    username = request.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username required")
        
    db = SyncSessionLocal()
    try:
        # Check if user exists
        user_query = text("SELECT id, username, capital_amount FROM users WHERE username = :u")
        user = db.execute(user_query, {"u": username}).fetchone()
        
        if not user:
            # Create new user
            insert_q = text(
                "INSERT INTO users (username, risk_appetite, capital_amount) "
                "VALUES (:u, 'moderate', 0) RETURNING id"
            )
            result = db.execute(insert_q, {"u": username})
            user_id = result.fetchone()[0]
            db.commit()
            return {"user_id": user_id, "username": username, "capital_amount": 0, "is_new": True}
        
        return {"user_id": user[0], "username": user[1], "capital_amount": user[2], "is_new": False}
    except Exception as e:
        db.rollback()
        print(f"[AUTH FALLBACK] DB error, using mock login: {e}")
        return {"user_id": 1, "username": username, "capital_amount": 20000000, "is_new": False}
    finally:
        db.close()


# --- Market Data ---
def _build_vnindex_snapshot(index_data: Optional[dict]) -> Optional[dict]:
    """Build a latest-price style snapshot for VNINDEX from recent closes."""
    if not index_data:
        return None

    closes = index_data.get('close') or []
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
        'open': previous_close,
        'high': latest_close,
        'low': latest_close,
        'volume': latest_volume,
        'change': round(change, 2),
        'change_pct': round((change / previous_close) * 100, 2) if previous_close > 0 else 0,
        'timestamp': datetime.now().isoformat(),
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
        data = await vnstock.get_market_index_snapshot_async()
        if not data:
            index_data = await vnstock.get_market_index_async(days=2)
            data = _build_vnindex_snapshot(index_data)
    else:
        data = await asyncio.to_thread(vnstock.get_intraday_price, symbol)
    if not data:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    return data


# --- Portfolio ---
class HoldingInput(BaseModel):
    symbol: str
    quantity: int
    avg_price: float

class PortfolioUpdateRequest(BaseModel):
    capital_amount: float
    holdings: List[HoldingInput]

@app.post("/api/portfolio/{user_id}/update")
async def update_portfolio(user_id: int, request: PortfolioUpdateRequest):
    """Update user capital and portfolio holdings."""
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
        
        # Insert new holdings
        if request.holdings:
            for h in request.holdings:
                if h.quantity > 0:
                    db.execute(text(
                        "INSERT INTO portfolios (user_id, symbol, quantity, avg_price, sector) "
                        "VALUES (:uid, :sym, :qty, :prc, 'Unknown')"
                    ), {
                        "uid": user_id, "sym": h.symbol.upper(),
                        "qty": h.quantity, "prc": h.avg_price
                    })
        
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        print(f"[PORTFOLIO FALLBACK] DB error, mock success: {e}")
        
        # MOCK PORTFOLIO IN AGENT STATE for demonstration
        agent.state['mock_portfolio'] = {
            'risk_appetite': 'moderate',
            'capital_amount': request.capital_amount,
            'holdings': [
                {'symbol': h.symbol.upper(), 'quantity': h.quantity, 'avg_price': h.avg_price, 'sector': 'Unknown'}
                for h in request.holdings if h.quantity > 0
            ]
        }
        
        return {"status": "success", "demo_mode": True}
    finally:
        db.close()

@app.get("/api/portfolio/{user_id}")
async def get_portfolio(user_id: int):
    return agent.tool_get_portfolio(user_id)


@app.get("/api/portfolio/{user_id}/risk")
async def get_portfolio_risk(user_id: int):
    """
    Get comprehensive portfolio risk analysis with REAL market prices.
    V3.1: Enriches holdings with latest prices from vnstock for real PnL.
    """
    import numpy as np
    from backend.risk_engine import (
        compute_portfolio_metrics, generate_capital_advice,
        calculate_returns, compute_portfolio_risk_summary,
    )

    portfolio = agent.tool_get_portfolio(user_id)
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

    portfolio_metrics = compute_portfolio_metrics(
        portfolio['holdings'], returns_dict, market_returns
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
@app.get("/api/insights/{user_id}")
async def get_latest_insights(user_id: int):
    insight = agent.state.get('latest_insight', None)
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
    news = agent.state.get('scored_news', [])
    if not news:
        raw_news = await agent.tool_fetch_news()
        if raw_news:
            news = await agent.tool_score_sentiment_batch(raw_news[:limit])
    # Fallback demo news if RSS is down
    if not news:
        news = FALLBACK_NEWS
    return {
        'articles': news[:limit],
        'total': len(news),
        'fetched_at': datetime.now().isoformat(),
    }


# --- Agent ---
@app.post("/api/agent/trigger")
async def trigger_agent(request: AgentTriggerRequest, req: Request):
    """Manually trigger agent analysis. Rate limited: 3 calls per 60s."""
    client_ip = req.client.host if req.client else "unknown"
    if not agent_rate_limiter.is_allowed(client_ip):
        retry = agent_rate_limiter.retry_after(client_ip)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry}s.",
            headers={"Retry-After": str(retry)}
        )
    try:
        if request.analysis_type == "morning":
            result = await agent.run_morning_analysis(request.user_id)
        elif request.analysis_type == "afternoon":
            result = await agent.run_afternoon_review(request.user_id)
        elif request.analysis_type == "quick" and request.symbol:
            result = await agent.run_quick_analysis(request.symbol.upper())
        else:
            raise HTTPException(status_code=400, detail="Invalid analysis_type")

        # Broadcast via WebSocket
        await ws_manager.broadcast({
            'type': 'agent_result',
            'data': result,
            'timestamp': datetime.now().isoformat(),
        })

        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent analysis timed out")
    except Exception as e:
        print(f"[Agent] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/status")
async def get_agent_status():
    return {
        'status': 'ready',
        'last_run': agent.execution_log[-1] if agent.execution_log else None,
        'total_runs': len(agent.execution_log),
        'state_keys': list(agent.state.keys()),
    }


# --- Predictions ---
@app.get("/api/predictions/{user_id}")
async def get_predictions(user_id: int):
    return {
        'morning_prediction': agent.state.get('morning_prediction'),
        'reflection': agent.state.get('reflection'),
    }


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
