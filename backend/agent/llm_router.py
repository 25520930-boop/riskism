"""
Riskism Agent - Gemini LLM Router
Routes AI tasks to Google Gemini with appropriate prompts.
"""
import json
import hashlib
import re
from typing import Dict, List, Optional
from backend.config import get_settings
from backend.utils.perf import TTLCache

settings = get_settings()

# Try to import Google GenAI
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class LLMRouter:
    """Routes AI tasks to Gemini models with specialized prompts."""

    def __init__(self):
        self.client = None
        if GENAI_AVAILABLE and settings.gemini_api_key:
            self.client = genai.Client(api_key=settings.gemini_api_key)
        
        # Multi-LLM Routing Map (Match Proposal)
        self.models = {
            "fast": "gemini-1.5-flash",           # More stable quota on free tier
            "reasoning": "gemini-1.5-flash", 
            "fallback": "gemini-1.5-flash"
        }

        # Response cache: avoid re-scoring identical articles (30min TTL)
        self._cache = TTLCache(maxsize=256, ttl_seconds=1800)
        self._cache_hits = 0
        self._cache_misses = 0

    def _call_gemini(self, prompt: str, system_instruction: str = "", temperature: float = 0.3, model_tier: str = "fast") -> str:
        """Call Gemini API with router logic."""
        if not self.client:
            return self._mock_response(prompt)
        
        # Router logic selecting model based on tier
        model_name = self.models.get(model_tier, self.models["fallback"])
        
        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=2048,
                ),
            )
            return response.text or ""
        except Exception as e:
            error_msg = str(e).lower()
            if (
                "api key" in error_msg
                or "401" in error_msg
                or "403" in error_msg
                or "expired" in error_msg
                or "429" in error_msg
                or "resource_exhausted" in error_msg
                or "quota exceeded" in error_msg
            ):
                print(f"[LLMRouter] CRITICAL: Gemini API Key is invalid or expired: {e}")
                # Store this state to avoid repeated failing calls
                self.client = None 
            else:
                print(f"[LLMRouter] Gemini ({model_name}) error: {e}")
            return self._mock_response(prompt, is_error=True, error_detail=str(e))

    def _extract_json(self, text: str) -> Optional[dict]:
        """Robustly extract JSON from LLM response text."""
        import re
        if not text:
            return None
        
        text = text.strip()
        
        # 1. Try direct parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        
        # 2. Remove markdown code blocks
        patterns = [
            r'```json\s*\n?(.*?)\n?```',  # ```json ... ```
            r'```\s*\n?(.*?)\n?```',       # ``` ... ```
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except (json.JSONDecodeError, ValueError):
                    continue
        
        # 3. Find first { ... } block
        depth = 0
        start = -1
        for i, c in enumerate(text):
            if c == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        return json.loads(text[start:i+1])
                    except (json.JSONDecodeError, ValueError):
                        start = -1
                        continue
        
        return None

    def _call_gemini_json(self, prompt: str, system: str, temperature: float = 0.3, fallback: dict = None, model_tier: str = "fast") -> dict:
        """Call Gemini and parse JSON response with retry."""
        result_text = self._call_gemini(prompt, system, temperature, model_tier)
        parsed = self._extract_json(result_text)
        if parsed:
            return parsed
        
        # Retry once with higher temperature on fallback model
        print(f"[LLMRouter] JSON parse failed, retrying with temp=0.5 on fallback tier")
        result_text = self._call_gemini(prompt, system, temperature=0.5, model_tier="fallback")
        parsed = self._extract_json(result_text)
        if parsed:
            return parsed
        
        print(f"[LLMRouter] JSON parse failed after retry. Raw: {result_text[:200]}")
        return fallback or {}

    def _payload_has_demo_marker(self, value) -> bool:
        if isinstance(value, dict):
            return any(self._payload_has_demo_marker(item) for item in value.values())
        if isinstance(value, list):
            return any(self._payload_has_demo_marker(item) for item in value)
        if not isinstance(value, str):
            return False

        normalized = value.lower()
        markers = (
            '[mock]',
            '[chế độ demo]',
            'resource_exhausted',
            'sự cố ai',
            'không thể phân tích',
            'không thể đánh giá tác động',
        )
        return any(marker in normalized for marker in markers)

    def _is_mock_payload(self, payload: Dict) -> bool:
        return self._payload_has_demo_marker(payload)

    def _merge_payload_defaults(self, payload: Dict, defaults: Dict) -> Dict:
        normalized = dict(defaults)
        if isinstance(payload, dict):
            for key, value in payload.items():
                if value is not None:
                    normalized[key] = value
        return normalized

    def _normalize_insight_payload(self, payload: Dict, fallback: Dict) -> Dict:
        normalized = self._merge_payload_defaults(payload, fallback)

        risk_level = str(normalized.get('risk_level') or fallback.get('risk_level') or 'medium').lower()
        if risk_level not in {'low', 'medium', 'high', 'critical'}:
            risk_level = fallback.get('risk_level', 'medium')
        normalized['risk_level'] = risk_level

        for list_key in ('key_findings', 'risk_factors', 'action_items', 'trends'):
            if not isinstance(normalized.get(list_key), list):
                normalized[list_key] = list(fallback.get(list_key, []))

        try:
            normalized['confidence_score'] = float(normalized.get('confidence_score', fallback.get('confidence_score', 0.5)))
        except (TypeError, ValueError):
            normalized['confidence_score'] = float(fallback.get('confidence_score', 0.5))

        normalized['title'] = str(normalized.get('title') or fallback.get('title') or 'Báo cáo rủi ro hàng ngày')
        normalized['summary'] = str(normalized.get('summary') or fallback.get('summary') or '')
        return normalized

    def _normalize_reflection_payload(self, payload: Dict, fallback: Dict) -> Dict:
        normalized = self._merge_payload_defaults(payload, fallback)
        try:
            normalized['accuracy_score'] = float(normalized.get('accuracy_score', fallback.get('accuracy_score', 0.5)))
        except (TypeError, ValueError):
            normalized['accuracy_score'] = float(fallback.get('accuracy_score', 0.5))

        for field in ('what_was_right', 'what_was_wrong', 'lesson_learned', 'improvement_suggestion'):
            normalized[field] = str(normalized.get(field) or fallback.get(field) or '')

        return normalized

    def _is_benchmark_symbol(self, symbol: str) -> bool:
        normalized = str(symbol or '').strip().upper()
        return normalized in {
            'VNINDEX', 'VN-INDEX', 'VN30', 'VN30INDEX',
            'HNXINDEX', 'HNX30', 'UPCOM', 'UPCOMINDEX',
        }

    def _extract_stock_metric_map(self, risk_metrics: Dict) -> Dict[str, Dict]:
        if not isinstance(risk_metrics, dict):
            return {}

        candidates = []
        for key in ('stock_metrics', 'risk_metrics', 'latest_metrics'):
            value = risk_metrics.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        candidates.append(risk_metrics)

        for candidate in candidates:
            extracted = {}
            for symbol, metrics in candidate.items():
                normalized_symbol = str(symbol or '').strip().upper()
                if self._is_benchmark_symbol(normalized_symbol):
                    continue
                if not isinstance(metrics, dict):
                    continue
                if not any(
                    field in metrics
                    for field in ('risk_score', 'beta', 'var_95', 'sharpe_ratio', 'volatility', 'max_drawdown')
                ):
                    continue
                extracted[normalized_symbol] = metrics
            if extracted:
                return extracted

        return {}

    def _build_insight_fallback(self, risk_metrics: Dict) -> Dict:
        stock_metric_map = self._extract_stock_metric_map(risk_metrics)
        if not stock_metric_map:
            return {
                'title': 'Báo cáo rủi ro hàng ngày',
                'risk_level': 'medium',
                'summary': 'Hệ thống đang thu thập và phân tích dữ liệu danh mục.',
                'key_findings': ['Đang cập nhật dữ liệu danh mục mới nhất...'],
                'risk_factors': [],
                'action_items': ['Theo dõi thêm'],
                'confidence_score': 0.5,
                'trends': [],
            }

        ranked = sorted(
            stock_metric_map.items(),
            key=lambda item: float(item[1].get('risk_score') or 50),
            reverse=True,
        )
        top_symbols = [symbol for symbol, _ in ranked[:3]]
        avg_risk = sum(float(metrics.get('risk_score') or 50) for _, metrics in ranked) / len(ranked)
        risk_level = 'high' if avg_risk >= 70 else 'medium' if avg_risk >= 45 else 'low'

        def trend_row(symbol: str, metrics: Dict) -> Dict:
            score = int(round(float(metrics.get('risk_score') or 50)))
            trend = 'down' if score >= 65 else 'neutral' if score >= 40 else 'up'
            return {'ticker': symbol, 'trend': trend, 'conf': score}

        key_findings = []
        top_symbol, top_metrics = ranked[0]
        key_findings.append(
            f"{top_symbol} đang có risk score khoảng {int(round(float(top_metrics.get('risk_score') or 50)))}/100 và là điểm cần theo dõi sát nhất."
        )
        if len(ranked) > 1:
            second_symbol, second_metrics = ranked[1]
            key_findings.append(
                f"{second_symbol} là lớp rủi ro tiếp theo với beta khoảng {float(second_metrics.get('beta') or 0):.2f}."
            )
        if len(ranked) > 2:
            safer_symbol, safer_metrics = ranked[-1]
            key_findings.append(
                f"{safer_symbol} đang là mã phòng thủ hơn trong danh mục với score khoảng {int(round(float(safer_metrics.get('risk_score') or 50)))}/100."
            )

        return {
            'title': 'Báo cáo rủi ro hàng ngày',
            'risk_level': risk_level,
            'summary': (
                f"Rủi ro danh mục hiện tập trung chủ yếu ở {', '.join(top_symbols[:2])}. "
                "Hệ thống đang dùng dữ liệu định lượng mới nhất để giữ AI insight bám đúng danh mục."
            ),
            'key_findings': key_findings[:3],
            'risk_factors': [f'Tập trung rủi ro ở {top_symbols[0]}'],
            'action_items': [f'Theo dõi thêm {top_symbols[0]} và cân đối tỷ trọng nếu biến động tăng mạnh'],
            'confidence_score': 0.62,
            'trends': [trend_row(symbol, metrics) for symbol, metrics in ranked[:3]],
        }

    def _heuristic_sentiment(self, title: str, summary: str) -> Dict:
        text = f"{title} {summary}".lower()
        score = 0.0
        matched = []

        positive_keywords = {
            'tăng trưởng': 0.35,
            'lãi': 0.25,
            'lợi nhuận': 0.25,
            'mua ròng': 0.35,
            'bứt phá': 0.30,
            'hồi phục': 0.25,
            'mở rộng': 0.20,
            'kỷ lục': 0.30,
            'tích cực': 0.20,
            'nâng hạng': 0.40,
            'giải ngân': 0.20,
            'ký hợp đồng': 0.20,
        }
        negative_keywords = {
            'lao dốc': -0.50,
            'giảm mạnh': -0.35,
            'sụt giảm': -0.30,
            'bán ròng': -0.35,
            'thua lỗ': -0.45,
            'lỗ': -0.40,
            'áp lực': -0.20,
            'rủi ro': -0.20,
            'điều tra': -0.50,
            'khởi tố': -0.70,
            'trái phiếu': -0.15,
            'thanh tra': -0.35,
            'siết': -0.20,
            'suy yếu': -0.25,
            'thoái vốn': -0.10,
        }

        for keyword, weight in positive_keywords.items():
            if keyword in text:
                score += weight
                matched.append(keyword)
        for keyword, weight in negative_keywords.items():
            if keyword in text:
                score += weight
                matched.append(keyword)

        score = max(-0.95, min(0.95, score))
        if score >= 0.55:
            label = 'rất tích cực'
        elif score >= 0.15:
            label = 'tích cực'
        elif score > -0.15:
            label = 'trung tính'
        elif score > -0.55:
            label = 'tiêu cực'
        else:
            label = 'rất tiêu cực'

        if matched:
            reasoning = f"Tín hiệu chính: {', '.join(matched[:3])}."
        else:
            reasoning = 'Đánh giá theo ngữ cảnh tiêu đề và tóm tắt bài viết.'

        return {
            'score': round(score, 2),
            'label': label,
            'reasoning': reasoning,
        }

    def _heuristic_news_impact(self, title: str, summary: str, related_symbols: List[str]) -> Dict:
        text = f"{title} {summary}".lower()
        impacted_symbols = related_symbols or []

        critical_keywords = ['khởi tố', 'hủy niêm yết', 'vỡ nợ', 'giải chấp', 'điều tra']
        high_keywords = ['lao dốc', 'thua lỗ', 'lỗ', 'giảm mạnh', 'bán ròng', 'áp lực']
        medium_keywords = ['lợi nhuận', 'tăng trưởng', 'mua ròng', 'mở rộng', 'huy động', 'thanh khoản']

        if any(keyword in text for keyword in critical_keywords):
            impact_level = 'critical'
            explanation = 'Tin có từ khóa sự kiện nghiêm trọng, có thể ảnh hưởng mạnh tới định giá.'
        elif any(keyword in text for keyword in high_keywords):
            impact_level = 'high'
            explanation = 'Tin có tín hiệu biến động lớn hoặc rủi ro đáng kể cho cổ phiếu liên quan.'
        elif any(keyword in text for keyword in medium_keywords) or impacted_symbols:
            impact_level = 'medium'
            explanation = 'Tin có khả năng ảnh hưởng đáng chú ý đến tâm lý thị trường hoặc doanh nghiệp liên quan.'
        else:
            impact_level = 'low'
            explanation = 'Tin mang tính tham khảo, tác động ngắn hạn dự kiến thấp.'

        return {
            'impact_level': impact_level,
            'affected_symbols': impacted_symbols,
            'explanation': explanation,
        }

    def score_sentiment(self, title: str, summary: str) -> Dict:
        """
        Score sentiment of a news article.
        Cached by title hash to avoid re-scoring identical articles.
        """
        cache_key = f"sent:{hashlib.md5(title.encode()).hexdigest()[:12]}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached
        self._cache_misses += 1

        if not self.client:
            result = self._heuristic_sentiment(title, summary)
            self._cache.set(cache_key, result)
            return result

        system = (
            "Bạn là chuyên gia phân tích sentiment tin tức tài chính Việt Nam. "
            "Chấm điểm sentiment từ -1.0 (rất tiêu cực) đến 1.0 (rất tích cực). "
            "Trả lời dưới dạng JSON với keys: score, label, reasoning."
        )
        prompt = f"""Phân tích sentiment của tin tức sau:

Tiêu đề: {title}
Tóm tắt: {summary}

Trả lời JSON (KHÔNG markdown):
{{"score": <float -1 to 1>, "label": "<tích cực/trung tính/tiêu cực>", "reasoning": "<lý do ngắn gọn>"}}"""

        result = self._call_gemini_json(
            prompt, system,
            fallback={'score': 0.0, 'label': 'trung tính', 'reasoning': 'Không thể phân tích'},
            model_tier="fast"
        )
        if self._is_mock_payload(result):
            result = self._heuristic_sentiment(title, summary)
        self._cache.set(cache_key, result)
        return result

    def classify_news_impact(self, title: str, summary: str, related_symbols: List[str]) -> Dict:
        """
        Classify impact level of news on specific stocks.
        Returns: {'impact_level': str, 'affected_symbols': list, 'explanation': str}
        """
        if not self.client:
            return self._heuristic_news_impact(title, summary, related_symbols)

        system = (
            "Bạn là chuyên gia đánh giá tác động tin tức đến giá cổ phiếu Việt Nam. "
            "Phân loại mức độ ảnh hưởng: low, medium, high, critical."
        )
        symbols_str = ', '.join(related_symbols) if related_symbols else 'Chưa xác định'
        prompt = f"""Đánh giá mức độ ảnh hưởng của tin tức sau đến thị trường chứng khoán:

Tiêu đề: {title}
Tóm tắt: {summary}
Mã liên quan: {symbols_str}

Trả lời JSON (KHÔNG markdown):
{{"impact_level": "<low/medium/high/critical>", "affected_symbols": [<list>], "explanation": "<giải thích>"}}"""

        result = self._call_gemini_json(
            prompt, system,
            fallback={
                'impact_level': 'low',
                'affected_symbols': related_symbols,
                'explanation': 'Không thể đánh giá tác động'
            }
        )
        if self._is_mock_payload(result):
            return self._heuristic_news_impact(title, summary, related_symbols)
        return result

    def generate_insight(
        self,
        risk_metrics: Dict,
        news_summary: str,
        anomalies: List[Dict],
        user_profile: Dict,
    ) -> Dict:
        """
        Generate comprehensive risk insight combining quantitative data + news.
        This is the core intelligence output.
        """
        system = (
            "Bạn là Riskism AI - hệ thống Chuyên Gia Phân Tích Rủi Ro Định Lượng (Quantitative Risk Analyst) cho thị trường chứng khoán Việt Nam. "
            "Nhiệm vụ: Tổng hợp dữ liệu VaR, Beta, Sharpe, Drawdown và tin tức thành báo cáo chuyên nghiệp, sắc bén. "
            "KHÔNG đưa ra khuyến nghị Mua/Bán. Chỉ được đưa ra cảnh báo rủi ro (Risk Alert) và hướng xử lý quản trị rủi ro. "
            "Sử dụng thuật ngữ tài chính chuẩn xác nhưng giải thích dễ hiểu (ví dụ: VaR là mức lỗ tiềm tàng). "
            "Trả về kết quả duy nhất là mã JSON."
        )
        
        risk_appetite = user_profile.get('risk_appetite', 'moderate')
        capital = user_profile.get('capital_amount', 0)
        
        prompt = f"""Phân tích hồ sơ rủi ro danh mục:
---
ĐỐI TƯỢNG: Nhà đầu tư cá nhân | Vốn: {capital:,.0f} VND | Khẩu vị: {risk_appetite}
DỮ LIỆU ĐỊNH LƯỢNG (Quantitative Data):
{json.dumps(risk_metrics, indent=2, ensure_ascii=False)}

DỮ LIỆU TIN TỨC & SENTIMENT:
{news_summary}

SỰ KIỆN BẤT THƯỜNG (Anomaly detection):
{json.dumps(anomalies, indent=2, ensure_ascii=False) if anomalies else 'Chưa phát hiện bất thường đáng kể'}
---
YÊU CẦU:
1. Xác định Risk Level dựa trên VaR và Volatility.
2. Tìm 3 "Tín hiệu rủi ro" (Signals) quan trọng nhất. Phải kết hợp cả số liệu và tin tức (vd: Beta cao + Tin xấu ngành).
3. trends: Dự báo xu hướng và mức độ tin cậy dựa trên tính chu kỳ và sentiment cho ít nhất 3 mã.

TRẢ VỀ ĐỊNH DẠNG JSON:
{{
    "title": "<Tiêu đề báo cáo - vd: Báo cáo rủi ro phiên sáng 28/03>",
    "risk_level": "<low/medium/high/critical>",
    "summary": "<Tóm tắt 2 câu về rủi ro tổng thể>",
    "key_findings": ["<Signal 1: Kết quả định lượng + Tin tức>", "<Signal 2>", "<Signal 3>"],
    "risk_factors": ["<Yếu tố rủi ro 1>", "<Yếu tố rủi ro 2>"],
    "action_items": ["<Hành động 1 - vd: Giảm tỷ trọng mã X>", "<Hành động 2>"],
    "confidence_score": 0.9,
    "trends": [
        {{"ticker": "Mã 1", "trend": "up/down/neutral", "conf": 85}},
        {{"ticker": "Mã 2", "trend": "up/down/neutral", "conf": 70}},
        {{"ticker": "Mã 3", "trend": "up/down/neutral", "conf": 60}}
    ]
}}"""

        fallback = self._build_insight_fallback(risk_metrics)

        result = self._call_gemini_json(
            prompt, system, temperature=0.4,
            fallback=fallback,
            model_tier="reasoning" # Use higher tier reasoning model for core insights
        )
        if self._is_mock_payload(result):
            return dict(fallback)
        return self._normalize_insight_payload(result, fallback)

    def generate_morning_prediction(self, market_data: Dict, news_data: List[Dict]) -> Dict:
        """Generate morning market prediction."""
        system = (
            "Bạn là Riskism AI. Tạo dự báo phiên sáng dựa trên dữ liệu thị trường "
            "và tin tức đêm qua. DỰ BÁO xu hướng rủi ro, KHÔNG dự đoán giá cụ thể."
        )
        
        news_text = "\n".join([f"- {n.get('title', '')}" for n in news_data[:10]])
        
        prompt = f"""Dữ liệu thị trường gần đây:
{json.dumps(market_data, indent=2, ensure_ascii=False)}

Tin tức mới nhất:
{news_text or 'Không có tin mới'}

Tạo dự báo phiên sáng (JSON):
{{
    "prediction": "<xu hướng rủi ro: tăng/giảm/đi ngang>",
    "confidence": <0.0-1.0>,
    "reasoning": "<phân tích ngắn>",
    "key_risks": ["<risk 1>", "<risk 2>"],
    "watch_symbols": ["<symbol 1>", "<symbol 2>"]
}}"""

        return self._call_gemini_json(
            prompt, system,
            fallback={
                'prediction': 'đi ngang',
                'confidence': 0.5,
                'reasoning': 'Chưa đủ dữ liệu để dự báo chính xác',
                'key_risks': [],
                'watch_symbols': [],
            },
            model_tier="reasoning"
        )

    def self_reflect(self, prediction: Dict, actual_result: Dict) -> Dict:
        """
        Self-reflection: compare morning prediction vs actual results.
        This is the feedback loop that makes the system smarter.
        """
        system = (
            "Bạn là Riskism AI. Thực hiện self-reflection: so sánh dự báo sáng với kết quả thực tế. "
            "Rút kinh nghiệm để cải thiện dự báo trong tương lai."
        )
        
        prompt = f"""## Dự báo sáng:
{json.dumps(prediction, indent=2, ensure_ascii=False)}

## Kết quả thực tế phiên chiều:
{json.dumps(actual_result, indent=2, ensure_ascii=False)}

Phân tích (JSON):
{{
    "accuracy_score": <0.0-1.0>,
    "what_was_right": "<điều gì đúng>",
    "what_was_wrong": "<điều gì sai>",
    "lesson_learned": "<bài học rút ra>",
    "improvement_suggestion": "<gợi ý cải thiện>"
}}"""

        fallback = {
            'accuracy_score': 0.0,
            'what_was_right': '⚠️ Quota Cloud Exceeded (RESOURCE_EXHAUSTED)',
            'what_was_wrong': 'Không thể gọi Gemini AI: Limit hiện tại là 0.',
            'lesson_learned': 'Vui lòng kiểm tra lại Google AI Studio hoặc thay API Key mới có đủ quota.',
            'improvement_suggestion': 'Dashboard đang tự động chuyển sang chế độ dự phòng (Mode Offline).',
        }

        result = self._call_gemini_json(
            prompt, system,
            fallback=fallback,
            model_tier="reasoning"
        )
        if self._is_mock_payload(result):
            return dict(fallback)
        return self._normalize_reflection_payload(result, fallback)

    def _chat_reply_from_context(self, message: str, app_context: Optional[Dict] = None) -> Optional[str]:
        """Deterministic replies for app-specific questions using live frontend context."""
        if not isinstance(app_context, dict) or not app_context:
            return None

        text = (message or '').lower()
        market = app_context.get('market') or {}
        portfolio = app_context.get('portfolio') or {}
        portfolio_risk = app_context.get('portfolio_risk') or {}
        holdings = portfolio.get('holdings') or []
        top_risk_symbols = portfolio.get('top_risk_symbols') or []
        tail_risk = portfolio_risk.get('tail_risk_contributors') or []
        liquidity_profile = portfolio_risk.get('liquidity_profile') or {}
        stress_details = portfolio_risk.get('stress_scenarios_detail') or []

        if any(keyword in text for keyword in ('vnindex', 'vn-index', 'thị trường hôm nay', 'thi truong hom nay', 'market hôm nay', 'market hom nay')):
            change_pct = market.get('change_pct')
            price = market.get('price')
            if change_pct is not None and price is not None:
                sign = '+' if float(change_pct) >= 0 else ''
                return (
                    f"VN-Index hiện quanh {float(price):,.2f} điểm, biến động {sign}{float(change_pct):.2f}%."
                    " Nếu muốn, mình có thể nối luôn sang ý nghĩa của nhịp này với danh mục hiện tại."
                )

        if any(keyword in text for keyword in ('danh mục', 'danh muc', 'portfolio', 'holding', 'đang giữ', 'dang giu', 'giữ mã nào', 'giu ma nao')):
            if holdings:
                holdings_text = ', '.join(
                    f"{item.get('symbol')} ({float(item.get('weight_pct', 0)):.0f}%, P&L {float(item.get('pnl_pct', 0)):+.1f}%)"
                    for item in holdings[:5]
                )
                total_pnl_pct = portfolio.get('total_pnl_pct')
                if total_pnl_pct is not None:
                    return f"Danh mục hiện có: {holdings_text}. Tổng P&L đang {float(total_pnl_pct):+.1f}%."
                return f"Danh mục hiện có: {holdings_text}."

        if any(keyword in text for keyword in ('mã nào rủi ro nhất', 'ma nao rui ro nhat', 'tail risk', 'nguy hiểm nhất', 'nguy hiem nhat')):
            if tail_risk:
                top = tail_risk[0]
                return (
                    f"Mã đang kéo tail risk mạnh nhất là {top.get('symbol')} với khoảng "
                    f"{float(top.get('contribution_pct', 0)) * 100:.0f}% đóng góp tail load."
                    f" Driver chính hiện là {top.get('driver', 'tail')}."
                )
            if top_risk_symbols:
                top = top_risk_symbols[0]
                return f"Theo risk score hiện tại, {top.get('symbol')} đang cao nhất với điểm rủi ro khoảng {int(top.get('risk_score', 0))}/100."

        if any(keyword in text for keyword in ('var', 'cvar', 'drawdown', 'beta', 't+2', 'thanh khoản', 'thanh khoan', 'liquidity')):
            parts = []
            if 'var' in text or 'cvar' in text:
                if portfolio_risk.get('var_95') is not None:
                    parts.append(
                        f"VaR 95% hiện khoảng {abs(float(portfolio_risk.get('var_95', 0))) * 100:.1f}%"
                    )
                if portfolio_risk.get('adjusted_var_95') is not None and any(k in text for k in ('t+2', 'thanh khoản', 'thanh khoan', 'liquidity', 'adjusted')):
                    parts.append(
                        f"Adj VaR T+2 khoảng {abs(float(portfolio_risk.get('adjusted_var_95', 0))) * 100:.1f}%"
                    )
                if portfolio_risk.get('cvar_95') is not None:
                    parts.append(
                        f"CVaR 95% khoảng {abs(float(portfolio_risk.get('cvar_95', 0))) * 100:.1f}%"
                    )
            if 'drawdown' in text and portfolio_risk.get('max_drawdown') is not None:
                parts.append(f"max drawdown khoảng {abs(float(portfolio_risk.get('max_drawdown', 0))) * 100:.1f}%")
            if 'beta' in text and portfolio_risk.get('beta_dimson') is not None:
                parts.append(f"beta Dimson khoảng {float(portfolio_risk.get('beta_dimson', 0)):.2f}")
            if any(k in text for k in ('t+2', 'thanh khoản', 'thanh khoan', 'liquidity')) and liquidity_profile:
                parts.append(
                    f"horizon thanh khoản hiệu dụng ~{float(liquidity_profile.get('effective_horizon_days', 3)):.1f} ngày"
                )
            if parts:
                return ' | '.join(parts) + '.'

        if any(keyword in text for keyword in ('stress', 'kịch bản xấu', 'kich ban xau', 'xấu nhất', 'xau nhat')):
            if stress_details:
                worst = stress_details[0]
                start_date = worst.get('start_date')
                end_date = worst.get('end_date')
                window = f" từ {start_date} đến {end_date}" if start_date and end_date else ""
                return (
                    f"Stress window xấu nhất hiện là {worst.get('label')} với mức lỗ khoảng "
                    f"{abs(float(worst.get('return', 0))) * 100:.1f}%{window}."
                )

        if any(keyword in text for keyword in ('insight', 'tóm tắt', 'tom tat', 'ai nói gì', 'ai noi gi')):
            summary = app_context.get('latest_insight_summary')
            if summary:
                return f"Tóm tắt AI gần nhất: {summary}"

        return None

    def _has_keyword(self, text: str, tokens: tuple) -> bool:
        """Helper to do word-boundary matching instead of raw substring."""
        for token in tokens:
            if re.search(rf'\b{re.escape(token)}\b', text):
                return True
        return False

    def _heuristic_chat_reply(self, message: str, app_context: Optional[Dict] = None) -> str:
        contextual_reply = self._chat_reply_from_context(message, app_context)
        if contextual_reply:
            return contextual_reply

        text = (message or '').lower().strip()

        if (
            re.search(r'\b(app|riskism)\b.*\b(giúp|giup|được|duoc|dcg|làm|lam|hỗ trợ|ho tro)\b', text)
            or re.search(r'\b(giúp|giup|được|duoc|dcg|làm|lam|hỗ trợ|ho tro)\b.*\b(app|riskism)\b', text)
        ):
            return (
                "Riskism hiện giúp bạn 4 việc chính: "
                "1) xem nhanh sức khỏe danh mục như VaR, CVaR, beta, drawdown; "
                "2) chỉ ra mã đang kéo tail risk, bottleneck thanh khoản T+2 và stress window xấu nhất; "
                "3) tóm tắt market context như VN-Index và news liên quan; "
                "4) trả lời các câu hỏi general ngắn gọn. "
                "Nếu muốn, mình có thể giải thích ngay trên danh mục bạn đang mở."
            )

        if self._has_keyword(text, ('xin chào', 'xin chao', 'chào', 'hello', 'hi')):
            return "Chào bạn! Mình có thể trả lời cả câu hỏi về Riskism/danh mục hiện tại lẫn các câu hỏi general ngắn gọn. Bạn hỏi thẳng ý chính là được."

        if self._has_keyword(text, ('cảm ơn', 'cam on', 'thanks', 'thank you')):
            return "Không có gì. Nếu muốn, mình có thể giải thích tiếp theo kiểu rất ngắn gọn hoặc đi sâu từng bước."

        if self._has_keyword(text, ('bạn làm được gì', 'ban lam duoc gi', 'giúp gì', 'giup gi', 'help', 'hỗ trợ gì', 'ho tro gi')):
            return "Mình hỗ trợ 2 kiểu: 1) câu hỏi trong Riskism như danh mục, VaR, tail risk, VN-Index, reflection loop; 2) câu hỏi ngoài luồng như học tập, công việc ở mức ngắn gọn, thực dụng."

        if self._has_keyword(text, ('requirement', 'requirements', 'yêu cầu', 'yeu cau', 'user story', 'acceptance criteria', 'spec', 'scope', 'prd')):
            return (
                "Mình có thể giúp bóc requirement nữa. Bạn chỉ cần nói mục tiêu, user nào dùng, đầu ra mong muốn và ràng buộc nếu có; "
                "mình sẽ tách lại thành problem, feature scope, user flow, acceptance criteria và edge cases."
            )

        glossary = [
            (('var', 'value at risk'), 'VaR là mức lỗ ước tính trong điều kiện bình thường ở một ngưỡng xác suất, ví dụ 95%. VaR càng lớn thì rủi ro ngắn hạn càng cao.'),
            (('cvar', 'expected shortfall'), 'CVaR là mức lỗ trung bình trong nhóm tình huống xấu nhất sau khi đã vượt VaR. Nó phản ánh tail risk rõ hơn VaR.'),
            (('sharpe',), 'Sharpe Ratio đo lợi nhuận trên mỗi đơn vị biến động. Chỉ số càng cao thì hiệu quả lợi nhuận so với rủi ro càng tốt.'),
            (('beta',), 'Beta cho biết cổ phiếu hoặc danh mục nhạy tới mức nào so với thị trường. Beta > 1 nghĩa là thường biến động mạnh hơn thị trường.'),
            (('drawdown', 'max drawdown'), 'Max Drawdown là mức sụt giảm lớn nhất từ đỉnh xuống đáy trong một giai đoạn. Nó giúp nhìn rủi ro mất vốn thực tế dễ hơn lợi nhuận trung bình.'),
            (('hhi', 'diversification'), 'HHI đo độ tập trung danh mục. HHI càng cao thì danh mục càng dồn vào ít mã, nghĩa là rủi ro tập trung lớn hơn.'),
            (('reflection', 'self-reflection', 'agentic reflection'), 'Reflection Loop là cơ chế để hệ thống so dự báo buổi sáng với kết quả thực tế buổi chiều rồi rút kinh nghiệm cho lần sau.'),
            (('capital tier', 'position size', 'capital'), 'Capital Tier dùng để gợi ý số lượng mã nên giữ và tỷ trọng mỗi vị thế sao cho phù hợp quy mô vốn, tránh danh mục quá loãng hoặc quá tập trung.'),
            (('volatility regime', 'regime'), 'Volatility regime là trạng thái biến động của thị trường như low, normal, high hoặc extreme. Regime cao thường đi kèm nhu cầu quản trị rủi ro chặt hơn.'),
        ]

        for keywords, answer in glossary:
            if self._has_keyword(text, keywords):
                return answer

        if self._has_keyword(text, ('học', 'hoc', 'study', 'ôn thi', 'on thi', 'tập trung', 'tap trung', 'học tập', 'hoc tap')):
            return (
                "Nếu bạn muốn học hiệu quả hơn, thử 3 bước ngắn này: "
                "1) chia mục tiêu thành block 25-45 phút, "
                "2) mỗi block chỉ làm 1 việc, "
                "3) cuối buổi tự tóm tắt lại 3 ý chính bằng lời của bạn. "
                "Nếu muốn, mình có thể giúp bạn lên luôn một plan học theo môn hoặc theo deadline."
            )

        if self._has_keyword(text, ('công việc', 'cong viec', 'productivity', 'năng suất', 'nang suat', 'quản lý thời gian', 'quan ly thoi gian')):
            return (
                "Với công việc, cách gọn nhất là: chốt 1 việc quan trọng nhất trong ngày, "
                "gom các việc nhỏ vào 1 khung xử lý riêng, và luôn để lại 15 phút cuối ngày để review + lên việc ngày mai. "
                "Nếu bạn muốn, mình có thể giúp bạn biến list việc hiện tại thành plan ưu tiên."
            )

        if self._has_keyword(text, ('caption', 'cap', 'status', 'bio', 'tiểu sử', 'tieu su')):
            topic = self._extract_general_topic(message, ('caption', 'status', 'bio', 'tiểu sử', 'tieu su'))
            topic = topic or 'chủ đề này'
            return (
                f"Thử 3 phiên bản ngắn cho {topic} nhé:\n"
                f"1. Nhẹ nhàng: \"Giữ lại một ngày thật đẹp cho {topic}.\"\n"
                f"2. Tươi hơn: \"Một chút niềm vui, một chút kỷ niệm, và rất nhiều năng lượng cho {topic}.\"\n"
                f"3. Ngắn gọn: \"{topic.capitalize()} mode: on.\""
            )

        if self._has_keyword(text, ('sinh nhật', 'sinh nhat', 'chúc mừng', 'chuc mung', 'lời chúc', 'loi chuc')):
            return (
                "Một lời chúc ngắn gọn bạn có thể dùng:\n"
                "\"Chúc bạn tuổi mới thật nhiều sức khỏe, niềm vui và những điều tốt đẹp đến đúng lúc. "
                "Mong năm nay sẽ là một năm thật đáng nhớ với bạn.\""
            )

        if self._has_keyword(text, ('câu đùa', 'cau dua', 'joke', 'đùa', 'dua')):
            return "Một câu ngắn nhé: \"Deadline không đáng sợ, đáng sợ là mình tưởng còn nhiều thời gian.\""

        if self._has_keyword(text, ('gợi ý', 'goi y', 'ý tưởng', 'y tuong', 'brainstorm', 'idea')):
            topic = self._extract_general_topic(message, ('gợi ý', 'goi y', 'ý tưởng', 'y tuong', 'idea', 'brainstorm'))
            topic = topic or 'việc này'
            return (
                f"Một vài ý tưởng nhanh cho {topic}:\n"
                "1. Làm bản đơn giản nhất trước để chốt hướng.\n"
                "2. Tạo 3 phiên bản khác tone để dễ chọn.\n"
                "3. Ưu tiên thứ dễ làm ngay trong 30 phút đầu.\n"
                "4. Nếu cần, mình có thể brainstorm sâu hơn theo mục tiêu cụ thể."
            )

        if self._has_keyword(text, ('viết mail', 'viet mail', 'email', 'tin nhắn', 'tin nhan', 'message', 'rewrite', 'viết lại', 'viet lai')):
            return (
                "Mình giúp viết ngắn được. Bạn chỉ cần nói rõ 3 thứ: viết cho ai, mục đích là gì, và tone muốn lịch sự hay thân mật. "
                "Nếu muốn, mình có thể draft luôn một bản ngắn ngay ở tin nhắn tiếp theo."
            )

        if self._has_keyword(text, ('code', 'lập trình', 'lap trinh', 'debug', 'bug', 'api', 'sql', 'javascript', 'python')):
            return "Mình hỗ trợ cả câu hỏi code ở mức ngắn gọn nữa. Nếu bạn dán lỗi, đoạn code, hoặc nói rõ muốn build gì, mình có thể cùng bóc nguyên nhân và đề xuất hướng làm."

        return "Mình có thể trả lời cả câu hỏi trong Riskism lẫn câu hỏi ngoài luồng ở mức ngắn gọn. Nếu bạn hỏi về app, mình sẽ bám vào dữ liệu đang mở; nếu hỏi general, cứ hỏi thẳng nội dung."

    def _extract_general_topic(self, message: str, markers: tuple) -> str:
        raw = (message or '').strip()
        normalized = raw
        for marker in markers:
            pattern = re.compile(re.escape(marker), re.IGNORECASE)
            normalized = pattern.sub(' ', normalized)
        normalized = re.sub(r'\b(cho mình|cho toi|giúp mình|giup minh|viết|viet|một|mot|ngắn gọn|ngan gon|với|ve|về|cho)\b', ' ', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\s+', ' ', normalized).strip(' .?!:')
        return normalized[:60]

    def _format_chat_context(self, app_context: Optional[Dict]) -> str:
        if not isinstance(app_context, dict) or not app_context:
            return "{}"
        try:
            return json.dumps(app_context, ensure_ascii=False)
        except (TypeError, ValueError):
            return "{}"

    def chat_assistant(self, message: str, history: list, app_context: Optional[Dict] = None) -> str:
        """Handle chat assistance for both Riskism context and broader user questions."""
        contextual_reply = self._chat_reply_from_context(message, app_context)
        if not self.client:
            return contextual_reply or self._heuristic_chat_reply(message, app_context)

        system = (
            "Bạn là 'Riskism Assistant', một trợ lý AI thân thiện trong ứng dụng Riskism. "
            "Bạn có thể trả lời cả câu hỏi trong app lẫn câu hỏi ngoài luồng của người dùng. "
            "Nguyên tắc:\n"
            "1. Luôn trả lời bằng tiếng Việt, thân thiện, dễ hiểu.\n"
            "2. Ưu tiên ngắn gọn, thực dụng, thường dưới 180 chữ.\n"
            "3. Nếu câu hỏi liên quan Riskism, danh mục, thị trường, AI report hoặc metric rủi ro, hãy dùng app_context để trả lời bằng số liệu cụ thể khi có.\n"
            "4. Nếu câu hỏi ngoài app, vẫn trả lời trực tiếp và tự nhiên; không được từ chối máy móc chỉ vì ngoài phạm vi tài chính.\n"
            "5. Nếu app_context chưa đủ dữ liệu cho câu hỏi cụ thể, nói rõ phần nào bạn chưa nhìn thấy thay vì bịa.\n"
            "6. Không bịa dữ liệu realtime ngoài app_context."
        )

        # Build prompt from history
        context = ""
        for h in history[-6:]:
            if h.get('sender') == 'user':
                context += f"\nUser: {h.get('text')}"
            else:
                context += f"\nAssistant: {h.get('text')}"

        prompt = (
            f"App context hiện tại (JSON):\n{self._format_chat_context(app_context)}\n\n"
            f"Lịch sử trò chuyện gần đây:\n{context}\n\n"
            f"User: {message}\nAssistant:"
        )
        
        reply = self._call_gemini(
            prompt, system,
            temperature=0.4,
            model_tier="fast"
        )
        # BUG FIX: Expose AI failure openly instead of masking it entirely with a normal-sounding fallback
        if isinstance(reply, str) and reply.startswith("⚠️ [Sự cố AI]"):
            fallback = contextual_reply or self._heuristic_chat_reply(message, app_context)
            if "Riskism lẫn câu hỏi ngoài luồng" in fallback or "Chào bạn" in fallback:
                return f"{reply}\n\n💡 Gợi ý tạm thời: {fallback}"
            else:
                return f"{reply}\n\n💡 Trả lời tự động: {fallback}"
                
        return reply

    def _mock_response(self, prompt: str, is_error: bool = False, error_detail: str = "") -> str:
        """Generate mock response when Gemini is not available or fails."""
        # Detect if this is an explicit error (e.g. invalid API Key)
        error_context = f" (Chi tiết: {error_detail})" if error_detail else ""
        
        if 'assistant:' in prompt.lower():
            if is_error or not self.client:
                return f"⚠️ [Sự cố AI] Google Gemini API Key đã hết hạn hoặc chưa được cấu hình! {error_context}. Vui lòng kiểm tra lại file .env của bạn."
            return "Xin lỗi, hiện tại tôi không thể kết nối với bộ não chính. Lời nhắc: Bạn có thể kiểm tra VaR (Value at Risk) trong tab Portfolio nhé!"
            
        elif 'sentiment' in prompt.lower():
            return json.dumps({
                'score': 0.0,
                'label': 'trung tính',
                'reasoning': f'[Chế độ Demo] AI đang bảo trì API Key. Chấm điểm theo trọng số từ khóa mặc định.{error_context}'
            })
        elif 'impact' in prompt.lower() or 'tác động' in prompt.lower():
            return json.dumps({
                'impact_level': 'medium',
                'affected_symbols': [],
                'explanation': f'[Chế độ Demo] Không thể phân tích chuyên sâu tin tức do lỗi API.{error_context}'
            })
        elif 'reflection' in prompt.lower():
            return json.dumps({
                'accuracy_score': 0.0,
                'what_was_right': f'⚠️ AI đang gặp sự cố kết nối.{error_context}',
                'what_was_wrong': 'Chế độ Demo: Không thể phân tích chéo dữ liệu do giới hạn API quota.',
                'lesson_learned': 'Cần kiểm tra lại Google Cloud Console hoặc thay API Key mới có đủ dung lượng.',
                'improvement_suggestion': 'Hệ thống đang tạm dùng logic dự phòng để không làm gián đoạn dashboard.',
            })
        elif 'dự báo' in prompt.lower() or 'prediction' in prompt.lower():
            return json.dumps({
                'prediction': 'đi ngang',
                'confidence': 0.5,
                'reasoning': f'[Chế độ Demo] AI đang sử dụng dự báo mẫu do mất kết nối Gemini.{error_context}',
                'key_risks': ['Thanh khoản thấp', 'Áp lực bán ròng từ khối ngoại'],
                'watch_symbols': ['VCB', 'FPT'],
            })
        else:
            return json.dumps({
                'title': f'Báo cáo rủi ro mẫu (Chế độ Mock){" - Lỗi API!" if is_error else ""}',
                'risk_level': 'medium',
                'summary': f'[Chế độ Demo] Hệ thống hiện đang phân tích dựa trên thuật toán offline do lỗi API Key. {error_context}',
                'key_findings': [
                    '[Offline] VN-Index đang dao dịch trong biên độ hẹp',
                    '[Offline] Thanh khoản giảm so với TB 20 phiên',
                ],
                'risk_factors': ['Rủi ro thanh khoản', 'Áp lực tỷ giá'],
                'action_items': ['Giữ tỷ trọng tiền mặt hợp lý', 'Theo dõi dòng tiền'],
                'confidence_score': 0.5,
                'trends': [
                    {'ticker': 'VCB', 'trend': 'up', 'conf': 85},
                    {'ticker': 'VIC', 'trend': 'down', 'conf': 70},
                    {'ticker': 'HPG', 'trend': 'neutral', 'conf': 55}
                ]
            })
