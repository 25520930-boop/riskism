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
        this.userId = localStorage.getItem('riskism_user_id') || null;
        this.username = localStorage.getItem('riskism_username') || null;
        this.API_TIMEOUT = 15000;
    }

    async init() {
        this.bindAuth();
        
        if (!this.userId) {
            document.getElementById('modal-login').classList.add('active');
            return;
        }
        
        this.finishInit();
    }

    finishInit() {
        this.bindNavigation();
        this.bindAgentButton();
        this.bindNewsToggle();
        this.bindNewsSearch();
        this.bindRiskSelect();
        this.bindPortfolioEditor();
        this.bindNotifications();
        this.bindLogout();
        this.bindKeyboardShortcuts();
        this.startClock();
        this.startTickerDemo();

        // Show user identity
        const nameEl = document.getElementById('user-display-name');
        if (nameEl) nameEl.textContent = this.username || 'User';

        // Draw demo sparklines immediately
        charts.drawAllSparklines(null);

        // Load all data from backend (non-blocking)
        this.loadAllData();

        // Update status bar
        this.updateStatusBar('connected');

        UI.toast(`Welcome back, ${this.username}! 🚀`, 'success');

        // Export Report button
        document.getElementById('btn-export-report')?.addEventListener('click', () => this.exportReport());
    }

    async exportReport() {
        const reportEl = document.getElementById('card-report');
        if (!reportEl) return;
        if (typeof html2canvas === 'undefined') {
            UI.toast('Export library not loaded', 'error'); return;
        }
        UI.toast('Generating export...', 'info');
        try {
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
        const input = document.getElementById('login-username');
        if (!btn || !input) return;

        const doLogin = async () => {
            const val = input.value.trim();
            if (!val) {
                UI.toast('Please enter username', 'error'); return;
            }
            btn.textContent = 'Authenticating...';
            btn.disabled = true;
            try {
                const res = await api.login(val);
                if (res && res.user_id) {
                    this.userId = res.user_id;
                    this.username = res.username;
                    localStorage.setItem('riskism_user_id', res.user_id);
                    localStorage.setItem('riskism_username', res.username);
                    document.getElementById('modal-login').classList.remove('active');
                    this.finishInit();
                } else {
                    UI.toast('Login error, please try again.', 'error');
                }
            } catch (e) {
                UI.toast('Server error', 'error');
            } finally {
                btn.textContent = 'Access Terminal';
                btn.disabled = false;
            }
        };

        btn.addEventListener('click', doLogin);
        input.addEventListener('keypress', (e) => { if(e.key==='Enter') doLogin() });
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
            UI.renderRiskAnalysis(this.portfolioData.stock_risks, []);
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
        btn.addEventListener('click', () => {
            localStorage.removeItem('riskism_user_id');
            localStorage.removeItem('riskism_username');
            this.userId = null;
            this.username = null;
            document.getElementById('modal-login').classList.add('active');
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

        // Risk Analysis (always populate)
        if (r.risk_metrics) {
            UI.renderRiskAnalysis(r.risk_metrics, r.anomalies || []);
        }

        // Reports
        if (r.insight) UI.renderReport(r.insight);
        if (r.reflection) {
            UI.renderReflection(r.reflection);
            UI.renderPredictionTimeline(r.reflection);
        }
        if (r.execution_log) UI.renderAgentLog(r.execution_log);

        // Portfolio
        if (r.portfolio_metrics && r.capital_advice) {
            const pData = {
                portfolio: portfolio,
                portfolio_metrics: r.portfolio_metrics,
                capital_advice: r.capital_advice,
                stock_risks: stockRisks,
            };
            this.portfolioData = pData;
            UI.renderPortfolio(pData);
        }
    }

    // ─── News Toggle ─────────────────────────────
    bindNewsToggle() {
        document.querySelectorAll('#news-toggle .toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#news-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    }

    // ─── Risk Analysis Select ────────────────────
    bindRiskSelect() {
        document.getElementById('ra-symbol-select')?.addEventListener('change', (e) => {
            const risks = (this.agentResult && this.agentResult.risk_metrics) ||
                          (this.portfolioData && this.portfolioData.stock_risks);
            if (risks) {
                UI.renderStockDetail(e.target.value, risks);
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

        const renderEditorRows = (holdings) => {
            editor.innerHTML = holdings.map((h, i) => `
                <div class="editor-row" data-idx="${i}" style="display:flex; gap:8px; margin-bottom:8px;">
                    <input type="text" class="form-input pf-sym" placeholder="Symbol" value="${h.symbol || ''}" style="width:30%" maxlength="3">
                    <input type="number" class="form-input pf-qty" placeholder="Quantity" value="${h.quantity || 0}" style="width:30%">
                    <input type="number" class="form-input pf-prc" placeholder="Avg Price" value="${h.avg_price || 0}" style="width:30%">
                    <button class="btn-outline btn-rm-row" style="padding: 4px 8px;">✕</button>
                </div>
            `).join('');

            editor.querySelectorAll('.btn-rm-row').forEach(b => {
                b.addEventListener('click', (e) => e.target.closest('.editor-row').remove());
            });
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
            row.style = "display:flex; gap:8px; margin-bottom:8px;";
            row.innerHTML = `
                <input type="text" class="form-input pf-sym" placeholder="Symbol" style="width:30%" maxlength="3">
                <input type="number" class="form-input pf-qty" placeholder="Quantity" style="width:30%">
                <input type="number" class="form-input pf-prc" placeholder="Avg Price" style="width:30%">
                <button class="btn-outline btn-rm-row" style="padding: 4px 8px;">✕</button>
            `;
            row.querySelector('.btn-rm-row').addEventListener('click', () => row.remove());
            editor.appendChild(row);
        });

        btnSave.addEventListener('click', async () => {
            const cap = parseFloat(inputCap.value) || 0;
            const rows = editor.querySelectorAll('.editor-row');
            const holdings = [];
            rows.forEach(r => {
                const sym = r.querySelector('.pf-sym').value.trim().toUpperCase();
                const qty = parseInt(r.querySelector('.pf-qty').value) || 0;
                const prc = parseFloat(r.querySelector('.pf-prc').value) || 0;
                if (sym && qty > 0) {
                    holdings.push({ symbol: sym, quantity: qty, avg_price: prc });
                }
            });

            btnSave.textContent = 'Saving...';
            btnSave.disabled = true;
            try {
                const res = await api.updatePortfolio(this.userId, cap, holdings);
                if (res && res.status === 'success') {
                    UI.toast('Portfolio updated successfully', 'success');
                    modal.classList.remove('active');
                    this.loadAllData(); // Reload data
                } else {
                    UI.toast('Failed to save portfolio', 'error');
                }
            } catch (e) {
                UI.toast('Server error while saving portfolio', 'error');
            } finally {
                btnSave.textContent = 'Save Portfolio & Reload';
                btnSave.disabled = false;
            }
        });
    }

    // ─── Data Loaders ────────────────────────────
    async loadAllData() {
        // Load news
        this._fetchWithTimeout(api.getNews(), this.API_TIMEOUT)
            .then(news => {
                if (news && news.articles) UI.renderNews(news.articles);
            })
            .catch(e => {
                console.warn('[Dashboard] News load failed:', e.message);
                const demoNews = api.getDemoNews();
                if (demoNews) UI.renderNews(demoNews.articles);
            });

        // Load portfolio risk (contains ALL real data)
        try {
            const port = await this._fetchWithTimeout(
                api.getPortfolioRisk(this.userId),
                this.API_TIMEOUT
            );
            if (port) {
                this.portfolioData = port;

                // Dashboard: Holdings with real prices
                UI.updateHoldings(port.portfolio.holdings, port.stock_risks);
                UI.updateMetrics(port.portfolio_risk, port.metrics_history);

                // AI Insights: Auto-populate from real risk data
                UI.updateAIFromRisk(port.stock_risks, port.portfolio_risk);

                // Pre-populate Risk Analysis tab with real stock risks + anomalies
                if (port.stock_risks && Object.keys(port.stock_risks).length > 0) {
                    UI.renderRiskAnalysis(port.stock_risks, port.anomalies || []);
                }

                // Correlation matrix
                if (port.correlation_matrix) {
                    UI.renderCorrelationMatrix(port.correlation_matrix, port.correlation_warnings || []);
                }

                // Pre-populate Portfolio tab
                UI.renderPortfolio(port);
            }
        } catch (e) {
            console.warn('[Dashboard] Portfolio load failed:', e.message);
        }
    }

    // ─── Utilities ───────────────────────────────

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
            console.log('[Dashboard] Auto-refreshing data...');
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

    startTickerDemo() {
        const bases = { 'VN-INDEX': 1.2 };
        const update = () => {
            const prices = {};
            Object.entries(bases).forEach(([sym, base]) => {
                const drift = (Math.random() - 0.5) * 0.3;
                bases[sym] = +(base + drift).toFixed(1);
                prices[sym] = { change_pct: bases[sym] };
            });
            UI.updateTicker(prices);
        };
        update();
        this.tickerInterval = setInterval(update, 5000);
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
document.addEventListener('DOMContentLoaded', () => app.init());
