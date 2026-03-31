/**
 * Riskism — Chart Components (Sparklines) V3.0
 * Fixed: proper canvas sizing, data normalization, neutral no-data placeholders.
 */
class RiskismCharts {
    constructor() {
        this.sparkCharts = {};
        this._lastHistory = null;
        this._warnedMissingChart = false;

        window.addEventListener('riskism:chartjs-ready', () => {
            this.drawAllSparklines(this._lastHistory);
        });
    }

    hasChartLibrary() {
        return typeof window.Chart !== 'undefined';
    }

    drawSparkline(canvasId, data, color) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        if (!this.hasChartLibrary()) {
            if (!this._warnedMissingChart) {
                console.warn('[Charts] Chart.js is unavailable. Sparkline rendering will retry when the library loads.');
                this._warnedMissingChart = true;
            }
            return;
        }

        // Ensure we have valid data
        if (!data || !Array.isArray(data) || data.length < 2) {
            data = this._placeholderSeries();
        }

        if (this.sparkCharts[canvasId]) {
            this.sparkCharts[canvasId].destroy();
        }

        const context = ctx.getContext('2d');
        if (!context) return;
        const gradient = context.createLinearGradient(0, 0, 0, ctx.parentElement.clientHeight || 50);
        gradient.addColorStop(0, color + '40');
        gradient.addColorStop(1, color + '05');

        try {
            this.sparkCharts[canvasId] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.map((_, i) => i),
                    datasets: [{
                        data,
                        borderColor: color,
                        backgroundColor: gradient,
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHitRadius: 0,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    scales: {
                        x: { display: false },
                        y: {
                            display: false,
                            // Auto-scale with 10% padding so curves aren't flat
                            grace: '10%',
                        }
                    },
                    animation: { duration: 600, easing: 'easeOutQuart' },
                    elements: { line: { capBezierPoints: true } },
                },
            });
        } catch (err) {
            console.error(`[Charts] Failed to draw sparkline ${canvasId}:`, err);
        }
    }

    drawAllSparklines(history) {
        this._lastHistory = history || null;
        if (!history) {
            // Keep charts visually calm when live history is unavailable.
            this.drawSparkline('spark-var', null, '#DC2626');
            this.drawSparkline('spark-sharpe', null, '#16A34A');
            this.drawSparkline('spark-drawdown', null, '#F59E0B');
            this.drawSparkline('spark-beta', null, '#3B82F6');
            return;
        }

        // Use actual data arrays from backend
        this.drawSparkline('spark-var', history.var_95, '#DC2626');
        this.drawSparkline('spark-sharpe', history.sharpe, '#16A34A');
        this.drawSparkline('spark-drawdown', history.drawdown, '#F59E0B');
        this.drawSparkline('spark-beta', history.beta, '#3B82F6');
    }

    _placeholderSeries() {
        return [0, 0];
    }
}
const charts = new RiskismCharts();
