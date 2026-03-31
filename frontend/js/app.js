/**
 * Riskism — Main App Controller V3.1
 * Auto-loads all tabs with real data. No empty states.
 */
class RiskismApp {
    constructor() {
        this.currentTab = 'dashboard';
        this.agentResult = null;
        this.portfolioData = null; // Cached portfolio risk data
        this.tickerInterval = null;
        this.userId = this.normalizeUserId(localStorage.getItem('riskism_user_id'));
        this.username = localStorage.getItem('riskism_username') || null;
        this.API_TIMEOUT = 15000;
        this.firebaseEnabled = false;
        this.authMode = 'signin';
        this._isLoadingData = false;
        this._bootstrapped = false;
    }

    normalizeUserId(value) {
        if (value == null) return null;
        const normalized = String(value).trim();
        if (!normalized || normalized === 'null' || normalized === 'undefined') {
            return null;
        }
        const parsed = Number(normalized);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
    }

    isAuthenticated() {
        return Number.isFinite(Number(this.userId)) && Number(this.userId) > 0;
    }

    runSafely(label, fn) {
        try {
            return fn();
        } catch (err) {
            console.error(`[Bootstrap] ${label} failed:`, err);
            return null;
        }
    }

    runBackgroundTask(label, fn) {
        try {
            return Promise.resolve(fn()).catch(err => {
                console.error(`[Bootstrap] ${label} failed:`, err);
                return null;
            });
        } catch (err) {
            console.error(`[Bootstrap] ${label} failed:`, err);
            return Promise.resolve(null);
        }
    }

