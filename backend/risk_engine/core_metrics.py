"""
Riskism Risk Engine - Core Metrics
Pure mathematical calculations using numpy/scipy.
No LLM involved - ensures accuracy and no hallucination.
"""
import numpy as np
from scipy import stats
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class RiskMetrics:
    """Container for all risk metrics of a single asset."""
    symbol: str
    var_95: float          # Value at Risk (95%)
    var_99: float          # Value at Risk (99%)
    cvar_95: float         # Conditional VaR (95%)
    cvar_99: float         # Conditional VaR (99%)
    beta: float            # Beta vs VN-Index
    sharpe_ratio: float    # Sharpe Ratio
    sortino_ratio: float   # Sortino Ratio
    calmar_ratio: float    # Calmar Ratio (annualized return / max drawdown)
    information_ratio: float  # Information Ratio (excess return vs benchmark / tracking error)
    max_drawdown: float    # Maximum Drawdown
    drawdown_duration: int # Days from peak to recovery
    volatility: float      # Annualized volatility
    daily_volatility: float
    avg_return: float      # Average daily return
    risk_score: int        # Overall risk score (0-100)

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'var_95': round(self.var_95, 4),
            'var_99': round(self.var_99, 4),
            'cvar_95': round(self.cvar_95, 4),
            'cvar_99': round(self.cvar_99, 4),
            'beta': round(self.beta, 4),
            'sharpe_ratio': round(self.sharpe_ratio, 4),
            'sortino_ratio': round(self.sortino_ratio, 4),
            'calmar_ratio': round(self.calmar_ratio, 4),
            'information_ratio': round(self.information_ratio, 4),
            'max_drawdown': round(self.max_drawdown, 4),
            'drawdown_duration': self.drawdown_duration,
            'volatility': round(self.volatility, 4),
            'daily_volatility': round(self.daily_volatility, 4),
            'avg_return': round(self.avg_return, 6),
            'risk_score': self.risk_score,
        }


def calculate_returns(prices: np.ndarray) -> np.ndarray:
    """Calculate daily log returns from price series."""
    if len(prices) < 2:
        return np.array([])
    return np.diff(np.log(prices))


def calculate_var(returns: np.ndarray, confidence: float = 0.95) -> float:
    """
    Historical Value at Risk.
    Negative value represents potential loss.
    """
    if len(returns) == 0:
        return 0.0
    return float(np.percentile(returns, (1 - confidence) * 100))


def calculate_cvar(returns: np.ndarray, confidence: float = 0.95) -> float:
    """
    Conditional Value at Risk (Expected Shortfall).
    Mean of returns below the VaR threshold.
    """
    if len(returns) == 0:
        return 0.0
    var = calculate_var(returns, confidence)
    tail_returns = returns[returns <= var]
    if len(tail_returns) == 0:
        return var
    return float(np.mean(tail_returns))


def calculate_beta(stock_returns: np.ndarray, market_returns: np.ndarray) -> float:
    """
    Beta coefficient: measures systematic risk relative to market (VN-Index).
    Beta > 1: more volatile than market
    Beta < 1: less volatile than market
    Beta < 0: moves opposite to market
    """
    if len(stock_returns) < 2 or len(market_returns) < 2:
        return 1.0

    # Align lengths
    min_len = min(len(stock_returns), len(market_returns))
    s = np.asarray(stock_returns[-min_len:], dtype=float)
    m = np.asarray(market_returns[-min_len:], dtype=float)

    finite_mask = np.isfinite(s) & np.isfinite(m)
    s = s[finite_mask]
    m = m[finite_mask]
    if len(s) < 2:
        return 1.0

    # Use a consistent population-style estimator for both covariance and variance.
    s_centered = s - np.mean(s)
    m_centered = m - np.mean(m)
    market_variance = float(np.mean(m_centered ** 2))
    if market_variance <= 0:
        return 1.0

    covariance = float(np.mean(s_centered * m_centered))
    return float(covariance / market_variance)


