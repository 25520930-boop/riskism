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

class RiskismAPIError extends Error {
    constructor(message, status = 0, detail = '', endpoint = '') {
        super(message);
        this.name = 'RiskismAPIError';
        this.status = status;
        this.detail = detail || message;
        this.endpoint = endpoint;
    }
}

class RiskismAPI {
    constructor() {
        this.ws = null;
        this.wsReconnectTimeout = null;
        this.onPriceUpdate = null;
        this.onAgentResult = null;
        this.onConnectionChange = null;
        this.REQUEST_TIMEOUT = 8000;
        this.accessToken = window.localStorage.getItem('riskism_access_token') || '';
    }

    hasAccessToken() {
        return Boolean(this.accessToken);
    }

    setAccessToken(token) {
        this.accessToken = token || '';
        if (this.accessToken) {
            window.localStorage.setItem('riskism_access_token', this.accessToken);
        } else {
            window.localStorage.removeItem('riskism_access_token');
        }
    }

    clearAccessToken() {
        this.setAccessToken('');
    }

    // ─── HTTP Methods ────────────────────────────────────

    async fetchWithTimeout(url, options = {}, timeoutMs = this.REQUEST_TIMEOUT) {
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
        const headers = new Headers(options.headers || {});

        if (this.accessToken && !headers.has('Authorization')) {
            headers.set('Authorization', `Bearer ${this.accessToken}`);
        }

        try {
            return await fetch(url, {
                ...options,
                headers,
                signal: controller.signal,
            });
        } finally {
            window.clearTimeout(timeoutId);
        }
    }

    _buildApiError(endpoint, status, payload, fallbackMessage = '') {
        const detail = payload?.detail || fallbackMessage || `HTTP ${status}`;
        return new RiskismAPIError(detail, status, detail, endpoint);
    }

    async requestJson(endpoint, options = {}, timeoutMs = this.REQUEST_TIMEOUT) {
        try {
            const res = await this.fetchWithTimeout(`${API_BASE}${endpoint}`, options, timeoutMs);
            const payload = await res.json().catch(() => null);
            if (res.status === 401) this.clearAccessToken();
            if (!res.ok) {
                throw this._buildApiError(endpoint, res.status, payload);
            }
            return payload;
        } catch (err) {
            if (err instanceof RiskismAPIError) {
                throw err;
            }
            if (err?.name === 'AbortError') {
                throw new RiskismAPIError('Request timed out.', 0, 'Request timed out.', endpoint);
            }
            throw new RiskismAPIError(
                err?.message || 'Network error. Please try again.',
                0,
                'Network error. Please try again.',
                endpoint,
            );
        }
    }

    async get(endpoint) {
        try {
            return await this.requestJson(endpoint);
        } catch (err) {
            console.warn(`[API] GET ${endpoint} failed:`, err.detail || err.message);
            return null;
        }
    }

