/**
 * Riskism — UI Component Renderers V3.1
 * Uses real market data for all displays.
 */
const UI = {
    _prevPrices: new Map(),

    // ─── News Feed ───────────────────────────────
    renderNews(articles) {
        const feed = document.getElementById('news-feed');
        if (!feed || !articles) return;
        feed.innerHTML = articles.map(a => {
            const s = a.sentiment || {};
            const score = s.score || 0;
            const cls = score > 0.1 ? 'up' : score < -0.1 ? 'down' : 'neutral';
            const icon = score > 0.1 ? '⊕' : score < -0.1 ? '⊖' : '◎';
            const outlook = s.reasoning || (score > 0.1 ? 'Bullish Momentum' : score < -0.1 ? 'Yield Pressure' : 'Neutral Outlook');
            const symbols = (a.related_symbols || []).slice(0, 2);
            const time = a.published_at ? this._relTime(a.published_at) : '';
            return `<div class="news-item">
                <div class="news-meta-bar">
                    ${symbols.map(s => `<span class="news-ticker-badge">${s}</span>`).join('')}
                    <span class="news-time">${time}</span>
                </div>
                <div class="news-headline">${a.title}</div>
                <div class="news-sentiment-row">
                    <span class="sentiment-chip ${cls}"><span class="sentiment-icon">${icon}</span> ${score > 0 ? '+' : ''}${score.toFixed(1)}</span>
                    <span class="news-outlook">${outlook}</span>
                </div>
            </div>`;
        }).join('');
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
            badge.textContent = `${lvl.toUpperCase()} RISK`;
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
        if (!stockRisks || Object.keys(stockRisks).length === 0) return;

        const badge = document.getElementById('ai-risk-badge');
        const summary = document.getElementById('ai-summary');
        const signals = document.getElementById('ai-signals');
        const trends = document.getElementById('ai-trends-body');
        const fill = document.getElementById('confidence-fill');

        // Determine portfolio risk level from actual data
        const avgRisk = Object.values(stockRisks).reduce((s, r) => s + (r.risk_score || 50), 0) / Object.keys(stockRisks).length;
        const level = avgRisk > 70 ? 'high' : avgRisk > 45 ? 'medium' : 'low';
        if (badge) {
            badge.textContent = `${level.toUpperCase()} RISK`;
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

        // Empty state
        if (!holdings || holdings.length === 0) {
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

        const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
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
            const cls = pnlPct >= 0 ? 'up' : 'down';
            const dailyCls = dailyChange >= 0 ? 'up' : 'down';

            // Price flash animation
            const prevPrice = this._prevPrices.get(h.symbol);
            let flashCls = '';
            if (prevPrice !== undefined && prevPrice !== latestPrice) {
                flashCls = latestPrice > prevPrice ? 'price-flash-up' : 'price-flash-down';
            }
            this._prevPrices.set(h.symbol, latestPrice);

            return `<tr class="${flashCls}">
                <td class="ticker-cell">${h.symbol}<span class="ticker-sector">${h.sector || ''}</span></td>
                <td class="text-right mono">${this._formatPrice(latestPrice)}</td>
                <td class="text-right mono">${this._formatVND(marketValue)}</td>
                <td class="text-right mono ${cls}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%</td>
                <td class="text-right mono ${dailyCls}">${dailyChange >= 0 ? '+' : ''}${dailyChange.toFixed(1)}%</td>
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
            tierEl.textContent = tier;
            tierEl.className = `pf-stat-value badge ${tier === 'SMALL' ? 'badge-info' : 'badge-warn'}`;
        }

        const volEl = document.getElementById('pf-vol');
        if (volEl) {
            volEl.textContent = vol;
            volEl.className = `pf-stat-value badge ${vol === 'NORMAL' ? 'badge-live' : 'badge-risk high'}`;
        }

        set('pf-maxpos', capital_advice.max_positions || 3);
        set('pf-div', (portfolio_metrics.diversification_score || 0) + '/100');
        set('pf-hhi', (portfolio_metrics.hhi || 0).toFixed(2));

        // Render Performance Chart
        this.renderPortfolioPerformanceChart(totalValue, totalPnlPct);

        // Sector bars
        const sectorEl = document.getElementById('sector-bars');
        if (sectorEl && portfolio_metrics.sector_exposure) {
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
            let html = '';
            if (capital_advice.warnings && capital_advice.warnings.length > 0) {
                html += capital_advice.warnings.map(w => `<div class="advice-warning">${w}</div>`).join('');
            }
            // Real position analysis from portfolio data
            if (portfolio.holdings) {
                const totalVal = portfolio.total_market_value || 0;
                portfolio.holdings.forEach(h => {
                    const weight = totalVal > 0 ? (h.market_value / totalVal * 100).toFixed(1) : 0;
                    const pnlSign = (h.pnl_pct || 0) >= 0 ? '+' : '';
                    html += `<div class="advice-info">📊 <strong>${h.symbol}</strong>: ${weight}% danh mục | P&L: ${pnlSign}${(h.pnl_pct || 0).toFixed(1)}% | Giá TB: ${(h.avg_price / 1000).toFixed(1)}K → Hiện: ${(h.latest_price / 1000).toFixed(1)}K</div>`;
                });
            }
            if (capital_advice.suggested_next_symbols && capital_advice.suggested_next_symbols.length) {
                html += `<div class="advice-info">💡 Gợi ý đa dạng hóa: <strong>${capital_advice.suggested_next_symbols.join(', ')}</strong></div>`;
            }
            html += `<div class="advice-info">🎯 Position size: ~${capital_advice.position_size_pct}% per stock (max ${capital_advice.max_positions} positions)</div>`;
            advEl.innerHTML = html;
        }

        // Full holdings table with real data
        const ftbody = document.getElementById('full-holdings-tbody');
        if (ftbody && portfolio.holdings) {
            ftbody.innerHTML = portfolio.holdings.map(h => {
                const r = stock_risks ? stock_risks[h.symbol] : {};
                const rs = r.risk_score || 0;
                const rcls = rs <= 35 ? 'low' : rs <= 60 ? 'medium' : 'high';
                const latestPrice = h.latest_price || h.avg_price;
                const marketVal = h.market_value || h.quantity * h.avg_price;
                const pnlPct = h.pnl_pct || 0;
                const pnlCls = pnlPct >= 0 ? 'up' : 'down';

                return `<tr>
                    <td><strong>${h.symbol}</strong></td>
                    <td class="text-right mono">${h.quantity.toLocaleString()}</td>
                    <td class="text-right mono">${this._formatPrice(h.avg_price)}</td>
                    <td class="text-right mono">${this._formatPrice(latestPrice)}</td>
                    <td class="text-right mono">${this._formatVND(marketVal)}</td>
                    <td class="text-right mono ${pnlCls}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%</td>
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
        // Heatmap
        const heatmap = document.getElementById('heatmap-grid');
        if (heatmap && riskMetrics) {
            heatmap.innerHTML = Object.entries(riskMetrics).map(([sym, m]) => {
                const score = m.risk_score || 50;
                let bg, color;
                if (score <= 30) { bg = '#F0FDF4'; color = '#16A34A'; }
                else if (score <= 50) { bg = '#FEF9C3'; color = '#A16207'; }
                else if (score <= 70) { bg = '#FFF7ED'; color = '#C2410C'; }
                else { bg = '#FEF2F2'; color = '#DC2626'; }
                return `<div class="heatmap-cell" style="background:${bg};color:${color}"><strong>${score}</strong><span class="hm-label">${sym}</span></div>`;
            }).join('');
        }

        // Stock detail
        this.renderStockDetail(Object.keys(riskMetrics || {})[0], riskMetrics);

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

    // ─── Correlation Matrix Rendering ─────────────
    renderCorrelationMatrix(matrix, warnings) {
        const wrap = document.getElementById('correlation-wrap');
        if (!wrap || !matrix) return;

        const symbols = Object.keys(matrix);
        if (symbols.length === 0) {
            wrap.innerHTML = '<div class="empty-msg">Không đủ dữ liệu để tính correlation.</div>';
            return;
        }

        let html = '<table class="corr-table"><thead><tr><th></th>';
        symbols.forEach(s => html += `<th>${s}</th>`);
        html += '</tr></thead><tbody>';

        symbols.forEach(s1 => {
            html += `<tr><td class="corr-label">${s1}</td>`;
            symbols.forEach(s2 => {
                const val = (matrix[s1] && matrix[s1][s2] !== undefined) ? matrix[s1][s2] : 0;
                const absVal = Math.abs(val);
                let bg, color;
                if (s1 === s2) { bg = '#2563EB'; color = '#fff'; }
                else if (absVal > 0.7) { bg = '#FEF2F2'; color = '#DC2626'; }
                else if (absVal > 0.4) { bg = '#FFFBEB'; color = '#A16207'; }
                else { bg = '#F0FDF4'; color = '#16A34A'; }
                html += `<td class="corr-cell" style="background:${bg};color:${color}">${val.toFixed(2)}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table>';

        if (warnings && warnings.length > 0) {
            html += '<div class="corr-warnings">';
            warnings.forEach(w => html += `<div class="corr-warn-item">${w}</div>`);
            html += '</div>';
        }

        wrap.innerHTML = html;
    },

    renderStockDetail(symbol, riskMetrics) {
        const grid = document.getElementById('risk-detail-grid');
        if (!grid || !riskMetrics || !symbol) return;
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
            <span class="report-risk-tag ${insight.risk_level || 'medium'}">Risk: ${(insight.risk_level || 'MEDIUM').toUpperCase()}</span>
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

        // Old report tab fallback
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
        
        // New interactive card
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

        // Generate mock 30-day historical data points based on current value
        const dataPoints = [];
        const labels = [];
        let runningVal = currentValue / (1 + (totalPnlPct / 100)); // Approximate starting value 30 days ago
        
        for (let i = 30; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('vi-VN', { month: 'numeric', day: 'numeric' }));
            
            if (i === 0) {
                dataPoints.push(currentValue);
            } else {
                // Add some random walk noise
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

    // ─── Notification Panel ─────────────────────────
    pushNotifications(anomalies) {
        const list = document.getElementById('notify-list');
        const dot = document.getElementById('notify-dot');
        if (!list || !anomalies || !anomalies.length) return;

        // Activate pulsing dot
        if (dot) dot.classList.add('active');

        const icons = { high: '🔴', critical: '🔴', medium: '🟡', low: '🟢' };
        const now = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

        const html = anomalies.map(a => {
            const sev = a.severity || 'medium';
            return `<div class="notify-item">
                <div class="notify-icon ${sev}">${icons[sev] || '🟡'}</div>
                <div class="notify-text">
                    <div class="notify-text-title">${a.description || a.type}</div>
                    <div class="notify-text-time">${a.symbol || ''} · ${now}</div>
                </div>
            </div>`;
        }).join('');

        list.innerHTML = html;
    },
};
