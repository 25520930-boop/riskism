"""
Riskism Risk Engine - Capital-Aware Recommendations
Specific logic for small capital investors (5-50M VND).
"""
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CapitalAdvice:
    """Capital-aware recommendation for small investors."""
    capital_tier: str                    # 'micro' / 'small' / 'medium'
    max_positions: int                   # Recommended max stocks
    position_size_pct: float             # % of capital per position
    suggested_next_symbols: List[str]    # Diversification suggestions
    accumulation_plan: Dict             # Monthly accumulation roadmap
    warnings: List[str]                 # Risk warnings

    def to_dict(self) -> Dict:
        return {
            'capital_tier': self.capital_tier,
            'max_positions': self.max_positions,
            'position_size_pct': round(self.position_size_pct, 2),
            'suggested_next_symbols': self.suggested_next_symbols,
            'accumulation_plan': self.accumulation_plan,
            'warnings': self.warnings,
        }


# Vietnamese stock lot size = 100 shares
MIN_LOT = 100

# Sector mapping for diversification
SECTOR_MAP = {
    'VCB': 'Banking', 'BID': 'Banking', 'CTG': 'Banking', 'TCB': 'Banking',
    'ACB': 'Banking', 'MBB': 'Banking', 'VPB': 'Banking', 'HDB': 'Banking',
    'STB': 'Banking', 'TPB': 'Banking', 'SHB': 'Banking', 'LPB': 'Banking',
    'VIC': 'Real Estate', 'VHM': 'Real Estate', 'VRE': 'Real Estate',
    'NVL': 'Real Estate', 'DXG': 'Real Estate', 'KDH': 'Real Estate',
    'MSN': 'Consumer', 'MWG': 'Consumer', 'VNM': 'Consumer', 'SAB': 'Consumer',
    'PNJ': 'Consumer', 'FRT': 'Consumer',
    'HPG': 'Industrial', 'HSG': 'Industrial', 'NKG': 'Industrial',
    'GAS': 'Energy', 'PLX': 'Energy', 'POW': 'Energy', 'PPC': 'Energy',
    'FPT': 'Technology', 'CMG': 'Technology',
    'VNR': 'Insurance', 'BVH': 'Insurance',
    'VCG': 'Construction', 'CTD': 'Construction', 'HBC': 'Construction',
    'GMD': 'Logistics', 'PVT': 'Logistics',
    'DGC': 'Chemicals', 'DCM': 'Chemicals',
}


def get_capital_tier(capital: float) -> str:
    """Classify capital amount (VND)."""
    if capital < 10_000_000:        # < 10M
        return 'micro'
    elif capital < 30_000_000:      # 10-30M
        return 'small'
    else:                           # 30-50M+
        return 'medium'


def recommend_positions(capital: float) -> tuple:
    """
    Recommend max positions and position size based on capital.
    Small accounts need fewer positions for meaningful impact.
    """
    tier = get_capital_tier(capital)
    
    if tier == 'micro':
        return 2, 50.0    # Max 2 stocks, 50% each
    elif tier == 'small':
        return 3, 33.33   # Max 3 stocks, ~33% each
    else:
        return 5, 20.0    # Max 5 stocks, 20% each


def find_hidden_correlations(
    current_symbols: List[str],
    returns_dict: Dict[str, np.ndarray],
    threshold: float = 0.7
) -> List[Dict]:
    """
    Find pairs of stocks with high correlation (hidden risk).
    Returns list of correlated pairs with warnings.
    """
    warnings = []
    symbols = [s for s in current_symbols if s in returns_dict]
    
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            r1, r2 = returns_dict[s1], returns_dict[s2]
            min_len = min(len(r1), len(r2))
            if min_len < 20:
                continue
            corr = np.corrcoef(r1[-min_len:], r2[-min_len:])[0, 1]
            if abs(corr) > threshold:
                warnings.append({
                    'pair': (s1, s2),
                    'correlation': round(float(corr), 4),
                    'warning': f'⚠️ {s1} và {s2} có tương quan cao ({corr:.1%}). Danh mục chưa thực sự đa dạng hóa.'
                })
    return warnings


