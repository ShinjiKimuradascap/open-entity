"""
AI Trading Backtest Engine
期待値の正な戦略をバックテストで検証し、実際の収益を生む
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import json

class Signal(Enum):
    BUY = 1
    SELL = -1
    HOLD = 0

@dataclass
class Trade:
    entry_date: datetime
    exit_date: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    side: str  # 'long' or 'short'
    size: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

@dataclass
class BacktestResult:
    strategy_name: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade: float
    equity_curve: List[float]
    trades: List[Trade]
    
    def to_dict(self) -> Dict:
        return {
            'strategy_name': self.strategy_name,
            'total_return': f"{self.total_return:.2%}",
            'sharpe_ratio': f"{self.sharpe_ratio:.2f}",
            'max_drawdown': f"{self.max_drawdown:.2%}",
            'win_rate': f"{self.win_rate:.2%}",
            'profit_factor': f"{self.profit_factor:.2f}",
            'total_trades': self.total_trades,
            'avg_trade': f"{self.avg_trade:.2%}"
        }

class BacktestEngine:
    """バックテストエンジン - リスク管理を重視"""
    
    def __init__(self, initial_capital: float = 10000.0, 
                 position_size_pct: float = 0.1,
                 stop_loss_pct: float = 0.05,
                 take_profit_pct: float = 0.15):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        
    def run_backtest(self, 
                     data: pd.DataFrame,
                     strategy_func: Callable[[pd.DataFrame], pd.Series],
                     strategy_name: str) -> BacktestResult:
        """
        バックテスト実行
        
        Args:
            data: OHLCVデータフレーム
            strategy_func: シグナル生成関数
            strategy_name: 戦略名
        """
        signals = strategy_func(data)
        trades = []
        equity = [self.initial_capital]
        current_capital = self.initial_capital
        
        position = None
        position_size = 0
        entry_price = 0
        
        for i in range(1, len(data)):
            current_price = data['close'].iloc[i]
            current_signal = signals.iloc[i]
            
            # ポジションクローズ判定
            if position is not None:
                exit_reason = None
                
                # ストップロス
                if position == 'long' and current_price <= entry_price * (1 - self.stop_loss_pct):
                    exit_reason = 'stop_loss'
                elif position == 'short' and current_price >= entry_price * (1 + self.stop_loss_pct):
                    exit_reason = 'stop_loss'
                    
                # テイクプロフィット
                elif position == 'long' and current_price >= entry_price * (1 + self.take_profit_pct):
                    exit_reason = 'take_profit'
                elif position == 'short' and current_price <= entry_price * (1 - self.take_profit_pct):
                    exit_reason = 'take_profit'
                    
                # シグナル反転
                elif (position == 'long' and current_signal == Signal.SELL.value) or \
                     (position == 'short' and current_signal == Signal.BUY.value):
                    exit_reason = 'signal_reverse'
                
                if exit_reason:
                    # トレードクローズ
                    if position == 'long':
                        pnl = (current_price - entry_price) * position_size
                        pnl_pct = (current_price - entry_price) / entry_price
                    else:
                        pnl = (entry_price - current_price) * position_size
                        pnl_pct = (entry_price - current_price) / entry_price
                    
                    trade = Trade(
                        entry_date=entry_date,
                        exit_date=data.index[i],
                        entry_price=entry_price,
                        exit_price=current_price,
                        side=position,
                        size=position_size,
                        pnl=pnl,
                        pnl_pct=pnl_pct
                    )
                    trades.append(trade)
                    
                    current_capital += pnl
                    position = None
                    equity.append(current_capital)
            
            # ポジションオープン判定
            if position is None and current_signal != Signal.HOLD.value:
                position_size = (current_capital * self.position_size_pct) / current_price
                entry_price = current_price
                entry_date = data.index[i]
                position = 'long' if current_signal == Signal.BUY.value else 'short'
        
        # メトリクス計算
        return self._calculate_metrics(trades, equity, strategy_name)
    
    def _calculate_metrics(self, trades: List[Trade], 
                          equity: List[float],
                          strategy_name: str) -> BacktestResult:
        """パフォーマンス指標計算"""
        
        if not trades:
            return BacktestResult(
                strategy_name=strategy_name,
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                total_trades=0,
                avg_trade=0.0,
                equity_curve=equity,
                trades=[]
            )
        
        pnls = [t.pnl for t in trades if t.pnl is not None]
        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p <= 0]
        
        total_return = (equity[-1] - self.initial_capital) / self.initial_capital
        win_rate = len(winning_trades) / len(trades) if trades else 0
        
        # プロフィットファクター
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # シャープレシオ（単純化版）
        returns = pd.Series(equity).pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        
        # 最大ドローダウン
        cummax = pd.Series(equity).cummax()
        drawdown = (pd.Series(equity) - cummax) / cummax
        max_drawdown = drawdown.min()
        
        avg_trade = np.mean(pnls) / self.initial_capital if pnls else 0
        
        return BacktestResult(
            strategy_name=strategy_name,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(trades),
            avg_trade=avg_trade,
            equity_curve=equity,
            trades=trades
        )


# === 戦略定義 ===

def momentum_strategy(data: pd.DataFrame, short_window: int = 10, long_window: int = 30) -> pd.Series:
    """
    モメンタム戦略 - トレンドフォロー
    短期MA > 長期MA で買い、逆で売り
    """
    signals = pd.Series(index=data.index, dtype=int)
    signals[:] = Signal.HOLD.value
    
    short_ma = data['close'].rolling(window=short_window).mean()
    long_ma = data['close'].rolling(window=long_window).mean()
    
    signals[short_ma > long_ma] = Signal.BUY.value
    signals[short_ma < long_ma] = Signal.SELL.value
    
    return signals

def mean_reversion_strategy(data: pd.DataFrame, window: int = 20, std_dev: float = 2.0) -> pd.Series:
    """
    均值回帰戦略 - ボリンジャーバンドベース
    価格が下限を割れたら買い、上限を超えたら売り
    """
    signals = pd.Series(index=data.index, dtype=int)
    signals[:] = Signal.HOLD.value
    
    ma = data['close'].rolling(window=window).mean()
    std = data['close'].rolling(window=window).std()
    
    upper_band = ma + (std * std_dev)
    lower_band = ma - (std * std_dev)
    
    signals[data['close'] < lower_band] = Signal.BUY.value
    signals[data['close'] > upper_band] = Signal.SELL.value
    
    return signals

def breakout_strategy(data: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    ブレイクアウト戦略 - ドンチャンチャネル
    高値を更新したら買い、安値を更新したら売り
    """
    signals = pd.Series(index=data.index, dtype=int)
    signals[:] = Signal.HOLD.value
    
    highest_high = data['high'].rolling(window=window).max()
    lowest_low = data['low'].rolling(window=window).min()
    
    signals[data['close'] > highest_high.shift(1)] = Signal.BUY.value
    signals[data['close'] < lowest_low.shift(1)] = Signal.SELL.value
    
    return signals


def dual_thrust_strategy(data: pd.DataFrame, lookback: int = 4, multiplier: float = 0.5) -> pd.Series:
    """
    Dual Thrust戦略 - 著名なアルゴリズム
    レンジブレイクアウトの改良版
    """
    signals = pd.Series(index=data.index, dtype=int)
    signals[:] = Signal.HOLD.value
    
    hh = data['high'].rolling(window=lookback).max()
    hc = data['close'].rolling(window=lookback).max()
    lc = data['close'].rolling(window=lookback).min()
    ll = data['low'].rolling(window=lookback).min()
    
    range1 = hh - lc
    range2 = hc - ll
    
    max_range = pd.concat([range1, range2], axis=1).max(axis=1)
    
    upper = data['open'] + max_range * multiplier
    lower = data['open'] - max_range * multiplier
    
    signals[data['close'] > upper.shift(1)] = Signal.BUY.value
    signals[data['close'] < lower.shift(1)] = Signal.SELL.value
    
    return signals
