/**
 * Riskism - API Client
 * Handles all HTTP and WebSocket communication with the backend.
 */

const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000' 
    : '';

const WS_BASE = window.location.hostname === 'localhost'
    ? 'ws://localhost:8000'
    : `ws://${window.location.host}`;

class RiskismAPI {
    constructor() {
        this.ws = null;
        this.wsReconnectTimeout = null;
        this.onPriceUpdate = null;
        this.onAgentResult = null;
        this.onConnectionChange = null;
        this.demoMode = true; // Fallback to demo when backend is unavailable
    }

    // ─── HTTP Methods ────────────────────────────────────

    async get(endpoint) {
        try {
            const res = await fetch(`${API_BASE}${endpoint}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.warn(`[API] GET ${endpoint} failed:`, err.message);
            return null;
        }
    }

    async post(endpoint, data) {
        try {
            const res = await fetch(`${API_BASE}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.warn(`[API] POST ${endpoint} failed:`, err.message);
            return null;
        }
    }

    // ─── Auth ────────────────────────────────────────────
    async login(username) {
        return await this.post('/api/auth/login', { username });
    }

    // ─── Market Data ─────────────────────────────────────

    async getMarketData(symbol, days = 180) {
        const data = await this.get(`/api/market/${symbol}?days=${days}`);
        return data || this.getDemoMarketData(symbol, days);
    }

    async getStockRisk(symbol) {
        const data = await this.get(`/api/market/${symbol}/risk`);
        return data || this.getDemoRiskData(symbol);
    }

    async getLatestPrice(symbol) {
        return await this.get(`/api/market/${symbol}/price`);
    }

    // ─── Portfolio ───────────────────────────────────────

    async getPortfolio(userId) {
        const data = await this.get(`/api/portfolio/${userId}`);
        return data || this.getDemoPortfolio();
    }

    async getPortfolioRisk(userId) {
        const data = await this.get(`/api/portfolio/${userId}/risk`);
        return data || this.getDemoPortfolioRisk();
    }

    async updatePortfolio(userId, capital, holdings) {
        return await this.post(`/api/portfolio/${userId}/update`, {
            capital_amount: capital,
            holdings: holdings
        });
    }

    // ─── Insights & News ─────────────────────────────────

    async getInsights(userId = 1) {
        return await this.get(`/api/insights/${userId}`);
    }

    async getNews(limit = 20) {
        const data = await this.get(`/api/news/latest?limit=${limit}`);
        return data || this.getDemoNews();
    }

    // ─── Agent ───────────────────────────────────────────

    async triggerAgent(userId, type = 'morning', symbol = null) {
        try {
            const res = await fetch(`${API_BASE}/api/agent/trigger`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, analysis_type: type, symbol }),
            });
            if (res.status === 429) {
                const err = await res.json();
                throw new Error(`429: ${err.detail || 'Rate limit exceeded'}`);
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            if (err.message.startsWith('429')) throw err; // propagate rate limit
            console.warn('[API] Agent trigger failed:', err.message);
            return this.getDemoAgentResult();
        }
    }

    async getAgentStatus() {
        return await this.get('/api/agent/status');
    }

    async getPredictions(userId = 1) {
        return await this.get(`/api/predictions/${userId}`);
    }

    // ─── WebSocket ───────────────────────────────────────

    connectWebSocket() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

        try {
            this.ws = new WebSocket(`${WS_BASE}/ws/prices`);

            this.ws.onopen = () => {
                console.log('[WS] Connected');
                this.demoMode = false;
                if (this.onConnectionChange) this.onConnectionChange('connected');
            };

            this.ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'price_update' && this.onPriceUpdate) {
                        this.onPriceUpdate(msg.data);
                    }
                    if (msg.type === 'agent_result' && this.onAgentResult) {
                        this.onAgentResult(msg.data);
                    }
                } catch (e) {
                    console.warn('[WS] Parse error:', e);
                }
            };

            this.ws.onclose = () => {
                console.log('[WS] Disconnected, reconnecting in 3s...');
                if (this.onConnectionChange) this.onConnectionChange('disconnected');
                this.wsReconnectTimeout = setTimeout(() => this.connectWebSocket(), 3000);
            };

            this.ws.onerror = () => {
                console.warn('[WS] Connection error, falling back to demo mode');
                this.demoMode = true;
                if (this.onConnectionChange) this.onConnectionChange('demo');
            };

        } catch (err) {
            console.warn('[WS] Failed to connect:', err);
            this.demoMode = true;
            if (this.onConnectionChange) this.onConnectionChange('demo');
        }
    }

    // ─── Demo Data (Fallback) ────────────────────────────

    getDemoMarketData(symbol, days) {
        const seed = symbol.charCodeAt(0) + symbol.charCodeAt(1);
        const basePrices = {
            VCB: 85000, FPT: 120000, HPG: 26000, TCB: 22000,
            MWG: 55000, VNM: 72000, VIC: 40000, MSN: 65000,
        };
        const base = basePrices[symbol] || 50000;
        const dates = [], close = [], open = [], high = [], low = [], volume = [];
        let price = base;

        for (let i = 0; i < days; i++) {
            const d = new Date();
            d.setDate(d.getDate() - (days - i));
            dates.push(d.toISOString().split('T')[0]);
            
            const ret = (Math.random() - 0.48) * 0.036;
            price = price * (1 + ret);
            const o = price * (1 + (Math.random() - 0.5) * 0.01);
            const h = Math.max(o, price) * (1 + Math.random() * 0.015);
            const l = Math.min(o, price) * (1 - Math.random() * 0.015);
            
            open.push(Math.round(o));
            high.push(Math.round(h));
            low.push(Math.round(l));
            close.push(Math.round(price));
            volume.push(Math.round(500000 + Math.random() * 2000000));
        }

        return { symbol, dates, open, high, low, close, volume };
    }

    getDemoRiskData(symbol) {
        const rand = (min, max) => Math.random() * (max - min) + min;
        return {
            symbol,
            risk_metrics: {
                symbol,
                var_95: -rand(0.01, 0.05),
                var_99: -rand(0.02, 0.07),
                cvar_95: -rand(0.02, 0.08),
                cvar_99: -rand(0.03, 0.1),
                beta: rand(0.5, 1.5),
                sharpe_ratio: rand(-0.5, 2.0),
                sortino_ratio: rand(-0.3, 2.5),
                max_drawdown: rand(0.05, 0.35),
                drawdown_duration: Math.round(rand(5, 60)),
                volatility: rand(0.15, 0.45),
                daily_volatility: rand(0.008, 0.025),
                avg_return: rand(-0.001, 0.002),
                risk_score: Math.round(rand(20, 80)),
            },
            anomalies: [],
        };
    }

    getDemoPortfolio() {
        return {
            user_id: 1,
            risk_appetite: 'moderate',
            capital_amount: 20000000,
            holdings: [
                { symbol: 'VCB', quantity: 100, avg_price: 85000, sector: 'Banking' },
                { symbol: 'FPT', quantity: 50, avg_price: 120000, sector: 'Technology' },
                { symbol: 'HPG', quantity: 200, avg_price: 26000, sector: 'Industrial' },
            ],
        };
    }

    getDemoPortfolioRisk() {
        return {
            portfolio: this.getDemoPortfolio(),
            portfolio_metrics: {
                hhi: 0.38,
                effective_n: 2.63,
                sector_exposure: { Banking: 0.45, Technology: 0.32, Industrial: 0.23 },
                max_sector_weight: 0.45,
                total_value: 19700000,
                diversification_score: 45,
                volatility_regime: 'normal',
            },
            capital_advice: {
                capital_tier: 'small',
                max_positions: 3,
                position_size_pct: 33.33,
                suggested_next_symbols: ['VNM', 'GAS', 'MWG'],
                warnings: [
                    '⚠️ VCB và HPG có tương quan cao (72.3%). Danh mục chưa thực sự đa dạng hóa.',
                    '📊 Với vốn 20M, bạn nên giữ tối đa 3 mã. Hiện tại bạn đang giữ 3 mã.',
                ],
                accumulation_plan: {
                    current_capital: 20000000,
                    monthly_savings: 2000000,
                    milestones: [
                        { amount: 30000000, month: 5, label: '30M VND', tier_unlock: 'medium' },
                        { amount: 50000000, month: 15, label: '50M VND', tier_unlock: 'medium' },
                    ],
                },
            },
            stock_risks: {
                VCB: { risk_score: 35, var_95: -0.022, sharpe_ratio: 1.2, beta: 0.85 },
                FPT: { risk_score: 42, var_95: -0.028, sharpe_ratio: 0.95, beta: 1.1 },
                HPG: { risk_score: 65, var_95: -0.042, sharpe_ratio: 0.3, beta: 1.45 },
            },
        };
    }

    getDemoNews() {
        return {
            articles: [
                {
                    title: 'VN-Index tăng nhẹ phiên đầu tuần, thanh khoản cải thiện',
                    source: 'cafef_stock',
                    summary: 'Thị trường chứng khoán khởi đầu tuần giao dịch tích cực...',
                    published_at: new Date().toISOString(),
                    sentiment: { score: 0.35, label: 'tích cực', reasoning: 'Thị trường có tín hiệu phục hồi' },
                    related_symbols: ['VNINDEX'],
                },
                {
                    title: 'FPT báo lãi quý tăng 25% nhờ mảng AI và chuyển đổi số',
                    source: 'cafef_enterprise',
                    summary: 'Tập đoàn FPT ghi nhận kết quả kinh doanh ấn tượng...',
                    published_at: new Date(Date.now() - 3600000).toISOString(),
                    sentiment: { score: 0.72, label: 'rất tích cực', reasoning: 'Kết quả KQ vượt kỳ vọng' },
                    related_symbols: ['FPT'],
                },
                {
                    title: 'Khối ngoại bán ròng phiên thứ 5 liên tiếp trên HOSE',
                    source: 'cafef_market',
                    summary: 'Nhà đầu tư nước ngoài tiếp tục rút vốn...',
                    published_at: new Date(Date.now() - 7200000).toISOString(),
                    sentiment: { score: -0.45, label: 'tiêu cực', reasoning: 'Áp lực bán ròng kéo dài' },
                    related_symbols: ['VNINDEX', 'VCB', 'HPG'],
                },
                {
                    title: 'Ngân hàng Nhà nước giữ nguyên lãi suất điều hành',
                    source: 'cafef_macro',
                    summary: 'NHNN quyết định giữ nguyên các mức lãi suất...',
                    published_at: new Date(Date.now() - 14400000).toISOString(),
                    sentiment: { score: 0.1, label: 'trung tính', reasoning: 'Chính sách ổn định, không bất ngờ' },
                    related_symbols: ['VCB', 'BID', 'CTG', 'TCB'],
                },
                {
                    title: 'Hòa Phát: Sản lượng thép tháng 2 giảm 8% do nhu cầu yếu',
                    source: 'cafef_enterprise',
                    summary: 'Tập đoàn Hòa Phát công bố sản lượng tháng 2...',
                    published_at: new Date(Date.now() - 28800000).toISOString(),
                    sentiment: { score: -0.3, label: 'tiêu cực', reasoning: 'Sản lượng sụt giảm đáng kể' },
                    related_symbols: ['HPG'],
                },
            ],
            total: 5,
        };
    }

    getDemoAgentResult() {
        return {
            status: 'completed',
            elapsed_seconds: 3.2,
            insight: {
                title: '📊 Báo cáo rủi ro hàng ngày — Riskism AI',
                risk_level: 'medium',
                summary: 'Danh mục đang ở mức rủi ro TRUNG BÌNH. HPG có biến động cao cần theo dõi. VCB ổn định.',
                key_findings: [
                    'VN-Index giao dịch trong biên độ hẹp, thanh khoản TB 20 phiên',
                    'HPG có beta 1.45 — biến động mạnh hơn thị trường 45%',
                    'FPT có Sharpe ratio tốt (0.95) — hiệu quả sinh lời tốt so với rủi ro',
                    'Tỷ trọng ngành Banking chiếm 45% — khá tập trung',
                ],
                risk_factors: [
                    'Khối ngoại bán ròng liên tục gây áp lực',
                    'HPG max drawdown 28% — rủi ro sụt giảm đáng kể',
                    'Danh mục chỉ có 3 mã, HHI = 0.38 (tập trung cao)',
                ],
                action_items: [
                    'Cân nhắc giảm tỷ trọng HPG nếu biến động tiếp tục tăng',
                    'Xem xét thêm mã ngành Consumer (VNM) để đa dạng hóa',
                    'Giữ tỷ trọng tiền mặt 15-20% khi volatility regime = normal',
                ],
                confidence_score: 0.72,
                saved_at: new Date().toISOString(),
            },
            prediction: {
                prediction: 'đi ngang có rủi ro giảm nhẹ',
                confidence: 0.65,
                reasoning: 'Thanh khoản thấp, khối ngoại bán ròng, nhưng nhóm banking hỗ trợ.',
                key_risks: ['Khối ngoại bán ròng', 'Thanh khoản giảm'],
                watch_symbols: ['HPG', 'VCB'],
            },
            risk_metrics: {
                VCB: { risk_score: 35, var_95: -0.022, cvar_95: -0.031, beta: 0.85, sharpe_ratio: 1.2, sortino_ratio: 1.5, max_drawdown: 0.12, volatility: 0.22 },
                FPT: { risk_score: 42, var_95: -0.028, cvar_95: -0.038, beta: 1.1, sharpe_ratio: 0.95, sortino_ratio: 1.1, max_drawdown: 0.18, volatility: 0.28 },
                HPG: { risk_score: 65, var_95: -0.042, cvar_95: -0.058, beta: 1.45, sharpe_ratio: 0.3, sortino_ratio: 0.35, max_drawdown: 0.28, volatility: 0.42 },
            },
            portfolio_metrics: {
                hhi: 0.38,
                effective_n: 2.63,
                diversification_score: 45,
                volatility_regime: 'normal',
                sector_exposure: { Banking: 0.45, Technology: 0.32, Industrial: 0.23 },
            },
            capital_advice: {
                capital_tier: 'small',
                max_positions: 3,
                position_size_pct: 33.33,
                warnings: [
                    '⚠️ VCB và HPG có tương quan cao. Danh mục chưa thực sự đa dạng hóa.',
                ],
                suggested_next_symbols: ['VNM', 'GAS', 'MWG'],
            },
            anomalies: [
                { type: 'volume_spike', symbol: 'HPG', severity: 'medium', description: '🔴 HPG: Khối lượng GD tăng đột biến (2.8σ so với TB 20 phiên).' },
            ],
            news_count: 15,
            execution_log: [
                { timestamp: new Date().toISOString(), step: 'START', message: '☀️ Starting morning analysis' },
                { timestamp: new Date().toISOString(), step: 'PERCEPTION', message: 'Getting portfolio for user 1' },
                { timestamp: new Date().toISOString(), step: 'PERCEPTION', message: 'Fetching market data: VCB, FPT, HPG' },
                { timestamp: new Date().toISOString(), step: 'PERCEPTION', message: 'Fetching news from CafeF RSS' },
                { timestamp: new Date().toISOString(), step: 'ANALYSIS', message: 'Scoring sentiment for 15 articles' },
                { timestamp: new Date().toISOString(), step: 'ANALYSIS', message: 'Calculating risk metrics' },
                { timestamp: new Date().toISOString(), step: 'ANALYSIS', message: 'Scanning for anomalies' },
                { timestamp: new Date().toISOString(), step: 'INSIGHT', message: 'Saving insight: Báo cáo rủi ro hàng ngày' },
                { timestamp: new Date().toISOString(), step: 'COMPLETE', message: '✅ Morning analysis completed in 3.2s' },
            ],
        };
    }
}

// Global instance
const api = new RiskismAPI();
