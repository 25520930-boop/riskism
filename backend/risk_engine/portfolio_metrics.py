"""
Riskism Risk Engine - Portfolio Metrics
Portfolio-level risk analysis: concentration, diversification, sector exposure.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from backend.risk_engine.capital_aware import SECTOR_MAP


@dataclass
class PortfolioMetrics:
    """Container for portfolio-level risk metrics."""
    hhi: float                                  # Herfindahl-Hirschman Index
    effective_n: float                          # Effective number of stocks
    sector_exposure: Dict[str, float]           # Weight per sector
    max_sector_weight: float                    # Highest sector concentration
    total_value: float                          # Total portfolio value
    diversification_score: int                  # 0-100
    correlation_matrix: Optional[Dict] = None   # Pairwise correlations
    rolling_correlation_vnindex: Optional[float] = None
    rolling_correlation_vn30: Optional[float] = None
    benchmark_sector_exposure: Dict[str, float] = field(default_factory=dict)
    sector_gap_vs_vn30: Dict[str, float] = field(default_factory=dict)
    volatility_regime: str = "normal"           # low/normal/high/extreme

    def to_dict(self) -> Dict:
        return {
            'hhi': round(self.hhi, 4),
            'effective_n': round(self.effective_n, 2),
            'sector_exposure': self.sector_exposure,
            'max_sector_weight': round(self.max_sector_weight, 4),
            'total_value': round(self.total_value, 2),
            'diversification_score': self.diversification_score,
            'rolling_correlation_vnindex': round(self.rolling_correlation_vnindex, 4) if self.rolling_correlation_vnindex is not None else None,
            'rolling_correlation_vn30': round(self.rolling_correlation_vn30, 4) if self.rolling_correlation_vn30 is not None else None,
            'benchmark_sector_exposure': self.benchmark_sector_exposure,
            'sector_gap_vs_vn30': self.sector_gap_vs_vn30,
            'volatility_regime': self.volatility_regime,
        }


def _holding_value(holding: Dict) -> float:
    """Prefer live market value when available, then latest price, then avg price."""
    if holding.get('market_value') is not None:
        try:
            value = float(holding['market_value'])
            if np.isfinite(value) and value >= 0:
                return value
        except (TypeError, ValueError):
            pass

    quantity = float(holding.get('quantity', 0) or 0)
    latest_price = holding.get('latest_price')
    if latest_price is not None:
        try:
            value = quantity * float(latest_price)
            if np.isfinite(value) and value >= 0:
                return value
        except (TypeError, ValueError):
            pass

    avg_price = float(holding.get('avg_price', 0) or 0)
    value = quantity * avg_price
    return value if np.isfinite(value) and value >= 0 else 0.0


def calculate_hhi(weights: np.ndarray) -> float:
    """
    Herfindahl-Hirschman Index - measures portfolio concentration.
    Range: 1/N (perfectly diversified) to 1.0 (single stock)
    HHI > 0.25 = highly concentrated
    HHI < 0.15 = well diversified
    """
    if len(weights) == 0:
        return 1.0
    normalized = weights / np.sum(weights)
    return float(np.sum(normalized ** 2))


def calculate_effective_n(hhi: float) -> float:
    """
    Effective number of stocks = 1 / HHI.
    Tells you: "your portfolio behaves like N equally-weighted stocks."
    """
    if hhi == 0:
        return 0.0
    return 1.0 / hhi


def calculate_sector_exposure(holdings: List[Dict]) -> Dict[str, float]:
    """
    Calculate weight of each sector in portfolio.
    Input: [{'symbol': 'VCB', 'sector': 'Banking', 'value': 5000000}, ...]
    """
    if not holdings:
        return {}

    total = sum(h.get('value', 0) for h in holdings)
    if total == 0:
        return {}

    sector_values = {}
    for h in holdings:
        symbol = str(h.get('symbol', '')).strip().upper()
        sector = h.get('sector') or SECTOR_MAP.get(symbol, 'Unknown')
        if sector == 'Unknown' and symbol:
            sector = SECTOR_MAP.get(symbol, 'Unknown')
        sector_values[sector] = sector_values.get(sector, 0) + h.get('value', 0)

    return {sector: round(value / total, 4) for sector, value in sector_values.items()}


def build_sector_benchmark_exposure(
    symbols: List[str],
    sector_map: Optional[Dict[str, str]] = None,
) -> Dict[str, float]:
    """
    Build an equal-weight sector benchmark from a list of symbols.
    Used for VN30 sector gap analysis when market-cap weights are unavailable.
    """
    sector_map = sector_map or SECTOR_MAP
    normalized = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    if not normalized:
        return {}

    counts: Dict[str, int] = {}
    for symbol in normalized:
        sector = sector_map.get(symbol, 'Unknown')
        counts[sector] = counts.get(sector, 0) + 1

    total = sum(counts.values())
    if total <= 0:
        return {}

    return {
        sector: round(count / total, 4)
        for sector, count in sorted(counts.items(), key=lambda item: item[0])
    }


def calculate_sector_gap(
    portfolio_exposure: Dict[str, float],
    benchmark_exposure: Dict[str, float],
) -> Dict[str, float]:
    """Portfolio sector overweight/underweight relative to benchmark exposure."""
    sectors = sorted(set(portfolio_exposure.keys()) | set(benchmark_exposure.keys()))
    gaps = {}
    for sector in sectors:
        gaps[sector] = round(
            float(portfolio_exposure.get(sector, 0.0) - benchmark_exposure.get(sector, 0.0)),
            4
        )
    return gaps


def calculate_rolling_correlation(
    stock_returns: np.ndarray,
    market_returns: np.ndarray,
    window: int = 20
) -> float:
    """
    Rolling correlation with VN-Index (default 20-day window).
    High correlation = portfolio moves with market (less diversification benefit).
    """
    if len(stock_returns) < window or len(market_returns) < window:
        return 0.0

    min_len = min(len(stock_returns), len(market_returns))
    s = stock_returns[-min_len:]
    m = market_returns[-min_len:]

    # Use last `window` days
    s_window = s[-window:]
    m_window = m[-window:]

    corr_matrix = np.corrcoef(s_window, m_window)
    return float(corr_matrix[0, 1])


def detect_volatility_regime(returns: np.ndarray, window: int = 20) -> str:
    """
    Detect current volatility regime based on recent vs historical volatility.
    Returns: 'low', 'normal', 'high', 'extreme'
    """
    if len(returns) < window * 2:
        return "normal"

    recent_vol = np.std(returns[-window:])
    historical_vol = np.std(returns)

    ratio = recent_vol / historical_vol if historical_vol > 0 else 1.0

    if ratio < 0.5:
        return "low"
    elif ratio < 1.2:
        return "normal"
    elif ratio < 2.0:
        return "high"
    else:
        return "extreme"


def calculate_portfolio_correlation_matrix(
    returns_dict: Dict[str, np.ndarray]
) -> Dict[str, Dict[str, float]]:
    """
    Calculate pairwise correlations between all stocks in portfolio.
    Detects hidden correlations that increase risk.
    
    Input: {'VCB': returns_array, 'TCB': returns_array, ...}
    """
    symbols = list(returns_dict.keys())
    if len(symbols) < 2:
        return {}

    # Align all return series to same length
    min_len = min(len(r) for r in returns_dict.values())
    aligned = {s: returns_dict[s][-min_len:] for s in symbols}

    matrix = {}
    for i, s1 in enumerate(symbols):
        matrix[s1] = {}
        for j, s2 in enumerate(symbols):
            if i == j:
                matrix[s1][s2] = 1.0
            else:
                corr = np.corrcoef(aligned[s1], aligned[s2])[0, 1]
                matrix[s1][s2] = round(float(corr), 4)

    return matrix


def calculate_diversification_score(
    hhi: float,
    sector_exposure: Dict[str, float],
    correlation_matrix: Optional[Dict] = None
) -> int:
    """
    Composite diversification score (0-100).
    100 = perfectly diversified, 0 = extremely concentrated.
    """
    score = 50

    # HHI contribution (lower = better diversified)
    if hhi < 0.1:
        score += 20
    elif hhi < 0.15:
        score += 10
    elif hhi > 0.4:
        score -= 20
    elif hhi > 0.25:
        score -= 10

    # Sector diversity
    num_sectors = len(sector_exposure)
    if num_sectors >= 5:
        score += 15
    elif num_sectors >= 3:
        score += 5
    elif num_sectors == 1:
        score -= 15

    # Max sector concentration
    max_sector = max(sector_exposure.values()) if sector_exposure else 1.0
    if max_sector > 0.6:
        score -= 10
    elif max_sector < 0.3:
        score += 10

    # Correlation penalty (high avg correlation = low diversification)
    if correlation_matrix:
        correlations = []
        symbols = list(correlation_matrix.keys())
        for i, s1 in enumerate(symbols):
            for j, s2 in enumerate(symbols):
                if i < j:
                    correlations.append(abs(correlation_matrix[s1][s2]))
        if correlations:
            avg_corr = np.mean(correlations)
            if avg_corr > 0.7:
                score -= 15
            elif avg_corr > 0.5:
                score -= 5
            elif avg_corr < 0.3:
                score += 10

    return max(0, min(100, score))


def compute_portfolio_metrics(
    holdings: List[Dict],
    returns_dict: Dict[str, np.ndarray],
    market_returns: Optional[np.ndarray] = None,
    benchmark_returns: Optional[np.ndarray] = None,
    benchmark_sector_exposure: Optional[Dict[str, float]] = None,
) -> PortfolioMetrics:
    """
    Compute all portfolio-level risk metrics.
    
    Args:
        holdings: [{'symbol': 'VCB', 'quantity': 100, 'avg_price': 85.5, 'sector': 'Banking'}, ...]
        returns_dict: {'VCB': np.array([...]), 'TCB': np.array([...]), ...}
        market_returns: Optional VN-Index returns for correlation
        benchmark_returns: Optional VN30 returns for benchmark correlation
        benchmark_sector_exposure: Optional benchmark sector weights, e.g. VN30
    """
    # Calculate values and weights
    for h in holdings:
        h['value'] = _holding_value(h)
    
    total_value = sum(h['value'] for h in holdings)
    weights = np.array([h['value'] / total_value if total_value > 0 else 0 for h in holdings])

    # Core metrics
    hhi = calculate_hhi(weights)
    effective_n = calculate_effective_n(hhi)
    sector_exposure = calculate_sector_exposure(holdings)
    max_sector_weight = max(sector_exposure.values()) if sector_exposure else 0.0

    # Correlation matrix
    corr_matrix = calculate_portfolio_correlation_matrix(returns_dict) if returns_dict else None

    portfolio_returns = None
    if returns_dict:
        portfolio_series = []
        for h, weight in zip(holdings, weights):
            symbol = h['symbol']
            returns = returns_dict.get(symbol)
            if returns is None or len(returns) == 0:
                continue
            portfolio_series.append((weight, np.asarray(returns, dtype=float)))

        if portfolio_series:
            min_len = min(len(series) for _, series in portfolio_series)
            if min_len > 0:
                portfolio_returns = np.zeros(min_len, dtype=float)
                for weight, series in portfolio_series:
                    portfolio_returns += weight * series[-min_len:]

    # Rolling correlation with VN-Index / VN30 (portfolio-level)
    rolling_corr_vnindex = None
    if market_returns is not None and portfolio_returns is not None:
        rolling_corr_vnindex = calculate_rolling_correlation(portfolio_returns, market_returns)

    rolling_corr_vn30 = None
    if benchmark_returns is not None and portfolio_returns is not None:
        rolling_corr_vn30 = calculate_rolling_correlation(portfolio_returns, benchmark_returns)

    # Volatility regime (portfolio-level)
    vol_regime = "normal"
    if portfolio_returns is not None and len(portfolio_returns) > 0:
        vol_regime = detect_volatility_regime(portfolio_returns)

    # Diversification score
    div_score = calculate_diversification_score(hhi, sector_exposure, corr_matrix)
    benchmark_sector_exposure = benchmark_sector_exposure or {}
    sector_gap_vs_vn30 = calculate_sector_gap(sector_exposure, benchmark_sector_exposure) if benchmark_sector_exposure else {}

    return PortfolioMetrics(
        hhi=hhi,
        effective_n=effective_n,
        sector_exposure=sector_exposure,
        max_sector_weight=max_sector_weight,
        total_value=total_value,
        diversification_score=div_score,
        correlation_matrix=corr_matrix,
        rolling_correlation_vnindex=rolling_corr_vnindex,
        rolling_correlation_vn30=rolling_corr_vn30,
        benchmark_sector_exposure=benchmark_sector_exposure,
        sector_gap_vs_vn30=sector_gap_vs_vn30,
        volatility_regime=vol_regime,
    )
