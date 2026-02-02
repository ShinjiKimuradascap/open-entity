"""
株・為替戦略エンジン
テクニカル分析 + バックテスト統合
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from ai_trading.market_data_fetcher import MarketDataFetcher
from ai_trading.backtest_engine import BacktestEngine, Signal

class StrategyType(Enum):
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    DUAL_THRUST = "dual_thrust"
    TREND_FOLLOWING = "trend_following"

@dataclass
class TradeSetup:
    """トレード設定"""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_reward_ratio: float
    setup_time: datetime
    strategy: str
    confidence: float  # 0.0 - 1.0

class StrategyEngine:
    """統合戦略エンジン"""
    
    def __init__(self, initial_capital: float = 1000000):
        self.fetcher = MarketDataFetcher()
        self.backtest = BacktestEngine(
            initial_capital=initial_capital,
            position_size_pct=0.1,
            stop_loss_pct=0.02,
            take_profit_pct=0.06
        )
        self.current_signals: Dict[str, Dict] = {}
    
    def analyze_symbol(self, symbol: str, period: str = "3mo") -> Optional[Dict]:
        """
        銘柄を分析してトレードシグナルを生成
        """
        # データ取得
        df = self.fetcher.fetch_stock_data(symbol, period=period)
        if df is None or len(df) < 50:
            print(f"[警告] {symbol} のデータ不足")
            return None
        
        # テクニカル指標計算
        df = self.fetcher.calculate_technical_indicators(df)
        
        # 複数戦略のシグナルを生成
        signals = self._generate_all_signals(df)
        
        # 最新データ
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # 分析結果
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'price': latest['close'],
            'indicators': {
                'rsi': latest.get('rsi'),
                'macd': latest.get('macd'),
                'macd_signal': latest.get('macd_signal'),
                'ma_10': latest.get('ma_10'),
                'ma_20': latest.get('ma_20'),
                'ma_50': latest.get('ma_50'),
                'bb_upper': latest.get('bb_upper'),
                'bb_lower': latest.get('bb_lower'),
            },
            'signals': signals,
            'trend': self._determine_trend(df),
            'volatility': self._calculate_volatility(df),
            'volume_trend': self._analyze_volume(df),
            'support_resistance': self._find_support_resistance(df)
        }
        
        # 総合評価
        analysis['composite_signal'] = self._calculate_composite_signal(signals)
        analysis['recommendation'] = self._generate_recommendation(analysis)
        
        self.current_signals[symbol] = analysis
        return analysis
    
    def _generate_all_signals(self, df: pd.DataFrame) -> Dict[str, int]:
        """複数戦略からシグナルを生成"""
        signals = {}
        
        # モメンタム戦略
        signals['momentum'] = self._momentum_signal(df)
        
        # 均值回帰戦略
        signals['mean_reversion'] = self._mean_reversion_signal(df)
        
        # ブレイクアウト戦略
        signals['breakout'] = self._breakout_signal(df)
        
        # トレンドフォロー戦略
        signals['trend_following'] = self._trend_following_signal(df)
        
        return signals
    
    def _momentum_signal(self, df: pd.DataFrame) -> int:
        """モメンタムシグナル"""
        latest = df.iloc[-1]
        
        # MACD確認
        if latest.get('macd') and latest.get('macd_signal'):
            if latest['macd'] > latest['macd_signal']:
                return Signal.BUY.value
            elif latest['macd'] < latest['macd_signal']:
                return Signal.SELL.value
        
        # MA確認
        if latest.get('ma_10') and latest.get('ma_20'):
            if latest['ma_10'] > latest['ma_20']:
                return Signal.BUY.value
            elif latest['ma_10'] < latest['ma_20']:
                return Signal.SELL.value
        
        return Signal.HOLD.value
    
    def _mean_reversion_signal(self, df: pd.DataFrame) -> int:
        """均值回帰シグナル"""
        latest = df.iloc[-1]
        
        # RSI極端値
        rsi = latest.get('rsi')
        if rsi is not None:
            if rsi < 30:  # 売られすぎ
                return Signal.BUY.value
            elif rsi > 70:  # 買われすぎ
                return Signal.SELL.value
        
        # ボリンジャーバンド
        if latest.get('bb_lower') and latest.get('bb_upper'):
            if latest['close'] < latest['bb_lower']:
                return Signal.BUY.value
            elif latest['close'] > latest['bb_upper']:
                return Signal.SELL.value
        
        return Signal.HOLD.value
    
    def _breakout_signal(self, df: pd.DataFrame) -> int:
        """ブレイクアウトシグナル"""
        if len(df) < 20:
            return Signal.HOLD.value
        
        latest = df.iloc[-1]
        highest_20 = df['high'].rolling(window=20).max().iloc[-2]
        lowest_20 = df['low'].rolling(window=20).min().iloc[-2]
        
        if latest['close'] > highest_20:
            return Signal.BUY.value
        elif latest['close'] < lowest_20:
            return Signal.SELL.value
        
        return Signal.HOLD.value
    
    def _trend_following_signal(self, df: pd.DataFrame) -> int:
        """トレンドフォローシグナル"""
        if len(df) < 50:
            return Signal.HOLD.value
        
        latest = df.iloc[-1]
        
        # 多層MA確認
        if latest.get('ma_10') and latest.get('ma_20') and latest.get('ma_50'):
            # ゴールデンクロス状況
            if latest['ma_10'] > latest['ma_20'] > latest['ma_50']:
                return Signal.BUY.value
            # デッドクロス状況
            elif latest['ma_10'] < latest['ma_20'] < latest['ma_50']:
                return Signal.SELL.value
        
        return Signal.HOLD.value
    
    def _calculate_composite_signal(self, signals: Dict[str, int]) -> Dict:
        """複数シグナルを統合"""
        buy_count = sum(1 for s in signals.values() if s == Signal.BUY.value)
        sell_count = sum(1 for s in signals.values() if s == Signal.SELL.value)
        hold_count = sum(1 for s in signals.values() if s == Signal.HOLD.value)
        
        total = len(signals)
        
        # シグナル強度計算
        if buy_count > sell_count and buy_count >= total * 0.5:
            direction = "BUY"
            strength = buy_count / total
        elif sell_count > buy_count and sell_count >= total * 0.5:
            direction = "SELL"
            strength = sell_count / total
        else:
            direction = "HOLD"
            strength = hold_count / total
        
        return {
            'direction': direction,
            'strength': strength,
            'buy_signals': buy_count,
            'sell_signals': sell_count,
            'hold_signals': hold_count,
            'details': signals
        }
    
    def _determine_trend(self, df: pd.DataFrame) -> str:
        """トレンド判定"""
        if len(df) < 20:
            return "UNKNOWN"
        
        sma_20 = df['close'].rolling(window=20).mean().iloc[-1]
        sma_50 = df['close'].rolling(window=50).mean().iloc[-1] if len(df) >= 50 else sma_20
        current_price = df['close'].iloc[-1]
        
        # 20日と50日の位置関係
        if current_price > sma_20 > sma_50:
            return "UPTREND"
        elif current_price < sma_20 < sma_50:
            return "DOWNTREND"
        else:
            return "SIDEWAYS"
    
    def _calculate_volatility(self, df: pd.DataFrame) -> Dict:
        """ボラティリティ計算"""
        returns = df['close'].pct_change().dropna()
        
        return {
            'daily_volatility': returns.std(),
            'annualized_volatility': returns.std() * np.sqrt(252),
            'atr': self.fetcher._calculate_atr(df)
        }
    
    def _analyze_volume(self, df: pd.DataFrame) -> str:
        """出来高分析"""
        if 'volume' not in df.columns:
            return "N/A"
        
        recent_vol = df['volume'].tail(5).mean()
        avg_vol = df['volume'].mean()
        
        if recent_vol > avg_vol * 1.5:
            return "HIGH"
        elif recent_vol < avg_vol * 0.5:
            return "LOW"
        return "NORMAL"
    
    def _find_support_resistance(self, df: pd.DataFrame) -> Dict:
        """サポート・レジスタンスを特定"""
        if len(df) < 20:
            return {'support': None, 'resistance': None}
        
        recent_highs = df['high'].tail(20)
        recent_lows = df['low'].tail(20)
        
        return {
            'resistance': recent_highs.max(),
            'support': recent_lows.min(),
            'resistance_10d': recent_highs.tail(10).max(),
            'support_10d': recent_lows.tail(10).min()
        }
    
    def _generate_recommendation(self, analysis: Dict) -> Optional[TradeSetup]:
        """取引推奨を生成"""
        composite = analysis['composite_signal']
        price = analysis['price']
        
        # HOLDシグナルは無視
        if composite['direction'] == "HOLD":
            return None
        
        # 強度チェック
        if composite['strength'] < 0.5:
            return None
        
        # サイド計算
        side = 'long' if composite['direction'] == "BUY" else 'short'
        
        # ストップとターゲット計算
        volatility = analysis['volatility']['atr'] if analysis['volatility']['atr'] else price * 0.02
        
        if side == 'long':
            stop_loss = price - (volatility * 1.5)
            take_profit = price + (volatility * 3)
        else:
            stop_loss = price + (volatility * 1.5)
            take_profit = price - (volatility * 3)
        
        # リスクリワード計算
        risk = abs(price - stop_loss)
        reward = abs(take_profit - price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        # R/R 1:2以上のみ採用
        if rr_ratio < 2:
            return None
        
        return TradeSetup(
            symbol=analysis['symbol'],
            side=side,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=0.1,  # 10%ポジション
            risk_reward_ratio=rr_ratio,
            setup_time=datetime.now(),
            strategy=composite['direction'],
            confidence=composite['strength']
        )
    
    def scan_for_opportunities(self, symbols: List[str]) -> List[TradeSetup]:
        """複数銘柄をスキャンして機会を探す"""
        opportunities = []
        
        for symbol in symbols:
            analysis = self.analyze_symbol(symbol)
            if analysis and analysis.get('recommendation'):
                opportunities.append(analysis['recommendation'])
        
        # 確信度でソート
        opportunities.sort(key=lambda x: x.confidence, reverse=True)
        return opportunities
    
    def run_backtest_analysis(self, symbol: str, period: str = "1y") -> Dict:
        """バックテスト分析を実行"""
        df = self.fetcher.fetch_stock_data(symbol, period=period)
        if df is None:
            return {}
        
        # 各戦略でバックテスト
        from ai_trading.backtest_engine import momentum_strategy, mean_reversion_strategy
        
        results = {}
        
        # モメンタム戦略
        try:
            momentum_result = self.backtest.run_backtest(
                df, momentum_strategy, "Momentum"
            )
            results['momentum'] = momentum_result.to_dict()
        except Exception as e:
            results['momentum'] = {'error': str(e)}
        
        # 均值回帰戦略
        try:
            mean_rev_result = self.backtest.run_backtest(
                df, mean_reversion_strategy, "Mean Reversion"
            )
            results['mean_reversion'] = mean_rev_result.to_dict()
        except Exception as e:
            results['mean_reversion'] = {'error': str(e)}
        
        return results


# === 使用例 ===
if __name__ == "__main__":
    engine = StrategyEngine(initial_capital=1000000)
    
    # 単一銘柄分析
    print("=== TSLA 分析 ===")
    analysis = engine.analyze_symbol("TSLA")
    if analysis:
        print(f"価格: ${analysis['price']:.2f}")
        print(f"トレンド: {analysis['trend']}")
        print(f"複合シグナル: {analysis['composite_signal']}")
        if analysis.get('recommendation'):
            rec = analysis['recommendation']
            print(f"推奨: {rec.side.upper()} @ ${rec.entry_price:.2f}")
            print(f"SL: ${rec.stop_loss:.2f} / TP: ${rec.take_profit:.2f}")
            print(f"R/R: 1:{rec.risk_reward_ratio:.1f}")
