"""
Riskism Data - vnstock Client Wrapper
Fetches Vietnamese stock market data using vnstock library.
V3.0: Graceful error handling, async support, smart caching.
"""
import json
import asyncio
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import numpy as np

try:
    from vnstock import Vnstock
    VNSTOCK_AVAILABLE = True
except ImportError:
    VNSTOCK_AVAILABLE = False

from backend.config import get_settings

settings = get_settings()


class VnstockClient:
    """Wrapper around vnstock with graceful fallbacks and async support."""

    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
                socket_timeout=1,
                socket_connect_timeout=1
            )
            self.redis_client.ping()
        except Exception:
            self.redis_client = None
        self._stock_cache = {}
        self._memory_cache = {}
        self._memory_cache_expiry = {}

    # ─── Cache Layer ─────────────────────────────────
    def _get_cache(self, key: str) -> Optional[str]:
        val = self._safe_redis_get(key)
        if val:
            return val
        if key in self._memory_cache:
            if datetime.now() < self._memory_cache_expiry.get(key, datetime.min):
                return self._memory_cache[key]
            else:
                self._memory_cache.pop(key, None)
                self._memory_cache_expiry.pop(key, None)
        return None

    def _set_cache(self, key: str, value: str, ttl: int):
        self._safe_redis_setex(key, ttl, value)
        self._memory_cache[key] = value
        self._memory_cache_expiry[key] = datetime.now() + timedelta(seconds=ttl)

    def _safe_redis_get(self, key: str) -> Optional[str]:
        if not self.redis_client:
            return None
        try:
            return self.redis_client.get(key)
        except Exception:
            self.redis_client = None
            return None

    def _safe_redis_setex(self, key: str, time: int, value: str):
        if not self.redis_client:
            return
        try:
            self.redis_client.setex(key, time, value)
        except Exception:
            self.redis_client = None

    def _get_stock(self, symbol: str):
        if not VNSTOCK_AVAILABLE:
            return None
        if symbol not in self._stock_cache:
            self._stock_cache[symbol] = Vnstock().stock(symbol=symbol, source='VCI')
        return self._stock_cache[symbol]

    # ─── Sync Methods ────────────────────────────────

    def get_historical_data(self, symbol: str, days: int = 180) -> Optional[Dict]:
        """Fetch historical OHLCV data. Returns None on error (never raises)."""
        cache_key = f"historical:{symbol}:{days}"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            print(f"[VnstockClient] vnstock not available, skipping {symbol}")
            return None

        try:
            stock = self._get_stock(symbol)
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            df = stock.quote.history(start=start_date, end=end_date, interval='1D')

            if df is None or df.empty:
                print(f"[VnstockClient] No data for {symbol}")
                return None

            result = {
                'symbol': symbol,
                'dates': df['time'].astype(str).tolist() if 'time' in df.columns else [],
                'open': df['open'].tolist() if 'open' in df.columns else [],
                'high': df['high'].tolist() if 'high' in df.columns else [],
                'low': df['low'].tolist() if 'low' in df.columns else [],
                'close': df['close'].tolist() if 'close' in df.columns else [],
                'volume': df['volume'].tolist() if 'volume' in df.columns else [],
            }
            self._set_cache(cache_key, json.dumps(result), 86400)
            return result

        except Exception as e:
            print(f"[VnstockClient] Error fetching {symbol}: {e}")
            return None  # Graceful: never raise

    def get_intraday_price(self, symbol: str) -> Optional[Dict]:
        """Get latest price. Cached 30s. Returns None on error."""
        cache_key = f"intraday:{symbol}"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            return None

        try:
            stock = self._get_stock(symbol)
            today = datetime.now().strftime('%Y-%m-%d')
            df = stock.quote.history(start=today, end=today, interval='1D')

            if df is None or df.empty:
                return None

            row = df.iloc[-1]
            open_price = float(row.get('open', 0))
            close_price = float(row.get('close', 0))
            result = {
                'symbol': symbol,
                'price': close_price,
                'open': open_price,
                'high': float(row.get('high', 0)),
                'low': float(row.get('low', 0)),
                'volume': int(row.get('volume', 0)),
                'change': round(close_price - open_price, 2),
                'change_pct': round((close_price - open_price) / open_price * 100, 2) if open_price > 0 else 0,
                'timestamp': datetime.now().isoformat(),
            }
            self._set_cache(cache_key, json.dumps(result), 30)
            return result

        except Exception as e:
            print(f"[VnstockClient] Intraday error {symbol}: {e}")
            return None

    def get_market_index(self, days: int = 180) -> Optional[Dict]:
        """Fetch VN-Index historical data. Returns None on error."""
        cache_key = f"vnindex:{days}"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            return None

        try:
            stock = Vnstock().stock(symbol='VNINDEX', source='VCI')
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            df = stock.quote.history(start=start_date, end=end_date, interval='1D')

            if df is None or df.empty:
                return None

            result = {
                'symbol': 'VNINDEX',
                'dates': df['time'].astype(str).tolist() if 'time' in df.columns else [],
                'close': df['close'].tolist() if 'close' in df.columns else [],
                'volume': df['volume'].tolist() if 'volume' in df.columns else [],
            }
            self._set_cache(cache_key, json.dumps(result), 86400)
            return result

        except Exception as e:
            print(f"[VnstockClient] VN-Index error: {e}")
            return None

    # ─── Async Wrappers ──────────────────────────────

    async def get_historical_data_async(self, symbol: str, days: int = 180) -> Optional[Dict]:
        """Async wrapper: runs sync fetch in thread pool."""
        return await asyncio.to_thread(self.get_historical_data, symbol, days)

    async def get_market_index_async(self, days: int = 180) -> Optional[Dict]:
        """Async wrapper for VN-Index."""
        return await asyncio.to_thread(self.get_market_index, days)

    async def fetch_multiple_async(self, symbols: List[str], days: int = 180) -> Dict:
        """Fetch data for multiple symbols + VNINDEX concurrently."""
        tasks = [self.get_historical_data_async(s, days) for s in symbols]
        tasks.append(self.get_market_index_async(days))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        market_data = {}
        for i, symbol in enumerate(symbols):
            res = results[i]
            if isinstance(res, dict) and res:
                market_data[symbol] = res

        vnindex = results[-1]
        if isinstance(vnindex, dict) and vnindex:
            market_data['VNINDEX'] = vnindex

        return market_data
