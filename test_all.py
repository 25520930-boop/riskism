"""
Riskism - Automated Test Suite
Kiểm tra tất cả module có chạy đúng logic không.
Không cần Docker, không cần API key, chạy offline.
"""
import sys
import numpy as np
from pathlib import Path

print("=" * 60)
print("🔷 RISKISM — KIỂM TRA TỰ ĐỘNG")
print("=" * 60)

errors = []
passed = 0

# ─── TEST 1: Risk Engine - Core Metrics ──────────────────
print("\n📊 Test 1: Risk Engine (core_metrics.py)")
try:
    repo_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(repo_root))
    from backend.risk_engine.core_metrics import (
        calculate_returns, calculate_var, calculate_cvar,
        calculate_beta, calculate_sharpe_ratio, calculate_sortino_ratio,
        calculate_max_drawdown, calculate_volatility, calculate_risk_score,
        compute_all_metrics, compute_portfolio_risk_summary,
        calculate_beta_dimson,
    )

    # Tạo dữ liệu giả: 100 ngày giá cổ phiếu
    prices = np.array([50000 + i * 100 + np.random.normal(0, 500) for i in range(100)])
    market_prices = np.array([1200000 + i * 1000 + np.random.normal(0, 5000) for i in range(100)])

    returns = calculate_returns(prices)
    assert len(returns) == 99, f"Returns phải có 99 phần tử, nhưng có {len(returns)}"
    print(f"  ✅ calculate_returns: OK ({len(returns)} giá trị)")

    var95 = calculate_var(returns, 0.95)
    assert -1 < var95 < 1, f"VaR phải nằm trong (-1, 1), nhưng = {var95}"
    print(f"  ✅ calculate_var (95%): {var95:.4f}")

    cvar95 = calculate_cvar(returns, 0.95)
    assert cvar95 <= var95, f"CVaR phải <= VaR (CVaR={cvar95}, VaR={var95})"
    print(f"  ✅ calculate_cvar (95%): {cvar95:.4f} (luôn <= VaR ✓)")

    beta = calculate_beta(returns, calculate_returns(market_prices))
    assert -5 < beta < 5, f"Beta bất thường: {beta}"
    print(f"  ✅ calculate_beta: {beta:.4f}")

    # Regression: beta phải giữ đúng tỷ lệ co giãn với benchmark
    doubled_market = np.array([0.005, 0.01, -0.005, 0.015, -0.01])
    doubled_stock = doubled_market * 2
    beta_exact = calculate_beta(doubled_stock, doubled_market)
    assert abs(beta_exact - 2.0) < 1e-9, f"Beta 2x market phải = 2.0, nhưng = {beta_exact}"
    print(f"  ✅ calculate_beta regression: 2x benchmark → beta={beta_exact:.4f}")

    delayed_market = np.array([0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.015, -0.005, 0.02, -0.01])
    delayed_stock = np.array([0.0, 0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.015, -0.005, 0.02])
    beta_plain = calculate_beta(delayed_stock, delayed_market)
    beta_dimson = calculate_beta_dimson(delayed_stock, delayed_market)
    assert beta_dimson > beta_plain, f"Dimson beta phải bù được lead/lag tốt hơn beta thường ({beta_dimson} <= {beta_plain})"
    print(f"  ✅ calculate_beta_dimson regression: delayed stock → beta={beta_plain:.4f}, dimson={beta_dimson:.4f}")

    sharpe = calculate_sharpe_ratio(returns)
    print(f"  ✅ calculate_sharpe_ratio: {sharpe:.4f}")

    sortino = calculate_sortino_ratio(returns)
    print(f"  ✅ calculate_sortino_ratio: {sortino:.4f}")

    max_dd, dd_dur = calculate_max_drawdown(prices)
    assert 0 <= max_dd <= 1, f"MaxDrawdown phải 0-1, nhưng = {max_dd}"
    print(f"  ✅ calculate_max_drawdown: {max_dd:.4f} ({dd_dur} ngày)")

    # Regression: duration phải là peak-to-recovery, không phải peak-to-trough
    dd_prices = np.array([100, 120, 110, 90, 95, 125], dtype=float)
    dd_value, dd_duration = calculate_max_drawdown(dd_prices)
    assert abs(dd_value - 0.25) < 1e-9, f"Max drawdown phải = 25%, nhưng = {dd_value}"
    assert dd_duration == 4, f"Duration phải từ peak tới recovery (=4), nhưng = {dd_duration}"
    print(f"  ✅ calculate_max_drawdown regression: dd={dd_value:.4f}, duration={dd_duration} ngày")

    ann_vol, daily_vol = calculate_volatility(returns)
    assert ann_vol > 0, "Volatility phải > 0"
    print(f"  ✅ calculate_volatility: annual={ann_vol:.4f}, daily={daily_vol:.4f}")

    risk_score = calculate_risk_score({'var_95': var95, 'beta': beta, 'max_drawdown': max_dd, 'sharpe_ratio': sharpe, 'volatility': ann_vol})
    assert 0 <= risk_score <= 100, f"Risk score phải 0-100, nhưng = {risk_score}"
    print(f"  ✅ calculate_risk_score: {risk_score}/100")

    metrics = compute_all_metrics('TEST', prices, market_prices)
    d = metrics.to_dict()
    assert d['symbol'] == 'TEST'
    assert all(k in d for k in ['var_95', 'cvar_95', 'beta', 'sharpe_ratio', 'sortino_ratio', 'max_drawdown', 'risk_score'])
    print(f"  ✅ compute_all_metrics: đầy đủ {len(d)} chỉ số")

    # Regression: portfolio metrics phải dựa trên value series thực tế, không phải weighted log returns
    portfolio_holdings = [
        {'symbol': 'AAA', 'quantity': 1, 'avg_price': 100},
        {'symbol': 'BBB', 'quantity': 1, 'avg_price': 100},
    ]
    portfolio_market_data = {
        'AAA': {'dates': ['2024-01-01', '2024-01-02', '2024-01-03'], 'close': [100, 150, 100]},
        'BBB': {'dates': ['2024-01-01', '2024-01-02', '2024-01-03'], 'close': [100, 50, 100]},
        'VNINDEX': {'dates': ['2024-01-01', '2024-01-02', '2024-01-03'], 'close': [100, 150, 100]},
    }
    portfolio_returns_dict = {
        'AAA': calculate_returns(np.array([100, 150, 100], dtype=float)),
        'BBB': calculate_returns(np.array([100, 50, 100], dtype=float)),
    }
    portfolio_summary = compute_portfolio_risk_summary(
        portfolio_holdings,
        portfolio_returns_dict,
        portfolio_market_data,
    )
    current_risk = portfolio_summary['current_risk']
    assert abs(current_risk['var_95']) < 1e-12, f"Portfolio VaR phải = 0 khi value series phẳng, nhưng = {current_risk['var_95']}"
    assert abs(current_risk['max_drawdown']) < 1e-12, f"Portfolio max drawdown phải = 0 khi value series phẳng, nhưng = {current_risk['max_drawdown']}"
    assert abs(current_risk['beta']) < 1e-12, f"Portfolio beta phải = 0 khi danh mục phẳng, nhưng = {current_risk['beta']}"
    print("  ✅ compute_portfolio_risk_summary regression: VaR/Beta/MaxDD đúng trên danh mục offsetting")

    # Regression: mixed date formats across data sources must still align portfolio series
    mixed_date_market_data = {
        'AAA': {'dates': ['2024-01-01', '2024-01-02', '2024-01-03'], 'close': [100, 110, 90]},
        'BBB': {'dates': ['2024-01-01 07:00:00', '2024-01-02 07:00:00', '2024-01-03 07:00:00'], 'close': [100, 95, 92]},
        'VNINDEX': {'dates': ['2024-01-01', '2024-01-02', '2024-01-03'], 'close': [100, 102, 101]},
    }
    mixed_returns_dict = {
        'AAA': calculate_returns(np.array([100, 110, 90], dtype=float)),
        'BBB': calculate_returns(np.array([100, 95, 92], dtype=float)),
    }
    mixed_summary = compute_portfolio_risk_summary(
        portfolio_holdings,
        mixed_returns_dict,
        mixed_date_market_data,
    )
    mixed_risk = mixed_summary['current_risk']
    assert any(abs(mixed_risk[k]) > 1e-12 for k in ['var_95', 'max_drawdown']), f"Mixed date formats không được làm portfolio risk về 0: {mixed_risk}"
    assert 'adjusted_var_95' in mixed_risk and abs(mixed_risk['adjusted_var_95']) >= abs(mixed_risk['var_95']), "Adjusted VaR phải tồn tại và có độ lớn >= VaR"
    assert 'adjusted_cvar_95' in mixed_risk and abs(mixed_risk['adjusted_cvar_95']) >= abs(mixed_risk['cvar_95']), "Adjusted CVaR phải tồn tại và có độ lớn >= CVaR"
    assert 'beta_dimson' in mixed_risk, "Portfolio risk phải expose beta_dimson"
    assert 'liquidity_profile' in mixed_risk and 'effective_horizon_days' in mixed_risk['liquidity_profile'], "Portfolio risk phải expose liquidity_profile"
    stress = mixed_risk.get('stress_scenarios', {})
    assert 'worst_1d' in stress, f"Stress scenarios phải có worst_1d: {stress}"
    print("  ✅ compute_portfolio_risk_summary regression: mixed date formats vẫn align đúng")

    stress_market_data = {
        'AAA': {'dates': ['2024-02-01', '2024-02-02', '2024-02-03', '2024-02-04', '2024-02-05', '2024-02-06'], 'close': [100, 96, 98, 92, 90, 95]},
        'VNINDEX': {'dates': ['2024-02-01', '2024-02-02', '2024-02-03', '2024-02-04', '2024-02-05', '2024-02-06'], 'close': [1000, 990, 995, 975, 970, 980]},
    }
    stress_summary = compute_portfolio_risk_summary(
        [{'symbol': 'AAA', 'quantity': 1, 'avg_price': 100}],
        {'AAA': calculate_returns(np.array([100, 96, 98, 92, 90, 95], dtype=float))},
        stress_market_data,
    )
    stress_risk = stress_summary['current_risk'].get('stress_scenarios', {})
    assert all(k in stress_risk for k in ['worst_1d', 'worst_3d', 'worst_5d']), f"Stress scenarios thiếu field khi đủ history: {stress_risk}"
    print("  ✅ compute_portfolio_risk_summary regression: adjusted VaR/CVaR, beta_dimson, stress scenarios đầy đủ")

    long_dates = [f'2024-03-{day:02d}' for day in range(1, 13)]
    contributor_market_data = {
        'AAA': {'dates': long_dates, 'close': [100, 101, 103, 102, 104, 107, 103, 99, 96, 98, 95, 93], 'volume': [100000, 110000, 95000, 98000, 105000, 100000, 102000, 97000, 96000, 99000, 94000, 93000]},
        'BBB': {'dates': long_dates, 'close': [100, 100, 99, 98, 99, 97, 96, 95, 94, 93, 92, 91], 'volume': [25000, 26000, 24000, 23000, 22000, 21000, 20000, 19500, 19000, 18800, 18500, 18000]},
        'VNINDEX': {'dates': long_dates, 'close': [1000, 1005, 1008, 1004, 1007, 1010, 1006, 999, 992, 995, 989, 985]},
    }
    contributor_summary = compute_portfolio_risk_summary(
        [
            {'symbol': 'AAA', 'quantity': 100, 'avg_price': 100},
            {'symbol': 'BBB', 'quantity': 200, 'avg_price': 100},
        ],
        {
            'AAA': calculate_returns(np.array(contributor_market_data['AAA']['close'], dtype=float)),
            'BBB': calculate_returns(np.array(contributor_market_data['BBB']['close'], dtype=float)),
        },
        contributor_market_data,
    )
    contributor_risk = contributor_summary['current_risk']
    assert contributor_risk['tail_risk_contributors'], "Portfolio risk phải có tail risk contributors khi đủ history"
    assert contributor_risk['liquidity_profile']['positions'], "Liquidity profile phải có chi tiết theo mã"
    print("  ✅ compute_portfolio_risk_summary regression: liquidity profile + tail risk contributors đã có")

    passed += 1
    print("  ✅ PASS — Core Metrics hoạt động đúng!")