def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.035) -> float:
    """
    Sharpe Ratio: risk-adjusted return.
    Uses annualized values. Risk-free rate default = 3.5% (VN gov bond approximate).
    """
    if len(returns) == 0 or np.std(returns) == 0:
        return 0.0
    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    return float(np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252))


def calculate_sortino_ratio(returns: np.ndarray, risk_free_rate: float = 0.035) -> float:
    """
    Sortino Ratio: like Sharpe but only penalizes downside volatility.
    Better measure for asymmetric return distributions.
    """
    if len(returns) == 0:
        return 0.0
    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    downside_returns = excess_returns[excess_returns < 0]
    if len(downside_returns) == 0 or np.std(downside_returns) == 0:
        return float(np.mean(excess_returns) * np.sqrt(252)) if np.mean(excess_returns) > 0 else 0.0
    downside_std = np.std(downside_returns)
    return float(np.mean(excess_returns) / downside_std * np.sqrt(252))


def calculate_max_drawdown(prices: np.ndarray) -> Tuple[float, int]:
    """
    Maximum Drawdown & Duration.
    Returns (max_drawdown_percentage, duration_in_days).
    Duration is measured from the peak that started the max drawdown
    until recovery back to that peak. If recovery has not happened yet,
    duration extends to the latest observation.
    """
    if len(prices) < 2:
        return 0.0, 0

    prices = np.asarray(prices, dtype=float)
    peak = prices[0]
    peak_idx = 0
    max_dd = 0.0
    max_dd_peak = peak
    max_dd_peak_idx = 0
    max_dd_trough_idx = 0

    for i in range(1, len(prices)):
        if prices[i] >= peak:
            peak = prices[i]
            peak_idx = i

        drawdown = (peak - prices[i]) / peak
        if drawdown > max_dd:
            max_dd = drawdown
            max_dd_peak = peak
            max_dd_peak_idx = peak_idx
            max_dd_trough_idx = i

    if max_dd == 0:
        return 0.0, 0

    recovery_idx = None
    for i in range(max_dd_trough_idx + 1, len(prices)):
        if prices[i] >= max_dd_peak:
            recovery_idx = i
            break

    if recovery_idx is None:
        duration = len(prices) - 1 - max_dd_peak_idx
    else:
        duration = recovery_idx - max_dd_peak_idx

    return float(max_dd), int(duration)


def calculate_calmar_ratio(returns: np.ndarray, max_drawdown: float) -> float:
    """
    Calmar Ratio: annualized return / maximum drawdown.
    Higher is better — measures return per unit of drawdown risk.
    Typically, Calmar > 3 is excellent, < 1 is poor.
    """
    if len(returns) == 0 or max_drawdown == 0:
        return 0.0
    annualized_return = float(np.mean(returns) * 252)
    return float(annualized_return / abs(max_drawdown))


def calculate_information_ratio(
    stock_returns: np.ndarray,
    market_returns: np.ndarray
) -> float:
    """
    Information Ratio: excess return over benchmark / tracking error.
    Measures consistency of alpha generation vs VN-Index.
    IR > 0.5 is good, > 1.0 is excellent.
    """
    if len(stock_returns) < 2 or len(market_returns) < 2:
        return 0.0
    min_len = min(len(stock_returns), len(market_returns))
    s = stock_returns[-min_len:]
    m = market_returns[-min_len:]
    excess = s - m
    tracking_error = float(np.std(excess))
    if tracking_error == 0:
        return 0.0
    return float(np.mean(excess) / tracking_error * np.sqrt(252))


def calculate_volatility(returns: np.ndarray) -> Tuple[float, float]:
    """
    Calculate daily and annualized volatility.
    Returns (annualized_volatility, daily_volatility).
    """
    if len(returns) == 0:
        return 0.0, 0.0
    daily_vol = float(np.std(returns))
    annual_vol = daily_vol * np.sqrt(252)
    return annual_vol, daily_vol


