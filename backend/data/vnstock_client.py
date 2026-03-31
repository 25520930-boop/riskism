"""
Riskism Data - vnstock Client Wrapper
Fetches Vietnamese stock market data with vnstock3-first compatibility,
graceful demo fallbacks, and 5-minute caching.
"""
import asyncio
import json
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    from vnstock3 import Vnstock
    VNSTOCK_BACKEND = "vnstock3"
    VNSTOCK_AVAILABLE = True
except ImportError:
    try:
        from vnstock import Vnstock
        VNSTOCK_BACKEND = "vnstock"
        VNSTOCK_AVAILABLE = True
    except ImportError:
        Vnstock = None
        VNSTOCK_BACKEND = None
        VNSTOCK_AVAILABLE = False

from backend.config import get_settings

settings = get_settings()


class VnstockClient:
    """Wrapper around vnstock3/vnstock with graceful fallbacks and async support."""

    STOCK_SOURCES = ("VCI", "KBS")
    INDEX_SOURCES = ("VCI", "KBS")
    CACHE_TTL_SECONDS = 300
    CACHE_NAMESPACE = "v2"
    DEFAULT_SYMBOLS = [
        {"symbol": "VCB", "organ_name": "Ngân hàng TMCP Ngoại thương Việt Nam"},
        {"symbol": "FPT", "organ_name": "CTCP FPT"},
        {"symbol": "HPG", "organ_name": "CTCP Tập đoàn Hòa Phát"},
        {"symbol": "TCB", "organ_name": "Ngân hàng TMCP Kỹ thương Việt Nam"},
        {"symbol": "MBB", "organ_name": "Ngân hàng TMCP Quân đội"},
        {"symbol": "MWG", "organ_name": "CTCP Đầu tư Thế Giới Di Động"},
        {"symbol": "VIC", "organ_name": "Tập đoàn Vingroup"},
        {"symbol": "VNM", "organ_name": "CTCP Sữa Việt Nam"},
        {"symbol": "SSI", "organ_name": "CTCP Chứng khoán SSI"},
        {"symbol": "VNINDEX", "organ_name": "VN-Index"},
        {"symbol": "VN30", "organ_name": "VN30 Index"},
    ]
    DEMO_BASE_PRICES = {
        "VCB": 58.0,
        "FPT": 124.0,
        "HPG": 27.4,
        "TCB": 28.6,
        "MBB": 25.6,
        "MWG": 80.5,
        "VIC": 132.0,
        "VNM": 72.0,
        "SSI": 34.8,
        "VNINDEX": 1670.0,
        "VN30": 1735.0,
    }

    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
                socket_timeout=1,
                socket_connect_timeout=1,
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
            self._memory_cache.pop(key, None)
            self._memory_cache_expiry.pop(key, None)
        return None

    def _set_cache(self, key: str, value: str, ttl: Optional[int] = None):
        effective_ttl = int(ttl or self.CACHE_TTL_SECONDS)
        self._safe_redis_setex(key, effective_ttl, value)
        self._memory_cache[key] = value
        self._memory_cache_expiry[key] = datetime.now() + timedelta(seconds=effective_ttl)

    def _cache_key(self, category: str, *parts: object) -> str:
        suffix = ":".join(str(part) for part in parts)
        return f"{self.CACHE_NAMESPACE}:{category}:{suffix}"

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

    # ─── vnstock Object Helpers ─────────────────────
    def _create_vnstock(self):
        if not VNSTOCK_AVAILABLE or Vnstock is None:
            return None
        try:
            return Vnstock(show_log=False)
        except TypeError:
            return Vnstock()

    def _get_stock(self, symbol: str, source: str):
        if not VNSTOCK_AVAILABLE:
            return None
        normalized_symbol = str(symbol or "").strip().upper()
        cache_key = f"{VNSTOCK_BACKEND}:{source}:{normalized_symbol}"
        if cache_key not in self._stock_cache:
            client = self._create_vnstock()
            if client is None:
                return None
            self._stock_cache[cache_key] = client.stock(symbol=normalized_symbol, source=source)
        return self._stock_cache[cache_key]

    def _quote_history(self, stock_obj, symbol: str, start_date: str, end_date: str, interval: Optional[str] = None):
        kwargs = {
            "symbol": symbol,
            "start": start_date,
            "end": end_date,
        }
        if interval:
            kwargs["interval"] = interval
        try:
            return stock_obj.quote.history(**kwargs)
        except TypeError:
            kwargs.pop("symbol", None)
            return stock_obj.quote.history(**kwargs)

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
            "symbol": symbol,
            "dates": df["time"].astype(str).tolist() if "time" in df.columns else [],
            "open": df["open"].tolist() if "open" in df.columns else [],
            "high": df["high"].tolist() if "high" in df.columns else [],
            "low": df["low"].tolist() if "low" in df.columns else [],
            "close": df["close"].tolist() if "close" in df.columns else [],
            "volume": df["volume"].tolist() if "volume" in df.columns else [],
        }

    def _fetch_history_with_sources(
        self,
        symbol: str,
        days: int,
        sources: tuple[str, ...],
        normalize_index: bool = False,
        interval: Optional[str] = None,
    ):
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=max(int(days or 1), 1))).strftime("%Y-%m-%d")
        normalized_symbol = str(symbol or "").strip().upper()
        errors = []

        for source in sources:
            try:
                stock = self._get_stock(normalized_symbol, source)
                if stock is None:
                    continue
                df = self._quote_history(stock, normalized_symbol, start_date, end_date, interval=interval)
                if df is None or df.empty:
                    continue
                if normalize_index:
                    df = self._normalize_index_df(df, source)
                return df, source
            except Exception as e:
                errors.append(f"{source}: {e}")

        if errors:
            print(f"[VnstockClient] History fetch failed for {normalized_symbol}: {' | '.join(errors)}")
        return None, None

    # ─── Demo Fallbacks ────────────────────────────
    def _demo_seed(self, symbol: str) -> int:
        normalized_symbol = str(symbol or "").strip().upper() or "DEMO"
        return sum((idx + 1) * ord(ch) for idx, ch in enumerate(normalized_symbol))

    def _make_demo_ohlcv(self, symbol: str, days: int = 180) -> Dict:
        normalized_symbol = str(symbol or "").strip().upper() or "DEMO"
        total_days = max(int(days or 2), 2)
        base_price = float(self.DEMO_BASE_PRICES.get(normalized_symbol, 50.0))
        seed = self._demo_seed(normalized_symbol)
        dates, open_, high, low, close, volume = [], [], [], [], [], []
        price = base_price

        for idx in range(total_days):
            current_day = datetime.now() - timedelta(days=(total_days - idx - 1))
            drift = (((seed + idx * 11) % 13) - 6) * 0.0025
            open_price = price * (1 + (((seed + idx * 5) % 7) - 3) * 0.0012)
            close_price = max(0.1, price * (1 + drift))
            high_price = max(open_price, close_price) * (1 + 0.003 + ((seed + idx) % 4) * 0.0007)
            low_price = min(open_price, close_price) * (1 - 0.003 - ((seed + idx) % 3) * 0.0006)
            vol = 250000 + ((seed * 97 + idx * 131) % 4000000)

            dates.append(current_day.strftime("%Y-%m-%d"))
            open_.append(round(open_price, 2))
            high.append(round(high_price, 2))
            low.append(round(low_price, 2))
            close.append(round(close_price, 2))
            volume.append(int(vol))
            price = close_price

        return {
            "symbol": normalized_symbol,
            "dates": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }

    def _build_snapshot_from_history(self, symbol: str, history: Dict, live_price: Optional[float] = None) -> Optional[Dict]:
        if not history:
            return None

        closes = history.get("close") or []
        opens = history.get("open") or []
        highs = history.get("high") or []
        lows = history.get("low") or []
        volumes = history.get("volume") or []
        dates = history.get("dates") or []
        if not closes:
            return None

        latest_close = float(closes[-1])
        latest_open = float(opens[-1]) if opens else latest_close
        latest_high = float(highs[-1]) if highs else latest_close
        latest_low = float(lows[-1]) if lows else latest_close
        latest_volume = int(volumes[-1]) if volumes else 0
        latest_date = str(dates[-1])[:10] if dates else datetime.now().strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        latest_price = float(live_price) if live_price is not None else latest_close

        if len(closes) >= 2 and latest_date == today:
            previous_close = float(closes[-2])
        else:
            previous_close = latest_close

        change = latest_price - previous_close
        return {
            "symbol": symbol,
            "price": round(latest_price, 2),
            "previous_close": round(previous_close, 2),
            "open": round(latest_open, 2),
            "high": round(max(latest_high, latest_price), 2),
            "low": round(min(latest_low, latest_price), 2),
            "volume": latest_volume,
            "change": round(change, 2),
            "change_pct": round((change / previous_close) * 100, 2) if previous_close > 0 else 0,
            "timestamp": datetime.now().isoformat(),
        }

    def _make_demo_price_snapshot(self, symbol: str) -> Dict:
        history = self._make_demo_ohlcv(symbol, days=2)
        snapshot = self._build_snapshot_from_history(symbol, history)
        return snapshot or {
            "symbol": symbol,
            "price": 0,
            "previous_close": 0,
            "open": 0,
            "high": 0,
            "low": 0,
            "volume": 0,
            "change": 0,
            "change_pct": 0,
            "timestamp": datetime.now().isoformat(),
        }

    def _demo_symbols(self) -> List[Dict]:
        return [dict(item) for item in self.DEFAULT_SYMBOLS]

    # ─── Sync Methods ────────────────────────────────
    def get_historical_data(self, symbol: str, days: int = 180) -> Optional[Dict]:
        """Fetch historical OHLCV data, with 5-minute cache and demo fallback."""
        normalized_symbol = str(symbol or "").strip().upper()
        cache_key = self._cache_key("historical", normalized_symbol, days)
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        result = None
        if VNSTOCK_AVAILABLE:
            try:
                df, source = self._fetch_history_with_sources(normalized_symbol, days, self.STOCK_SOURCES)
                if df is not None and not df.empty:
                    result = self._build_ohlcv_result(normalized_symbol, df)
                    result["source"] = source
            except Exception as e:
                print(f"[VnstockClient] Error fetching {normalized_symbol}: {e}")

        if not result:
            result = self._make_demo_ohlcv(normalized_symbol, days)
            result["source"] = "demo"

        self._set_cache(cache_key, json.dumps(result), self.CACHE_TTL_SECONDS)
        return result

    def get_intraday_price(self, symbol: str) -> Optional[Dict]:
        """Get latest price snapshot from intraday history when possible, else daily history/demo."""
        normalized_symbol = str(symbol or "").strip().upper()
        cache_key = self._cache_key("intraday", normalized_symbol)
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        snapshot = None
        if VNSTOCK_AVAILABLE:
            try:
                intraday_df, _ = self._fetch_history_with_sources(
                    normalized_symbol,
                    days=2,
                    sources=self.STOCK_SOURCES,
                    interval="1m",
                )
                history = self.get_historical_data(normalized_symbol, days=5)
                live_price = None
                if intraday_df is not None and not intraday_df.empty and "close" in intraday_df.columns:
                    live_price = float(intraday_df.iloc[-1]["close"])
                snapshot = self._build_snapshot_from_history(normalized_symbol, history, live_price=live_price)
            except Exception as e:
                print(f"[VnstockClient] Intraday error {normalized_symbol}: {e}")

        if not snapshot:
            snapshot = self._make_demo_price_snapshot(normalized_symbol)
            snapshot["source"] = "demo"
        else:
            snapshot["source"] = VNSTOCK_BACKEND or "demo"

        self._set_cache(cache_key, json.dumps(snapshot), self.CACHE_TTL_SECONDS)
        return snapshot

    def get_market_index(self, days: int = 180) -> Optional[Dict]:
        """Fetch VN-Index historical data."""
        return self.get_index_data("VNINDEX", days)

    def get_index_data(self, symbol: str, days: int = 180) -> Optional[Dict]:
        """Fetch historical benchmark data such as VNINDEX or VN30."""
        normalized_symbol = str(symbol or "").strip().upper()
        cache_key = self._cache_key("index", normalized_symbol, days)
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        result = None
        if VNSTOCK_AVAILABLE:
            try:
                df, source = self._fetch_history_with_sources(
                    normalized_symbol,
                    days,
                    self.INDEX_SOURCES,
                    normalize_index=True,
                )
                if df is not None and not df.empty:
                    result = self._build_ohlcv_result(normalized_symbol, df)
                    result["source"] = source
            except Exception as e:
                print(f"[VnstockClient] {normalized_symbol} index error: {e}")

        if not result:
            result = self._make_demo_ohlcv(normalized_symbol, days)
            result["source"] = "demo"

        self._set_cache(cache_key, json.dumps(result), self.CACHE_TTL_SECONDS)
        return result

    def get_vn30_constituents(self) -> List[str]:
        """Fetch VN30 membership from listing metadata with demo fallback."""
        cache_key = self._cache_key("benchmark", "vn30", "constituents")
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        symbols = []
        if VNSTOCK_AVAILABLE:
            errors = []
            for source in self.STOCK_SOURCES:
                try:
                    listing = self._get_stock("VCB", source).listing
                    raw = listing.symbols_by_group("VN30")
                    if raw is None:
                        continue
                    if hasattr(raw, "tolist"):
                        raw_symbols = raw.tolist()
                    elif isinstance(raw, (list, tuple, set)):
                        raw_symbols = list(raw)
                    else:
                        raw_symbols = [raw]
                    symbols = sorted({
                        str(item).strip().upper()
                        for item in raw_symbols
                        if str(item).strip()
                    })
                    if symbols:
                        break
                except Exception as e:
                    errors.append(f"{source}: {e}")
            if errors and not symbols:
                print(f"[VnstockClient] VN30 membership error: {' | '.join(errors)}")

        if not symbols:
            symbols = ["ACB", "BCM", "BID", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB", "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE", "VPL"]

        self._set_cache(cache_key, json.dumps(symbols), self.CACHE_TTL_SECONDS)
        return symbols

    def get_market_index_snapshot(self) -> Optional[Dict]:
        """Get latest VN-Index snapshot with 5-minute cache."""
        cache_key = self._cache_key("vnindex", "snapshot", "live")
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        snapshot = None
        if VNSTOCK_AVAILABLE:
            try:
                intraday_df, _ = self._fetch_history_with_sources(
                    "VNINDEX",
                    days=2,
                    sources=self.INDEX_SOURCES,
                    normalize_index=True,
                    interval="1m",
                )
                history = self.get_index_data("VNINDEX", days=5)
                live_price = None
                if intraday_df is not None and not intraday_df.empty and "close" in intraday_df.columns:
                    live_price = float(intraday_df.iloc[-1]["close"])
                snapshot = self._build_snapshot_from_history("VNINDEX", history, live_price=live_price)
            except Exception as e:
                print(f"[VnstockClient] VN-Index snapshot error: {e}")

        if not snapshot:
            snapshot = self._make_demo_price_snapshot("VNINDEX")
            snapshot["source"] = "demo"
        else:
            snapshot["source"] = VNSTOCK_BACKEND or "demo"

        self._set_cache(cache_key, json.dumps(snapshot), self.CACHE_TTL_SECONDS)
        return snapshot

    def get_all_symbols(self) -> List[Dict]:
        """Fetch full symbol universe for autocomplete with 5-minute cache."""
        cache_key = self._cache_key("symbols", "all")
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        items = []
        if VNSTOCK_AVAILABLE:
            errors = []
            for source in self.STOCK_SOURCES:
                try:
                    listing = self._get_stock("VCB", source).listing
                    df = listing.all_symbols()
                    if df is None or df.empty:
                        continue

                    for _, row in df.iterrows():
                        symbol = str(row.get("symbol", "")).strip().upper()
                        organ_name = str(
                            row.get("organ_name")
                            or row.get("company_name")
                            or row.get("organ_short_name")
                            or ""
                        ).strip()
                        if symbol:
                            items.append({
                                "symbol": symbol,
                                "organ_name": organ_name,
                            })
                    if items:
                        break
                except Exception as e:
                    errors.append(f"{source}: {e}")
            if errors and not items:
                print(f"[VnstockClient] Symbol universe error: {' | '.join(errors)}")

        if not items:
            items = self._demo_symbols()

        unique_items = {}
        for item in items:
            symbol = item.get("symbol", "").strip().upper()
            if symbol and symbol not in unique_items:
                unique_items[symbol] = {
                    "symbol": symbol,
                    "organ_name": item.get("organ_name", "").strip(),
                }

        result = list(unique_items.values())
        self._set_cache(cache_key, json.dumps(result), self.CACHE_TTL_SECONDS)
        return result

    def search_symbols(self, query: str, limit: int = 8) -> List[Dict]:
        """Search symbols from vnstock listing metadata with graceful fallback."""
        normalized_query = (query or "").strip().upper()
        if not normalized_query:
            return []

        cache_key = self._cache_key("symbols", "search", normalized_query, limit)
        cached = self._get_cache(cache_key)
        if cached:
            return json.loads(cached)

        symbols = self.get_all_symbols()
        ranked = []
        for item in symbols:
            symbol = item.get("symbol", "")
            organ_name = item.get("organ_name", "")
            organ_upper = organ_name.upper()

            if symbol.startswith(normalized_query):
                rank = 0
            elif normalized_query in symbol:
                rank = 1
            elif normalized_query in organ_upper:
                rank = 2
            else:
                continue

            alpha_penalty = 0 if symbol.isalpha() else 1
            length_penalty = abs(len(symbol) - 3)
            ranked.append((rank, alpha_penalty, length_penalty, symbol, item))

        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        result = [item for _, _, _, _, item in ranked[:limit]]
        self._set_cache(cache_key, json.dumps(result), self.CACHE_TTL_SECONDS)
        return result

    # ─── Async Wrappers ──────────────────────────────
    async def get_historical_data_async(self, symbol: str, days: int = 180) -> Optional[Dict]:
        return await asyncio.to_thread(self.get_historical_data, symbol, days)

    async def get_market_index_async(self, days: int = 180) -> Optional[Dict]:
        return await asyncio.to_thread(self.get_market_index, days)

    async def get_index_data_async(self, symbol: str, days: int = 180) -> Optional[Dict]:
        return await asyncio.to_thread(self.get_index_data, symbol, days)

    async def get_market_index_snapshot_async(self) -> Optional[Dict]:
        return await asyncio.to_thread(self.get_market_index_snapshot)

    async def get_vn30_constituents_async(self) -> List[str]:
        return await asyncio.to_thread(self.get_vn30_constituents)

    async def search_symbols_async(self, query: str, limit: int = 8) -> List[Dict]:
        return await asyncio.to_thread(self.search_symbols, query, limit)

    async def fetch_multiple_async(self, symbols: List[str], days: int = 180) -> Dict:
        """Fetch data for multiple symbols plus benchmark indexes concurrently."""
        tasks = [self.get_historical_data_async(symbol, days) for symbol in symbols]
        tasks.append(self.get_market_index_async(days))
        tasks.append(self.get_index_data_async("VN30", days))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        market_data = {}
        for index, symbol in enumerate(symbols):
            payload = results[index]
            if isinstance(payload, dict) and payload:
                market_data[symbol] = payload

        vnindex_payload = results[-2]
        if isinstance(vnindex_payload, dict) and vnindex_payload:
            market_data["VNINDEX"] = vnindex_payload

        vn30_payload = results[-1]
        if isinstance(vn30_payload, dict) and vn30_payload:
            market_data["VN30"] = vn30_payload

        return market_data
