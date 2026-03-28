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
    s = stock_returns[-min_len:]
    m = market_returns[-min_len:]
    covariance = np.cov(s, m)[0][1]
    market_variance = np.var(m)
    if market_variance == 0:
        return 1.0
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
    """
    if len(prices) < 2:
        return 0.0, 0

    peak = prices[0]
    max_dd = 0.0
    max_dd_duration = 0
    current_dd_start = 0

    for i in range(1, len(prices)):
        if prices[i] > peak:
            peak = prices[i]
            current_dd_start = i
        drawdown = (peak - prices[i]) / peak
        if drawdown > max_dd:
            max_dd = drawdown
            max_dd_duration = i - current_dd_start

    return float(max_dd), int(max_dd_duration)


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
    
    total_val = sum(h.get('avg_price', 0) * h.get('quantity', 0) for h in holdings)
    weights = []
    for h in holdings:
        if total_val > 0:
            weights.append((h.get('avg_price', 0) * h.get('quantity', 0)) / total_val)
        else:
            weights.append(0)
    
    min_len = min(len(returns_dict[s]) for s in valid_symbols)
    if min_len < 2:
        return {'current_risk': current_risk, 'metrics_history': metrics_history, 'stock_metrics': stock_metrics}
    
    # Build weighted portfolio returns
    portfolio_returns = np.zeros(min_len)
    for i, h in enumerate(holdings):
        sym = h['symbol']
        if sym in returns_dict:
            portfolio_returns += weights[i] * returns_dict[sym][-min_len:]
    
    # Current risk values
    portfolio_prices = np.exp(np.cumsum(np.insert(portfolio_returns, 0, 0))) * 1000
    current_risk['var_95'] = float(calculate_var(portfolio_returns, 0.95))
    current_risk['sharpe_ratio'] = float(calculate_sharpe_ratio(portfolio_returns))
    dd, _ = calculate_max_drawdown(portfolio_prices)
    current_risk['max_drawdown'] = float(dd)
    
    # Beta vs VNINDEX
    if market_prices is not None and len(market_prices) > 1:
        market_returns = calculate_returns(market_prices)
        current_risk['beta'] = float(calculate_beta(portfolio_returns, market_returns))
    
    # Rolling history for sparklines (need enough data points)
    if min_len > 25:
        vnindex_prices = np.array(vnindex_data.get('close', [])) if vnindex_data else None
        metrics_history = compute_rolling_metrics(
            portfolio_prices,
            vnindex_prices,
            window=20,
            num_points=30
        )
    
    return {
        'current_risk': current_risk,
        'metrics_history': metrics_history,
        'stock_metrics': stock_metrics,
    }