def _prepare_price_series(data: Dict) -> Tuple[List[str], Dict[str, float]]:
    """
    Normalize an OHLCV payload into an ordered date list and date->close map.
    Invalid or non-positive prices are discarded.
    """
    dates = data.get('dates', []) or []
    closes = data.get('close', []) or []
    if len(dates) != len(closes):
        return [], {}

    ordered_dates: List[str] = []
    date_to_close: Dict[str, float] = {}
    for raw_date, raw_close in zip(dates, closes):
        try:
            close = float(raw_close)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(close) or close <= 0:
            continue
        # Some sources return date-only strings while others include a time component.
        # Normalize both to YYYY-MM-DD so multi-asset alignment still works.
        date = str(raw_date).strip()[:10]
        if len(date) != 10:
            continue
        ordered_dates.append(date)
        date_to_close[date] = close

    return ordered_dates, date_to_close


def _build_portfolio_value_series(
    holdings: List[Dict],
    market_data: Dict,
) -> Tuple[List[str], np.ndarray]:
    """
    Build the exact historical portfolio value series from quantities and prices.
    This is more accurate than weighting individual return series because it
    naturally captures offsetting moves and changing effective weights over time.
    """
    series_parts = []
    for holding in holdings:
        symbol = holding.get('symbol')
        quantity = float(holding.get('quantity', 0) or 0)
        if not symbol or quantity <= 0:
            continue

        ordered_dates, date_to_close = _prepare_price_series(market_data.get(symbol, {}))
        if len(ordered_dates) < 2:
            continue

        series_parts.append((symbol, quantity, ordered_dates, date_to_close))

    if not series_parts:
        return [], np.array([])

    common_dates = set(series_parts[0][3].keys())
    for _, _, _, date_to_close in series_parts[1:]:
        common_dates &= set(date_to_close.keys())

    if len(common_dates) < 2:
        return [], np.array([])

    ordered_common_dates = [d for d in series_parts[0][2] if d in common_dates]
    if len(ordered_common_dates) < 2:
        return [], np.array([])

    portfolio_values = []
    for date in ordered_common_dates:
        total_value = 0.0
        for _, quantity, _, date_to_close in series_parts:
            total_value += quantity * date_to_close[date]
        portfolio_values.append(total_value)

    return ordered_common_dates, np.array(portfolio_values, dtype=float)


def calculate_risk_score(metrics_dict: Dict) -> int:
    """
    Composite risk score from 0 (safest) to 100 (riskiest).
    Weighted combination of all metrics.
    """
    score = 50  # Start neutral

    # VaR contribution (higher loss = higher risk)
    var_95 = abs(metrics_dict.get('var_95', 0))
    if var_95 > 0.05:
        score += 15
    elif var_95 > 0.03:
        score += 8
    elif var_95 < 0.01:
        score -= 5

    # Beta contribution
    beta = abs(metrics_dict.get('beta', 1))
    if beta > 1.5:
        score += 12
    elif beta > 1.2:
        score += 6
    elif beta < 0.8:
        score -= 5

    # Max Drawdown contribution
    max_dd = metrics_dict.get('max_drawdown', 0)
    if max_dd > 0.4:
        score += 15
    elif max_dd > 0.25:
        score += 8
    elif max_dd < 0.1:
        score -= 8

    # Sharpe ratio contribution (higher = better = lower risk score)
    sharpe = metrics_dict.get('sharpe_ratio', 0)
    if sharpe > 1.5:
        score -= 10
    elif sharpe > 0.5:
        score -= 5
    elif sharpe < -0.5:
        score += 10

    # Volatility contribution
    volatility = metrics_dict.get('volatility', 0)
    if volatility > 0.5:
        score += 10
    elif volatility > 0.3:
        score += 5
    elif volatility < 0.15:
        score -= 5

    return max(0, min(100, score))


