"""
Riskism Risk Engine - Anomaly Detector
Detect unusual market behavior: volume spikes, volatility shifts, price breakouts.
"""
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Anomaly:
    """Detected market anomaly."""
    anomaly_type: str          # 'volume_spike', 'volatility_shift', 'price_breakout', 'correlation_break'
    symbol: str
    severity: str              # 'low', 'medium', 'high', 'critical'
    description: str
    current_value: float
    threshold_value: float
    z_score: float

    def to_dict(self) -> Dict:
        return {
            'type': self.anomaly_type,
            'symbol': self.symbol,
            'severity': self.severity,
            'description': self.description,
            'current_value': round(self.current_value, 4),
            'threshold_value': round(self.threshold_value, 4),
            'z_score': round(self.z_score, 2),
        }


def detect_volume_spike(
    volumes: np.ndarray,
    symbol: str,
    window: int = 20,
    threshold_z: float = 2.5
) -> Optional[Anomaly]:
    """
    Detect unusual volume spike.
    Volume > mean + threshold_z * std = potential anomaly.
    """
    if len(volumes) < window + 1:
        return None

    historical = volumes[-(window + 1):-1]
    current = volumes[-1]
    
    mean_vol = np.mean(historical)
    std_vol = np.std(historical)

    if std_vol == 0:
        return None

    z_score = (current - mean_vol) / std_vol

    if z_score > threshold_z:
        severity = 'critical' if z_score > 4 else ('high' if z_score > 3 else 'medium')
        return Anomaly(
            anomaly_type='volume_spike',
            symbol=symbol,
            severity=severity,
            description=f'🔴 {symbol}: Khối lượng GD tăng đột biến ({z_score:.1f}σ so với TB 20 phiên). '
                        f'Hiện tại: {current:,.0f} | TB: {mean_vol:,.0f}',
            current_value=float(current),
            threshold_value=float(mean_vol + threshold_z * std_vol),
            z_score=float(z_score),
        )
    return None


def detect_volatility_shift(
    returns: np.ndarray,
    symbol: str,
    short_window: int = 5,
    long_window: int = 20,
    threshold_ratio: float = 2.0
) -> Optional[Anomaly]:
    """
    Detect volatility regime shift.
    If short-term volatility >> long-term volatility = regime change.
    """
    if len(returns) < long_window:
        return None

    short_vol = np.std(returns[-short_window:])
    long_vol = np.std(returns[-long_window:])

    if long_vol == 0:
        return None

    ratio = short_vol / long_vol

    if ratio > threshold_ratio:
        severity = 'critical' if ratio > 3 else ('high' if ratio > 2.5 else 'medium')
        return Anomaly(
            anomaly_type='volatility_shift',
            symbol=symbol,
            severity=severity,
            description=f'⚡ {symbol}: Biến động tăng mạnh. Vol 5 phiên gấp {ratio:.1f}x vol 20 phiên. '
                        f'Thị trường đang bất ổn.',
            current_value=float(short_vol),
            threshold_value=float(long_vol * threshold_ratio),
            z_score=float(ratio),
        )
    return None


def detect_price_breakout(
    prices: np.ndarray,
    symbol: str,
    window: int = 20,
    threshold_pct: float = 0.03
) -> Optional[Anomaly]:
    """
    Detect price breaking out of recent range.
    Price > highest high or < lowest low of last N days by threshold %.
    """
    if len(prices) < window + 1:
        return None

    historical = prices[-(window + 1):-1]
    current = prices[-1]
    
    high = np.max(historical)
    low = np.min(historical)
    mean_price = np.mean(historical)
    std_price = np.std(historical)

    z_score = (current - mean_price) / std_price if std_price > 0 else 0

    if current > high * (1 + threshold_pct):
        return Anomaly(
            anomaly_type='price_breakout',
            symbol=symbol,
            severity='medium',
            description=f'📈 {symbol}: Breakout lên cao nhất {window} phiên. '
                        f'Giá hiện tại: {current:,.0f} | Đỉnh cũ: {high:,.0f}',
            current_value=float(current),
            threshold_value=float(high),
            z_score=float(z_score),
        )
    elif current < low * (1 - threshold_pct):
        return Anomaly(
            anomaly_type='price_breakout',
            symbol=symbol,
            severity='high',
            description=f'📉 {symbol}: Phá đáy {window} phiên! '
                        f'Giá hiện tại: {current:,.0f} | Đáy cũ: {low:,.0f}',
            current_value=float(current),
            threshold_value=float(low),
            z_score=float(z_score),
        )
    return None


def scan_all_anomalies(
    symbol: str,
    prices: np.ndarray,
    volumes: np.ndarray,
    returns: np.ndarray,
) -> List[Anomaly]:
    """
    Run all anomaly detection checks for a single stock.
    Returns list of detected anomalies.
    """
    anomalies = []

    vol_spike = detect_volume_spike(volumes, symbol)
    if vol_spike:
        anomalies.append(vol_spike)

    vol_shift = detect_volatility_shift(returns, symbol)
    if vol_shift:
        anomalies.append(vol_shift)

    breakout = detect_price_breakout(prices, symbol)
    if breakout:
        anomalies.append(breakout)

    return anomalies
