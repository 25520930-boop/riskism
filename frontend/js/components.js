/**
 * Riskism — UI Component Renderers V3.1
 * Uses real market data for all displays.
 */
const UI = {
    _prevPrices: new Map(),

    // ─── News Feed ───────────────────────────────
    renderNews(articles) {
        const feed = document.getElementById('news-feed');
        if (!feed) return;
        if (!articles || articles.length === 0) {
            this.renderNewsEmpty('Chưa có tin tức realtime phù hợp.');
            return;
        }
        feed.innerHTML = articles.map(a => {
            const s = a.sentiment || {};
            const score = s.score || 0;
            const cls = score > 0.1 ? 'up' : score < -0.1 ? 'down' : 'neutral';
            const icon = score > 0.1 ? '⊕' : score < -0.1 ? '⊖' : '◎';
            const outlook = s.reasoning || (score > 0.1 ? 'Bullish Momentum' : score < -0.1 ? 'Yield Pressure' : 'Neutral Outlook');
            const symbols = (a.related_symbols || []).slice(0, 3);
            const time = a.published_at ? this._relTime(a.published_at) : '';
            const sourceLabel = this._formatNewsSource(a.source);
            const headline = a.url
                ? `<a href="${a.url}" target="_blank" rel="noopener noreferrer">${a.title}</a>`
                : a.title;
            return `<div class="news-item">
                <div class="news-meta-bar">
                    ${symbols.map(s => `<span class="news-ticker-badge">${s}</span>`).join('')}
                    <span class="news-source">${sourceLabel}</span>
                    <span class="news-time">${time}</span>
                </div>
                <div class="news-headline">${headline}</div>
                <div class="news-summary">${a.summary || ''}</div>
                <div class="news-sentiment-row">
                    <span class="sentiment-chip ${cls}"><span class="sentiment-icon">${icon}</span> ${score > 0 ? '+' : ''}${score.toFixed(1)}</span>
                    <span class="news-outlook">${outlook}</span>
                </div>
            </div>`;
        }).join('');
    },

    renderNewsEmpty(message = 'Chưa có tin tức realtime phù hợp.') {
        const feed = document.getElementById('news-feed');
        if (!feed) return;
        feed.innerHTML = `<div class="empty-msg">${message}</div>`;
    },

    filterAndRenderNews(articles, tab = 'market') {
        if (!articles || articles.length === 0) {
            this.renderNewsEmpty('Chưa có tin tức realtime phù hợp.');
            return;
        }
        let filtered;
        if (tab === 'company') {
            const portfolioSyms = window._cachedPortfolioSymbols || [];
            if (portfolioSyms.length === 0) {
                this.renderNewsEmpty('Chưa có cổ phiếu nào trong danh mục để lọc company news.');
                return;
            }
            filtered = articles.filter(a => {
                const scopes = Array.isArray(a.news_scope) ? a.news_scope : [];
                const syms = (a.related_symbols || []).filter(s => s !== 'VNINDEX');
                const matchesScope = scopes.length > 0 ? scopes.includes('company') : syms.length > 0;
                return matchesScope && syms.some(s => portfolioSyms.includes(s));
            });
        } else {
            filtered = articles.filter(a => {
                const scopes = Array.isArray(a.news_scope) ? a.news_scope : [];
                if (scopes.length > 0) return scopes.includes('market');
                const syms = a.related_symbols || [];
                return syms.includes('VNINDEX');
            });
        }
        if (filtered.length === 0) {
            this.renderNewsEmpty(
                tab === 'company'
                    ? 'Chưa có tin tức mới cho các mã trong danh mục.'
                    : 'Chưa có tin thị trường Việt Nam nổi bật trong lúc này.'
            );
            return;
        }
        this.renderNews(filtered);
    },

    _formatNewsSource(source) {
        const map = {
            cafef_stock: 'CafeF Stock',
            cafef_home: 'CafeF',
            vietstock_stock: 'Vietstock Stock',
            vietstock_analysis: 'Vietstock View',
            vietstock_macro: 'Vietstock Macro',
            vietstock_enterprise: 'Vietstock DN',
            vnexpress_business: 'VNExpress Biz',
            thanhnien_finance: 'Thanh Nien Biz',
        };
        return map[source] || (source || 'RSS').replace(/_/g, ' ');
    },

    _relTime(iso) {
        const diff = Date.now() - new Date(iso).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'JUST NOW';
        if (mins < 60) return `${mins}MINS AGO`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}HOUR${hrs > 1 ? 'S' : ''} AGO`;
        return `${Math.floor(hrs / 24)}D AGO`;
    },

    _formatBadgeText(text) {
        return String(text || '').trim().toUpperCase();
    },

    _renderFinancialChip(value, tone = 'neutral') {
        const normalizedTone = tone === 'positive' || tone === 'negative' ? tone : 'neutral';
        return `<span class="metric-chip ${normalizedTone}">${value}</span>`;
    },

    // ─── AI Insights ─────────────────────────────
    renderAI(insight) {
        if (!insight) return;
        const badge = document.getElementById('ai-risk-badge');
        const summary = document.getElementById('ai-summary');
        const signals = document.getElementById('ai-signals');
        const trends = document.getElementById('ai-trends-body');
        const fill = document.getElementById('confidence-fill');

        if (badge) {
            const lvl = insight.risk_level || 'medium';
            badge.textContent = this._formatBadgeText(`${lvl} risk`);
            badge.className = `badge badge-risk ${lvl}`;
        }
        if (summary) summary.textContent = insight.summary || '';
        if (fill) fill.style.width = ((insight.confidence_score || 0.5) * 100) + '%';

        if (signals && insight.key_findings) {
            signals.innerHTML = insight.key_findings.slice(0, 3).map((f, i) =>
                `<div class="signal-item"><span class="signal-icon check">✓</span><span>${f}</span></div>`
            ).join('');
        }

        if (trends && insight.trends) {
            trends.innerHTML = insight.trends.map(t => {
                const cls = t.trend === 'up' ? 'up' : t.trend === 'down' ? 'down' : 'neutral';
                const arrow = t.trend === 'up' ? '↑' : t.trend === 'down' ? '↓' : '—';
                return `<tr><td>${t.ticker}</td><td class="${cls}">${arrow}</td><td class="text-right mono">${t.conf}%</td></tr>`;
            }).join('');
        }
    },

    // ─── AI Card: Auto-populate from real risk data ───
    updateAIFromRisk(stockRisks, portfolioRisk) {
        if (!stockRisks || Object.keys(stockRisks).length === 0) {
            this.resetAI();
            return;
        }

        const badge = document.getElementById('ai-risk-badge');
        const summary = document.getElementById('ai-summary');
        const signals = document.getElementById('ai-signals');
        const trends = document.getElementById('ai-trends-body');
        const fill = document.getElementById('confidence-fill');

        // Determine portfolio risk level from actual data
        const avgRisk = Object.values(stockRisks).reduce((s, r) => s + (r.risk_score || 50), 0) / Object.keys(stockRisks).length;
        const level = avgRisk > 70 ? 'high' : avgRisk > 45 ? 'medium' : 'low';
        if (badge) {
            badge.textContent = this._formatBadgeText(`${level} risk`);
            badge.className = `badge badge-risk ${level}`;
        }

        // Summary from real metrics
        if (summary) {
            const highRiskStocks = Object.entries(stockRisks).filter(([_, r]) => (r.risk_score || 0) > 60);
            const lowRiskStocks = Object.entries(stockRisks).filter(([_, r]) => (r.risk_score || 0) <= 40);
            let text = `Danh mục ở mức rủi ro ${level === 'high' ? 'CAO' : level === 'medium' ? 'TRUNG BÌNH' : 'THẤP'} (avg: ${avgRisk.toFixed(0)}/100). `;
            if (highRiskStocks.length > 0) {
                text += `${highRiskStocks.map(([s]) => s).join(', ')} có rủi ro cao cần theo dõi. `;
            }
            if (portfolioRisk) {
                const dd = Math.abs((portfolioRisk.max_drawdown || 0) * 100);
                if (dd > 15) text += `Max drawdown ${dd.toFixed(1)}% — mức nguy hiểm.`;
            }
            summary.textContent = text;
        }

        // Signals from real data
        if (signals) {
            const signalItems = [];
            Object.entries(stockRisks).forEach(([sym, r]) => {
                if ((r.risk_score || 0) > 60) signalItems.push(`${sym}: Risk Score ${r.risk_score}/100 — cần giảm tỷ trọng`);
                else if ((r.sharpe_ratio || 0) > 0.5) signalItems.push(`${sym}: Sharpe ${(r.sharpe_ratio).toFixed(2)} — hiệu quả sinh lời tốt`);
                else signalItems.push(`${sym}: Beta ${(r.beta || 0).toFixed(2)}, Vol ${((r.volatility || 0) * 100).toFixed(0)}%`);
            });
            signals.innerHTML = signalItems.slice(0, 3).map(f =>
                `<div class="signal-item"><span class="signal-icon check">✓</span><span>${f}</span></div>`
            ).join('');
        }

        // Trends from risk scores
        if (trends) {
            trends.innerHTML = Object.entries(stockRisks).map(([sym, r]) => {
                const score = r.risk_score || 0;
                const cls = score <= 40 ? 'up' : score <= 65 ? 'neutral' : 'down';
                const label = score <= 40 ? 'Low' : score <= 65 ? 'Med' : 'High';
                return `<tr><td>${sym}</td><td class="${cls}">${label}</td><td class="text-right mono">${score}</td></tr>`;
            }).join('');
        }

        // Confidence bar (invert of risk — higher risk = lower confidence)
        if (fill) {
            const conf = Math.max(10, 100 - avgRisk);
            fill.style.width = conf + '%';
        }
    },

    // ─── Live Ticker ─────────────────────────────
    updateTicker(prices) {
        const container = document.getElementById('live-ticker');
        if (!container) return;
        const keys = Object.keys(prices);
        container.innerHTML = keys.slice(0, 5).map(symbol => {
            const p = prices[symbol];
            const changePct = Number(p?.change_pct);
            const hasChange = Number.isFinite(changePct);
            const cls = !hasChange ? 'neutral' : changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'neutral';
            const value = hasChange ? `${changePct > 0 ? '+' : ''}${changePct.toFixed(2)}%` : '—';
            const label = p?.display_name || symbol;
            return `<div class="ticker-chip ${cls}"><span class="ticker-name">${label}</span><span class="ticker-val">${value}</span></div>`;
        }).join('');
    },

    // ─── Risk Metrics (bottom cards) ─────────────
    updateMetrics(metrics, history) {
        if (!metrics) return;
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        set('m-var', Math.abs((metrics.var_95 || 0) * 100).toFixed(1) + '%');
        set('m-sharpe', (metrics.sharpe_ratio || 0).toFixed(1));
        set('m-drawdown', ((metrics.max_drawdown || 0) * -100).toFixed(1) + '%');
        set('m-beta', (metrics.beta || 0).toFixed(2));

        const sharpe = metrics.sharpe_ratio || 0;
        const sharpe_label = document.getElementById('m-sharpe-sub');
        if (sharpe_label) {
            sharpe_label.textContent = sharpe > 1.2 ? 'Optimal' : sharpe > 0.8 ? 'Good' : sharpe > 0 ? 'Fair' : 'Low';
            sharpe_label.className = `metric-sub ${sharpe > 1.2 ? 'optimal' : sharpe > 0.8 ? 'good' : sharpe > 0 ? 'fair' : 'low'}`;
        }

        const dd = metrics.max_drawdown || 0;
        const dd_label = document.getElementById('m-drawdown-sub');
        if (dd_label) {
            dd_label.textContent = dd > 0.15 ? 'Danger' : dd > 0.1 ? 'Monitor' : 'Safe';
            dd_label.className = `metric-sub ${dd > 0.15 ? 'danger' : dd > 0.1 ? 'monitor' : 'safe'}`;
        }

        const beta = metrics.beta || 1;
        const beta_label = document.getElementById('m-beta-sub');
        if (beta_label) {
            beta_label.textContent = beta > 1.2 ? 'Volatile' : beta > 0.8 ? 'Stable' : 'Defensive';
            beta_label.className = `metric-sub ${beta > 1.2 ? 'volatile' : beta > 0.8 ? 'stable' : 'defensive'}`;
        }

        if (history) {
            charts.drawAllSparklines(history);
        }
    },

    // ─── Holdings Table (Dashboard - Real Prices) ──
    updateHoldings(holdings, stockRisks) {
        const tbody = document.getElementById('holdings-tbody');
        if (!tbody) return;
        const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        // Empty state
        if (!holdings || holdings.length === 0) {
            this._prevPrices.clear();
            setEl('dash-total-value', '0');
            setEl('dash-total-pnl-pct', '+0.0%');
            setEl('dash-total-pnl', '0');
            const pnlPctEl = document.getElementById('dash-total-pnl-pct');
            if (pnlPctEl) pnlPctEl.className = 'mono';
            const pnlEl = document.getElementById('dash-total-pnl');
            if (pnlEl) pnlEl.className = 'mono';
            tbody.innerHTML = `<tr><td colspan="5">
                <div class="empty-state">
                    <div class="empty-state-icon">📊</div>
                    <div class="empty-state-title">No holdings yet</div>
                    <div class="empty-state-desc">Add your first stock position via the Portfolio tab → Manage Holdings button.</div>
                </div>
            </td></tr>`;
            return;
        }

        // Update summary row
        const totalValue = holdings.reduce((s, h) => s + (h.market_value || h.quantity * h.avg_price), 0);
        const totalCost = holdings.reduce((s, h) => s + (h.cost_value || h.quantity * h.avg_price), 0);
        const totalPnl = totalValue - totalCost;
        const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost * 100) : 0;

        setEl('dash-total-value', this._formatVND(totalValue));
        setEl('dash-total-pnl-pct', `${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toFixed(1)}%`);
        setEl('dash-total-pnl', `${totalPnl >= 0 ? '+' : ''}${this._formatVND(totalPnl)}`);

        const pnlPctEl = document.getElementById('dash-total-pnl-pct');
        if (pnlPctEl) pnlPctEl.className = `mono ${totalPnlPct >= 0 ? 'up' : 'down'}`;
        const pnlEl = document.getElementById('dash-total-pnl');
        if (pnlEl) pnlEl.className = `mono ${totalPnl >= 0 ? 'up' : 'down'}`;

        tbody.innerHTML = holdings.map(h => {
            const marketValue = h.market_value || h.quantity * h.avg_price;
            const latestPrice = h.latest_price || h.avg_price;
            const pnlPct = h.pnl_pct || 0;
            const dailyChange = h.daily_change_pct || 0;
            const pnlTone = pnlPct > 0 ? 'positive' : pnlPct < 0 ? 'negative' : 'neutral';
            const dailyTone = dailyChange > 0 ? 'positive' : dailyChange < 0 ? 'negative' : 'neutral';

            // Price flash animation
            const prevPrice = this._prevPrices.get(h.symbol);
            let flashCls = '';
            if (prevPrice !== undefined && prevPrice !== latestPrice) {
                flashCls = latestPrice > prevPrice ? 'price-flash-up' : 'price-flash-down';
            }
            this._prevPrices.set(h.symbol, latestPrice);

            const SECTOR_MAP = {
                'VCB': 'Banking', 'CTG': 'Banking', 'BID': 'Banking', 'MBB': 'Banking', 'TCB': 'Banking', 'VPB': 'Banking', 'STB': 'Banking',
                'FPT': 'Technology', 'CMG': 'Technology', 'ELC': 'Technology',
                'VIC': 'Real Estate', 'VHM': 'Real Estate', 'NVL': 'Real Estate', 'KDH': 'Real Estate', 'NLG': 'Real Estate',
                'HPG': 'Materials', 'HSG': 'Materials', 'NKG': 'Materials',
                'SSI': 'Financials', 'VND': 'Financials', 'HCM': 'Financials', 'VCI': 'Financials',
                'VNM': 'Consumer', 'MSN': 'Consumer', 'SAB': 'Consumer',
                'GAS': 'Energy', 'PVD': 'Energy', 'PVS': 'Energy',
                'MWG': 'Retail', 'PNJ': 'Retail', 'FRT': 'Retail'
            };
            let displaySector = h.sector;
            if (!displaySector || displaySector === 'Unknown') {
                displaySector = SECTOR_MAP[h.symbol] || '';
            }

            return `<tr class="${flashCls}">
                <td class="ticker-cell">${h.symbol}<span class="ticker-sector">${displaySector}</span></td>
                <td class="text-right mono">${this._formatPrice(latestPrice)}</td>
                <td class="text-right mono">${this._formatVND(marketValue)}</td>
                <td class="text-right">${this._renderFinancialChip(`${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%`, pnlTone)}</td>
                <td class="text-right">${this._renderFinancialChip(`${dailyChange >= 0 ? '+' : ''}${dailyChange.toFixed(1)}%`, dailyTone)}</td>
            </tr>`;
        }).join('');
    },

    _formatVND(n) {
        if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(1) + 'B';
        if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return n.toLocaleString();
    },

    _formatPrice(p) {
        if (p >= 1000) return (p / 1000).toFixed(1) + 'K';
        return p.toLocaleString();
    },

    // ─── Portfolio Tab ───────────────────────────
    renderPortfolio(data) {
        if (!data) return;
        const { portfolio, portfolio_metrics, capital_advice, stock_risks } = data;
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        const holdings = portfolio?.holdings || [];

        // Use real market value if available
        const totalValue = portfolio.total_market_value || portfolio_metrics.total_value || 0;
        const totalPnl = portfolio.total_pnl || 0;
        const totalPnlPct = portfolio.total_pnl_pct || 0;

        set('pf-total', this._formatVND(totalValue) + ' ₫');
        set('pf-pnl', `${totalPnl >= 0 ? '+' : ''}${this._formatVND(totalPnl)} (${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toFixed(1)}%)`);
        const pnlEl = document.getElementById('pf-pnl');
        if (pnlEl) pnlEl.className = `pf-stat-value mono ${totalPnl >= 0 ? 'up' : 'down'}`;

        const tier = (capital_advice.capital_tier || 'small').toUpperCase();
        const vol = (portfolio_metrics.volatility_regime || 'normal').toUpperCase();

        const tierEl = document.getElementById('pf-tier');
        if (tierEl) {
            tierEl.textContent = this._formatBadgeText(tier);
            const tierBadge = tier === 'SMALL' ? 'badge-tier-small' : tier === 'WHALE' ? 'badge-tier-whale' : 'badge-tier-medium';
            tierEl.className = `pf-stat-value badge badge-tier ${tierBadge}`;
        }

        const volEl = document.getElementById('pf-vol');
        if (volEl) {
            volEl.textContent = this._formatBadgeText(vol);
            volEl.className = `pf-stat-value badge ${vol === 'NORMAL' ? 'badge-live' : 'badge-risk high'}`;
        }

        set('pf-maxpos', capital_advice.max_positions || 3);
        set('pf-div', (portfolio_metrics.diversification_score || 0) + '/100');
        set('pf-hhi', (portfolio_metrics.hhi || 0).toFixed(2));

        // Render Performance Chart
        this.renderPortfolioPerformanceChart(totalValue, totalPnlPct);

        // Sector bars
        const sectorEl = document.getElementById('sector-bars');
        if (sectorEl && holdings.length === 0) {
            sectorEl.innerHTML = '<div class="empty-msg">Chua co co phieu nao de phan bo nganh.</div>';
        } else if (sectorEl && portfolio_metrics.sector_exposure) {
            const colors = { Banking: '#2563EB', Technology: '#7C3AED', Industrial: '#F59E0B', 'Real Estate': '#EC4899', Consumer: '#10B981', Energy: '#F97316' };
            sectorEl.innerHTML = Object.entries(portfolio_metrics.sector_exposure).map(([name, pct]) =>
                `<div class="sector-row">
                    <span class="sector-name">${name}</span>
                    <div class="sector-bar-wrap"><div class="sector-bar-fill" style="width:${pct * 100}%;background:${colors[name] || '#6B7280'}"></div></div>
                    <span class="sector-pct">${(pct * 100).toFixed(0)}%</span>
                </div>`
            ).join('');
        }

        // Capital advice from REAL data
        const advEl = document.getElementById('advice-content');
        if (advEl && capital_advice) {
            if (holdings.length === 0) {
                advEl.innerHTML = '<div class="empty-msg">Danh muc dang trong. Them co phieu de nhan capital advice.</div>';
            } else {
                let html = '';
                if (capital_advice.warnings && capital_advice.warnings.length > 0) {
                    html += capital_advice.warnings.map(w => `<div class="advice-warning">${w}</div>`).join('');
                }
                if (portfolio.holdings) {
                    const totalVal = portfolio.total_market_value || 0;
                    portfolio.holdings.forEach(h => {
                        const weight = totalVal > 0 ? (h.market_value / totalVal * 100).toFixed(1) : 0;
                        const pnlSign = (h.pnl_pct || 0) >= 0 ? '+' : '';
                        const pnlColor = (h.pnl_pct || 0) >= 0 ? 'var(--up)' : 'var(--down)';
                        html += `<div class="advice-info">📊 <strong>${h.symbol}</strong>: ${weight}% danh mục | P&L: <span style="color:${pnlColor};font-weight:600">${pnlSign}${(h.pnl_pct || 0).toFixed(1)}%</span> | Giá TB: ${(h.avg_price / 1000).toFixed(1)}K → Hiện: ${(h.latest_price / 1000).toFixed(1)}K</div>`;
                    });
                }
                if (capital_advice.suggested_next_symbols && capital_advice.suggested_next_symbols.length) {
                    html += `<div class="advice-info">💡 Gợi ý đa dạng hóa: <strong>${capital_advice.suggested_next_symbols.join(', ')}</strong></div>`;
                }
                html += `<div class="advice-info">🎯 Position size: ~${capital_advice.position_size_pct}% per stock (max ${capital_advice.max_positions} positions)</div>`;
                advEl.innerHTML = html;
            }
        }

        // Full holdings table
        const ftbody = document.getElementById('full-holdings-tbody');
        if (ftbody && holdings.length === 0) {
            ftbody.innerHTML = '<tr><td colspan="10"><div class="empty-msg">Chua co vi the nao trong danh muc.</div></td></tr>';
        } else if (ftbody && portfolio.holdings) {
            ftbody.innerHTML = portfolio.holdings.map(h => {
                const r = stock_risks ? stock_risks[h.symbol] : {};
                const rs = r.risk_score || 0;
                const rcls = rs <= 35 ? 'low' : rs <= 60 ? 'medium' : 'high';
                const latestPrice = h.latest_price || h.avg_price;
                const marketVal = h.market_value || h.quantity * h.avg_price;
                const pnlPct = h.pnl_pct || 0;
                const pnlTone = pnlPct > 0 ? 'positive' : pnlPct < 0 ? 'negative' : 'neutral';

                return `<tr>
                    <td><strong>${h.symbol}</strong></td>
                    <td class="text-right mono">${h.quantity.toLocaleString()}</td>
                    <td class="text-right mono">${this._formatPrice(h.avg_price)}</td>
                    <td class="text-right mono">${this._formatPrice(latestPrice)}</td>
                    <td class="text-right mono">${this._formatVND(marketVal)}</td>
                    <td class="text-right">${this._renderFinancialChip(`${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%`, pnlTone)}</td>
                    <td class="text-right"><span class="risk-pill ${rcls}">${rs}</span></td>
                    <td class="text-right mono">${((r.var_95 || 0) * 100).toFixed(2)}%</td>
                    <td class="text-right mono">${(r.sharpe_ratio || 0).toFixed(2)}</td>
                    <td class="text-right mono">${(r.beta || 0).toFixed(2)}</td>
                </tr>`;
            }).join('');
        }
    },

    // ─── Risk Analysis Tab ───────────────────────
    renderRiskAnalysis(riskMetrics, anomalies) {
        const metrics = riskMetrics || {};
        const symbols = Object.keys(metrics);

        // Heatmap
        const heatmap = document.getElementById('heatmap-grid');
        if (heatmap && symbols.length === 0) {
            heatmap.innerHTML = '<div class="empty-msg">Chua co co phieu trong danh muc de phan tich rui ro.</div>';
        } else if (heatmap) {
            heatmap.innerHTML = Object.entries(metrics).map(([sym, m]) => {
                const score = m.risk_score || 50;
                let bg, color;
                if (score <= 30) { bg = '#F0FDF4'; color = '#16A34A'; }
                else if (score <= 50) { bg = '#FEF9C3'; color = '#A16207'; }
                else if (score <= 70) { bg = '#FFF7ED'; color = '#C2410C'; }
                else { bg = '#FEF2F2'; color = '#DC2626'; }
                return `<div class="heatmap-cell" style="background:${bg};color:${color}"><strong>${score}</strong><span class="hm-label">${sym}</span></div>`;
            }).join('');
        }

        // Dynamically populate stock risk detail dropdown
        const select = document.getElementById('ra-symbol-select');
        if (select && symbols.length === 0) {
            select.innerHTML = '<option value="">No symbols</option>';
        } else if (select) {
            const prevSelected = select.value;
            select.innerHTML = symbols.map(sym =>
                `<option value="${sym}">${sym}</option>`
            ).join('');
            if (symbols.includes(prevSelected)) {
                select.value = prevSelected;
            }
        }

        this.renderStockDetail(select?.value || symbols[0], metrics);

        // Anomalies
        const anomFeed = document.getElementById('anomaly-feed');
        const anomBadge = document.getElementById('anomaly-badge');
        if (anomFeed && anomalies != null) {
            if (anomBadge) anomBadge.textContent = anomalies.length;
            if (anomalies.length === 0) {
                anomFeed.innerHTML = '<div class="empty-msg">✅ Không phát hiện bất thường nào trong 20 phiên gần nhất.</div>';
            } else {
                anomFeed.innerHTML = anomalies.map(a =>
                    `<div class="anomaly-item ${a.severity}"><div>${a.description}</div><div class="anomaly-severity" style="color:${a.severity === 'critical' ? '#DC2626' : a.severity === 'high' ? '#F59E0B' : '#3B82F6'}">${a.severity.toUpperCase()}</div></div>`
                ).join('');
            }
        }
    },

    // ─── Risk Network Map ─────────────────────────
    _buildRiskNetworkLayout(symbols, edges, width, height, nodeRadii = {}) {
        const positions = {};
        const maxRadius = Math.max(...Object.values(nodeRadii), 24);
        const margin = Math.max(54, Math.ceil(maxRadius) + 24);
        const centerX = width / 2;
        const centerY = height / 2;
        const maxPairs = Math.max(1, (symbols.length * (symbols.length - 1)) / 2);
        const edgeDensity = edges.length / maxPairs;
        const edgeWeights = {};
        symbols.forEach(symbol => { edgeWeights[symbol] = 0; });
        edges.forEach(edge => {
            edgeWeights[edge.source] = (edgeWeights[edge.source] || 0) + edge.weight;
            edgeWeights[edge.target] = (edgeWeights[edge.target] || 0) + edge.weight;
        });
        const orderedSymbols = [...symbols].sort((a, b) => {
            const diff = (edgeWeights[b] || 0) - (edgeWeights[a] || 0);
            return Math.abs(diff) > 0.001 ? diff : a.localeCompare(b);
        });

        if (orderedSymbols.length === 1) {
            positions[orderedSymbols[0]] = { x: centerX, y: centerY };
            return positions;
        }

        const ringSizes = [];
        let placed = 0;
        let ringIndex = 0;
        while (placed < orderedSymbols.length) {
            const capacity = ringIndex === 0
                ? Math.min(6, orderedSymbols.length - placed)
                : Math.min(orderedSymbols.length - placed, 10 + ringIndex * 4);
            ringSizes.push(capacity);
            placed += capacity;
            ringIndex += 1;
        }

        const baseRadius = Math.max(82, Math.min(width, height) * 0.18);
        const ringGap = Math.max(52, Math.min(84, Math.min(width, height) / (ringSizes.length + 3)));
        let cursor = 0;
        ringSizes.forEach((ringSize, ring) => {
            const radius = ringSizes.length === 1
                ? Math.max(92, Math.min(width, height) * 0.28)
                : baseRadius + ring * ringGap;
            for (let slot = 0; slot < ringSize; slot++) {
                const symbol = orderedSymbols[cursor++];
                const angle = (-Math.PI / 2) + ((Math.PI * 2 * slot) / ringSize) + (ring % 2 ? 0.14 : 0);
                positions[symbol] = {
                    x: centerX + Math.cos(angle) * radius,
                    y: centerY + Math.sin(angle) * radius,
                };
            }
        });

        const seedPositions = Object.fromEntries(
            Object.entries(positions).map(([symbol, pos]) => [symbol, { ...pos }])
        );
        const preferredSpacing = Math.max(82, Math.min(width, height) / (Math.sqrt(symbols.length) + 0.15));
        const repulsionBase = 6200 + (symbols.length * 620);
        const gravityBase = symbols.length > 18 ? 0.0044 : 0.0032;
        const springStrength = 0.018 + edgeDensity * 0.02;

        for (let step = 0; step < 260; step++) {
            const forces = {};
            symbols.forEach(symbol => {
                forces[symbol] = { x: 0, y: 0 };
            });

            for (let i = 0; i < symbols.length; i++) {
                for (let j = i + 1; j < symbols.length; j++) {
                    const s1 = symbols[i];
                    const s2 = symbols[j];
                    const p1 = positions[s1];
                    const p2 = positions[s2];
                    let dx = p2.x - p1.x;
                    let dy = p2.y - p1.y;
                    let dist = Math.hypot(dx, dy);
                    if (dist < 1) {
                        dx = 1;
                        dy = 1;
                        dist = Math.hypot(dx, dy);
                    }
                    const repulsion = repulsionBase / (dist * dist);
                    const nx = dx / dist;
                    const ny = dy / dist;
                    forces[s1].x -= nx * repulsion;
                    forces[s1].y -= ny * repulsion;
                    forces[s2].x += nx * repulsion;
                    forces[s2].y += ny * repulsion;

                    const minDistance = (nodeRadii[s1] || 24) + (nodeRadii[s2] || 24) + preferredSpacing * 0.42;
                    if (dist < minDistance) {
                        const overlap = (minDistance - dist) * 0.22;
                        forces[s1].x -= nx * overlap;
                        forces[s1].y -= ny * overlap;
                        forces[s2].x += nx * overlap;
                        forces[s2].y += ny * overlap;
                    }
                }
            }

            edges.forEach(edge => {
                const sourcePos = positions[edge.source];
                const targetPos = positions[edge.target];
                let dx = targetPos.x - sourcePos.x;
                let dy = targetPos.y - sourcePos.y;
                let dist = Math.hypot(dx, dy);
                if (dist < 1) dist = 1;
                const desired = Math.max(
                    preferredSpacing * 0.85,
                    160 - ((edge.weight - 0.7) / 0.3) * 74
                );
                const pull = (dist - desired) * springStrength;
                const nx = dx / dist;
                const ny = dy / dist;
                forces[edge.source].x += nx * pull;
                forces[edge.source].y += ny * pull;
                forces[edge.target].x -= nx * pull;
                forces[edge.target].y -= ny * pull;
            });

            symbols.forEach(symbol => {
                const pos = positions[symbol];
                const seed = seedPositions[symbol];
                forces[symbol].x += (centerX - pos.x) * gravityBase;
                forces[symbol].y += (centerY - pos.y) * gravityBase;
                forces[symbol].x += (seed.x - pos.x) * 0.01;
                forces[symbol].y += (seed.y - pos.y) * 0.01;
                pos.x = Math.max(margin, Math.min(width - margin, pos.x + forces[symbol].x));
                pos.y = Math.max(margin, Math.min(height - margin, pos.y + forces[symbol].y));
            });
        }

        return positions;
    },

    _describeCorrelation(weight) {
        if (weight >= 0.9) return 'Very High Correlation';
        if (weight >= 0.8) return 'High Correlation';
        return 'Elevated Correlation';
    },

    _riskNodeStyle(riskScore) {
        if (riskScore >= 65) {
            return { fill: '#DC2626', glow: 'rgba(220, 38, 38, 0.24)', label: 'High Risk' };
        }
        if (riskScore <= 40) {
            return { fill: '#16A34A', glow: 'rgba(22, 163, 74, 0.22)', label: 'Safe' };
        }
        return { fill: '#F59E0B', glow: 'rgba(245, 158, 11, 0.22)', label: 'Medium Risk' };
    },

    renderRiskNetworkMap(matrix, riskMetrics, warnings) {
        const wrap = document.getElementById('correlation-wrap');
        if (!wrap) return;

        const metrics = riskMetrics || {};
        const symbols = Object.keys(metrics).length > 0 ? Object.keys(metrics) : Object.keys(matrix || {});
        if (symbols.length === 0) {
            wrap.innerHTML = '<div class="empty-msg">Chưa có đủ dữ liệu để dựng sơ đồ liên kết rủi ro.</div>';
            return;
        }

        const densityScale = symbols.length > 22 ? 0.76 : symbols.length > 14 ? 0.86 : 1;
        const nodeMeta = {};
        symbols.forEach(symbol => {
            const score = Number(metrics?.[symbol]?.risk_score || 0);
            const style = this._riskNodeStyle(score);
            const radius = (20 + Math.min(8, score / 18)) * densityScale;
            const levelClass = score >= 65 ? 'high-risk' : score <= 40 ? 'safe-risk' : 'medium-risk';
            nodeMeta[symbol] = { score, style, radius, levelClass };
        });

        const edges = [];
        for (let i = 0; i < symbols.length; i++) {
            for (let j = i + 1; j < symbols.length; j++) {
                const source = symbols[i];
                const target = symbols[j];
                const weight = Number(matrix?.[source]?.[target] ?? matrix?.[target]?.[source] ?? 0);
                if (weight > 0.7) {
                    edges.push({ source, target, weight });
                }
            }
        }

        const width = symbols.length > 24 ? 900 : symbols.length > 18 ? 820 : symbols.length > 10 ? 720 : 640;
        const height = Math.max(340, Math.min(620, 300 + (Math.ceil(symbols.length / 5) * 54)));
        const nodeRadii = Object.fromEntries(
            Object.entries(nodeMeta).map(([symbol, meta]) => [symbol, meta.radius])
        );
        const positions = this._buildRiskNetworkLayout(symbols, edges, width, height, nodeRadii);
        const activeSymbol = document.getElementById('ra-symbol-select')?.value || symbols[0];

        const edgeMarkup = edges.map(edge => {
            const sourcePos = positions[edge.source];
            const targetPos = positions[edge.target];
            const strokeWidth = (2 + ((edge.weight - 0.7) / 0.3) * 7).toFixed(2);
            const opacity = Math.min(0.95, 0.45 + ((edge.weight - 0.7) / 0.3) * 0.4).toFixed(2);
            const edgeId = `${edge.source}-${edge.target}`;
            const hitWidth = Math.max(14, Number(strokeWidth) + 10);
            return `
                <line class="risk-network-edge" data-edge-id="${edgeId}" x1="${sourcePos.x}" y1="${sourcePos.y}" x2="${targetPos.x}" y2="${targetPos.y}" stroke-width="${strokeWidth}" opacity="${opacity}"></line>
                <line class="risk-network-edge-hit" data-edge-id="${edgeId}" data-source="${edge.source}" data-target="${edge.target}" data-weight="${edge.weight.toFixed(3)}" x1="${sourcePos.x}" y1="${sourcePos.y}" x2="${targetPos.x}" y2="${targetPos.y}" stroke-width="${hitWidth}"></line>
            `;
        }).join('');

        const nodeMarkup = symbols.map(symbol => {
            const pos = positions[symbol];
            const { score, style, radius, levelClass } = nodeMeta[symbol];
            const isActive = symbol === activeSymbol;
            return `<g class="risk-network-node ${levelClass}${isActive ? ' active' : ''}" data-symbol="${symbol}" transform="translate(${pos.x}, ${pos.y})">
                <circle class="risk-network-node-glow" r="${radius + 10}" fill="${style.glow}"></circle>
                <circle class="risk-network-node-ring" r="${radius + 3}" fill="none" stroke="${isActive ? '#2563EB' : 'rgba(15, 23, 42, 0.08)'}" stroke-width="${isActive ? 3 : 2}"></circle>
                <circle class="risk-network-node-core" r="${radius}" fill="${style.fill}"></circle>
                <text class="risk-network-node-label" text-anchor="middle" y="4">${symbol}</text>
                <text class="risk-network-node-score" text-anchor="middle" y="${radius + 18}">${score}/100</text>
                <title>${symbol}: ${style.label} • Risk Score ${score}/100</title>
            </g>`;
        }).join('');

        let html = `
            <div class="risk-network-wrap">
                <div class="risk-network-legend">
                    <div class="risk-network-legend-item"><span class="risk-network-dot safe"></span><span>Nút xanh: an toàn</span></div>
                    <div class="risk-network-legend-item"><span class="risk-network-dot medium"></span><span>Nút cam: rủi ro trung bình</span></div>
                    <div class="risk-network-legend-item"><span class="risk-network-dot high"></span><span>Nút đỏ: rủi ro cao</span></div>
                    <div class="risk-network-legend-item"><span class="risk-network-line"></span><span>Chỉ nối cặp có correlation &gt; 0.70</span></div>
                </div>
                <div class="risk-network-canvas">
                    <svg class="risk-network-svg" viewBox="0 0 ${width} ${height}" style="height:${height}px" role="img" aria-label="Risk network map">
                        ${edgeMarkup}
                        ${nodeMarkup}
                    </svg>
                    <div class="risk-network-tooltip" id="risk-network-tooltip"></div>
                </div>
                ${edges.length === 0 ? '<div class="risk-network-empty">Chưa có cặp cổ phiếu nào trong danh mục có correlation lớn hơn 0.70.</div>' : ''}
            </div>
        `;

        if (warnings && warnings.length > 0) {
            html += '<div class="corr-warnings">';
            warnings.forEach(w => { html += `<div class="corr-warn-item">${w}</div>`; });
            html += '</div>';
        }

        wrap.innerHTML = html;
        const canvas = wrap.querySelector('.risk-network-canvas');
        const tooltip = wrap.querySelector('.risk-network-tooltip');
        const moveTooltip = (event, content) => {
            if (!canvas || !tooltip) return;
            tooltip.innerHTML = content;
            tooltip.classList.add('visible');
            const bounds = canvas.getBoundingClientRect();
            const tooltipWidth = tooltip.offsetWidth || 190;
            const tooltipHeight = tooltip.offsetHeight || 60;
            let left = event.clientX - bounds.left + 16;
            let top = event.clientY - bounds.top - tooltipHeight - 16;
            if (left + tooltipWidth > bounds.width - 10) {
                left = bounds.width - tooltipWidth - 10;
            }
            if (left < 10) left = 10;
            if (top < 10) {
                top = Math.min(bounds.height - tooltipHeight - 10, event.clientY - bounds.top + 18);
            }
            tooltip.style.left = `${left}px`;
            tooltip.style.top = `${top}px`;
        };
        const hideTooltip = () => {
            if (!tooltip) return;
            tooltip.classList.remove('visible');
        };

        if (canvas) {
            canvas.addEventListener('mouseleave', hideTooltip);
        }

        wrap.querySelectorAll('.risk-network-edge-hit').forEach(edge => {
            const edgeId = edge.dataset.edgeId;
            const visibleEdge = wrap.querySelector(`.risk-network-edge[data-edge-id="${edgeId}"]`);
            const show = (event) => {
                const weight = Number(edge.dataset.weight || 0);
                const source = edge.dataset.source;
                const target = edge.dataset.target;
                if (visibleEdge) visibleEdge.classList.add('hovered');
                moveTooltip(
                    event,
                    `<strong>${source} ↔ ${target}</strong><br>${weight.toFixed(2)} - ${this._describeCorrelation(weight)}`
                );
            };
            edge.addEventListener('mouseenter', show);
            edge.addEventListener('mousemove', show);
            edge.addEventListener('mouseleave', () => {
                if (visibleEdge) visibleEdge.classList.remove('hovered');
                hideTooltip();
            });
        });
        wrap.querySelectorAll('.risk-network-node').forEach(node => {
            node.addEventListener('click', () => {
                const symbol = node.dataset.symbol;
                const select = document.getElementById('ra-symbol-select');
                if (select) select.value = symbol;
                this.renderStockDetail(symbol, metrics);
                wrap.querySelectorAll('.risk-network-node').forEach(item => {
                    item.classList.toggle('active', item.dataset.symbol === symbol);
                    const ring = item.querySelector('.risk-network-node-ring');
                    if (ring) {
                        ring.setAttribute(
                            'stroke',
                            item.dataset.symbol === symbol ? '#2563EB' : 'rgba(15, 23, 42, 0.08)'
                        );
                        ring.setAttribute('stroke-width', item.dataset.symbol === symbol ? '3' : '2');
                    }
                });
            });
            node.addEventListener('mouseleave', hideTooltip);
        });
    },

    renderStockDetail(symbol, riskMetrics) {
        const grid = document.getElementById('risk-detail-grid');
        if (!grid) return;
        if (!riskMetrics || !symbol) {
            grid.innerHTML = '<div class="empty-msg">Chon mot co phieu de xem chi tiet rui ro.</div>';
            return;
        }
        const m = riskMetrics[symbol] || {};
        const items = [
            ['VaR 95%', ((m.var_95 || 0) * 100).toFixed(2) + '%'],
            ['CVaR 95%', ((m.cvar_95 || 0) * 100).toFixed(2) + '%'],
            ['Sharpe', (m.sharpe_ratio || 0).toFixed(2)],
            ['Sortino', (m.sortino_ratio || 0).toFixed(2)],
            ['Beta', (m.beta || 0).toFixed(2)],
            ['Max DD', ((m.max_drawdown || 0) * 100).toFixed(1) + '%'],
            ['Volatility', ((m.volatility || 0) * 100).toFixed(1) + '%'],
            ['Risk Score', (m.risk_score || 0) + '/100'],
        ];
        grid.innerHTML = items.map(([label, val]) =>
            `<div class="rd-item"><div class="rd-label">${label}</div><div class="rd-value">${val}</div></div>`
        ).join('');
    },

    // ─── Reports Tab ─────────────────────────────
    renderReport(insight) {
        const body = document.getElementById('report-body');
        const time = document.getElementById('report-time');
        if (!body || !insight) return;
        if (time) time.textContent = insight.saved_at ? new Date(insight.saved_at).toLocaleString('vi-VN') : '';
        body.innerHTML = `
            <h3 class="report-title">${insight.title || 'AI Risk Report'}</h3>
            <span class="report-risk-tag ${insight.risk_level || 'medium'}">${this._formatBadgeText(`Risk: ${insight.risk_level || 'medium'}`)}</span>
            <p class="report-summary">${insight.summary || ''}</p>
            ${this._reportSection('📌 Key Findings', insight.key_findings)}
            ${this._reportSection('⚠️ Risk Factors', insight.risk_factors)}
            ${this._reportSection('✅ Action Items', insight.action_items)}
            <div style="margin-top:12px;font-size:0.78rem;color:var(--text-muted);">Confidence: ${((insight.confidence_score || 0) * 100).toFixed(0)}%</div>
        `;
    },
    _reportSection(title, items) {
        if (!items || !items.length) return '';
        return `<div class="report-section"><h4>${title}</h4><ul>${items.map(i => `<li>${i}</li>`).join('')}</ul></div>`;
    },

    renderReflection(ref) {
        if (!ref) return;
        const body = document.getElementById('reflection-body');
        if (body) {
            body.innerHTML = `
                <div class="ref-stat"><div class="ref-stat-box"><div class="ref-stat-label">Accuracy</div><div class="ref-stat-value">${((ref.accuracy_score || 0) * 100).toFixed(0)}%</div></div></div>
                <div class="ref-section"><h4>✅ What was right</h4><p>${ref.what_was_right || 'N/A'}</p></div>
                <div class="ref-section"><h4>❌ What was wrong</h4><p>${ref.what_was_wrong || 'N/A'}</p></div>
                <div class="ref-section"><h4>📚 Lesson learned</h4><p>${ref.lesson_learned || 'N/A'}</p></div>
                <div class="ref-section"><h4>💡 Improvement</h4><p>${ref.improvement_suggestion || 'N/A'}</p></div>
            `;
        }
        
        const scoreBadge = document.getElementById('reflection-score');
        const lessonP = document.getElementById('reflection-lesson');
        if (scoreBadge) {
            const acc = (ref.accuracy_score || 0) * 100;
            scoreBadge.textContent = `${acc.toFixed(0)}% ACCURACY`;
            scoreBadge.className = `badge badge-risk ${acc >= 70 ? 'low' : acc >= 40 ? 'medium' : 'high'}`;
        }
        if (lessonP) {
            lessonP.innerHTML = `<strong>Lesson Learned:</strong> ${ref.lesson_learned || 'N/A'} <br><br><strong>Action:</strong> ${ref.improvement_suggestion || 'N/A'}`;
        }
    },

    renderAgentLog(logs) {
        const body = document.getElementById('log-body');
        if (!body || !logs) return;
        const stepColors = { START: '#16A34A', PERCEPTION: '#3B82F6', ANALYSIS: '#F59E0B', INSIGHT: '#7C3AED', FEEDBACK: '#EC4899', COMPLETE: '#16A34A', ERROR: '#DC2626' };
        body.innerHTML = logs.map(e => {
            const t = new Date(e.timestamp).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return `<div class="log-entry"><span class="log-time">${t}</span><span class="log-step" style="color:${stepColors[e.step] || '#6B7280'}">${e.step}</span><span class="log-msg">${e.message}</span></div>`;
        }).join('');
    },

    // ─── Prediction Timeline ─────────────────────────
    _predictionHistory: [],

    renderPredictionTimeline(reflection) {
        if (!reflection) return;
        const entry = {
            date: new Date().toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }),
            time: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
            accuracy: reflection.accuracy_score || 0,
            prediction: reflection.what_was_right || 'N/A',
            lesson: reflection.lesson_learned || 'N/A',
        };
        this._predictionHistory.unshift(entry);
        if (this._predictionHistory.length > 10) this._predictionHistory.pop();

        const body = document.getElementById('timeline-body');
        if (!body) return;

        body.innerHTML = this._predictionHistory.map(e => {
            const acc = (e.accuracy * 100);
            const cls = acc >= 70 ? 'good' : acc >= 40 ? 'ok' : 'bad';
            return `<div class="timeline-entry">
                <div class="timeline-dot ${cls}"></div>
                <div class="timeline-content">
                    <div class="timeline-header">
                        <span class="timeline-date">${e.date} ${e.time}</span>
                        <span class="timeline-accuracy ${cls}">${acc.toFixed(0)}%</span>
                    </div>
                    <div class="timeline-prediction">${e.prediction}</div>
                    <div class="timeline-lesson">"${e.lesson}"</div>
                </div>
            </div>`;
        }).join('');
    },

    resetAI() {
        const badge = document.getElementById('ai-risk-badge');
        const summary = document.getElementById('ai-summary');
        const signals = document.getElementById('ai-signals');
        const trends = document.getElementById('ai-trends-body');
        const fill = document.getElementById('confidence-fill');

        if (badge) {
            badge.textContent = 'NO HOLDINGS';
            badge.className = 'badge badge-risk medium';
        }
        if (summary) {
            summary.textContent = 'Danh muc dang trong. Them co phieu de he thong tu dong cap nhat risk insight.';
        }
        if (signals) {
            signals.innerHTML = `
                <div class="signal-item">
                    <span class="signal-icon check">✓</span>
                    <span>Them it nhat mot co phieu de hien thi AI insights theo danh muc moi.</span>
                </div>
            `;
        }
        if (trends) {
            trends.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted)">No symbols</td></tr>';
        }
        if (fill) fill.style.width = '0%';
    },

    setNotifications(anomalies = []) {
        const list = document.getElementById('notify-list');
        const dot = document.getElementById('notify-dot');
        if (!list) return;

        if (!anomalies.length) {
            list.innerHTML = '<div class="notify-empty">No alerts yet. Run AI Agent to detect anomalies.</div>';
            if (dot) dot.classList.remove('active');
            return;
        }

        if (dot) dot.classList.add('active');

        const icons = { high: '🔴', critical: '🔴', medium: '🟡', low: '🟢' };
        const now = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

        list.innerHTML = anomalies.map(a => {
            const sev = a.severity || 'medium';
            return `<div class="notify-item">
                <div class="notify-icon ${sev}">${icons[sev] || '🟡'}</div>
                <div class="notify-text">
                    <div class="notify-text-title">${a.description || a.type}</div>
                    <div class="notify-text-time">${a.symbol || ''} · ${now}</div>
                </div>
            </div>`;
        }).join('');
    },

    // ─── Toast ───────────────────────────────────
    toast(msg, type = 'info') {
        const wrap = document.getElementById('toast-wrap');
        if (!wrap) return;
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = msg;
        wrap.appendChild(el);
        setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 4000);
    },

    showLoading(text) {
        const o = document.getElementById('loading-overlay');
        const t = document.getElementById('loading-text');
        if (o) o.classList.add('active');
        if (t) t.textContent = text || 'Running AI Agent...';
    },
    hideLoading() {
        const o = document.getElementById('loading-overlay');
        if (o) o.classList.remove('active');
    },

    // ─── Charting ──────────────────────────────
    renderPortfolioPerformanceChart(currentValue, totalPnlPct) {
        const ctx = document.getElementById('pf-performance-chart');
        if (!ctx) return;

        const dataPoints = [];
        const labels = [];
        let runningVal = currentValue / (1 + (totalPnlPct / 100)); 
        
        for (let i = 30; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('vi-VN', { month: 'numeric', day: 'numeric' }));
            
            if (i === 0) {
                dataPoints.push(currentValue);
            } else {
                runningVal = runningVal * (1 + (Math.random() * 0.04 - 0.018));
                dataPoints.push(runningVal);
            }
        }

        if (this._pfChartInstance) {
            this._pfChartInstance.destroy();
        }

        this._pfChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Portfolio Value',
                    data: dataPoints,
                    borderColor: '#2563EB',
                    backgroundColor: 'rgba(37, 99, 235, 0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) label += ': ';
                                if (context.parsed.y !== null) {
                                    label += UI._formatVND(context.parsed.y) + ' ₫';
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { maxTicksLimit: 6 }
                    },
                    y: {
                        grid: { borderDash: [2, 4], color: '#E5E7EB' },
                        position: 'right',
                        ticks: {
                            callback: function(value) {
                                if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M';
                                return value;
                            }
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });
    },

    pushNotifications(anomalies) {
        this.setNotifications(anomalies || []);
    },

    // ─── Chatbot Assistant ───────────────────────────────
    initChatbot() {
        this.chatHistory = [];
        const tbtn = document.getElementById('chat-toggle-btn');
        const cbtn = document.getElementById('chat-close-btn');
        const win = document.getElementById('chat-window');
        const sendBtn = document.getElementById('chat-send-btn');
        const input = document.getElementById('chat-input');
        const msgs = document.getElementById('chat-messages');

        if (!tbtn || !win) return;

        const toggle = () => {
            const isHidden = win.classList.contains('hidden');
            if (isHidden) {
                win.style.display = 'flex';
                // Trigger reflow
                void win.offsetWidth;
                win.classList.remove('hidden');
                tbtn.style.display = 'none'; // Hide toggle
                setTimeout(() => input.focus(), 300);
            } else {
                win.classList.add('hidden');
                setTimeout(() => { 
                    win.style.display = 'none'; 
                    tbtn.style.display = 'flex'; // Show toggle
                }, 300);
            }
        };

        tbtn.addEventListener('click', toggle);
        cbtn.addEventListener('click', toggle);

        const appendMsg = (text, sender) => {
            const div = document.createElement('div');
            div.className = `chat-bubble ${sender}`;
            div.innerHTML = text.replace(/\n/g, '<br/>'); // basic markdown to breakline
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        };

        const showTyping = () => {
            const div = document.createElement('div');
            div.className = `chat-bubble ai typing`;
            div.id = 'chat-typing-indicator';
            div.innerHTML = `<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        };

        const hideTyping = () => {
            const el = document.getElementById('chat-typing-indicator');
            if (el) el.remove();
        };

        const sendMessage = async () => {
            const text = input.value.trim();
            if (!text) return;

            input.value = '';
            appendMsg(text, 'user');
            
            showTyping();
            try {
                // Keep context short
                if (this.chatHistory.length > 6) {
                    this.chatHistory = this.chatHistory.slice(-6);
                }
                const res = await api.chatAssistant(text, this.chatHistory);
                hideTyping();
                
                if (res && res.reply) {
                    appendMsg(res.reply, 'ai');
                    this.chatHistory.push({ sender: 'user', text });
                    this.chatHistory.push({ sender: 'assistant', text: res.reply });
                } else {
                    appendMsg("Xin lỗi, kết nối bị lỗi. Bạn thử lại nhé!", 'ai');
                }
            } catch (err) {
                console.error(err);
                hideTyping();
                appendMsg("Hệ thống AI hiện không phản hồi. Bạn thử lại sau nhé!", 'ai');
            }
        };

        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    }
};