    async ensureExternalScript(key, src, isReady, timeoutMs = 8000) {
        if (typeof isReady === 'function' && isReady()) {
            return true;
        }

        window.__riskismScriptPromises = window.__riskismScriptPromises || {};
        if (window.__riskismScriptPromises[key]) {
            return window.__riskismScriptPromises[key];
        }

        window.__riskismScriptPromises[key] = new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[data-riskism-asset="${key}"]`);
            if (existing) {
                const timer = window.setTimeout(() => reject(new Error(`${key} load timed out`)), timeoutMs);
                existing.addEventListener('load', () => {
                    window.clearTimeout(timer);
                    resolve(true);
                }, { once: true });
                existing.addEventListener('error', () => {
                    window.clearTimeout(timer);
                    reject(new Error(`${key} failed to load`));
                }, { once: true });
                return;
            }

            const script = document.createElement('script');
            script.src = src;
            script.async = true;
            script.dataset.riskismAsset = key;

            const timer = window.setTimeout(() => {
                reject(new Error(`${key} load timed out`));
            }, timeoutMs);

            script.addEventListener('load', () => {
                window.clearTimeout(timer);
                if (typeof isReady === 'function' && !isReady()) {
                    reject(new Error(`${key} loaded but is not ready`));
                    return;
                }
                resolve(true);
            }, { once: true });

            script.addEventListener('error', () => {
                window.clearTimeout(timer);
                reject(new Error(`${key} failed to load`));
            }, { once: true });

            document.head.appendChild(script);
        });

        return window.__riskismScriptPromises[key];
    }

    async ensureChartLibrary() {
        if (typeof window.Chart !== 'undefined') {
            window.dispatchEvent(new Event('riskism:chartjs-ready'));
            return true;
        }

        await this.ensureExternalScript(
            'chartjs',
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
            () => typeof window.Chart !== 'undefined',
            8000
        );

        window.dispatchEvent(new Event('riskism:chartjs-ready'));
        if (this.portfolioData) {
            UI.renderPortfolio(this.portfolioData);
        }
        return true;
    }

    async ensureHtml2Canvas() {
        if (typeof window.html2canvas !== 'undefined') {
            return true;
        }

        await this.ensureExternalScript(
            'html2canvas',
            'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js',
            () => typeof window.html2canvas === 'function',
            8000
        );
        return true;
    }

    async ensureFirebaseSdk() {
        await this.ensureExternalScript(
            'firebase-app',
            'https://www.gstatic.com/firebasejs/10.12.5/firebase-app-compat.js',
            () => typeof window.firebase !== 'undefined',
            8000
        );
        await this.ensureExternalScript(
            'firebase-auth',
            'https://www.gstatic.com/firebasejs/10.12.5/firebase-auth-compat.js',
            () => typeof window.firebase?.auth === 'function',
            8000
        );
        return true;
    }

    async init() {
        this.bindAuth();
        this.runBackgroundTask('Firebase auth bootstrap', () => this.initFirebaseAuth());
        
        if (!this.isAuthenticated()) {
            this.showLoginModal();
            return;
        }
        
        this.hideLoginModal();
        this.finishInit();
    }

    finishInit() {
        const nameEl = document.getElementById('user-display-name');
        if (nameEl) nameEl.textContent = this.username || 'User';

        if (this._bootstrapped) {
            this.runBackgroundTask('Dashboard refresh', () => this.loadAllData());
            this.updateStatusBar('connected');
            UI.toast(`Welcome back, ${this.username}! 🚀`, 'success');
            return;
        }

        this._bootstrapped = true;
        this.runSafely('Bind navigation', () => this.bindNavigation());
        this.runSafely('Bind agent actions', () => this.bindAgentButton());
        this.runSafely('Bind news toggle', () => this.bindNewsToggle());
        this.runSafely('Bind news search', () => this.bindNewsSearch());
        this.runSafely('Bind risk selectors', () => this.bindRiskSelect());
        this.runSafely('Bind portfolio editor', () => this.bindPortfolioEditor());
        this.runSafely('Bind notifications', () => this.bindNotifications());
        this.runSafely('Bind logout', () => this.bindLogout());
        this.runSafely('Bind keyboard shortcuts', () => this.bindKeyboardShortcuts());
        this.runSafely('Start clock', () => this.startClock());
        this.updateStatusBar('connected');
        this.runBackgroundTask('Load market ticker', () => this.loadMarketTicker());
        this.runBackgroundTask('Chart.js bootstrap', async () => {
            await this.ensureChartLibrary();
            charts.drawAllSparklines(this.portfolioData?.metrics_history || null);
        });
        this.runSafely('Draw fallback sparklines', () => charts.drawAllSparklines(null));
        this.runBackgroundTask('Load dashboard data', () => this.loadAllData());
        this.runSafely('Init chatbot', () => UI.initChatbot());

        UI.toast(`Welcome back, ${this.username}! 🚀`, 'success');

        // Export Report button
        document.getElementById('btn-export-report')?.addEventListener('click', () => this.exportReport());
    }

    async initFirebaseAuth() {
        const googleBtn = document.getElementById('btn-login-google');
        const divider = document.getElementById('auth-divider');
        const note = document.getElementById('firebase-auth-note');

        try {
            const payload = await api.getFirebaseConfig();
            const wantsFirebase = Boolean(payload?.enabled && payload?.config && window.FirebaseAuthBridge);
            if (!wantsFirebase) {
                this.firebaseEnabled = false;
                [googleBtn, divider, note].forEach(el => el?.classList.add('hidden'));
                return;
            }

            await this.ensureFirebaseSdk();
            const enabled = Boolean(window.FirebaseAuthBridge.init(payload.config));
            this.firebaseEnabled = enabled;
            [googleBtn, divider, note].forEach(el => el?.classList.toggle('hidden', !enabled));
            if (note) {
                note.textContent = enabled
                    ? 'Google sign-in is available.'
                    : '';
            }
        } catch (err) {
            console.warn('[Firebase] Config bootstrap failed:', err);
            this.firebaseEnabled = false;
            [googleBtn, divider, note].forEach(el => el?.classList.add('hidden'));
        }
    }

    completeLoginSession(res) {
        if (!res || !res.user_id) return false;

        this.userId = this.normalizeUserId(res.user_id);
        this.username = res.display_name || res.username;
        localStorage.setItem('riskism_user_id', String(this.userId));
        localStorage.setItem('riskism_username', this.username);
        localStorage.setItem('riskism_auth_provider', res.auth_provider || 'local');
        this.hideLoginModal();
        this.finishInit();
        return true;
    }

    setAuthMode(mode = 'signin') {
        this.authMode = mode === 'signup' ? 'signup' : 'signin';
        const isSignup = this.authMode === 'signup';

        document.querySelectorAll('.auth-mode-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.authMode === this.authMode);
        });

        const kicker = document.getElementById('auth-form-kicker');
        const title = document.getElementById('auth-form-title');
        const copy = document.getElementById('auth-form-copy');
        const note = document.getElementById('auth-inline-note');
        const submit = document.getElementById('btn-login');
        const switchCopy = document.getElementById('auth-switch-copy');
        const switchBtn = document.getElementById('auth-switch-btn');
        const confirmGroup = document.getElementById('auth-confirm-group');
        const passwordInput = document.getElementById('login-password');
        const confirmInput = document.getElementById('login-password-confirm');

        if (kicker) kicker.textContent = isSignup ? 'Get started' : 'Welcome back';
        if (title) title.textContent = isSignup ? 'Create your Riskism account' : 'Sign in to Riskism';
        if (copy) copy.textContent = isSignup
            ? 'Create a username and password to start with a fresh workspace.'
            : 'Use your username and password to access your workspace.';
        if (note) note.textContent = isSignup
            ? 'Choose a password with at least 8 characters.'
            : 'Use the account you already created on this device.';
        if (submit) submit.textContent = isSignup ? 'Create account' : 'Sign in';
        if (switchCopy) switchCopy.textContent = isSignup ? 'Already have an account?' : 'New here?';
        if (switchBtn) switchBtn.textContent = isSignup ? 'Sign in' : 'Create an account';
        if (confirmGroup) confirmGroup.classList.toggle('hidden', !isSignup);
        if (passwordInput) {
            passwordInput.autocomplete = isSignup ? 'new-password' : 'current-password';
        }
        if (confirmInput && !isSignup) {
            confirmInput.value = '';
        }
    }

    showLoginModal() {
    this.setAuthMode('signin');
    const u = document.getElementById('login-username');
    const p = document.getElementById('login-password');
    const c = document.getElementById('login-password-confirm');
    if (u) u.value = '';
    if (p) p.value = '';
    if (c) c.value = '';
    document.getElementById('modal-login')?.classList.add('active');
    document.body.classList.add('auth-active');
    window.setTimeout(() => {
        document.getElementById('login-username')?.focus();
    }, 80);
}

    hideLoginModal() {
        document.getElementById('modal-login')?.classList.remove('active');
        document.body.classList.remove('auth-active');
    }

    async exportReport() {
        const reportEl = document.getElementById('card-report');
        if (!reportEl) return;
        UI.toast('Generating export...', 'info');
        try {
            await this.ensureHtml2Canvas();
            const canvas = await html2canvas(reportEl, {
                backgroundColor: '#ffffff',
                scale: 2,
                useCORS: true,
            });
            const link = document.createElement('a');
            link.download = `riskism_report_${new Date().toISOString().slice(0,10)}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
            UI.toast('Report exported!', 'success');
        } catch (e) {
            UI.toast('Export failed', 'error');
            console.error('[Export]', e);
        }
    }

    // ─── Auth ────────────────────────────────────
    bindAuth() {
        const btn = document.getElementById('btn-login');
        const usernameInput = document.getElementById('login-username');
        const passwordInput = document.getElementById('login-password');
        const confirmInput = document.getElementById('login-password-confirm');
        const googleBtn = document.getElementById('btn-login-google');
        const switchBtn = document.getElementById('auth-switch-btn');
        const modeButtons = document.querySelectorAll('.auth-mode-btn');
        if (!btn || !usernameInput || !passwordInput || !switchBtn) return;

        this.setAuthMode(this.authMode);

        const setLoadingState = (loading, label = '') => {
            btn.disabled = loading;
            if (googleBtn) googleBtn.disabled = loading;
            if (loading && label) {
                btn.textContent = label;
                return;
            }
            this.setAuthMode(this.authMode);
        };

        const submitAuth = async () => {
            const username = usernameInput.value.trim().toLowerCase();
            const password = passwordInput.value;
            const confirmPassword = confirmInput?.value || '';

            if (!username) {
                UI.toast('Enter your username.', 'error'); return;
            }
            if (!password) {
                UI.toast('Enter your password.', 'error'); return;
            }
            if (this.authMode === 'signup') {
                if (password.length < 8) {
                    UI.toast('Use at least 8 characters for your password.', 'error'); return;
                }
                if (password !== confirmPassword) {
                    UI.toast('Passwords do not match.', 'error'); return;
                }
            }

            setLoadingState(true, this.authMode === 'signup' ? 'Creating account...' : 'Signing in...');
            try {
                const result = this.authMode === 'signup'
                    ? await api.signup(username, password)
                    : await api.login(username, password);

                if (!result?.ok) {
                    UI.toast(result?.error || 'Authentication failed.', 'error');
                    return;
                }
                if (!this.completeLoginSession(result.data)) {
                    UI.toast('Authentication failed. Please try again.', 'error');
                    return;
                }
                if (this.authMode === 'signup') {
                    UI.toast('Account created. Welcome to Riskism.', 'success');
                }
            } catch (e) {
                UI.toast('Server error. Please try again shortly.', 'error');
            } finally {
                setLoadingState(false);
            }
        };

        btn.addEventListener('click', submitAuth);
        [usernameInput, passwordInput, confirmInput].forEach(input => {
            input?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    submitAuth();
                }
            });
        });
        modeButtons.forEach(modeBtn => {
            modeBtn.addEventListener('click', () => this.setAuthMode(modeBtn.dataset.authMode));
        });
        switchBtn.addEventListener('click', () => {
            this.setAuthMode(this.authMode === 'signup' ? 'signin' : 'signup');
        });

        if (googleBtn) {
            googleBtn.addEventListener('click', async () => {
                if (!this.firebaseEnabled || !window.FirebaseAuthBridge?.enabled) {
                    UI.toast('Google sign-in is not configured on the backend.', 'info');
                    return;
                }

                googleBtn.textContent = 'Opening Google...';
                googleBtn.disabled = true;
                try {
                    const firebaseUser = await window.FirebaseAuthBridge.signInWithGoogle();
                    const result = await api.loginWithFirebase(
                        firebaseUser.idToken,
                        firebaseUser.displayName || firebaseUser.email || usernameInput.value.trim()
                    );
                    if (!result?.ok) {
                        UI.toast(result?.error || 'Google sign-in failed.', 'error');
                    } else if (!this.completeLoginSession(result.data)) {
                        UI.toast('Firebase login error, please try again.', 'error');
                    }
                } catch (e) {
                    const message = String(e?.message || '');
                    if (message.includes('popup') || message.includes('cancel')) {
                        UI.toast('Google sign-in was cancelled.', 'info');
                    } else {
                        console.error('[Firebase Login]', e);
                        UI.toast('Google sign-in failed.', 'error');
                    }
                } finally {
                    googleBtn.textContent = 'Continue with Google';
                    googleBtn.disabled = false;
                }
            });
        }
    }

    // ─── Navigation ──────────────────────────────
    bindNavigation() {
        document.querySelectorAll('.sub-nav-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });
    }

    switchTab(tab) {
        this.currentTab = tab;
        document.querySelectorAll('.sub-nav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.tab === tab));

        // Re-render tab data if we have it
        if (tab === 'portfolio' && this.portfolioData) {
            UI.renderPortfolio(this.portfolioData);
        }
        if (tab === 'risk-analysis' && this.portfolioData) {
            UI.renderRiskAnalysis(this.portfolioData.stock_risks, this.portfolioData.anomalies || []);
            UI.renderRiskNetworkMap(
                this.portfolioData.correlation_matrix || {},
                this.portfolioData.stock_risks || {},
                this.portfolioData.correlation_warnings || []
            );
        }
    }

    // ─── Notifications ──────────────────────────────
    bindNotifications() {
        const btn = document.getElementById('btn-notify');
        const panel = document.getElementById('notify-panel');
        if (!btn || !panel) return;

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            panel.classList.toggle('open');
            const dot = document.getElementById('notify-dot');
            if (dot) dot.classList.remove('active');
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('#notify-wrapper')) {
                panel.classList.remove('open');
            }
        });
    }

    // ─── Logout ─────────────────────────────────────
    bindLogout() {
        const btn = document.getElementById('btn-logout');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            await window.FirebaseAuthBridge?.signOut?.();
            localStorage.removeItem('riskism_user_id');
            localStorage.removeItem('riskism_username');
            localStorage.removeItem('riskism_auth_provider');
            this.userId = null;
            this.username = null;
            this._isLoadingData = false;
            this.showLoginModal();
            UI.toast('Logged out successfully', 'info');
        });
    }

    // ─── Agent Trigger ───────────────────────────
    bindAgentButton() {
        document.getElementById('btn-run-agent')?.addEventListener('click', () => this.runAgent('morning'));
        document.getElementById('btn-run-agent-dash')?.addEventListener('click', () => this.runAgent('morning'));
        document.getElementById('btn-run-reflection')?.addEventListener('click', () => this.runAgent('afternoon'));
    }

    async runAgent(type = 'morning') {
        UI.showLoading(`🤖 Riskism AI is running ${type} analysis...`);
        try {
            const result = await this._fetchWithTimeout(
                api.triggerAgent(this.userId, type),
                120000
            );
            this.agentResult = result;
            if (result) {
                this.applyAgentResult(result);
                const elapsed = result.elapsed_seconds ? ` in ${result.elapsed_seconds}s` : '';
                UI.toast(`✅ AI Agent phân tích xong${elapsed}!`, 'success');
            }
        } catch (e) {
            console.error('[Agent] Error:', e);
            if (e.message && e.message.includes('429')) {
                UI.toast('⏳ Rate limit reached. Please wait ~60s before running again.', 'error');
            } else {
                UI.toast('❌ Agent error: ' + (e.message || 'timeout'), 'error');
            }
        } finally {
            UI.hideLoading();
        }
    }

    applyAgentResult(r) {
        // Dashboard: Update core metrics + sparklines
        if (r.portfolio_risk) {
            UI.updateMetrics(r.portfolio_risk, r.metrics_history);
        }
        if (r.insight) UI.renderAI(r.insight);
        if (r.anomalies && r.anomalies.length) {
            UI.toast(`⚡ ${r.anomalies.length} anomalies detected`, 'info');
            UI.pushNotifications(r.anomalies);
        }

        // Update holdings with agent's data
        const portfolio = r.portfolio || (this.portfolioData ? this.portfolioData.portfolio : api.getDemoPortfolio());
        const stockRisks = r.risk_metrics || r.stock_risks || {};
        UI.updateHoldings(portfolio.holdings, stockRisks);
        window._cachedPortfolioSymbols = (portfolio.holdings || []).map(h => h.symbol);

        // Risk Analysis (always populate)
        UI.renderRiskAnalysis(stockRisks, r.anomalies || []);
        UI.renderRiskNetworkMap(
            r.correlation_matrix || this.portfolioData?.correlation_matrix || {},
            stockRisks,
            r.correlation_warnings || this.portfolioData?.correlation_warnings || []
        );

        // Reports
        if (r.insight) UI.renderReport(r.insight);
        if (r.reflection) {
            UI.renderReflection(r.reflection);
            UI.renderPredictionTimeline(r.reflection);
        }
        if (r.execution_log) UI.renderAgentLog(r.execution_log);

        // Portfolio
        if (r.portfolio_metrics && r.capital_advice) {
            const previous = this.portfolioData || {};
            const pData = {
                ...previous,
                portfolio: portfolio,
                portfolio_metrics: r.portfolio_metrics,
                capital_advice: r.capital_advice,
                stock_risks: stockRisks,
                anomalies: r.anomalies || previous.anomalies || [],
                correlation_matrix: r.correlation_matrix || previous.correlation_matrix || {},
                correlation_warnings: r.correlation_warnings || previous.correlation_warnings || [],
                portfolio_risk: r.portfolio_risk || previous.portfolio_risk,
                metrics_history: r.metrics_history || previous.metrics_history,
            };
            this.portfolioData = pData;
            UI.renderPortfolio(pData);
            UI.setNotifications(pData.anomalies || []);
            this.refreshNewsForCurrentPortfolio();
        }
    }

    // ─── News Toggle ─────────────────────────────
    bindNewsToggle() {
        document.querySelectorAll('#news-toggle .toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#news-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const tab = btn.dataset.filter || btn.textContent.trim().toLowerCase();
                const articles = (window._cachedNews && window._cachedNews.length > 0)
                    ? window._cachedNews
                    : [];
                if (articles.length === 0) {
                    UI.renderNewsEmpty('Chưa có tin tức realtime phù hợp.');
                    return;
                }
                UI.filterAndRenderNews(articles, tab);
            });
        });
    }

    // ─── Risk Analysis Select ────────────────────
    bindRiskSelect() {
        document.getElementById('ra-symbol-select')?.addEventListener('change', (e) => {
            const risks = (this.portfolioData && this.portfolioData.stock_risks) ||
                          (this.agentResult && (this.agentResult.risk_metrics || this.agentResult.stock_risks));
            if (risks) {
                UI.renderStockDetail(e.target.value, risks);
                UI.renderRiskNetworkMap(
                    this.portfolioData?.correlation_matrix || this.agentResult?.correlation_matrix || {},
                    risks,
                    this.portfolioData?.correlation_warnings || this.agentResult?.correlation_warnings || []
                );
            }
        });

        document.querySelectorAll('#card-heatmap .period-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#card-heatmap .period-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    }

    // ─── Portfolio Editor ────────────────────────
    bindPortfolioEditor() {
        const btnEdit = document.getElementById('btn-edit-pf');
        const modal = document.getElementById('modal-portfolio');
        const btnAdd = document.getElementById('btn-add-holding');
        const btnSave = document.getElementById('btn-save-portfolio');
        const editor = document.getElementById('holdings-editor');
        const inputCap = document.getElementById('edit-pf-capital');

        if (!btnEdit || !modal) return;

        const formatAutoPrice = (price) => {
            const value = Number(price);
            if (!Number.isFinite(value) || value <= 0) return '';
            return Math.round(value).toLocaleString('en-US');
        };

        const buildEditorRow = (holding = {}, index = 0) => {
            const autoPrice = holding.latest_price || holding.avg_price || '';
            return `
                <div class="editor-row" data-idx="${index}" style="display:grid; grid-template-columns:minmax(0, 1.6fr) minmax(110px, 0.8fr) minmax(130px, 1fr) auto; gap:8px; margin-bottom:10px; align-items:start;">
                    <div style="display:flex; flex-direction:column; gap:4px; min-width:0;">
                        <input type="text" class="form-input pf-sym" list="pf-suggestions-${index}" placeholder="Ticker" value="${holding.symbol || ''}" style="width:100%" maxlength="10" autocomplete="off">
                        <datalist id="pf-suggestions-${index}"></datalist>
                        <div class="pf-sym-meta" style="font-size:0.72rem; color:var(--text-muted); min-height:16px;">${holding.organ_name || ''}</div>
                    </div>
                    <input type="number" class="form-input pf-qty" placeholder="Quantity" value="${holding.quantity || 0}" style="width:100%">
                    <input type="text" class="form-input pf-prc mono" placeholder="Auto price today" value="${formatAutoPrice(autoPrice)}" style="width:100%" readonly>
                    <button class="btn-outline btn-rm-row" style="padding: 4px 8px;">✕</button>
                </div>
            `;
        };

        const attachEditorRowBehavior = (row) => {
            const symInput = row.querySelector('.pf-sym');
            const qtyInput = row.querySelector('.pf-qty');
            const priceInput = row.querySelector('.pf-prc');
            const metaEl = row.querySelector('.pf-sym-meta');
            const listEl = row.querySelector('datalist');
            const removeBtn = row.querySelector('.btn-rm-row');
            let searchTimer = null;
            let priceTimer = null;

            const setAutoPrice = async (symbol) => {
                const sym = (symbol || '').trim().toUpperCase();
                symInput.value = sym;

                if (!sym) {
                    priceInput.value = '';
                    priceInput.dataset.price = '';
                    return;
                }

                if (sym.length < 3) {
                    priceInput.value = '';
                    priceInput.dataset.price = '';
                    return;
                }

                const token = `${Date.now()}-${Math.random()}`;
                row.dataset.priceToken = token;
                priceInput.value = 'Loading...';
                priceInput.dataset.price = '';

                const quote = await api.getSymbolReferencePrice(sym);
                if (row.dataset.priceToken !== token) return;

                if (quote && Number.isFinite(Number(quote.price))) {
                    const normalized = Math.round(Number(quote.price));
                    priceInput.value = formatAutoPrice(normalized);
                    priceInput.dataset.price = String(normalized);
                } else {
                    priceInput.value = 'N/A';
                    priceInput.dataset.price = '';
                }
            };

            const setSuggestions = async () => {
                const q = (symInput.value || '').trim().toUpperCase();
                symInput.value = q;

                if (!q) {
                    listEl.innerHTML = '';
                    metaEl.textContent = '';
                    priceInput.value = '';
                    priceInput.dataset.price = '';
                    return;
                }

                const items = await api.searchSymbols(q, 8);
                if ((symInput.value || '').trim().toUpperCase() !== q) return;

                listEl.innerHTML = items.map(item =>
                    `<option value="${item.symbol}" label="${item.organ_name || ''}"></option>`
                ).join('');

                const exact = items.find(item => item.symbol === q);
                if (exact) {
                    metaEl.textContent = exact.organ_name || '';
                } else if (items.length > 0) {
                    metaEl.textContent = `Gợi ý: ${items.map(item => item.symbol).join(', ')}`;
                } else {
                    metaEl.textContent = 'Không tìm thấy mã phù hợp';
                }
            };

            symInput.addEventListener('input', () => {
                clearTimeout(searchTimer);
                clearTimeout(priceTimer);
                searchTimer = setTimeout(() => { setSuggestions(); }, 160);
                priceTimer = setTimeout(() => { setAutoPrice(symInput.value); }, 240);
            });

            symInput.addEventListener('change', () => {
                setSuggestions();
                setAutoPrice(symInput.value);
            });

            qtyInput.addEventListener('input', () => {
                if ((parseInt(qtyInput.value, 10) || 0) < 0) {
                    qtyInput.value = 0;
                }
            });

            removeBtn.addEventListener('click', () => row.remove());

            if (symInput.value) {
                setSuggestions();
                setAutoPrice(symInput.value);
            }
        };

        const renderEditorRows = (holdings) => {
            editor.innerHTML = holdings.map((h, i) => buildEditorRow(h, i)).join('');
            editor.querySelectorAll('.editor-row').forEach(attachEditorRowBehavior);
        };

        btnEdit.addEventListener('click', () => {
            if (this.portfolioData && this.portfolioData.portfolio) {
                inputCap.value = this.portfolioData.portfolio.capital_amount || 0;
                renderEditorRows(this.portfolioData.portfolio.holdings || []);
            } else {
                inputCap.value = 0;
                renderEditorRows([]);
            }
            modal.classList.add('active');
        });

        btnAdd.addEventListener('click', () => {
            const row = document.createElement('div');
            row.className = 'editor-row';
            row.innerHTML = buildEditorRow({}, Date.now());
            editor.appendChild(row);
            attachEditorRowBehavior(row);
        });

        btnSave.addEventListener('click', async () => {
            const cap = parseFloat(inputCap.value) || 0;
            const rows = editor.querySelectorAll('.editor-row');
            const holdingsMap = new Map();
            let saveSucceeded = false;
            rows.forEach(r => {
                const sym = r.querySelector('.pf-sym').value.trim().toUpperCase();
                const qty = parseInt(r.querySelector('.pf-qty').value) || 0;
                const priceInput = r.querySelector('.pf-prc');
                const rawPrice = (priceInput?.dataset?.price || priceInput?.value || '').replace(/,/g, '').trim();
                const avgPrice = Number(rawPrice);
                if (sym && qty > 0) {
                    const existing = holdingsMap.get(sym) || { symbol: sym, quantity: 0, avg_price: null };
                    existing.quantity += qty;
                    if (Number.isFinite(avgPrice) && avgPrice > 0) {
                        existing.avg_price = avgPrice;
                    }
                    holdingsMap.set(sym, existing);
                }
            });
            const holdings = Array.from(holdingsMap.values()).map(item => ({
                symbol: item.symbol,
                quantity: item.quantity,
                avg_price: item.avg_price,
            }));

            btnSave.textContent = 'Saving...';
            btnSave.disabled = true;
            try {
                const res = await api.updatePortfolio(this.userId, cap, holdings);
                if (!res || res.status !== 'success') {
                    UI.toast(res?.detail || 'Failed to save portfolio', 'error');
                    return;
                }

                saveSucceeded = true;
                UI.toast('Portfolio updated successfully', 'success');
                modal.classList.remove('active');

                const port = await this._fetchWithTimeout(
                    api.getPortfolioRisk(this.userId),
                    this.API_TIMEOUT
                );
                if (port) {
                    this.applyPortfolioSnapshot(port);
                    return;
                }

                this.loadAllData();
                UI.toast('Portfolio đã lưu. Đang đồng bộ lại dữ liệu...', 'info');
            } catch (e) {
                if (saveSucceeded) {
                    console.warn('[Portfolio] Saved but refresh failed:', e?.message || e);
                    this.loadAllData();
                    UI.toast('Portfolio đã lưu. Đang đồng bộ lại dữ liệu...', 'info');
                } else {
                    UI.toast('Server error while saving portfolio', 'error');
                }
            } finally {
                btnSave.textContent = 'Save Portfolio & Reload';
                btnSave.disabled = false;
            }
        });
    }

    getActiveNewsFilter() {
        return document.querySelector('#news-toggle .toggle-btn.active')?.dataset.filter || 'market';
    }

    refreshNewsForCurrentPortfolio() {
        if (!window._cachedNews || window._cachedNews.length === 0) {
            UI.renderNewsEmpty('Chưa có tin tức realtime phù hợp.');
            return;
        }
        UI.filterAndRenderNews(window._cachedNews, this.getActiveNewsFilter());
    }

    applyPortfolioSnapshot(port) {
        this.portfolioData = port;

        const holdings = port?.portfolio?.holdings || [];
        const stockRisks = port?.stock_risks || {};
        const anomalies = port?.anomalies || [];
        const hasHoldings = holdings.length > 0;
        const fallbackMetrics = {
            var_95: 0,
            sharpe_ratio: 0,
            max_drawdown: 0,
            beta: 0,
        };
        const flatHistory = {
            var_95: [0, 0],
            sharpe: [0, 0],
            drawdown: [0, 0],
            beta: [0, 0],
        };

        window._cachedPortfolioSymbols = holdings.map(h => h.symbol);

        UI.updateHoldings(holdings, stockRisks);
        UI.updateMetrics(port?.portfolio_risk || fallbackMetrics, port?.metrics_history || flatHistory);

        if (hasHoldings) {
            UI.updateAIFromRisk(stockRisks, port?.portfolio_risk || fallbackMetrics);
        } else {
            UI.resetAI();
        }

        UI.renderRiskAnalysis(stockRisks, anomalies);
        UI.renderRiskNetworkMap(port?.correlation_matrix || {}, stockRisks, port?.correlation_warnings || []);
        UI.renderPortfolio(port);
        UI.setNotifications(anomalies);
        this.refreshNewsForCurrentPortfolio();
    }

    // ─── Data Loaders ────────────────────────────
    async loadAllData() {
        if (!this.isAuthenticated() || this._isLoadingData) {
            return;
        }
        this._isLoadingData = true;
        this.loadMarketTicker();

        // Load news
        const newsPromise = this._fetchWithTimeout(api.getNews(8), this.API_TIMEOUT)
            .then(news => {
                window._cachedNews = news?.articles || [];
                this.refreshNewsForCurrentPortfolio();
            })
            .catch(e => {
                console.warn('[Dashboard] News load failed:', e.message);
                window._cachedNews = [];
                UI.renderNewsEmpty('Live news is temporarily unavailable.');
            });

        // Load portfolio risk (contains ALL real data)
        try {
            const port = await this._fetchWithTimeout(
                api.getPortfolioRisk(this.userId),
                this.API_TIMEOUT
            );
            if (port) {
                this.applyPortfolioSnapshot(port);
            }
        } catch (e) {
            console.warn('[Dashboard] Portfolio load failed:', e.message);
        } finally {
            await newsPromise.catch(() => null);
            this._isLoadingData = false;
        }
    }

    // ─── Utilities ───────────────────────────────

    async loadMarketTicker() {
        try {
            const snapshot = await this._fetchWithTimeout(
                api.getMarketIndexSnapshot(),
                this.API_TIMEOUT
            );

            if (snapshot && Number.isFinite(Number(snapshot.change_pct))) {
                UI.updateTicker({
                    VNINDEX: {
                        display_name: 'VN-INDEX',
                        change_pct: Number(snapshot.change_pct),
                    },
                });
                return;
            }
        } catch (e) {
            console.warn('[Dashboard] VN-Index load failed:', e.message);
        }

        UI.updateTicker({
            VNINDEX: {
                display_name: 'VN-INDEX',
                change_pct: null,
            },
        });
    }

    _fetchWithTimeout(promise, ms) {
        return Promise.race([
            promise,
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error(`Request timed out after ${ms}ms`)), ms)
            ),
        ]);
    }

    startClock() {
        const update = () => {
            const now = new Date();
            const el = document.getElementById('clock');
            if (el) el.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            // Market status indicator
            this.updateMarketStatus(now);
        };
        update();
        setInterval(update, 1000);

        // Realtime Polling (Every 30s)
        setInterval(() => {
            if (!this.isAuthenticated()) return;
            this.loadAllData();
            this.updateStatusBar('connected');
        }, 30000);
    }

    updateMarketStatus(now) {
        const el = document.getElementById('market-status');
        if (!el) return;
        const day = now.getDay(); // 0=Sun, 6=Sat
        const h = now.getHours();
        const m = now.getMinutes();
        const mins = h * 60 + m;
        const isWeekday = day >= 1 && day <= 5;
        const isOpen = isWeekday && mins >= 540 && mins < 900; // 9:00 - 15:00
        el.textContent = isOpen ? '🟢 OPEN' : '🔴 CLOSED';
        el.className = `market-status ${isOpen ? 'open' : 'closed'}`;
    }

    // ─── Keyboard Shortcuts ──────────────────
    bindKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ignore when typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            // Ctrl+R or Cmd+R = Run AI Agent
            if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
                e.preventDefault();
                this.runAgent('morning');
            }
            // Number keys 1-4 = Switch tabs
            const tabMap = { '1': 'dashboard', '2': 'risk-analysis', '3': 'portfolio', '4': 'reports' };
            if (tabMap[e.key] && !e.ctrlKey && !e.metaKey) {
                this.switchTab(tabMap[e.key]);
            }
        });
    }

    // ─── News Search ───────────────────────
    bindNewsSearch() {
        const input = document.getElementById('news-search');
        if (!input) return;
        input.addEventListener('input', () => {
            const q = input.value.toLowerCase().trim();
            const items = document.querySelectorAll('#news-feed .news-item');
            items.forEach(item => {
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(q) ? '' : 'none';
            });
        });
    }

    // ─── Status Bar ───────────────────────
    updateStatusBar(status) {
        const dot = document.getElementById('status-dot');
        const connEl = document.getElementById('status-connection');
        const updateEl = document.getElementById('status-last-update');
        if (dot) {
            dot.className = `status-dot ${status}`;
        }
        if (connEl) {
            const labels = { connected: 'API Connected', disconnected: 'Disconnected', demo: 'Demo Mode' };
            connEl.textContent = labels[status] || status;
        }
        if (updateEl) {
            updateEl.textContent = `Last update: ${new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}`;
        }
    }
}

const app = new RiskismApp();
window.app = app;
document.addEventListener('DOMContentLoaded', () => {
    Promise.resolve(app.init()).catch(err => {
        console.error('[App] Initialization failed:', err);
        app.updateStatusBar('disconnected');
        UI.toast('App loaded with limited features. Refresh to retry.', 'error');
    });
});