    async post(endpoint, data) {
        try {
            return await this.requestJson(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
        } catch (err) {
            console.warn(`[API] POST ${endpoint} failed:`, err.detail || err.message);
            return null;
        }
    }

    async postAuth(endpoint, data) {
        try {
            const res = await this.fetchWithTimeout(`${API_BASE}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            const payload = await res.json().catch(() => null);
            if (!res.ok) {
                return {
                    ok: false,
                    status: res.status,
                    error: payload?.detail || `HTTP ${res.status}`,
                };
            }
            return { ok: true, status: res.status, data: payload };
        } catch (err) {
            console.warn(`[API] AUTH ${endpoint} failed:`, err.message);
            return {
                ok: false,
                status: 0,
                error: 'Network error. Please try again.',
            };
        }
    }

    // ─── Auth ────────────────────────────────────────────
    async login(username, password) {
        return await this.postAuth('/api/auth/login', { username, password });
    }

    async signup(username, password) {
        return await this.postAuth('/api/auth/signup', { username, password });
    }

    async getCurrentUser() {
        return await this.get('/api/auth/me');
    }

    async getFirebaseConfig() {
        return await this.get('/api/auth/firebase/config');
    }

    async loginWithFirebase(idToken, usernameHint = '') {
        return await this.postAuth('/api/auth/firebase/login', {
            id_token: idToken,
            username_hint: usernameHint,
        });
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

    async searchSymbols(query, limit = 8) {
        const q = (query || '').trim();
        if (!q) return [];
        const data = await this.get(`/api/market/symbols/search?q=${encodeURIComponent(q)}&limit=${limit}`);
        return data?.items || [];
    }

    async getSymbolReferencePrice(symbol) {
        const sym = (symbol || '').trim().toUpperCase();
        if (!sym) return null;

        const history = await this.get(`/api/market/${sym}?days=2`);
        const closes = history?.close || [];
        if (!Array.isArray(closes) || closes.length === 0) {
            const live = await this.getLatestPrice(sym);
            if (live && Number.isFinite(Number(live.price))) {
                return {
                    ...live,
                    symbol: sym,
                    price: Number(live.price),
                };
            }
            return null;
        }

        const latest = Number(closes[closes.length - 1]);
        if (!Number.isFinite(latest)) {
            return null;
        }

        return {
            symbol: sym,
            price: latest < 1000 ? latest * 1000 : latest,
            timestamp: new Date().toISOString(),
        };
    }

    async getMarketIndexSnapshot() {
        const live = await this.getLatestPrice('VNINDEX');
        if (live && Number.isFinite(Number(live.change_pct))) {
            return live;
        }

        const history = await this.get('/api/market/VNINDEX?days=2');
        const closes = history?.close || [];
        if (!Array.isArray(closes) || closes.length === 0) {
            return null;
        }

        const latest = Number(closes[closes.length - 1]);
        const previous = Number(closes[closes.length - 2] ?? closes[closes.length - 1]);
        if (!Number.isFinite(latest) || !Number.isFinite(previous)) {
            return null;
        }

        const change = latest - previous;
        return {
            symbol: 'VNINDEX',
            price: latest,
            previous_close: previous,
            change: Number(change.toFixed(2)),
            change_pct: previous > 0 ? Number(((change / previous) * 100).toFixed(2)) : 0,
            timestamp: new Date().toISOString(),
        };
    }

    // ─── Portfolio ───────────────────────────────────────

    async getPortfolio() {
        if (!this.hasAccessToken()) return null;
        return await this.requestJson('/api/portfolio');
    }

    async getPortfolioRisk() {
        if (!this.hasAccessToken()) return null;
        return await this.requestJson('/api/portfolio/risk');
    }

    async updatePortfolio(capital, holdings) {
        try {
            const res = await this.fetchWithTimeout(`${API_BASE}/api/portfolio/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    capital_amount: capital,
                    holdings: holdings
                }),
            });
            const data = await res.json().catch(() => null);
            if (res.status === 401) this.clearAccessToken();
            if (!res.ok) {
                return {
                    status: 'error',
                    detail: data?.detail || `HTTP ${res.status}`,
                };
            }
            return data;
        } catch (err) {
            const detail = err instanceof RiskismAPIError
                ? err.detail
                : (err?.message || 'Network error. Please try again.');
            console.warn('[API] POST /api/portfolio/update failed:', detail);
            return {
                status: 'error',
                detail,
            };
        }
    }

    // ─── Insights & News ─────────────────────────────────

    async getInsights() {
        return await this.requestJson('/api/insights');
    }

    async getNews(limit = 8) {
        const data = await this.get(`/api/news/latest?limit=${limit}`);
        return data || { articles: [], total: 0, fetched_at: new Date().toISOString() };
    }

    // ─── Agent ───────────────────────────────────────────

    async triggerAgent(type = 'morning', symbol = null) {
        return await this.requestJson('/api/agent/trigger', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analysis_type: type, symbol }),
        }, 120000);
    }

    async getAgentStatus() {
        return await this.requestJson('/api/agent/status');
    }

    async getPredictions() {
        return await this.requestJson('/api/predictions');
    }

    async getPredictionsHistory(limit = 10) {
        return await this.requestJson(`/api/predictions/history?limit=${limit}`);
    }

    async chatAssistant(message, history = [], appContext = {}) {
        return await this.requestJson('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
            message: message,
            history: history,
            app_context: appContext,
            }),
        });
    }

    // ─── WebSocket ───────────────────────────────────────

    connectWebSocket() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

        try {
            this.ws = new WebSocket(`${WS_BASE}/ws/prices`);

            this.ws.onopen = () => {
                console.log('[WS] Connected');
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
                console.warn('[WS] Connection error, realtime feed degraded');
                if (this.onConnectionChange) this.onConnectionChange('degraded');
            };

        } catch (err) {
            console.warn('[WS] Failed to connect:', err);
            if (this.onConnectionChange) this.onConnectionChange('degraded');
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
            portfolio_risk: {
                var_95: -0.031,
                cvar_95: -0.044,
                cvar_99: -0.058,
                adjusted_var_95: -0.055,
                adjusted_cvar_95: -0.076,
                sharpe_ratio: 0.92,
                max_drawdown: 0.142,
                beta: 1.08,
                beta_dimson: 1.14,
                liquidity_multiplier: 1.78,
                liquidity_profile: {
                    multiplier: 1.78,
                    effective_horizon_days: 3.9,
                    safe_adv_share: 0.2,
                    locked_capital_pct: 0.18,
                    worst_symbol: 'FPT',
                    positions: [
                        { symbol: 'FPT', weight: 0.32, liquidation_days: 2.4, liquidity_penalty: 1.19, locked_fraction: 0.27 },
                        { symbol: 'VCB', weight: 0.45, liquidation_days: 1.6, liquidity_penalty: 1.07, locked_fraction: 0.0 },
                    ],
                },
                stress_scenarios: { worst_1d: -0.034, worst_3d: -0.071, worst_5d: -0.096 },
                stress_scenarios_detail: [
                    { label: 'Worst 5D', horizon_days: 5, return: -0.096, start_date: '2026-03-11', end_date: '2026-03-17' },
                    { label: 'Worst 3D', horizon_days: 3, return: -0.071, start_date: '2026-03-12', end_date: '2026-03-17' },
                ],
                tail_risk_contributors: [
                    { symbol: 'HPG', contribution_pct: 0.44, driver: 'beta' },
                    { symbol: 'FPT', contribution_pct: 0.31, driver: 'liquidity' },
                    { symbol: 'VCB', contribution_pct: 0.25, driver: 'concentration' },
                ],
            },
            portfolio_metrics: {
                hhi: 0.38,
                effective_n: 2.63,
                sector_exposure: { Banking: 0.45, Technology: 0.32, Industrial: 0.23 },
                benchmark_sector_exposure: { Banking: 0.27, Technology: 0.1, Industrial: 0.17, 'Real Estate': 0.13, Consumer: 0.17, Energy: 0.07, Chemicals: 0.1 },
                sector_gap_vs_vn30: { Banking: 0.18, Technology: 0.22, Industrial: 0.06, Consumer: -0.17, 'Real Estate': -0.13, Energy: -0.07, Chemicals: -0.1 },
                max_sector_weight: 0.45,
                total_value: 19700000,
                diversification_score: 45,
                rolling_correlation_vn30: 0.74,
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
                VCB: { risk_score: 35, var_95: -0.022, cvar_95: -0.031, sharpe_ratio: 1.2, beta: 0.85, beta_dimson: 0.89 },
                FPT: { risk_score: 42, var_95: -0.028, cvar_95: -0.038, sharpe_ratio: 0.95, beta: 1.1, beta_dimson: 1.16 },
                HPG: { risk_score: 65, var_95: -0.042, cvar_95: -0.058, sharpe_ratio: 0.3, beta: 1.45, beta_dimson: 1.52 },
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