def compute_all_metrics(
    symbol: str,
    prices: np.ndarray,
    market_prices: Optional[np.ndarray] = None,
    risk_free_rate: float = 0.035
) -> RiskMetrics:
    """
    Compute all risk metrics for a single asset.
    
    Args:
        symbol: Stock ticker (e.g., 'VCB')
        prices: Array of closing prices (oldest first)
        market_prices: Optional VN-Index prices for Beta calculation
        risk_free_rate: Annual risk-free rate (default 3.5%)
    
    Returns:
        RiskMetrics dataclass with all computed metrics
    """
    returns = calculate_returns(prices)
    market_returns = calculate_returns(market_prices) if market_prices is not None else np.array([])

    var_95 = calculate_var(returns, 0.95)
    var_99 = calculate_var(returns, 0.99)
    cvar_95 = calculate_cvar(returns, 0.95)
    cvar_99 = calculate_cvar(returns, 0.99)
    beta = calculate_beta(returns, market_returns) if len(market_returns) > 0 else 1.0
    sharpe = calculate_sharpe_ratio(returns, risk_free_rate)
    sortino = calculate_sortino_ratio(returns, risk_free_rate)
    max_dd, dd_duration = calculate_max_drawdown(prices)
    calmar = calculate_calmar_ratio(returns, max_dd)
    info_ratio = calculate_information_ratio(returns, market_returns) if len(market_returns) > 0 else 0.0
    annual_vol, daily_vol = calculate_volatility(returns)
    avg_return = float(np.mean(returns)) if len(returns) > 0 else 0.0

    # Build metrics dict for risk score calculation
    metrics_dict = {
        'var_95': var_95,
        'beta': beta,
        'max_drawdown': max_dd,
        'sharpe_ratio': sharpe,
        'volatility': annual_vol,
    }
    risk_score = calculate_risk_score(metrics_dict)

    return RiskMetrics(
        symbol=symbol,
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        beta=beta,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        information_ratio=info_ratio,
        max_drawdown=max_dd,
        drawdown_duration=dd_duration,
        volatility=annual_vol,
        daily_volatility=daily_vol,
        avg_return=avg_return,
        risk_score=risk_score,
    )


