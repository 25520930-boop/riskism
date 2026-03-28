/**
 * Riskism — Chart Components (Sparklines) V3.0
 * Fixed: proper canvas sizing, data normalization, fallback sparklines.
 */
class RiskismCharts {
    constructor() {
        this.sparkCharts = {};
    }

    drawSparkline(canvasId, data, color) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        // Ensure we have valid data
        if (!data || !Array.isArray(data) || data.length < 2) {
            // Generate smooth demo curve as fallback
            data = this._generateSmoothCurve(30, canvasId);
        }

        if (this.sparkCharts[canvasId]) {
            this.sparkCharts[canvasId].destroy();
        }

        const context = ctx.getContext('2d');
        const gradient = context.createLinearGradient(0, 0, 0, ctx.parentElement.clientHeight || 50);
        gradient.addColorStop(0, color + '40');
        gradient.addColorStop(1, color + '05');

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
    }

    drawAllSparklines(history) {
        if (!history) {
            // Draw demo sparklines when no data
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

    _generateSmoothCurve(points, seed) {
        // Generate a smooth, realistic-looking curve for demo
        const seedNum = typeof seed === 'string'
            ? seed.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
            : seed;
        
        const data = [];
        let value = 50 + (seedNum % 30);
        const amplitude = 5 + (seedNum % 10);
        
        for (let i = 0; i < points; i++) {
            // Sine wave with gentle noise
            const wave = Math.sin(i / (3 + (seedNum % 3))) * amplitude;
            const noise = (Math.sin(seedNum + i * 7.3) * 0.5 + Math.sin(seedNum + i * 13.7) * 0.3) * amplitude * 0.3;
            value = 50 + wave + noise + (seedNum % 20) - 10;
            data.push(Math.round(value * 100) / 100);
        }
        return data;
    }
}
const charts = new RiskismCharts();
