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

    STOCK_SOURCES = ("KBS", "VCI")
    INDEX_SOURCES = ("KBS", "VCI")

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

    def _get_stock(self, symbol: str, source: str):
        if not VNSTOCK_AVAILABLE:
            return None
        cache_key = f"{source}:{symbol}"
        if cache_key not in self._stock_cache:
            self._stock_cache[cache_key] = Vnstock(show_log=False).stock(
                symbol=symbol,
                source=source,
            )
        return self._stock_cache[cache_key]

    def _normalize_index_df(self, df, source: str):
        if df is None or df.empty or source != "KBS":
            return df

        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                series = df[col].astype(float)
                if not series.empty and float(series.abs().max()) < 20:
                    df[col] = series * 1000
        return df

    def _build_ohlcv_result(self, symbol: str, df) -> Dict:
        return {
            'symbol': symbol,
            'dates': df['time'].astype(str).tolist() if 'time' in df.columns else [],
            'open': df['open'].tolist() if 'open' in df.columns else [],
            'high': df['high'].tolist() if 'high' in df.columns else [],
            'low': df['low'].tolist() if 'low' in df.columns else [],
            'close': df['close'].tolist() if 'close' in df.columns else [],
            'volume': df['volume'].tolist() if 'volume' in df.columns else [],
        }

    def _fetch_history_with_sources(
        self,
        symbol: str,
        days: int,
        sources: tuple[str, ...],
        normalize_index: bool = False,
    ):
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        errors = []

        for source in sources:
            try:
                stock = self._get_stock(symbol, source)
                df = stock.quote.history(start=start_date, end=end_date, interval='1D')
                if df is None or df.empty:
                    continue
                if normalize_index:
                    df = self._normalize_index_df(df, source)
                return df, source
            except Exception as e:
                errors.append(f"{source}: {e}")

        if errors:
            print(f"[VnstockClient] History fetch failed for {symbol}: {' | '.join(errors)}")
        return None, None

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
            df, source = self._fetch_history_with_sources(
                symbol,
                days,
                self.STOCK_SOURCES,
            )
            if df is None or df.empty:
                print(f"[VnstockClient] No data for {symbol} from {self.STOCK_SOURCES}")
                return None

            result = self._build_ohlcv_result(symbol, df)
            result['source'] = source
            self._set_cache(cache_key, json.dumps(result), 86400)
            return result

        except Exception as e:
            print(f"[VnstockClient] Error fetching {symbol}: {e}")
            return None  # Graceful: never raise

    def get_intraday_price(self, symbol: str) -> Optional[Dict]:
        """Get latest reference price from the most recent daily bar. Cached 30s."""
        cache_key = f"intraday:{symbol}"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            return None

        try:
            historical = self.get_historical_data(symbol, days=5)
            if not historical:
                return None

            closes = historical.get('close') or []
            opens = historical.get('open') or []
            highs = historical.get('high') or []
            lows = historical.get('low') or []
            volumes = historical.get('volume') or []
            if not closes:
                return None

            close_price = float(closes[-1])
            open_price = float(opens[-1]) if opens else close_price
            high_price = float(highs[-1]) if highs else close_price
            low_price = float(lows[-1]) if lows else close_price
            previous_close = float(closes[-2]) if len(closes) > 1 else close_price
            result = {
                'symbol': symbol,
                'price': close_price,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'previous_close': previous_close,
                'volume': int(volumes[-1]) if volumes else 0,
                'change': round(close_price - previous_close, 2),
                'change_pct': round((close_price - previous_close) / previous_close * 100, 2) if previous_close > 0 else 0,
                'timestamp': datetime.now().isoformat(),
            }
            self._set_cache(cache_key, json.dumps(result), 30)
            return result

        except Exception as e:
            print(f"[VnstockClient] Intraday error {symbol}: {e}")
            return None

    def get_market_index(self, days: int = 180) -> Optional[Dict]:
        """Fetch VN-Index historical data. Returns None on error."""
        return self.get_index_data('VNINDEX', days)

    def get_index_data(self, symbol: str, days: int = 180) -> Optional[Dict]:
        """Fetch historical data for benchmark indexes such as VNINDEX or VN30."""
        symbol = (symbol or '').upper().strip()
        if not symbol:
            return None

        cache_key = f"index:{symbol}:{days}"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            return None

        try:
            df, source = self._fetch_history_with_sources(
                symbol,
                days,
                self.INDEX_SOURCES,
                normalize_index=True,
            )
            if df is None or df.empty:
                return None

            result = {
                'symbol': symbol,
                'dates': df['time'].astype(str).tolist() if 'time' in df.columns else [],
                'close': df['close'].tolist() if 'close' in df.columns else [],
                'volume': df['volume'].tolist() if 'volume' in df.columns else [],
                'source': source,
            }
            self._set_cache(cache_key, json.dumps(result), 86400)
            return result

        except Exception as e:
            print(f"[VnstockClient] {symbol} index error: {e}")
            return None

    def get_vn30_constituents(self) -> List[str]:
        """Fetch VN30 membership from vnstock listing metadata."""
        cache_key = "benchmark:vn30:constituents"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            return []

        try:
            listing = None
            errors = []
            for source in self.STOCK_SOURCES:
                try:
                    listing = self._get_stock('VCB', source).listing
                    raw = listing.symbols_by_group('VN30')
                    if raw is None:
                        continue

                    if hasattr(raw, 'tolist'):
                        symbols = raw.tolist()
                    elif isinstance(raw, (list, tuple, set)):
                        symbols = list(raw)
                    else:
                        symbols = [raw]

                    normalized = []
                    for item in symbols:
                        value = str(item).strip().upper()
                        if value:
                            normalized.append(value)

                    unique_symbols = sorted(set(normalized))
                    if unique_symbols:
                        self._set_cache(cache_key, json.dumps(unique_symbols), 86400)
                        return unique_symbols
                except Exception as e:
                    errors.append(f"{source}: {e}")

            if errors:
                print(f"[VnstockClient] VN30 membership error: {' | '.join(errors)}")
            return []
        except Exception as e:
            print(f"[VnstockClient] VN30 membership error: {e}")
            return []

    def get_market_index_snapshot(self) -> Optional[Dict]:
        """Get latest VN-Index snapshot with short cache for ticker usage."""
        cache_key = "vnindex:snapshot:live-v2"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            return None

        try:
            today = datetime.now().strftime('%Y-%m-%d')
            lookback = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
            index_quote = self._get_stock('VNINDEX', 'VCI').quote

            intraday_df = index_quote.history(start=today, end=today, interval='1m')
            daily_df = index_quote.history(start=lookback, end=today, interval='1D')

            latest_price = None
            latest_volume = 0
            if intraday_df is not None and not intraday_df.empty and 'close' in intraday_df.columns:
                latest_price = float(intraday_df.iloc[-1]['close'])

            if daily_df is None or daily_df.empty or 'close' not in daily_df.columns:
                return None

            daily_closes = [float(v) for v in daily_df['close'].tolist()]
            daily_times = daily_df['time'].tolist() if 'time' in daily_df.columns else []
            latest_daily_date = str(daily_times[-1])[:10] if daily_times else today

            if latest_price is None:
                latest_price = daily_closes[-1]

            if len(daily_closes) >= 2:
                if latest_daily_date == today:
                    previous_close = daily_closes[-2]
                else:
                    previous_close = daily_closes[-1]
            else:
                previous_close = latest_price

            if 'volume' in daily_df.columns and not daily_df.empty:
                latest_volume = int(float(daily_df.iloc[-1]['volume']))

            change = latest_price - previous_close

            result = {
                'symbol': 'VNINDEX',
                'price': round(latest_price, 2),
                'previous_close': previous_close,
                'change': round(change, 2),
                'change_pct': round((change / previous_close) * 100, 2) if previous_close > 0 else 0,
                'volume': latest_volume,
                'timestamp': datetime.now().isoformat(),
            }
            self._set_cache(cache_key, json.dumps(result), 10)
            return result

        except Exception as e:
            print(f"[VnstockClient] VN-Index snapshot error: {e}")
            return None

    def get_all_symbols(self) -> List[Dict]:
        """Fetch full symbol universe for autocomplete."""
        cache_key = "symbols:all"
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        if not VNSTOCK_AVAILABLE:
            return []

        try:
            df = None
            errors = []
            for source in self.STOCK_SOURCES:
                try:
                    listing = self._get_stock('VCB', source).listing
                    df = listing.all_symbols()
                    if df is not None and not df.empty:
                        break
                except Exception as e:
                    errors.append(f"{source}: {e}")
                    df = None

            if df is None or df.empty:
                if errors:
                    print(f"[VnstockClient] Symbol universe error: {' | '.join(errors)}")
                return []

            result = []
            for _, row in df.iterrows():
                symbol = str(row.get('symbol', '')).strip().upper()
                organ_name = str(row.get('organ_name', '')).strip()
                if symbol:
                    result.append({
                        'symbol': symbol,
                        'organ_name': organ_name,
                    })

            self._set_cache(cache_key, json.dumps(result), 86400)
            return result
        except Exception as e:
            print(f"[VnstockClient] Symbol universe error: {e}")
            return []

    def search_symbols(self, query: str, limit: int = 8) -> List[Dict]:
        """Search symbols from cached vnstock listing data."""
        q = (query or '').strip().upper()
        if not q:
            return []

        symbols = self.get_all_symbols()
        ranked = []
        for item in symbols:
            symbol = item.get('symbol', '')
            organ_name = item.get('organ_name', '')
            organ_upper = organ_name.upper()

            if symbol.startswith(q):
                rank = 0
            elif q in symbol:
                rank = 1
            elif q in organ_upper:
                rank = 2
            else:
                continue

            alpha_penalty = 0 if symbol.isalpha() else 1
            length_penalty = abs(len(symbol) - 3)
            ranked.append((rank, alpha_penalty, length_penalty, symbol, item))

        ranked.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        return [item for _, _, _, _, item in ranked[:limit]]

    # ─── Async Wrappers ──────────────────────────────

    async def get_historical_data_async(self, symbol: str, days: int = 180) -> Optional[Dict]:
        """Async wrapper: runs sync fetch in thread pool."""
        return await asyncio.to_thread(self.get_historical_data, symbol, days)

    async def get_market_index_async(self, days: int = 180) -> Optional[Dict]:
        """Async wrapper for VN-Index."""
        return await asyncio.to_thread(self.get_market_index, days)

    async def get_index_data_async(self, symbol: str, days: int = 180) -> Optional[Dict]:
        """Async wrapper for benchmark index history."""
        return await asyncio.to_thread(self.get_index_data, symbol, days)

    async def get_market_index_snapshot_async(self) -> Optional[Dict]:
        """Async wrapper for latest VN-Index snapshot."""
        return await asyncio.to_thread(self.get_market_index_snapshot)

    async def get_vn30_constituents_async(self) -> List[str]:
        """Async wrapper for VN30 membership."""
        return await asyncio.to_thread(self.get_vn30_constituents)

    async def search_symbols_async(self, query: str, limit: int = 8) -> List[Dict]:
        """Async wrapper for symbol search."""
        return await asyncio.to_thread(self.search_symbols, query, limit)

    async def fetch_multiple_async(self, symbols: List[str], days: int = 180) -> Dict:
        """Fetch data for multiple symbols + benchmark indexes concurrently."""
        tasks = [self.get_historical_data_async(s, days) for s in symbols]
        tasks.append(self.get_market_index_async(days))
        tasks.append(self.get_index_data_async('VN30', days))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        market_data = {}
        for i, symbol in enumerate(symbols):
            res = results[i]
            if isinstance(res, dict) and res:
                market_data[symbol] = res

        vnindex = results[-2]
        if isinstance(vnindex, dict) and vnindex:
            market_data['VNINDEX'] = vnindex

        vn30 = results[-1]
        if isinstance(vn30, dict) and vn30:
            market_data['VN30'] = vn30

        return market_data
