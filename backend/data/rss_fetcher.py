"""
Riskism Data - RSS News Fetcher
Crawls financial news from Vietnamese RSS feeds and curated market pages.
"""
import feedparser
import hashlib
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass
import json
import re
import unicodedata
from urllib.parse import urljoin
import redis
from bs4 import BeautifulSoup
from backend.config import get_settings

settings = get_settings()

@dataclass
class NewsArticle:
    """Parsed news article."""
    title: str
    source: str
    url: str
    summary: str
    published_at: Optional[datetime]
    url_hash: str

    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'source': self.source,
            'url': self.url,
            'summary': self.summary,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'url_hash': self.url_hash,
        }


# RSS Feed URLs for Vietnamese financial news (Multi-source with fallback)
RSS_FEEDS = {
    # Primary: CafeF + Vietstock official RSS pages
    'cafef_stock': 'https://cafef.vn/thi-truong-chung-khoan.rss',
    'cafef_home': 'https://cafef.vn/home.rss',
    'vietstock_stock': 'https://vietstock.vn/830/chung-khoan/co-phieu.rss',
    'vietstock_analysis': 'https://vietstock.vn/1636/nhan-dinh-phan-tich/nhan-dinh-thi-truong.rss',
    'vietstock_macro': 'https://vietstock.vn/761/kinh-te/vi-mo.rss',
    'vietstock_enterprise': 'https://vietstock.vn/737/doanh-nghiep/hoat-dong-kinh-doanh.rss',
    # Backup: VNExpress
    'vnexpress_business': 'https://vnexpress.net/rss/kinh-doanh.rss',
}

VNEXPRESS_STOCK_URL = 'https://vnexpress.net/kinh-doanh/chung-khoan'

MARKET_SOURCES = {
    'cafef_stock',
    'vietstock_stock',
    'vietstock_analysis',
    'vietstock_macro',
    'vnexpress_stock',
}

MARKET_KEYWORDS = [
    'THI TRUONG CHUNG KHOAN',
    'CHUNG KHOAN',
    'VNINDEX',
    'VN-INDEX',
    'VN30',
    'HOSE',
    'HNX',
    'UPCOM',
    'KHOI NGOAI',
    'THANH KHOAN',
    'DONG TIEN',
    'AP LUC BAN',
    'CHOT LOI',
]

MACRO_FINANCE_KEYWORDS = [
    'LAI SUAT',
    'TY GIA',
    'LAM PHAT',
    'VI MO',
    'NGAN HANG NHA NUOC',
    'ROOM TIN DUNG',
    'TRAI PHIEU',
]

VIETNAM_MARKET_HINTS = [
    'VIET NAM',
    'VNINDEX',
    'VN-INDEX',
    'VN30',
    'HOSE',
    'HNX',
    'UPCOM',
    'NGAN HANG NHA NUOC',
    'KHOI NGOAI',
]

FOREIGN_MARKET_HINTS = [
    'MY',
    'HOA KY',
    'PHO WALL',
    'WALL STREET',
    'NASDAQ',
    'DOW JONES',
    'S&P 500',
    'TRUNG QUOC',
    'NHAT BAN',
    'HAN QUOC',
    'CHAU AU',
    'FEDERAL RESERVE',
]


