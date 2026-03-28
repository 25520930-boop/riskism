"""
Riskism Data - RSS News Fetcher
Crawls financial news from CafeF and Vietstock RSS feeds.
"""
import feedparser
import hashlib
import httpx
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
import json
import redis
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
    # Primary: CafeF
    'cafef_stock': 'https://cafef.vn/rss/chung-khoan.rss',
    'cafef_market': 'https://cafef.vn/rss/thi-truong.rss',
    'cafef_enterprise': 'https://cafef.vn/rss/doanh-nghiep.rss',
    'cafef_macro': 'https://cafef.vn/rss/kinh-te-vi-mo.rss',
    # Backup: VNExpress
    'vnexpress_business': 'https://vnexpress.net/rss/kinh-doanh.rss',
    'vnexpress_stock': 'https://vnexpress.net/rss/chung-khoan.rss',
    # Backup: Thanh Nien
    'thanhnien_finance': 'https://thanhnien.vn/rss/tai-chinh-kinh-doanh.rss',
}


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
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        return None

    def _hash_url(self, url: str) -> str:
        """Generate hash for deduplication."""
        return hashlib.md5(url.encode()).hexdigest()

    def fetch_feed(self, feed_url: str, source_name: str) -> List[NewsArticle]:
        """Fetch and parse a single RSS feed."""
        articles = []
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:20]:  # Limit to 20 latest
                url = entry.get('link', '')
                url_hash = self._hash_url(url)
                
                if url_hash in self.seen_hashes:
                    continue
                self.seen_hashes.add(url_hash)

                title = entry.get('title', '').strip()
                summary = entry.get('summary', entry.get('description', '')).strip()
                # Remove HTML tags from summary
                import re
                summary = re.sub(r'<[^>]+>', '', summary).strip()
                
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

    def fetch_all_news(self) -> List[NewsArticle]:
        """Fetch news from all configured RSS feeds with Redis Caching."""
        cache_key = "rss:all_news"
        
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
        for source_name, feed_url in RSS_FEEDS.items():
            articles = self.fetch_feed(feed_url, source_name)
            all_articles.extend(articles)
            print(f"[RSSFetcher] {source_name}: {len(articles)} articles")

        # Sort by published date (newest first)
        all_articles.sort(
            key=lambda a: a.published_at or datetime.min,
            reverse=True
        )

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
        text = f"{title} {summary}".upper()
        
        # Common Vietnamese stock symbols
        known_symbols = [
            'VCB', 'BID', 'CTG', 'TCB', 'ACB', 'MBB', 'VPB', 'HDB',
            'STB', 'TPB', 'SHB', 'LPB', 'VIC', 'VHM', 'VRE', 'NVL',
            'DXG', 'KDH', 'MSN', 'MWG', 'VNM', 'SAB', 'PNJ', 'FRT',
            'HPG', 'HSG', 'NKG', 'GAS', 'PLX', 'POW', 'PPC', 'FPT',
            'CMG', 'VNR', 'BVH', 'VCG', 'CTD', 'HBC', 'GMD', 'PVT',
            'DGC', 'DCM', 'SSI', 'VND', 'HCM', 'VCI',
        ]
        
        # Also match company names
        name_map = {
            'VIETCOMBANK': 'VCB', 'BIDV': 'BID', 'VIETINBANK': 'CTG',
            'TECHCOMBANK': 'TCB', 'VINGROUP': 'VIC', 'VINHOMES': 'VHM',
            'VINAMILK': 'VNM', 'MASAN': 'MSN', 'HOA PHAT': 'HPG',
            'FPT': 'FPT', 'PETROLIMEX': 'PLX', 'SABECO': 'SAB',
            'THE GIOI DI DONG': 'MWG', 'MOBILE WORLD': 'MWG',
            'VN-INDEX': 'VNINDEX', 'VNINDEX': 'VNINDEX',
        }

        found = set()
        
        for symbol in known_symbols:
            if f' {symbol} ' in f' {text} ' or f'({symbol})' in text:
                found.add(symbol)
        
        for name, symbol in name_map.items():
            if name in text:
                found.add(symbol)

        return list(found)
