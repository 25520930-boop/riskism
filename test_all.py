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
    for pkg in ['fastapi', 'uvicorn', 'sqlalchemy', 'redis', 'celery', 'numpy', 'scipy']:
        assert pkg in reqs, f"requirements.txt thiếu: {pkg}"
    print(f"  ✅ requirements.txt: đầy đủ các thư viện")

    passed += 1
    print("  ✅ PASS — Docker & infra files đầy đủ!")

except Exception as e:
    errors.append(f"Docker/SQL: {e}")
    print(f"  ❌ FAIL: {e}")


# ─── KẾT QUẢ TỔNG ────────────────────────────────────────
print("\n" + "=" * 60)
print(f"📊 KẾT QUẢ: {passed}/7 tests PASSED")
if errors:
    print(f"❌ LỖI ({len(errors)}):")
    for e in errors:
        print(f"   - {e}")
else:
    print("✅ TẤT CẢ ĐỀU ĐÚNG! Code backend hoạt động chính xác.")
print("=" * 60)