except Exception as e:
    errors.append(f"Core Metrics: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 2: Portfolio Metrics ───────────────────────────
print("\n📦 Test 2: Portfolio Metrics (portfolio_metrics.py)")
try:
    from backend.risk_engine.portfolio_metrics import (
        calculate_hhi, calculate_effective_n, calculate_sector_exposure,
        detect_volatility_regime, compute_portfolio_metrics,
        build_sector_benchmark_exposure,
    )

    # Test HHI
    weights = np.array([0.5, 0.3, 0.2])
    hhi = calculate_hhi(weights)
    assert 0 < hhi <= 1, f"HHI phải 0-1, nhưng = {hhi}"
    print(f"  ✅ HHI: {hhi:.4f} (3 cổ phiếu)")

    eff_n = calculate_effective_n(hhi)
    assert eff_n > 0, f"Effective N phải > 0"
    print(f"  ✅ Effective N: {eff_n:.2f} (danh mục 'tương đương' {eff_n:.1f} cổ phiếu)")

    # Test 1 cổ phiếu (tập trung tối đa)
    hhi_single = calculate_hhi(np.array([1.0]))
    assert abs(hhi_single - 1.0) < 0.01, f"HHI 1 cổ phiếu phải = 1.0"
    print(f"  ✅ HHI (1 cổ phiếu): {hhi_single:.4f} = tập trung tối đa")

    # Test sector exposure
    holdings = [
        {'symbol': 'VCB', 'sector': 'Banking', 'value': 5000000},
        {'symbol': 'FPT', 'sector': 'Technology', 'value': 3000000},
    ]
    exposure = calculate_sector_exposure(holdings)
    assert abs(sum(exposure.values()) - 1.0) < 0.01, "Tổng sector exposure phải = 1"
    print(f"  ✅ Sector exposure: {exposure}")

    inferred_exposure = calculate_sector_exposure([
        {'symbol': 'VCB', 'value': 5000000},
        {'symbol': 'FPT', 'value': 3000000},
    ])
    assert inferred_exposure.get('Banking', 0) > 0 and inferred_exposure.get('Technology', 0) > 0, f"Sector exposure phải suy ra được từ symbol: {inferred_exposure}"
    print(f"  ✅ Sector exposure fallback: {inferred_exposure}")

    # Test volatility regime
    normal_returns = np.random.normal(0, 0.02, 100)
    regime = detect_volatility_regime(normal_returns)
    assert regime in ['low', 'normal', 'high', 'extreme']
    print(f"  ✅ Volatility regime: '{regime}'")

    benchmark_sector_exposure = build_sector_benchmark_exposure(['VCB', 'FPT', 'VIC'])
    trend_a = np.array([0.01, -0.005, 0.008, 0.004, -0.003] * 6, dtype=float)
    trend_b = np.array([0.006, -0.002, 0.005, 0.003, -0.001] * 6, dtype=float)
    vn30_returns = np.array([0.008, -0.003, 0.006, 0.003, -0.002] * 6, dtype=float)
    pm = compute_portfolio_metrics(
        [
            {'symbol': 'VCB', 'market_value': 5000000},
            {'symbol': 'FPT', 'market_value': 3000000},
        ],
        {'VCB': trend_a, 'FPT': trend_b},
        market_returns=trend_a,
        benchmark_returns=vn30_returns,
        benchmark_sector_exposure=benchmark_sector_exposure,
    ).to_dict()
    assert pm['rolling_correlation_vn30'] is not None, "Portfolio metrics phải có rolling correlation vs VN30"
    assert 'sector_gap_vs_vn30' in pm and 'Banking' in pm['sector_gap_vs_vn30'], f"Thiếu sector gap vs VN30: {pm}"
    print(f"  ✅ compute_portfolio_metrics regression: rolling corr VN30 + sector gap đã có")

    passed += 1
    print("  ✅ PASS — Portfolio Metrics hoạt động đúng!")

except Exception as e:
    errors.append(f"Portfolio Metrics: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 3: Capital Aware ───────────────────────────────
print("\n💰 Test 3: Capital Aware (capital_aware.py)")
try:
    from backend.risk_engine.capital_aware import (
        get_capital_tier, recommend_positions, SECTOR_MAP
    )

    # Test capital tiers
    assert get_capital_tier(5_000_000) == 'micro', "5M phải là micro"
    assert get_capital_tier(15_000_000) == 'small', "15M phải là small"
    assert get_capital_tier(40_000_000) == 'medium', "40M phải là medium"
    print("  ✅ Capital tiers: micro (<10M), small (10-30M), medium (30M+)")

    # Test position recommendations
    max_pos, pct = recommend_positions(5_000_000)
    assert max_pos == 2 and pct == 50.0, f"5M: max 2 mã, 50% mỗi mã"
    print(f"  ✅ 5M VND → max {max_pos} mã, {pct}% mỗi vị thế")

    max_pos, pct = recommend_positions(20_000_000)
    assert max_pos == 3 and pct == 33.33
    print(f"  ✅ 20M VND → max {max_pos} mã, {pct}% mỗi vị thế")

    max_pos, pct = recommend_positions(50_000_000)
    assert max_pos == 5 and pct == 20.0
    print(f"  ✅ 50M VND → max {max_pos} mã, {pct}% mỗi vị thế")

    # Test sector mapping
    assert SECTOR_MAP['VCB'] == 'Banking'
    assert SECTOR_MAP['FPT'] == 'Technology'
    assert SECTOR_MAP['HPG'] == 'Industrial'
    print(f"  ✅ Sector map: {len(SECTOR_MAP)} mã cổ phiếu đã phân loại")

    passed += 1
    print("  ✅ PASS — Capital Aware hoạt động đúng!")

except Exception as e:
    errors.append(f"Capital Aware: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 4: Anomaly Detector ────────────────────────────
print("\n⚡ Test 4: Anomaly Detector (anomaly_detector.py)")
try:
    from backend.risk_engine.anomaly_detector import (
        detect_volume_spike, detect_volatility_shift,
        detect_price_breakout, scan_all_anomalies
    )

    # Test volume spike detection
    normal_vol = np.random.normal(1000000, 200000, 30)
    # Tạo spike: ngày cuối gấp 5x
    spike_vol = np.append(normal_vol, [5000000])
    result = detect_volume_spike(spike_vol, 'TEST')
    assert result is not None, "Phải phát hiện volume spike khi KL gấp 5x"
    print(f"  ✅ Volume spike: phát hiện KL bất thường (z={result.z_score:.1f}σ)")

    # Test no spike (bình thường)
    result2 = detect_volume_spike(normal_vol, 'TEST')
    assert result2 is None, "Không nên phát hiện spike khi KL bình thường"
    print(f"  ✅ Volume normal: không phát hiện bất thường (đúng)")

    # Test price breakout
    prices = np.linspace(50000, 52000, 30)
    prices = np.append(prices, [58000])  # Breakout lên cao
    result3 = detect_price_breakout(prices, 'TEST')
    assert result3 is not None, "Phải phát hiện breakout khi giá tăng đột biến"
    print(f"  ✅ Price breakout: phát hiện phá đỉnh")

    # Test scan all
    prices_full = np.random.normal(50000, 1000, 50)
    volumes_full = np.random.normal(500000, 100000, 50)
    returns_full = calculate_returns(prices_full)
    anomalies = scan_all_anomalies('TEST', prices_full, volumes_full, returns_full)
    print(f"  ✅ scan_all_anomalies: trả về {len(anomalies)} bất thường")

    passed += 1
    print("  ✅ PASS — Anomaly Detector hoạt động đúng!")

except Exception as e:
    errors.append(f"Anomaly Detector: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 5: Config ──────────────────────────────────────
print("\n⚙️ Test 5: Config (config.py)")
try:
    from backend.config import Settings

    s = Settings()
    assert s.app_name == 'Riskism'
    assert s.postgres_db == 'riskism'
    assert 'postgresql://' in s.database_url
    assert 'redis://' in s.redis_url
    print(f"  ✅ App name: {s.app_name}")
    print(f"  ✅ Database URL: postgresql://.../{s.postgres_db}")
    print(f"  ✅ Redis URL: {s.redis_url}")
    print(f"  ✅ Market timezone: {s.market_timezone}")

    passed += 1
    print("  ✅ PASS — Config hoạt động đúng!")

except Exception as e:
    errors.append(f"Config: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 6: RSS Fetcher ─────────────────────────────────
print("\n📰 Test 6: RSS Fetcher (rss_fetcher.py)")
try:
    from backend.data.rss_fetcher import RSSFetcher

    fetcher = RSSFetcher()

    # Test symbol detection
    symbols = fetcher.detect_related_symbols(
        "Vietcombank (VCB) báo lãi kỷ lục",
        "Ngân hàng BIDV cũng tăng trưởng tốt"
    )
    assert 'VCB' in symbols, "Phải phát hiện VCB trong tiêu đề"
    assert 'BID' in symbols, "Phải phát hiện BID (BIDV) trong nội dung"
    print(f"  ✅ Phát hiện mã CK trong tin: {symbols}")

    # Test URL hashing (dedup)
    h1 = fetcher._hash_url("https://cafef.vn/article-1")
    h2 = fetcher._hash_url("https://cafef.vn/article-1")
    h3 = fetcher._hash_url("https://cafef.vn/article-2")
    assert h1 == h2, "Cùng URL phải cùng hash"
    assert h1 != h3, "Khác URL phải khác hash"
    print(f"  ✅ Deduplication: cùng URL → cùng hash, khác URL → khác hash")

    passed += 1
    print("  ✅ PASS — RSS Fetcher hoạt động đúng!")

except Exception as e:
    errors.append(f"RSS Fetcher: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 7: Docker & SQL Files ──────────────────────────
print("\n🐳 Test 7: Docker & SQL files")
try:
    import os
    base = str(repo_root)

    # Check all required files exist
    required_files = [
        'docker-compose.yml',
        'Dockerfile',
        'nginx.conf',
        'requirements.txt',
        '.env.example',
        'backend/init.sql',
    ]

    for f in required_files:
        path = os.path.join(base, f)
        assert os.path.exists(path), f"File thiếu: {f}"
        size = os.path.getsize(path)
        print(f"  ✅ {f} ({size:,} bytes)")

    # Check docker-compose has all services
    with open(os.path.join(base, 'docker-compose.yml')) as f:
        content = f.read()
    for service in ['postgres', 'redis', 'backend', 'celery-worker', 'celery-beat', 'frontend']:
        assert service in content, f"Docker Compose thiếu service: {service}"
    print(f"  ✅ Docker Compose: đầy đủ 6 services")

    # Check SQL has all tables
    with open(os.path.join(base, 'backend/init.sql')) as f:
        sql = f.read()
    for table in ['users', 'portfolios', 'market_data', 'news', 'insights', 'predictions', 'risk_snapshots']:
        assert f'CREATE TABLE' in sql and table in sql, f"SQL thiếu bảng: {table}"
    print(f"  ✅ init.sql: đầy đủ 7 bảng database")

    # Check requirements.txt
    with open(os.path.join(base, 'requirements.txt')) as f:
        reqs = f.read()
    for pkg in ['fastapi', 'uvicorn', 'sqlalchemy', 'redis', 'celery', 'numpy', 'scipy', 'slowapi', 'limits', 'python-jose']:
        assert pkg in reqs, f"requirements.txt thiếu: {pkg}"
    print(f"  ✅ requirements.txt: đầy đủ các thư viện")

    passed += 1
    print("  ✅ PASS — Docker & infra files đầy đủ!")

except Exception as e:
    errors.append(f"Docker/SQL: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 8: AI Insight & Chatbot Fallbacks ─────────────
print("\n🤖 Test 8: AI Insight & Chatbot fallbacks")
try:
    from backend.agent.llm_router import LLMRouter

    router = LLMRouter()
    router.client = None

    mock_risk_metrics = {
        'AAA': {'risk_score': 78, 'beta': 1.34, 'var_95': -0.041},
        'BBB': {'risk_score': 52, 'beta': 0.91, 'var_95': -0.024},
        'CCC': {'risk_score': 33, 'beta': 0.62, 'var_95': -0.013},
        'VNINDEX': {'risk_score': 50, 'beta': 1.0, 'var_95': -0.02},
    }

    fallback_insight = router.generate_insight(
        mock_risk_metrics,
        news_summary='',
        anomalies=[],
        user_profile={'risk_appetite': 'moderate', 'capital_amount': 50_000_000},
    )
    trend_symbols = [item.get('ticker') for item in fallback_insight.get('trends', [])]
    assert trend_symbols, "Fallback insight phải có stock trends"
    assert 'VNINDEX' not in trend_symbols, "Fallback insight không được đẩy VNINDEX vào stock trends"
    assert trend_symbols[0] == 'AAA', f"Trend đầu tiên phải là mã rủi ro cao nhất AAA, nhưng = {trend_symbols[0]}"
    print(f"  ✅ Insight fallback: trends bám danh mục thật {trend_symbols}")

    app_help_reply = router.chat_assistant('app này giúp dcg gi', [], {})
    normalized_help = app_help_reply.lower()
    assert any(token in normalized_help for token in ('riskism', 'danh mục', 'var', 'tail risk')), \
        f"Chatbot phải trả lời được câu hỏi khả năng app, nhưng nhận: {app_help_reply}"
    print("  ✅ Chatbot fallback: trả lời được câu hỏi 'app này giúp dcg gi'")

    requirement_reply = router.chat_assistant('giúp mình bóc requirement cho chatbot', [], {})
    normalized_requirement = requirement_reply.lower()
    assert any(token in normalized_requirement for token in ('requirement', 'yêu cầu', 'acceptance criteria', 'scope')), \
        f"Chatbot phải hỗ trợ requirement, nhưng nhận: {requirement_reply}"
    print("  ✅ Chatbot fallback: trả lời được câu hỏi requirement")

    class _FakeResponse:
        def __init__(self, text):
            self.text = text

    class _FakeModels:
        def __init__(self):
            self.calls = []

        def generate_content(self, model, contents, config):
            self.calls.append(model)
            if model == 'gemini-2.5-pro':
                raise Exception("404 NOT_FOUND: model is not supported")
            return _FakeResponse('{"ok": true}')

    class _FakeClient:
        def __init__(self):
            self.models = _FakeModels()

    router_retry = LLMRouter()
    router_retry.client = _FakeClient()
    router_retry.model_sequences = {
        'fast': ['gemini-2.5-flash'],
        'reasoning': ['gemini-2.5-pro'],
        'fallback': ['gemini-2.5-flash'],
    }
    retry_text = router_retry._call_gemini('test prompt', 'system', model_tier='reasoning')
    assert retry_text == '{"ok": true}', f"Router phải fallback sang model kế tiếp khi model đầu 404, nhưng nhận: {retry_text}"
    assert router_retry._last_working_model == 'gemini-2.5-flash', f"Model working cuối cùng phải là fallback flash, nhưng = {router_retry._last_working_model}"
    print("  ✅ Gemini router: tự fallback sang model dự phòng khi model đầu không hỗ trợ")

    passed += 1
    print("  ✅ PASS — AI insight fallback và chatbot heuristic hoạt động đúng!")

except Exception as e:
    errors.append(f"AI Insight/Chatbot: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 9: Market Client Contract ────────────────────
print("\n📈 Test 9: Market Client contract")
try:
    from backend.data.vnstock_client import VnstockClient

    client = VnstockClient()
    assert client.CACHE_TTL_SECONDS == 300, f"Cache TTL phải là 300s, nhưng = {client.CACHE_TTL_SECONDS}"

    demo_history = client._make_demo_ohlcv('VNINDEX', days=3)
    required_history_keys = {'symbol', 'dates', 'open', 'high', 'low', 'close', 'volume'}
    assert required_history_keys.issubset(demo_history.keys()), f"OHLCV demo thiếu key: {required_history_keys - set(demo_history.keys())}"
    assert demo_history['symbol'] == 'VNINDEX', f"Symbol phải là VNINDEX, nhưng = {demo_history['symbol']}"
    assert len(demo_history['dates']) == 3, f"Phải có đúng 3 daily bars, nhưng = {len(demo_history['dates'])}"
    assert len(demo_history['close']) == len(demo_history['open']) == len(demo_history['high']) == len(demo_history['low']) == len(demo_history['volume']) == 3
    print("  ✅ Demo OHLCV fallback: đúng shape cho frontend")

    snapshot = client._build_snapshot_from_history('VNINDEX', demo_history)
    required_snapshot_keys = {'symbol', 'price', 'previous_close', 'open', 'high', 'low', 'volume', 'change', 'change_pct', 'timestamp'}
    assert snapshot and required_snapshot_keys.issubset(snapshot.keys()), f"Snapshot thiếu key: {required_snapshot_keys - set((snapshot or {}).keys())}"
    assert snapshot['symbol'] == 'VNINDEX', f"Snapshot symbol phải là VNINDEX, nhưng = {snapshot['symbol']}"
    print("  ✅ Latest price snapshot: đúng response contract")

    demo_symbols = client._demo_symbols()
    assert any(item['symbol'] == 'VNINDEX' for item in demo_symbols), "Demo symbol universe phải có VNINDEX"
    print("  ✅ Search fallback universe: có VNINDEX để giữ search/search-fallback ổn định")

    passed += 1
    print("  ✅ PASS — Market client giữ đúng contract backend/frontend!")

except Exception as e:
    errors.append(f"Market Client: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 10: Rate Limiting Contract ───────────────────
print("\n⏱️ Test 10: Rate limiting contract")
try:
    import json as _json
    import importlib.util
    from types import SimpleNamespace
    fastapi_available = importlib.util.find_spec('fastapi') is not None
    jose_available = importlib.util.find_spec('jose') is not None

    if fastapi_available and jose_available:
        from backend.main import (
            _fallback_rate_limiter_for_request,
            _rate_limit_response,
            general_rate_limiter,
            auth_rate_limiter,
            agent_rate_limiter,
        )

        agent_request = SimpleNamespace(method='POST', url=SimpleNamespace(path='/api/agent/trigger'))
        login_request = SimpleNamespace(method='POST', url=SimpleNamespace(path='/api/auth/login'))
        signup_request = SimpleNamespace(method='POST', url=SimpleNamespace(path='/api/auth/signup'))
        market_request = SimpleNamespace(method='GET', url=SimpleNamespace(path='/api/market/VCB'))

        assert _fallback_rate_limiter_for_request(agent_request) is agent_rate_limiter, "Agent trigger phải dùng bucket 5 req/min"
        assert _fallback_rate_limiter_for_request(login_request) is auth_rate_limiter, "Login phải dùng bucket 10 req/min"
        assert _fallback_rate_limiter_for_request(signup_request) is auth_rate_limiter, "Signup phải dùng bucket 10 req/min"
        assert _fallback_rate_limiter_for_request(market_request) is general_rate_limiter, "General endpoint phải dùng bucket 60 req/min"
        print("  ✅ Route buckets: đúng mapping general/auth/agent")

        response = _rate_limit_response(7)
        payload = _json.loads(response.body.decode())
        assert response.status_code == 429, f"Status code phải là 429, nhưng = {response.status_code}"
        assert payload == {"detail": "Rate limit exceeded. Try again in 7s."}, f"JSON 429 sai format: {payload}"
        assert response.headers.get("Retry-After") == "7", f"Retry-After header phải là 7, nhưng = {response.headers.get('Retry-After')}"
        print("  ✅ 429 response: đúng JSON + Retry-After header")
    else:
        main_source = (repo_root / 'backend' / 'main.py').read_text()
        assert 'slowapi' in main_source, "main.py phải import slowapi"
        assert 'default_limits=["60/minute"]' in main_source, "General limit 60/min chưa được cấu hình"
        assert '@limit_decorator("5/minute")' in main_source, "Agent trigger phải có limit 5/minute"
        assert main_source.count('@limit_decorator("10/minute")') >= 2, "Login và signup phải có limit 10/minute"
        assert 'Rate limit exceeded. Try again in' in main_source, "429 JSON contract chưa có trong main.py"
        print("  ✅ Static contract check: slowapi config + 429 message đã có trong source")

    passed += 1
    print("  ✅ PASS — Rate limiting giữ đúng contract backend!")

except Exception as e:
    errors.append(f"Rate Limiting: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 11: JWT Auth Contract ─────────────────────────
print("\n🔐 Test 11: JWT auth contract")
try:
    main_source = (repo_root / 'backend' / 'main.py').read_text()
    config_source = (repo_root / 'backend' / 'config.py').read_text()
    env_source = (repo_root / '.env.example').read_text()
    req_source = (repo_root / 'requirements.txt').read_text()

    assert 'python-jose' in req_source, "requirements.txt phải có python-jose"
    assert 'SECRET_KEY=' in env_source, ".env.example phải khai báo SECRET_KEY"
    assert 'jwt_secret_key' in config_source, "config.py phải expose jwt_secret_key"
    assert 'HTTPBearer' in main_source and 'Depends(get_current_user)' in main_source, "main.py phải dùng Bearer auth dependency"
    assert '"access_token"' in main_source and '"token_type"' in main_source, "login/signup phải trả về access_token + token_type"
    for route in [
        '@app.get("/api/auth/me")',
        '@app.post("/api/portfolio/update")',
        '@app.get("/api/portfolio")',
        '@app.get("/api/portfolio/risk")',
        '@app.get("/api/insights")',
        '@app.get("/api/predictions")',
        '@app.get("/api/predictions/history")',
    ]:
        assert route in main_source, f"Thiếu protected route JWT mới: {route}"
    assert '/api/portfolio/{user_id}' not in main_source, "Portfolio endpoint cũ theo user_id phải được bỏ"
    assert 'payload.user_id' not in main_source, "Agent trigger không được lấy user_id từ body nữa"
    print("  ✅ JWT dependencies/config: đã có SECRET_KEY + python-jose")
    print("  ✅ Protected routes: đã chuyển sang current-user context")

    passed += 1
    print("  ✅ PASS — JWT auth contract giữ đúng yêu cầu!")

except Exception as e:
    errors.append(f"JWT Auth: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 12: No Demo Masking On Authenticated Screens ───
print("\n🧪 Test 12: No demo masking on authenticated screens")
try:
    main_source = (repo_root / 'backend' / 'main.py').read_text()
    orchestrator_source = (repo_root / 'backend' / 'agent' / 'orchestrator.py').read_text()
    api_source = (repo_root / 'frontend' / 'js' / 'api.js').read_text()
    app_source = (repo_root / 'frontend' / 'js' / 'app.js').read_text()
    components_source = (repo_root / 'frontend' / 'js' / 'components.js').read_text()
    charts_source = (repo_root / 'frontend' / 'js' / 'charts.js').read_text()
    index_source = (repo_root / 'frontend' / 'index.html').read_text()

    assert 'mock_portfolio' not in main_source, "backend/main.py không được mock portfolio khi save lỗi"
    assert 'demo_mode' not in main_source, "Portfolio update không được trả demo_mode success giả"
    assert 'mock_portfolio' not in orchestrator_source, "Agent orchestrator không được rơi về mock_portfolio nữa"
    assert "return this.hasAccessToken() ? this.getDemoPortfolio() : null;" not in api_source, "getPortfolio không được fallback sang demo sau khi login"
    assert "return this.hasAccessToken() ? this.getDemoPortfolioRisk() : null;" not in api_source, "getPortfolioRisk không được fallback sang demo sau khi login"
    assert "return this.getDemoAgentResult();" not in api_source, "triggerAgent không được fallback sang demo result"
    assert 'class RiskismAPIError extends Error' in api_source, "API client phải có structured error cho protected endpoints"
    assert 'UI.renderLiveSyncIssue' in app_source, "App phải render trạng thái lỗi thật khi chưa có snapshot"
    assert "this.updateStatusBar('connected');" in app_source, "App vẫn phải cập nhật lại trạng thái connected khi sync thành công"
    assert "this.loadAllData();\n            this.updateStatusBar('connected');" not in app_source, "Không được ép status bar về connected mỗi chu kỳ poll"
    assert 'showAIUnavailable' in components_source and 'renderLiveSyncIssue' in components_source, "UI phải có trạng thái degraded thay vì sample data"
    assert 'WAITING FOR LIVE DATA' in index_source, "index.html phải bỏ sample placeholder và dùng live-state placeholder"
    assert '_placeholderSeries' in charts_source and '_generateSmoothCurve' not in charts_source, "charts không được vẽ demo sparkline khi chưa có data"
    print("  ✅ Protected UI/API: không còn fallback demo sau khi user đã đăng nhập")
    print("  ✅ Dashboard placeholders: chuyển sang live-state/degraded-state rõ ràng")

    passed += 1
    print("  ✅ PASS — Authenticated flow không còn che lỗi bằng dữ liệu demo!")

except Exception as e:
    errors.append(f"No Demo Masking: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 13: Deploy Config & Observability Contract ─────
print("\n🛰️ Test 13: Deploy config & observability")
try:
    main_source = (repo_root / 'backend' / 'main.py').read_text()
    config_source = (repo_root / 'backend' / 'config.py').read_text()
    env_source = (repo_root / '.env.example').read_text()
    api_source = (repo_root / 'frontend' / 'js' / 'api.js').read_text()
    index_source = (repo_root / 'frontend' / 'index.html').read_text()
    nginx_source = (repo_root / 'nginx.conf').read_text()
    compose_source = (repo_root / 'docker-compose.yml').read_text()

    assert '@app.get("/api/health/live")' in main_source, "Thiếu liveness endpoint /api/health/live"
    assert '@app.get("/api/health/ready")' in main_source, "Thiếu readiness endpoint /api/health/ready"
    assert 'X-Request-ID' in main_source and 'X-Process-Time-Ms' in main_source, "Backend phải gắn request tracing headers"
    assert 'content={"detail": str(exc), "type": type(exc).__name__}' not in main_source, "Global error handler không được leak raw exception ra client"
    assert 'expose_internal_errors' in config_source and 'EXPOSE_INTERNAL_ERRORS=' in env_source, "Config phải có cờ expose_internal_errors"
    assert "http://localhost:8000" not in api_source and "ws://localhost:8000" not in api_source, "Frontend không được hardcode localhost backend nữa"
    assert 'riskism-api-base' in index_source and 'riskism-ws-base' in index_source, "Frontend phải có runtime config hooks cho API/WS base"
    assert 'wss:' in api_source and 'window.location.host' in api_source, "WebSocket base phải protocol-safe cho HTTPS"
    assert 'proxy_set_header X-Request-ID $request_id;' in nginx_source, "Nginx phải forward X-Request-ID vào backend"
    assert 'healthcheck:' in compose_source and '/api/health/live' in compose_source, "docker-compose phải có backend healthcheck thật"
    print("  ✅ Backend observability: request tracing + safe error handling + live/ready healthcheck")
    print("  ✅ Frontend/proxy deploy config: bỏ hardcode localhost, dùng runtime config + request-id forwarding")

    passed += 1
    print("  ✅ PASS — Deploy config & observability contract đã được khóa!")

except Exception as e:
    errors.append(f"Deploy Config/Observability: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── TEST 14: Security Hardening Contract ────────────────
print("\n🛡️ Test 14: Security hardening contract")
try:
    main_source = (repo_root / 'backend' / 'main.py').read_text()
    config_source = (repo_root / 'backend' / 'config.py').read_text()
    env_source = (repo_root / '.env.example').read_text()

    assert 'TrustedHostMiddleware' in main_source, "Backend phải bật TrustedHostMiddleware"
    assert 'allow_origins=["*"]' not in main_source, "CORS không được dùng wildcard origins nữa"
    assert 'allow_credentials=True' not in main_source, "CORS không nên bật credentials khi đang dùng Bearer token"
    assert 'settings.cors_allowed_origin_list' in main_source, "CORS phải đọc origin allowlist từ config"
    assert 'settings.trusted_host_list' in main_source, "Trusted hosts phải đọc từ config"
    assert 'cors_allowed_origins' in config_source and 'trusted_hosts' in config_source, "config.py phải có cors_allowed_origins + trusted_hosts"
    assert 'CORS_ALLOWED_ORIGINS=' in env_source and 'TRUSTED_HOSTS=' in env_source, ".env.example phải khai báo CORS_ALLOWED_ORIGINS + TRUSTED_HOSTS"
    assert 'def _audit_log(' in main_source, "Backend phải có helper audit log"
    for action in [
        '"auth.login"',
        '"auth.signup"',
        '"auth.firebase_login"',
        '"portfolio.update"',
        '"agent.trigger"',
        '"chat.reply"',
    ]:
        assert action in main_source, f"Thiếu audit action {action}"
    assert 'detail=str(e)' not in main_source, "Backend không được trả raw exception detail ra client"
    assert 'Agent analysis failed right now. Please try again shortly.' in main_source, "Agent trigger phải trả 500 message an toàn"
    assert 'Chat assistant is unavailable right now. Please try again shortly.' in main_source, "Chat endpoint phải trả 500 message an toàn"
    print("  ✅ CORS/trusted-host: đã chuyển sang allowlist có cấu hình qua env")
    print("  ✅ Audit logging: đã có cho auth, portfolio, agent, chat")
    print("  ✅ Safe errors: không còn leak raw exception detail ở route nhạy cảm")

    passed += 1
    print("  ✅ PASS — Security hardening contract đã được khóa!")

except Exception as e:
    errors.append(f"Security Hardening: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── KẾT QUẢ TỔNG ────────────────────────────────────────
print("\n" + "=" * 60)
print(f"📊 KẾT QUẢ: {passed}/14 tests PASSED")
if errors:
    print(f"❌ LỖI ({len(errors)}):")
    for e in errors:
        print(f"   - {e}")
else:
    print("✅ TẤT CẢ ĐỀU ĐÚNG! Code backend hoạt động chính xác.")
print("=" * 60)
