"""
Riskism Agent - Orchestrator (Agentic Loop) V3.0
Goal-driven AI agent that autonomously decides which tools to call.
Flow: Perception → Analysis → Reasoning → Insight
V3.0: Fully async, no duplicate logic, timeout protection, log reset.
"""
import json
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np

from backend.utils.perf import PerfTimer

from backend.agent.llm_router import LLMRouter
from backend.data.vnstock_client import VnstockClient
from backend.data.rss_fetcher import RSSFetcher
from backend.risk_engine import (
    compute_all_metrics, compute_portfolio_metrics,
    generate_capital_advice, scan_all_anomalies,
    calculate_returns, SECTOR_MAP,
    compute_portfolio_risk_summary,
)


class AgentOrchestrator:
    """
    Agentic AI Orchestrator V3.0.
    Fully async, uses shared risk calculations, timeout-protected.
    """

    def __init__(self):
        self.llm = LLMRouter()
        self.vnstock = VnstockClient()
        self.rss = RSSFetcher()
        self.execution_log = []
        self.state = {}

    def log(self, step: str, message: str, data: Optional[Dict] = None):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'step': step,
            'message': message,
            'data_keys': list(data.keys()) if data else [],
        }
        self.execution_log.append(entry)
        print(f"[Agent] [{step}] {message}")

    async def _run_sync(self, func, *args, **kwargs):
        """Helper to run synchronous tool logic in a thread to keep event loop responsive."""
        return await asyncio.to_thread(func, *args, **kwargs)

    # ─── TOOLS (All async-safe) ──────────────────────────

    async def tool_fetch_market_data(self, symbols: List[str], days: int = 180) -> Dict:
        """Tool 1: Fetch all market data concurrently via VnstockClient."""
        self.log('PERCEPTION', f'Fetching market data for {len(symbols)} symbols concurrently')
        try:
            market_data = await self.vnstock.fetch_multiple_async(symbols, days)
            self.state['market_data'] = market_data
            self.log('PERCEPTION', f'Got data for {len(market_data)} symbols')
            return market_data
        except Exception as e:
            self.log('ERROR', f'Market data fetch failed: {e}')
            return {}

    async def tool_fetch_news(self) -> List[Dict]:
        """Tool 2: Fetch latest news (runs in thread to avoid blocking)."""
        self.log('PERCEPTION', 'Fetching live Vietnamese market news via RSS')
        try:
            articles = await self._run_sync(self.rss.fetch_all_news)
            news_list = []

            for raw_article in (articles or [])[:60]:
                article = raw_article.to_dict()
                symbols = self.rss.detect_related_symbols(
                    article.get('title', ''),
                    article.get('summary', '')
                )
                article.update(
                    self.rss.classify_article(
                        article.get('title', ''),
                        article.get('summary', ''),
                        article.get('source', ''),
                        symbols,
                    )
                )
                if article.get('news_scope'):
                    news_list.append(article)

            self.state['news'] = news_list
            self.log('PERCEPTION', f'Found {len(news_list)} relevant articles')
            return news_list
        except Exception as e:
            self.log('ERROR', f'News fetch failed: {e}')
            return []

    def _fallback_portfolio(self, user_id: int) -> Dict:
        """Fallback if DB is empty/fails."""
        if 'mock_portfolio' in self.state:
            portfolio = self.state['mock_portfolio']
            portfolio['user_id'] = user_id
            self.state['portfolio'] = portfolio
            return portfolio

        portfolio = {
            'user_id': user_id,
            'risk_appetite': 'moderate',
            'capital_amount': 20_000_000,
            'holdings': [
                {'symbol': 'VCB', 'quantity': 100, 'avg_price': 85000, 'sector': 'Banking'},
                {'symbol': 'FPT', 'quantity': 50, 'avg_price': 120000, 'sector': 'Technology'},
                {'symbol': 'HPG', 'quantity': 200, 'avg_price': 26000, 'sector': 'Industrial'},
            ]
        }
        self.state['portfolio'] = portfolio
        return portfolio

    def _get_portfolio_sync(self, user_id: int) -> Dict:
        """Synchronous part of tool_get_portfolio."""
        from backend.database import SyncSessionLocal
        from sqlalchemy import text
        db = None
        try:
            db = SyncSessionLocal()
            user_result = db.execute(
                text("SELECT risk_appetite, capital_amount FROM users WHERE id = :uid"),
                {"uid": user_id}
            ).fetchone()
            
            if not user_result:
                return self._fallback_portfolio(user_id)
                
            holdings_result = db.execute(
                text("SELECT symbol, quantity, avg_price, sector FROM portfolios WHERE user_id = :uid AND quantity > 0"),
                {"uid": user_id}
            ).fetchall()
            
            return {
                'user_id': user_id,
                'risk_appetite': user_result[0],
                'capital_amount': float(user_result[1]),
                'holdings': [
                    {'symbol': r[0], 'quantity': r[1], 'avg_price': float(r[2]), 'sector': r[3] or 'Unknown'}
                    for r in holdings_result
                ]
            }
        except Exception as e:
            print(f"[Agent] DB Error in _get_portfolio_sync: {e}")
            return self._fallback_portfolio(user_id)
        finally:
            if db: db.close()

    async def tool_get_portfolio(self, user_id: int = 1) -> Dict:
        """Tool 3: Get user's actual portfolio (async-wrapped)."""
        self.log('PERCEPTION', f'Getting portfolio for user {user_id} from DB')
        portfolio = await self._run_sync(self._get_portfolio_sync, user_id)
        self.state['portfolio'] = portfolio
        return portfolio

    async def tool_score_sentiment_batch(self, articles: List[Dict]) -> List[Dict]:
        """Tool 4: Score sentiment for articles concurrently."""
        self.log('ANALYSIS', f'Scoring sentiment for {len(articles)} articles')
        if not articles:
            self.state['scored_news'] = []
            return []

        semaphore = asyncio.Semaphore(6)

        async def score_one(article):
            async with semaphore:
                result = await self._run_sync(
                    self.llm.score_sentiment,
                    article.get('title', ''),
                    article.get('summary', '')
                )
                article['sentiment'] = result
            return article

        tasks = [score_one(dict(a)) for a in articles]
        scored = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [s for s in scored if isinstance(s, dict)]
        self.state['scored_news'] = valid
        return valid

    async def tool_classify_news_impact_batch(self, articles: List[Dict]) -> List[Dict]:
        """Tool 5: Classify impact of news concurrently."""
        self.log('ANALYSIS', f'Classifying impact for {len(articles)} articles')
        if not articles:
            self.state['classified_news'] = []
            return []

        semaphore = asyncio.Semaphore(6)

        async def classify_one(article):
            async with semaphore:
                result = await self._run_sync(
                    self.llm.classify_news_impact,
                    article.get('title', ''),
                    article.get('summary', ''),
                    article.get('related_symbols', []),
                )
                article['impact'] = result
            return article

        tasks = [classify_one(dict(a)) for a in articles]
        classified = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [c for c in classified if isinstance(c, dict)]
        self.state['classified_news'] = valid
        return valid

    async def tool_calculate_risk_metrics(self, symbols: List[str]) -> Dict:
        """Tool 6: Calculate risk metrics using Risk Engine."""
        self.log('ANALYSIS', 'Calculating risk metrics')
        market_data = self.state.get('market_data', {})
        vnindex_data = market_data.get('VNINDEX', {})
        market_prices = np.array(vnindex_data.get('close', [])) if vnindex_data else None

        async def calc_one(symbol):
            data = market_data.get(symbol, {})
            prices = np.array(data.get('close', []))
            if len(prices) > 10:
                metrics = await self._run_sync(compute_all_metrics, symbol, prices, market_prices)
                return symbol, metrics.to_dict()
            return symbol, None

        tasks = [calc_one(s) for s in symbols]
        results_list = await asyncio.gather(*tasks)
        results = {s: m for s, m in results_list if m}

        self.state['risk_metrics'] = results
        self.log('ANALYSIS', f'Computed metrics for {len(results)} symbols')
        return results

    async def tool_detect_anomaly(self, symbols: List[str]) -> List[Dict]:
        """Tool 7: Detect anomalies in market data."""
        self.log('ANALYSIS', 'Scanning for anomalies')
        market_data = self.state.get('market_data', {})
        
        async def scan_one(symbol):
            data = market_data.get(symbol, {})
            prices = np.array(data.get('close', []))
            volumes = np.array(data.get('volume', []))
            if len(prices) > 20:
                returns = calculate_returns(prices)
                anomalies = await self._run_sync(scan_all_anomalies, symbol, prices, volumes, returns)
                return [a.to_dict() for a in anomalies]
            return []

        tasks = [scan_one(s) for s in symbols]
        anomalies_lists = await asyncio.gather(*tasks)
        all_anomalies = [a for sublist in anomalies_lists for a in sublist]

        self.state['anomalies'] = all_anomalies
        self.log('ANALYSIS', f'Found {len(all_anomalies)} anomalies')
        return all_anomalies

    async def tool_save_insight(self, insight: Dict) -> Dict:
        """Tool 8: Save generated insight."""
        self.log('INSIGHT', f'Saving insight: {insight.get("title", "Untitled")}')
        insight['saved_at'] = datetime.now().isoformat()
        insight['agent_session'] = len(self.execution_log)
        self.state['latest_insight'] = insight
        return insight

    def _save_morning_prediction_sync(self, prediction: Dict, user_id: int) -> Optional[int]:
        from backend.database import SyncSessionLocal
        from sqlalchemy import text
        db = None
        try:
            db = SyncSessionLocal()
            result = db.execute(
                text("INSERT INTO morning_predictions (user_id, prediction_type, content) VALUES (:uid, 'morning', :content) RETURNING id"),
                {"uid": user_id, "content": json.dumps(prediction)}
            )
            pid = result.fetchone()[0]
            db.commit()
            return pid
        except Exception as e:
            print(f"[Agent] DB Error in _save_morning_prediction_sync: {e}")
            return None
        finally:
            if db: db.close()

    async def tool_save_morning_prediction(self, prediction: Dict, user_id: int = 1) -> Dict:
        """Tool 9: Save morning prediction to DB + state."""
        self.log('INSIGHT', 'Saving morning prediction to DB')
        prediction['predicted_at'] = datetime.now().isoformat()
        prediction['prediction_type'] = 'morning'
        self.state['morning_prediction'] = prediction

        pid = await self._run_sync(self._save_morning_prediction_sync, prediction, user_id)
        if pid:
            prediction['db_id'] = pid
            self.state['morning_prediction_db_id'] = pid
            self.log('INSIGHT', f'Morning prediction saved to DB with id={pid}')
        return prediction

    def _save_reflection_sync(self, user_id: int, mpid: Optional[int], reflection: Dict):
        from backend.database import SyncSessionLocal
        from sqlalchemy import text
        db = None
        try:
            db = SyncSessionLocal()
            db.execute(
                text("INSERT INTO reflections (user_id, morning_prediction_id, content) VALUES (:uid, :mpid, :content)"),
                {"uid": user_id, "mpid": mpid, "content": json.dumps(reflection)}
            )
            db.commit()
        except Exception as e:
            print(f"[Agent] DB Error in _save_reflection_sync: {e}")
        finally:
            if db: db.close()

    async def tool_evaluate_predictions(self, prediction: Dict, actual: Dict, user_id: int = 1) -> Dict:
        """Tool 10: Self-reflection — compare prediction vs actual, persist to DB."""
        if not prediction or not actual:
            self.log('FEEDBACK', 'Skipping reflection: Missing prediction or actual results')
            return {}

        self.log('FEEDBACK', 'Self-reflection: evaluating prediction accuracy')
        reflection = await self._run_sync(self.llm.self_reflect, prediction, actual)
        reflection['evaluated_at'] = datetime.now().isoformat()
        self.state['reflection'] = reflection

        mpid = self.state.get('morning_prediction_db_id')
        await self._run_sync(self._save_reflection_sync, user_id, mpid, reflection)
        self.log('FEEDBACK', 'Reflection saved to DB')
        return reflection

    def _load_morning_prediction_sync(self, user_id: int) -> Dict:
        from backend.database import SyncSessionLocal
        from sqlalchemy import text
        db = None
        try:
            db = SyncSessionLocal()
            result = db.execute(
                text("SELECT id, content FROM morning_predictions WHERE user_id = :uid ORDER BY predicted_at DESC LIMIT 1"),
                {"uid": user_id}
            ).fetchone()
            if result:
                content = result[1] if isinstance(result[1], dict) else json.loads(result[1])
                return {**content, 'db_id': result[0]}
        except Exception as e:
            print(f"[Agent] DB Error in _load_morning_prediction_sync: {e}")
        finally:
            if db: db.close()
        return {}

    async def _load_morning_prediction_from_db(self, user_id: int) -> Dict:
        """Load latest morning prediction from DB for a user (async-wrapped)."""
        content = await self._run_sync(self._load_morning_prediction_sync, user_id)
        if content:
            self.state['morning_prediction_db_id'] = content.get('db_id')
            self.log('FEEDBACK', f"Loaded morning prediction from DB id={content.get('db_id')}")
        return content

    # ─── AGENTIC LOOPS ─────────────────────────────────

    async def run_morning_analysis(self, user_id: int = 1) -> Dict:
        """Morning Analysis with timeout protection."""
        self.execution_log = []
        self.log('START', '☀️ Starting morning analysis V3.0')
        start_time = time.time()

        try:
            return await asyncio.wait_for(
                self._morning_analysis_impl(user_id, start_time),
                timeout=120
            )
        except Exception as e:
            elapsed = time.time() - start_time
            self.log('ERROR', f'Analysis failed/timed out after {elapsed:.1f}s: {e}')
            return {
                'status': 'error',
                'elapsed_seconds': round(elapsed, 1),
                'error': str(e),
                'execution_log': self.execution_log,
            }

    async def _morning_analysis_impl(self, user_id: int, start_time: float) -> Dict:
        """Internal implementation of morning analysis."""
        # === PERCEPTION PHASE ===
        portfolio = await self.tool_get_portfolio(user_id)
        symbols = [h['symbol'] for h in portfolio['holdings']]

        market_data, news = await asyncio.gather(
            self.tool_fetch_market_data(symbols),
            self.tool_fetch_news(),
        )

        # === ANALYSIS PHASE ===
        nlp_tasks = []
        if news:
            nlp_tasks = [
                self.tool_score_sentiment_batch(news[:5]),
                self.tool_classify_news_impact_batch(news[:5]),
            ]
        
        risk_tasks = [
            self.tool_calculate_risk_metrics(symbols),
            self.tool_detect_anomaly(symbols),
        ]

        # Run everything in analysis phase concurrently
        analysis_results = await asyncio.gather(*nlp_tasks, *risk_tasks)
        
        # Unpack results safely
        idx = 0
        if news:
            scored_news = analysis_results[idx]; idx += 1
            classified_news = analysis_results[idx]; idx += 1
        else:
            scored_news = []; classified_news = []
            
        risk_metrics = analysis_results[idx]; idx += 1
        anomalies = analysis_results[idx]; idx += 1

        # Calculate portfolio-level metrics
        returns_dict = {}
        for symbol in symbols:
            data = market_data.get(symbol, {})
            prices = np.array(data.get('close', []))
            if len(prices) > 1:
                returns_dict[symbol] = calculate_returns(prices)

        vnindex_returns = None
        if 'VNINDEX' in market_data:
            vnindex_prices = np.array(market_data['VNINDEX'].get('close', []))
            if len(vnindex_prices) > 1:
                vnindex_returns = calculate_returns(vnindex_prices)

        portfolio_metrics = await self._run_sync(compute_portfolio_metrics, portfolio['holdings'], returns_dict, vnindex_returns)
        capital_advice = await self._run_sync(generate_capital_advice, portfolio['capital_amount'], portfolio['holdings'], returns_dict)
        risk_summary = await self._run_sync(compute_portfolio_risk_summary, portfolio['holdings'], returns_dict, market_data)

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
                    else: row[s2] = 0
                else: row[s2] = 0
            correlation_matrix[s1] = row
        corr_warnings = await self._run_sync(find_hidden_correlations, symbols, returns_dict)

        # === REASONING PHASE (LLM) ===
        news_summary = "\n".join([
            f"- [{n.get('sentiment', {}).get('label', '?')}] {n.get('title', '')}"
            for n in classified_news[:5]
        ])

        insight_task = self._run_sync(self.llm.generate_insight, risk_metrics, news_summary, anomalies, {
            'risk_appetite': portfolio['risk_appetite'],
            'capital_amount': portfolio['capital_amount'],
        })
        prediction_task = self._run_sync(self.llm.generate_morning_prediction, {'latest_metrics': risk_metrics}, classified_news[:5])
        
        insight, prediction = await asyncio.gather(insight_task, prediction_task)

        # === INSIGHT PHASE ===
        saved_insight = await self.tool_save_insight(insight)
        saved_prediction = await self.tool_save_morning_prediction(prediction, user_id)

        elapsed = time.time() - start_time
        self.log('COMPLETE', f'✅ Morning analysis completed in {elapsed:.1f}s')

        return {
            'status': 'completed',
            'elapsed_seconds': round(elapsed, 1),
            'insight': saved_insight,
            'prediction': saved_prediction,
            'risk_metrics': risk_metrics,
            'portfolio_metrics': portfolio_metrics.to_dict(),
            'portfolio_risk': risk_summary['current_risk'],
            'metrics_history': risk_summary['metrics_history'],
            'capital_advice': capital_advice.to_dict(),
            'anomalies': anomalies,
            'correlation_matrix': correlation_matrix,
            'correlation_warnings': [w['warning'] for w in corr_warnings],
            'news_count': len(news),
            'execution_log': self.execution_log,
        }

    async def run_afternoon_review(self, user_id: int = 1) -> Dict:
        """Afternoon Review with self-reflection."""
        self.execution_log = []
        self.log('START', '🌆 Starting afternoon review')
        start_time = time.time()

        try:
            portfolio = await self.tool_get_portfolio(user_id)
            symbols = [h['symbol'] for h in portfolio['holdings']]
            market_data = await self.tool_fetch_market_data(symbols, days=5)

            actual_result = {}
            for symbol in symbols:
                data = market_data.get(symbol, {})
                close_prices = data.get('close', [])
                if len(close_prices) >= 2:
                    actual_result[symbol] = {
                        'close': close_prices[-1],
                        'prev_close': close_prices[-2],
                        'change_pct': round((close_prices[-1] - close_prices[-2]) / close_prices[-2] * 100, 2),
                    }

            morning_pred = self.state.get('morning_prediction')
            if not morning_pred:
                morning_pred = await self._load_morning_prediction_from_db(user_id)

            reflection = await self.tool_evaluate_predictions(morning_pred, actual_result, user_id)
            risk_metrics = await self.tool_calculate_risk_metrics(symbols)
            news = await self.tool_fetch_news()

            afternoon_insight = await self._run_sync(self.llm.generate_insight, risk_metrics, f"Phiên chiều - {len(news)} tin tức mới", self.state.get('anomalies', []), {
                'risk_appetite': portfolio.get('risk_appetite', 'moderate'),
                'capital_amount': portfolio.get('capital_amount', 0),
            })

            afternoon_insight['insight_type'] = 'afternoon_review'
            await self.tool_save_insight(afternoon_insight)

            elapsed = time.time() - start_time
            self.log('COMPLETE', f'✅ Afternoon review completed in {elapsed:.1f}s')

            return {
                'status': 'completed',
                'elapsed_seconds': round(elapsed, 1),
                'reflection': reflection,
                'afternoon_insight': afternoon_insight,
                'actual_results': actual_result,
                'execution_log': self.execution_log,
            }
        except Exception as e:
            elapsed = time.time() - start_time
            self.log('ERROR', f'Afternoon review failed: {e}')
            return {'status': 'error', 'error': str(e), 'elapsed_seconds': round(elapsed, 1)}

    async def run_quick_analysis(self, symbol: str) -> Dict:
        """Quick single-stock analysis."""
        self.log('START', f'⚡ Quick analysis for {symbol}')
        try:
            data = await self.vnstock.fetch_multiple_async([symbol])
            stock_data = data.get(symbol, {})
            vnindex_data = data.get('VNINDEX', {})

            prices = np.array(stock_data.get('close', []))
            market_prices = np.array(vnindex_data.get('close', []))
            volumes = np.array(stock_data.get('volume', []))

            if len(prices) < 10:
                return {'error': f'Không đủ dữ liệu cho {symbol}'}

            returns = calculate_returns(prices)
            metrics = await self._run_sync(compute_all_metrics, symbol, prices, market_prices)
            anomalies = await self._run_sync(scan_all_anomalies, symbol, prices, volumes, returns)

            return {
                'symbol': symbol,
                'risk_metrics': metrics.to_dict(),
                'anomalies': [a.to_dict() for a in anomalies],
                'latest_price': float(prices[-1]),
            }
        except Exception as e:
            self.log('ERROR', f'Quick analysis failed: {e}')
            return {'error': str(e)}