def suggest_diversification(
    current_symbols: List[str],
    available_returns: Dict[str, np.ndarray],
    top_n: int = 3
) -> List[str]:
    """
    Suggest stocks that would improve portfolio diversification.
    Picks stocks with lowest average correlation to current holdings.
    """
    current_sectors = set(SECTOR_MAP.get(s, 'Unknown') for s in current_symbols)
    candidates = []

    for symbol, returns in available_returns.items():
        if symbol in current_symbols:
            continue
        sector = SECTOR_MAP.get(symbol, 'Unknown')
        
        # Prefer different sectors
        sector_bonus = -0.2 if sector not in current_sectors else 0

        # Calculate average correlation with current holdings
        correlations = []
        for curr_sym in current_symbols:
            if curr_sym in available_returns:
                curr_ret = available_returns[curr_sym]
                min_len = min(len(returns), len(curr_ret))
                if min_len > 20:
                    corr = np.corrcoef(returns[-min_len:], curr_ret[-min_len:])[0, 1]
                    correlations.append(abs(corr))

        avg_corr = np.mean(correlations) if correlations else 0.5
        score = avg_corr + sector_bonus  # Lower is better
        candidates.append((symbol, score))

    candidates.sort(key=lambda x: x[1])
    return [c[0] for c in candidates[:top_n]]


def build_accumulation_plan(capital: float, monthly_savings: Optional[float] = None) -> Dict:
    """
    Build a monthly capital accumulation roadmap.
    Default savings rate: 10% of current capital per month.
    """
    if monthly_savings is None:
        monthly_savings = capital * 0.1

    plan = {
        'current_capital': capital,
        'monthly_savings': monthly_savings,
        'milestones': [],
    }

    target_milestones = [10_000_000, 20_000_000, 30_000_000, 50_000_000, 100_000_000]
    accumulated = capital

    for month in range(1, 61):  # Max 5 years
        accumulated += monthly_savings
        for milestone in target_milestones:
            if accumulated >= milestone and capital < milestone:
                plan['milestones'].append({
                    'amount': milestone,
                    'month': month,
                    'label': f'{milestone/1_000_000:.0f}M VND',
                    'tier_unlock': get_capital_tier(milestone),
                })
                capital = milestone  # Prevent duplicate milestone
                break

    return plan


def generate_capital_advice(
    capital: float,
    current_holdings: List[Dict],
    returns_dict: Dict[str, np.ndarray],
    available_returns: Optional[Dict[str, np.ndarray]] = None,
    monthly_savings: Optional[float] = None,
) -> CapitalAdvice:
    """
    Generate capital-aware advice for the investor.
    """
    tier = get_capital_tier(capital)
    max_pos, pos_size = recommend_positions(capital)
    
    current_symbols = [h['symbol'] for h in current_holdings]
    
    # Find hidden correlations
    warnings = []
    corr_warnings = find_hidden_correlations(current_symbols, returns_dict)
    warnings.extend([w['warning'] for w in corr_warnings])
    
    # Check over-concentration
    if len(current_symbols) > max_pos:
        warnings.append(
            f'📊 Với vốn {capital/1_000_000:.0f}M, bạn nên giữ tối đa {max_pos} mã. '
            f'Hiện tại bạn đang giữ {len(current_symbols)} mã.'
        )
    
    # Check if capital too small for current positions
    for h in current_holdings:
        min_value = h.get('avg_price', 0) * MIN_LOT
        if min_value > capital * (pos_size / 100):
            warnings.append(
                f'💰 {h["symbol"]} (giá ~{h["avg_price"]:,.0f}) cần tối thiểu '
                f'{min_value:,.0f} VND/lot, chiếm quá nhiều so với vốn.'
            )
    
    # Suggest diversification
    suggested = []
    if available_returns:
        suggested = suggest_diversification(current_symbols, available_returns)
    
    # Build accumulation plan
    acc_plan = build_accumulation_plan(capital, monthly_savings)
    
    return CapitalAdvice(
        capital_tier=tier,
        max_positions=max_pos,
        position_size_pct=pos_size,
        suggested_next_symbols=suggested,
        accumulation_plan=acc_plan,
        warnings=warnings,
    )
