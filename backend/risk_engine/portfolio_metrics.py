"""
Riskism Risk Engine - Portfolio Metrics
Portfolio-level risk analysis: concentration, diversification, sector exposure.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


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
    volatility_regime: str = "normal"           # low/normal/high/extreme

    def to_dict(self) -> Dict:
        return {
            'hhi': round(self.hhi, 4),
            'effective_n': round(self.effective_n, 2),
            'sector_exposure': self.sector_exposure,
            'max_sector_weight': round(self.max_sector_weight, 4),
            'total_value': round(self.total_value, 2),
            'diversification_score': self.diversification_score,
            'rolling_correlation_vnindex': round(self.rolling_correlation_vnindex, 4) if self.rolling_correlation_vnindex else None,
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
        sector = h.get('sector', 'Unknown')
        sector_values[sector] = sector_values.get(sector, 0) + h.get('value', 0)

    return {sector: round(value / total, 4) for sector, value in sector_values.items()}


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
    market_returns: Optional[np.ndarray] = None
) -> PortfolioMetrics:
    """
    Compute all portfolio-level risk metrics.
    
    Args:
        holdings: [{'symbol': 'VCB', 'quantity': 100, 'avg_price': 85.5, 'sector': 'Banking'}, ...]
        returns_dict: {'VCB': np.array([...]), 'TCB': np.array([...]), ...}
        market_returns: Optional VN-Index returns for correlation
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

    # Rolling correlation with VN-Index (portfolio-level)
    rolling_corr = None
    if market_returns is not None and returns_dict:
        # Weighted portfolio returns
        symbols = [h['symbol'] for h in holdings]
        min_len = min(len(returns_dict.get(s, [])) for s in symbols if s in returns_dict)
        if min_len > 0:
            portfolio_returns = np.zeros(min_len)
            for i, h in enumerate(holdings):
                s = h['symbol']
                if s in returns_dict and len(returns_dict[s]) >= min_len:
                    portfolio_returns += weights[i] * returns_dict[s][-min_len:]
            rolling_corr = calculate_rolling_correlation(portfolio_returns, market_returns)

    # Volatility regime (portfolio-level)
    vol_regime = "normal"
    if returns_dict:
        symbols = [h['symbol'] for h in holdings]
        valid_returns = [returns_dict[s] for s in symbols if s in returns_dict and len(returns_dict[s]) > 0]
        if valid_returns:
            min_len = min(len(r) for r in valid_returns)
            portfolio_returns = np.zeros(min_len)
            for i, r in enumerate(valid_returns):
                portfolio_returns += weights[i] * r[-min_len:] if i < len(weights) else r[-min_len:]
            vol_regime = detect_volatility_regime(portfolio_returns)

    # Diversification score
    div_score = calculate_diversification_score(hhi, sector_exposure, corr_matrix)

    return PortfolioMetrics(
        hhi=hhi,
        effective_n=effective_n,
        sector_exposure=sector_exposure,
        max_sector_weight=max_sector_weight,
        total_value=total_value,
        diversification_score=div_score,
        correlation_matrix=corr_matrix,
        rolling_correlation_vnindex=rolling_corr,
        volatility_regime=vol_regime,
    )
