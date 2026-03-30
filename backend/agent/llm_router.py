"""
Riskism Agent - Gemini LLM Router
Routes AI tasks to Google Gemini with appropriate prompts.
"""
import json
import hashlib
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
            "fast": "gemini-2.0-flash",           # For news sentiment, entity extraction
            "reasoning": "gemini-2.0-flash",    # For complex insight generation
            "fallback": "gemini-2.0-flash"
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
            print(f"[LLMRouter] Gemini ({model_name}) error: {e}")
            return self._mock_response(prompt)

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

    def _is_mock_payload(self, payload: Dict) -> bool:
        return isinstance(payload, dict) and any(
            isinstance(value, str) and '[Mock]' in value
            for value in payload.values()
        )

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

        return self._call_gemini_json(
            prompt, system, temperature=0.4,
            fallback={
                'title': 'Báo cáo rủi ro hàng ngày',
                'risk_level': 'medium',
                'summary': 'Hệ thống đang thu thập và phân tích dữ liệu.',
                'key_findings': ['Đang cập nhật dữ liệu...'],
                'risk_factors': [],
                'action_items': ['Theo dõi thêm'],
                'confidence_score': 0.5,
                'trends': [{'ticker': 'VNINDEX', 'trend': 'neutral', 'conf': 50}]
            },
            model_tier="reasoning" # Use higher tier reasoning model for core insights
        )

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

        return self._call_gemini_json(
            prompt, system,
            fallback={
                'accuracy_score': 0.5,
                'what_was_right': 'Đang phân tích',
                'what_was_wrong': 'Đang phân tích',
                'lesson_learned': 'Cần thêm dữ liệu',
                'improvement_suggestion': 'Thu thập thêm dữ liệu',
            },
            model_tier="reasoning"
        )

    def chat_assistant(self, message: str, history: list) -> str:
        """Handle chatbot assistance specifically for terms and explanations."""
        system = (
            "Bạn là 'Riskism Assistant', một trợ lý AI thân thiện chuyên giải thích các thuật ngữ "
            "về tài chính, quản trị rủi ro chứng khoán và dự án Riskism (như VaR, CVaR, Sharpe Ratio, HHI, "
            "Agentic Reflection, Capital Tier, Vol Regime) cho người dùng mới (newbie). "
            "Nguyên tắc:\n"
            "1. Luôn trả lời bằng tiếng Việt, thân thiện, dễ hiểu, dùng ngôn ngữ sinh động.\n"
            "2. Trả lời NGẮN GỌN (dưới 150 chữ).\n"
            "3. Nếu người dùng hỏi các chủ đề không liên quan đến tài chính, chứng khoán hoặc ứng dụng này (ví dụ: code, lập trình, sức khoẻ, cá nhân), "
            "hãy khéo léo từ chối và nhắc họ rằng bạn chỉ hỗ trợ giải thích thuật ngữ Riskism."
        )

        # Build prompt from history
        context = ""
        for h in history[-5:]: # Only keep last 5 for context
            if h.get('sender') == 'user':
                context += f"\nUser: {h.get('text')}"
            else:
                context += f"\nAssistant: {h.get('text')}"
                
        prompt = f"Lịch sử trò chuyện gần đây:\n{context}\n\nUser: {message}\nAssistant:"
        
        return self._call_gemini(
            prompt, system,
            temperature=0.4,
            model_tier="fast"
        )

    def _mock_response(self, prompt: str) -> str:
        """Generate mock response when Gemini is not available."""
        if 'assistant:' in prompt.lower():
            return "Xin lỗi, hiện tại AI backend đang tắt hoặc thiếu API Key! Lời nhắc: VaR là Value at Risk nhé!"
        elif 'sentiment' in prompt.lower():
            return json.dumps({
                'score': 0.2,
                'label': 'hơi tích cực',
                'reasoning': '[Mock] Tin tức có yếu tố tích cực nhẹ cho thị trường.'
            })
        elif 'impact' in prompt.lower() or 'tác động' in prompt.lower():
            return json.dumps({
                'impact_level': 'medium',
                'affected_symbols': [],
                'explanation': '[Mock] Tin tức có ảnh hưởng trung bình đến thị trường.'
            })
        elif 'dự báo' in prompt.lower() or 'prediction' in prompt.lower():
            return json.dumps({
                'prediction': 'đi ngang',
                'confidence': 0.5,
                'reasoning': '[Mock] Thị trường đang trong giai đoạn tích lũy.',
                'key_risks': ['Thanh khoản thấp', 'Áp lực bán ròng từ khối ngoại'],
                'watch_symbols': ['VCB', 'FPT'],
            })
        elif 'reflection' in prompt.lower():
            return json.dumps({
                'accuracy_score': 0.6,
                'what_was_right': '[Mock] Xu hướng chung khớp dự báo',
                'what_was_wrong': '[Mock] Mức biến động mạnh hơn dự kiến',
                'lesson_learned': '[Mock] Cần chú ý hơn đến dòng tiền ngoại',
                'improvement_suggestion': '[Mock] Thêm chỉ báo dòng tiền vào phân tích',
            })
        else:
            return json.dumps({
                'title': 'Báo cáo rủi ro Riskism',
                'risk_level': 'medium',
                'summary': '[Mock] Thị trường đang ở mức rủi ro trung bình. Cần theo dõi thêm.',
                'key_findings': [
                    '[Mock] VN-Index đang giao dịch trong biên độ hẹp',
                    '[Mock] Thanh khoản giảm so với TB 20 phiên',
                ],
                'risk_factors': ['Rủi ro thanh khoản', 'Áp lực tỷ giá'],
                'action_items': ['Giữ tỷ trọng tiền mặt hợp lý', 'Theo dõi dòng tiền'],
                'confidence_score': 0.6,
                'trends': [
                    {'ticker': 'VCB', 'trend': 'up', 'conf': 85},
                    {'ticker': 'VIC', 'trend': 'down', 'conf': 70},
                    {'ticker': 'HPG', 'trend': 'neutral', 'conf': 55}
                ]
            })
