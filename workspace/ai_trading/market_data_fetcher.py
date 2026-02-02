"""
株・為替市場データ取得モジュール
Yahoo FinanceとAlpha Vantage API連携
"""

import pandas as pd
import yfinance as yf
import requests
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import time
import os
from dataclasses import dataclass

@dataclass
class MarketData:
    """市場データ構造体"""
    symbol: str
    timeframe: str
    df: pd.DataFrame
    last_updated: datetime

class MarketDataFetcher:
    """市場データ取得クラス"""
    
    # 主要な株式インデックス
    STOCK_INDICES = {
        'SP500': '^GSPC',      # S&P 500
        'NASDAQ': '^IXIC',     # NASDAQ
        'DOW': '^DJI',         # ダウ平均
        'NIKKEI': '^N225',     # 日経平均
        'TOPIX': '^TOPX',      # TOPIX
    }
    
    # 主要なFXペア
    FX_PAIRS = [
        'EURUSD=X', 'USDJPY=X', 'GBPUSD=X', 'USDCHF=X',
        'AUDUSD=X', 'USDCAD=X', 'NZDUSD=X', 'EURJPY=X',
        'GBPJPY=X', 'AUDJPY=X'
    ]
    
    # 人気個別株
    POPULAR_STOCKS = {
        'AAPL': 'Apple',
        'MSFT': 'Microsoft',
        'GOOGL': 'Alphabet',
        'AMZN': 'Amazon',
        'TSLA': 'Tesla',
        'NVDA': 'NVIDIA',
        'META': 'Meta',
        'BTC-USD': 'Bitcoin',
        'ETH-USD': 'Ethereum'
    }
    
    def __init__(self, alpha_vantage_key: Optional[str] = None):
        self.alpha_vantage_key = alpha_vantage_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        self.data_cache: Dict[str, MarketData] = {}
        
    def fetch_stock_data(self, 
                         symbol: str,
                         period: str = "1y",
                         interval: str = "1d") -> Optional[pd.DataFrame]:
        """
        株価データを取得
        
        Args:
            symbol: 銘柄コード (例: 'AAPL', '^N225')
            period: 期間 ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            interval: 間隔 ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
        """
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print(f"[警告] {symbol} のデータが取得できませんでした")
                return None
                
            # カラム名を標準化
            df.columns = [col.lower().replace(' ', '_') for col in df.columns]
            
            # キャッシュに保存
            self.data_cache[symbol] = MarketData(
                symbol=symbol,
                timeframe=f"{period}_{interval}",
                df=df,
                last_updated=datetime.now()
            )
            
            print(f"[成功] {symbol} のデータを取得: {len(df)} 件")
            return df
            
        except Exception as e:
            print(f"[エラー] {symbol} の取得失敗: {e}")
            return None
    
    def fetch_fx_data(self,
                      pair: str = "USDJPY=X",
                      period: str = "6mo",
                      interval: str = "1d") -> Optional[pd.DataFrame]:
        """為替データを取得"""
        return self.fetch_stock_data(pair, period, interval)
    
    def fetch_multiple_symbols(self, 
                               symbols: List[str],
                               period: str = "6mo") -> Dict[str, pd.DataFrame]:
        """複数銘柄のデータを一括取得"""
        results = {}
        
        for symbol in symbols:
            df = self.fetch_stock_data(symbol, period)
            if df is not None:
                results[symbol] = df
            time.sleep(0.5)  # APIレート制限対策
            
        return results
    
    def get_stock_screener(self, 
                          min_volume: int = 1000000,
                          min_price: float = 5.0) -> pd.DataFrame:
        """
        取引活発な銘柄をスクリーニング
        
        注意: Yahoo Financeのスクリーニングは制限あり
        主要銘柄リストからボリュームでフィルタリング
        """
        screening_results = []
        
        # 主要銘柄をチェック
        symbols = list(self.POPULAR_STOCKS.keys())[:20]
        
        for symbol in symbols:
            df = self.fetch_stock_data(symbol, period="5d")
            if df is not None and len(df) > 0:
                latest = df.iloc[-1]
                avg_volume = df['volume'].mean() if 'volume' in df.columns else 0
                latest_price = latest['close']
                
                if avg_volume >= min_volume and latest_price >= min_price:
                    # ボラティリティ計算
                    returns = df['close'].pct_change().dropna()
                    volatility = returns.std() * (252 ** 0.5)  # 年率化
                    
                    screening_results.append({{
                        'symbol': symbol,
                        'name': self.POPULAR_STOCKS.get(symbol, 'Unknown'),
                        'price': latest_price,
                        'volume_5d_avg': avg_volume,
                        'volatility_annual': volatility,
                        'change_5d': (latest_price - df['close'].iloc[0]) / df['close'].iloc[0],
                        'atr': self._calculate_atr(df)
                    }})
        
        if screening_results:
            result_df = pd.DataFrame(screening_results)
            # ボリュームでソート
            result_df = result_df.sort_values('volume_5d_avg', ascending=False)
            return result_df
        
        return pd.DataFrame()
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Average True Rangeを計算"""
        if len(df) < period:
            return 0.0
            
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        
        return atr
    
    def get_fx_data_all(self, period: str = "6mo") -> Dict[str, pd.DataFrame]:
        """主要なFXペアのデータを全て取得"""
        return self.fetch_multiple_symbols(self.FX_PAIRS, period)
    
    def get_realtime_quote(self, symbol: str) -> Optional[Dict]:
        """リアルタイム株価を取得"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # 主要情報を抽出
            return {
                'symbol': symbol,
                'price': info.get('regularMarketPrice'),
                'change': info.get('regularMarketChange'),
                'change_percent': info.get('regularMarketChangePercent'),
                'volume': info.get('regularMarketVolume'),
                'market_cap': info.get('marketCap'),
                '52w_high': info.get('fiftyTwoWeekHigh'),
                '52w_low': info.get('fiftyTwoWeekLow'),
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f"[エラー] リアルタイムデータ取得失敗: {e}")
            return None
    
    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """テクニカル指標を計算"""
        df = df.copy()
        
        # 移動平均線
        df['ma_10'] = df['close'].rolling(window=10).mean()
        df['ma_20'] = df['close'].rolling(window=20).mean()
        df['ma_50'] = df['close'].rolling(window=50).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = df['close'].ewm(span=12).mean()
        exp2 = df['close'].ewm(span=26).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # ボリンジャーバンド
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        return df


# === 使用例 ===
if __name__ == "__main__":
    fetcher = MarketDataFetcher()
    
    # 単一銘柄取得
    print("=== AAPL株価データ ===")
    aapl = fetcher.fetch_stock_data("AAPL", period="1mo")
    if aapl is not None:
        print(aapl.tail())
    
    # FXデータ取得
    print("\n=== USD/JPY 為替データ ===")
    fx = fetcher.fetch_fx_data("USDJPY=X", period="1mo")
    if fx is not None:
        print(fx.tail())
    
    # スクリーニング
    print("\n=== 銘柄スクリーニング ===")
    screen = fetcher.get_stock_screener()
    if not screen.empty:
        print(screen)