def compute_rolling_metrics(
    prices: np.ndarray, 
    market_prices: Optional[np.ndarray] = None,
    window: int = 20,
    num_points: int = 30
) -> Dict[str, List[float]]:
    """
    Compute a time-series of risk metrics over a rolling window.
    Always returns exactly `num_points` data points for smooth sparklines.
    """
    prices = np.array(prices, dtype=float)
    n = len(prices)
    
    if n <= window + 2:
        return {'var_95': [], 'sharpe': [], 'drawdown': [], 'beta': []}
    
    # Align market prices to same length as prices (trim from front)
    market_arr = None
    if market_prices is not None:
        market_arr = np.array(market_prices, dtype=float)
        if len(market_arr) > n:
            market_arr = market_arr[-n:]
        elif len(market_arr) < n:
            # Pad with NaN at front, we'll skip beta for those windows
            pad = np.full(n - len(market_arr), np.nan)
            market_arr = np.concatenate([pad, market_arr])
    
    result = {'var_95': [], 'sharpe': [], 'drawdown': [], 'beta': []}
    
    # Calculate stride to get exactly num_points
    available_steps = n - window
    stride = max(1, available_steps // num_points)
    
    indices = list(range(window, n, stride))
    # Ensure we always include the last point
    if indices[-1] != n:
        indices.append(n)
    # Trim to num_points
    if len(indices) > num_points:
        step = len(indices) / num_points
        indices = [indices[int(i * step)] for i in range(num_points)]
    
    for i in indices:
        window_prices = prices[i-window:i]
        window_returns = calculate_returns(window_prices)
        
        if len(window_returns) < 2:
            continue
        
        # VaR (absolute % for display)
        var_val = calculate_var(window_returns, 0.95)
        result['var_95'].append(abs(round(float(var_val) * 100, 2)))
        
        # Sharpe
        result['sharpe'].append(round(calculate_sharpe_ratio(window_returns), 2))
        
        # Max Drawdown
        dd, _ = calculate_max_drawdown(window_prices)
        result['drawdown'].append(round(float(dd) * 100, 2))
        
        # Beta (with proper alignment check)
        if market_arr is not None and i <= len(market_arr):
            window_market = market_arr[i-window:i]
            if not np.any(np.isnan(window_market)) and len(window_market) == window:
                window_market_ret = calculate_returns(window_market)
                result['beta'].append(round(calculate_beta(window_returns, window_market_ret), 2))
            else:
                result['beta'].append(result['beta'][-1] if result['beta'] else 1.0)
        else:
            result['beta'].append(result['beta'][-1] if result['beta'] else 1.0)
            
    return result


def compute_portfolio_risk_summary(
    holdings: List[Dict],
    returns_dict: Dict[str, np.ndarray],
    market_data: Dict,
) -> Dict:
    """
    Shared function: compute portfolio-level current_risk + metrics_history.
    Used by both orchestrator.py and main.py to avoid code duplication.
    
    Returns: {
        'current_risk': {'var_95': ..., 'sharpe_ratio': ..., 'max_drawdown': ..., 'beta': ...},
        'metrics_history': {'var_95': [...], 'sharpe': [...], 'drawdown': [...], 'beta': [...]},
        'stock_metrics': {symbol: RiskMetrics.to_dict(), ...}
    }
    """
    symbols = [h['symbol'] for h in holdings]
    
    current_risk = {
        'var_95': 0,
        'sharpe_ratio': 0,
        'max_drawdown': 0,
        'beta': 1.0
    }
    metrics_history = {}
    stock_metrics = {}
    
    # Calculate individual stock metrics
    vnindex_data = market_data.get('VNINDEX', {})
    market_prices = np.array(vnindex_data.get('close', [])) if vnindex_data else None
    
    for symbol in symbols:
        data = market_data.get(symbol, {})
        prices = np.array(data.get('close', []))
        if len(prices) > 10:
            metrics = compute_all_metrics(symbol, prices, market_prices)
            stock_metrics[symbol] = metrics.to_dict()
    
    # Portfolio-level calculations
    valid_symbols = [s for s in symbols if s in returns_dict and len(returns_dict[s]) > 1]
    if not valid_symbols:
        return {'current_risk': current_risk, 'metrics_history': metrics_history, 'stock_metrics': stock_metrics}

    portfolio_dates, portfolio_prices = _build_portfolio_value_series(holdings, market_data)
    if len(portfolio_prices) < 2:
        return {'current_risk': current_risk, 'metrics_history': metrics_history, 'stock_metrics': stock_metrics}

    portfolio_returns = calculate_returns(portfolio_prices)
    if len(portfolio_returns) < 1:
        return {'current_risk': current_risk, 'metrics_history': metrics_history, 'stock_metrics': stock_metrics}

    current_risk['var_95'] = float(calculate_var(portfolio_returns, 0.95))
    current_risk['sharpe_ratio'] = float(calculate_sharpe_ratio(portfolio_returns))
    dd, _ = calculate_max_drawdown(portfolio_prices)
    current_risk['max_drawdown'] = float(dd)

    aligned_market_prices = None
    if vnindex_data:
        _, market_date_to_close = _prepare_price_series(vnindex_data)
        if market_date_to_close:
            aligned_dates = [d for d in portfolio_dates if d in market_date_to_close]
            if len(aligned_dates) >= 2:
                portfolio_value_map = dict(zip(portfolio_dates, portfolio_prices))
                aligned_portfolio_prices = np.array([portfolio_value_map[d] for d in aligned_dates], dtype=float)
                aligned_market_prices = np.array([market_date_to_close[d] for d in aligned_dates], dtype=float)

                market_returns = calculate_returns(aligned_market_prices)
                aligned_portfolio_returns = calculate_returns(aligned_portfolio_prices)
                if len(aligned_portfolio_returns) > 1 and len(market_returns) > 1:
                    current_risk['beta'] = float(calculate_beta(aligned_portfolio_returns, market_returns))

    # Rolling history for sparklines (need enough data points)
    if len(portfolio_prices) > 25:
        metrics_history = compute_rolling_metrics(
            portfolio_prices,
            aligned_market_prices,
            window=20,
            num_points=30
        )

    return {
        'current_risk': current_risk,
        'metrics_history': metrics_history,
        'stock_metrics': stock_metrics,
    }