class RSSFetcher:
    """Fetches and parses financial news from Vietnamese RSS feeds."""

    def __init__(self):
        self.seen_hashes = set()
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
        self._memory_cache = {}

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize('NFD', text or '')
        normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
        return normalized.upper()

    def _sort_symbols(self, symbols: List[str]) -> List[str]:
        return sorted(set(symbols), key=lambda symbol: (symbol != 'VNINDEX', symbol))

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats from RSS feeds."""
        formats = [
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S GMT',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%d %H:%M:%S',
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.tzinfo is not None:
                    return parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed
            except (ValueError, TypeError):
                continue
        return None

    def _hash_url(self, url: str) -> str:
        """Generate hash for deduplication."""
        return hashlib.md5(url.encode()).hexdigest()

    def _sanitize_summary(self, summary: str) -> str:
        summary = re.sub(r'<[^>]+>', '', summary or '').strip()
        return re.sub(r'\s+', ' ', summary)[:500].strip()

    def fetch_feed(self, feed_url: str, source_name: str) -> List[NewsArticle]:
        """Fetch and parse a single RSS feed."""
        articles = []
        try:
            headers = {'User-Agent': 'Mozilla/5.0 Riskism/1.0'}
            timeout = httpx.Timeout(4.0, connect=2.0, read=4.0, write=4.0, pool=2.0)
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                response = client.get(feed_url)
                response.raise_for_status()
                feed = feedparser.parse(response.text)
            
            for entry in feed.entries[:20]:  # Limit to 20 latest
                url = entry.get('link', '')
                url_hash = self._hash_url(url)

                title = entry.get('title', '').strip()
                summary = self._sanitize_summary(
                    entry.get('summary', entry.get('description', '')).strip()
                )
                
                published = self._parse_date(
                    entry.get('published', entry.get('updated', ''))
                )

                if title:
                    articles.append(NewsArticle(
                        title=title,
                        source=source_name,
                        url=url,
                        summary=summary[:500],  # Limit summary length
                        published_at=published,
                        url_hash=url_hash,
                    ))

        except Exception as e:
            print(f"[RSSFetcher] Error parsing {feed_url}: {e}")

        return articles

    def fetch_vnexpress_stock_page(self) -> List[NewsArticle]:
        """Fetch latest stock-market articles from VNExpress stock page."""
        articles = []
        try:
            headers = {'User-Agent': 'Mozilla/5.0 Riskism/1.0'}
            timeout = httpx.Timeout(4.0, connect=2.0, read=4.0, write=4.0, pool=2.0)
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                response = client.get(VNEXPRESS_STOCK_URL)
                response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            base_time = datetime.now()

            for idx, item in enumerate(soup.select('.item-news')[:24]):
                title_el = item.select_one('.title-news a')
                if not title_el:
                    continue

                title = title_el.get_text(' ', strip=True)
                url = urljoin(VNEXPRESS_STOCK_URL, title_el.get('href', '').strip())
                if not title or not url:
                    continue

                summary_el = item.select_one('.description a') or item.select_one('.description')
                summary = self._sanitize_summary(
                    summary_el.get_text(' ', strip=True) if summary_el else ''
                )
                articles.append(NewsArticle(
                    title=title,
                    source='vnexpress_stock',
                    url=url,
                    summary=summary,
                    published_at=base_time - timedelta(minutes=idx),
                    url_hash=self._hash_url(url),
                ))
        except Exception as e:
            print(f"[RSSFetcher] Error parsing {VNEXPRESS_STOCK_URL}: {e}")

        return articles

    def fetch_all_news(self) -> List[NewsArticle]:
        """Fetch news from all configured RSS feeds with Redis Caching."""
        cache_key = "rss:all_news:v3"
        
        # 1. Try Memory Cache
        if cache_key in self._memory_cache:
            cache_time, cached_data = self._memory_cache[cache_key]
            if (datetime.now() - cache_time).total_seconds() < 300: # 5 min TTL
                return cached_data
                
        # 2. Try Redis Cache
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    articles = []
                    for item in json.loads(cached):
                        # Re-parse isoformat string back to datetime
                        if item.get('published_at'):
                            try:
                                item['published_at'] = datetime.fromisoformat(item['published_at'])
                            except ValueError:
                                item['published_at'] = None
                        articles.append(NewsArticle(**item))
                    
                    self._memory_cache[cache_key] = (datetime.now(), articles)
                    return articles
            except Exception as e:
                print(f"[RSSFetcher] Redis cache read error: {e}")

        # 3. Fetch Fresh Data
        all_articles = []
        with ThreadPoolExecutor(max_workers=min(4, len(RSS_FEEDS))) as executor:
            future_map = {
                executor.submit(self.fetch_feed, feed_url, source_name): source_name
                for source_name, feed_url in RSS_FEEDS.items()
            }
            future_map[executor.submit(self.fetch_vnexpress_stock_page)] = 'vnexpress_stock'
            for future in as_completed(future_map):
                source_name = future_map[future]
                try:
                    articles = future.result()
                except Exception as e:
                    print(f"[RSSFetcher] Worker error for {source_name}: {e}")
                    articles = []
                all_articles.extend(articles)
                print(f"[RSSFetcher] {source_name}: {len(articles)} articles")

        # Sort by published date (newest first)
        all_articles.sort(
            key=lambda a: a.published_at or datetime.min,
            reverse=True
        )

        deduped_articles = []
        seen_hashes = set()
        for article in all_articles:
            if article.url_hash in seen_hashes:
                continue
            seen_hashes.add(article.url_hash)
            deduped_articles.append(article)
        all_articles = deduped_articles

        # 4. Save to Cache
        self._memory_cache[cache_key] = (datetime.now(), all_articles)
        if self.redis_client:
            try:
                serialized = [a.to_dict() for a in all_articles]
                self.redis_client.setex(cache_key, 300, json.dumps(serialized))
            except Exception as e:
                print(f"[RSSFetcher] Redis cache write error: {e}")

        return all_articles

    def detect_related_symbols(self, title: str, summary: str) -> List[str]:
        """
        Extract stock symbols mentioned in news.
        Simple keyword matching for Vietnamese stock tickers.
        """
        text = self._normalize_text(f"{title} {summary}")
        
        # Common Vietnamese stock symbols
        known_symbols = [
            'VCB', 'BID', 'CTG', 'TCB', 'ACB', 'MBB', 'VPB', 'HDB',
            'STB', 'TPB', 'SHB', 'LPB', 'VIB', 'EIB', 'OCB', 'SSB',
            'VIC', 'VHM', 'VRE', 'NVL', 'DXG', 'KDH', 'DIG', 'PDR', 'NLG',
            'MSN', 'MWG', 'VNM', 'SAB', 'PNJ', 'FRT', 'DGW',
            'HPG', 'HSG', 'NKG', 'GAS', 'PLX', 'POW', 'PPC', 'FPT',
            'CMG', 'VNR', 'BVH', 'VCG', 'CTD', 'HBC', 'GMD', 'PVT', 'GEX',
            'DGC', 'DCM', 'DPM', 'SSI', 'VND', 'HCM', 'VCI', 'VIX',
            'BCM', 'IDC', 'REE', 'HAG', 'HNG', 'CEO', 'BAB', 'BVB', 'VVS', 'KBC',
        ]
        
        # Also match company names
        name_map = {
            'VIETCOMBANK': 'VCB', 'BIDV': 'BID', 'VIETINBANK': 'CTG',
            'TECHCOMBANK': 'TCB', 'VINGROUP': 'VIC', 'VINHOMES': 'VHM',
            'VINCOM RETAIL': 'VRE', 'NOVALAND': 'NVL', 'VINAMILK': 'VNM',
            'MASAN': 'MSN', 'HOA PHAT': 'HPG', 'FPT': 'FPT',
            'PETROLIMEX': 'PLX', 'SABECO': 'SAB', 'VPBANK': 'VPB',
            'VIETJET': 'VJC', 'VIETJET AIR': 'VJC', 'DIGIWORLD': 'DGW',
            'KINH BAC': 'KBC', 'BVBANK': 'BVB', 'BAC A BANK': 'BAB',
            'THE GIOI DI DONG': 'MWG', 'MOBILE WORLD': 'MWG',
            'VN-INDEX': 'VNINDEX', 'VNINDEX': 'VNINDEX',
        }

        found = set()
        
        for symbol in known_symbols:
            if symbol == 'HCM' and any(marker in text for marker in ['TPHCM', 'TP.HCM', 'TP HCM', 'HO CHI MINH']):
                continue
            pattern = rf'(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])'
            if re.search(pattern, text):
                found.add(symbol)
        
        for name, symbol in name_map.items():
            if name in text:
                found.add(symbol)

        return self._sort_symbols(list(found))

    def classify_article(self, title: str, summary: str, source: str, related_symbols: List[str]) -> Dict:
        """
        Classify whether an article belongs to market news, company news, or both.
        """
        text = self._normalize_text(f"{title} {summary}")
        symbols = set(related_symbols or [])
        scopes = set()

        company_symbols = {symbol for symbol in symbols if symbol != 'VNINDEX'}
        market_signal = (
            source in MARKET_SOURCES
            or any(keyword in text for keyword in MARKET_KEYWORDS)
            or (
                any(keyword in text for keyword in MACRO_FINANCE_KEYWORDS)
                and any(hint in text for hint in VIETNAM_MARKET_HINTS)
            )
        )
        foreign_only_signal = (
            any(hint in text for hint in FOREIGN_MARKET_HINTS)
            and not company_symbols
            and not any(hint in text for hint in VIETNAM_MARKET_HINTS)
        )
        if foreign_only_signal:
            market_signal = False

        if market_signal:
            scopes.add('market')
            symbols.add('VNINDEX')

        if company_symbols:
            scopes.add('company')

        return {
            'related_symbols': self._sort_symbols(list(symbols)),
            'news_scope': sorted(scopes),
        }
