#!/usr/bin/env python3
"""
AI Trading Strategy Backtest Runner
実際の市場データで戦略を検証し、最適なパラメータを発見
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import json
from typing import Dict, List
import sys
import os

# エンジンをインポート
sys.path.insert(0, os.path.dirname(__file__))
from backtest_engine import (
    BacktestEngine, momentum_strategy, mean_reversion_strategy,
    breakout_strategy, dual_thrust_strategy, Signal
)


def fetch_market_data(symbols: List[str], period: str = "5y") -> Dict[str, pd.DataFrame]:
    """
    Yahoo Financeから市場データを取得
    """
    data = {}
    for symbol in symbols:
        print(f"📊 {symbol} のデータを取得中...")
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            # カラム名を小文字に変換
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            if len(df) > 100:
                data[symbol] = df
                print(f"   ✓ {len(df)} 日分のデータを取得")
            else:
                print(f"   ⚠ データが不足 ({len(df)} 日)")
        except Exception as e:
            print(f"   ✗ エラー: {e}")
    return data


def run_strategy_comparison(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    複数の戦略を比較テスト
    """
    engine = BacktestEngine(
        initial_capital=100000,
        position_size_pct=0.2,
        stop_loss_pct=0.03,
        take_profit_pct=0.10
    )
    
    strategies = [
        ("Momentum(10,30)", lambda df: momentum_strategy(df, 10, 30)),
        ("Momentum(5,20)", lambda df: momentum_strategy(df, 5, 20)),
        ("MeanReversion(20)", lambda df: mean_reversion_strategy(df, 20, 2.0)),
        ("MeanReversion(10)", lambda df: mean_reversion_strategy(df, 10, 1.5)),
        ("Breakout(20)", lambda df: breakout_strategy(df, 20)),
        ("Breakout(10)", lambda df: breakout_strategy(df, 10)),
        ("DualThrust", lambda df: dual_thrust_strategy(df, 4, 0.5)),
    ]
    
    results = []
    
    for symbol, df in data.items():
        print(f"\n📈 {symbol} のバックテスト実行中...")
        
        for strategy_name, strategy_func in strategies:
            try:
                result = engine.run_backtest(df, strategy_func, strategy_name)
                
                # スコア計算（シャープレシオ重視）
                score = result.sharpe_ratio * (1 + result.total_return) * (1 + result.win_rate)
                
                results.append({
                    'Symbol': symbol,
                    'Strategy': strategy_name,
                    'TotalReturn': result.total_return,
                    'SharpeRatio': result.sharpe_ratio,
                    'MaxDrawdown': result.max_drawdown,
                    'WinRate': result.win_rate,
                    'ProfitFactor': result.profit_factor,
                    'TotalTrades': result.total_trades,
                    'AvgTrade': result.avg_trade,
                    'Score': score
                })
                
                print(f"   {strategy_name:20s}: Return={result.total_return:7.2%}, "
                      f"Sharpe={result.sharpe_ratio:5.2f}, DD={result.max_drawdown:7.2%}")
                
            except Exception as e:
                print(f"   ✗ {strategy_name} でエラー: {e}")
    
    return pd.DataFrame(results)


def analyze_results(results_df: pd.DataFrame) -> Dict:
    """
    結果を分析し、最適な戦略を特定
    """
    if results_df.empty:
        return {"error": "有効な結果がありません"}
    
    analysis = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(results_df),
        "best_overall": None,
        "best_by_symbol": {},
        "top_strategies": [],
        "risk_adjusted_best": None
    }
    
    # 全体ベスト（スコアベース）
    best_idx = results_df['Score'].idxmax()
    best = results_df.loc[best_idx]
    analysis["best_overall"] = {
        "symbol": best['Symbol'],
        "strategy": best['Strategy'],
        "return": f"{best['TotalReturn']:.2%}",
        "sharpe": f"{best['SharpeRatio']:.2f}",
        "drawdown": f"{best['MaxDrawdown']:.2%}"
    }
    
    # シンボル別ベスト
    for symbol in results_df['Symbol'].unique():
        symbol_df = results_df[results_df['Symbol'] == symbol]
        best_sym_idx = symbol_df['Score'].idxmax()
        best_sym = symbol_df.loc[best_sym_idx]
        analysis["best_by_symbol"][symbol] = {
            "strategy": best_sym['Strategy'],
            "return": f"{best_sym['TotalReturn']:.2%}",
            "sharpe": f"{best_sym['SharpeRatio']:.2f}"
        }
    
    # トップ5戦略
    top5 = results_df.nlargest(5, 'Score')[['Symbol', 'Strategy', 'TotalReturn', 
                                              'SharpeRatio', 'MaxDrawdown', 'Score']]
    analysis["top_strategies"] = top5.to_dict('records')
    
    # リスク調整後ベスト（ドローダウン考慮）
    results_df['RiskAdjusted'] = results_df['TotalReturn'] / abs(results_df['MaxDrawdown'].clip(lower=-0.001))
    risk_best_idx = results_df['RiskAdjusted'].idxmax()
    risk_best = results_df.loc[risk_best_idx]
    analysis["risk_adjusted_best"] = {
        "symbol": risk_best['Symbol'],
        "strategy": risk_best['Strategy'],
        "risk_adjusted_return": f"{risk_best['RiskAdjusted']:.2f}",
        "return": f"{risk_best['TotalReturn']:.2%}",
        "drawdown": f"{risk_best['MaxDrawdown']:.2%}"
    }
    
    return analysis


def generate_report(results_df: pd.DataFrame, analysis: Dict) -> str:
    """
    HTML/PDFレポート生成（簡易版）
    """
    report = f"""
# AI Trading Backtest Report
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Strategies Tested | {analysis['total_tests']} |
| Best Strategy | {analysis['best_overall']['strategy']} ({analysis['best_overall']['symbol']}) |
| Best Return | {analysis['best_overall']['return']} |
| Best Sharpe Ratio | {analysis['best_overall']['sharpe']} |

## Top 5 Strategies

| Rank | Symbol | Strategy | Return | Sharpe | Max DD | Score |
|------|--------|----------|--------|--------|--------|-------|
"""
    
    for i, strat in enumerate(analysis['top_strategies'], 1):
        report += f"| {i} | {strat['Symbol']} | {strat['Strategy']} | "
        report += f"{strat['TotalReturn']:.2%} | {strat['SharpeRatio']:.2f} | "
        report += f"{strat['MaxDrawdown']:.2%} | {strat['Score']:.2f} |\n"
    
    report += f"""
## Risk Analysis

**リスク調整後ベスト**: {analysis['risk_adjusted_best']['strategy']} ({analysis['risk_adjusted_best']['symbol']})
- Risk-Adjusted Return: {analysis['risk_adjusted_best']['risk_adjusted_return']}
- Actual Return: {analysis['risk_adjusted_best']['return']}
- Max Drawdown: {analysis['risk_adjusted_best']['drawdown']}

## Key Insights

1. **期待値の正な戦略**: Sharpe Ratio > 1.0 の戦略は {len(results_df[results_df['SharpeRatio'] > 1.0])} 個
2. **負けない戦略**: Max Drawdown < 20% の戦略は {len(results_df[results_df['MaxDrawdown'] > -0.20])} 個
3. **収益性**: Profit Factor > 1.5 の戦略は {len(results_df[results_df['ProfitFactor'] > 1.5])} 個

## Recommendation

**プロダクション推奨戦略**:
- Primary: {analysis['top_strategies'][0]['Strategy']} ({analysis['top_strategies'][0]['Symbol']})
- Backup: {analysis['top_strategies'][1]['Strategy']} ({analysis['top_strategies'][1]['Symbol']})
"""
    
    return report


def main():
    """メイン実行関数"""
    print("=" * 60)
    print("🤖 AI Trading Backtest System")
    print("=" * 60)
    
    # テスト対象銘柄（主要インデックスと人気株）
    symbols = [
        "SPY",    # S&P500 ETF
        "QQQ",    # NASDAQ ETF
        "IWM",    # Russell 2000
        "AAPL",   # Apple
        "MSFT",   # Microsoft
        "NVDA",   # NVIDIA
        "TSLA",   # Tesla
    ]
    
    # データ取得
    print("\n📥 市場データを取得中...")
    data = fetch_market_data(symbols, period="5y")
    
    if not data:
        print("✗ データ取得に失敗しました")
        return
    
    # バックテスト実行
    print("\n🧪 戦略バックテストを実行中...")
    results_df = run_strategy_comparison(data)
    
    if results_df.empty:
        print("✗ バックテスト結果がありません")
        return
    
    # 結果分析
    print("\n📊 結果を分析中...")
    analysis = analyze_results(results_df)
    
    # レポート生成
    report = generate_report(results_df, analysis)
    
    # ファイル保存
    output_dir = "ai_trading/results"
    os.makedirs(output_dir, exist_ok=True)
    
    # JSON保存
    json_path = f"{output_dir}/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\n💾 分析結果を保存: {json_path}")
    
    # CSV保存
    csv_path = f"{output_dir}/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"💾 詳細結果を保存: {csv_path}")
    
    # レポート保存
    report_path = f"{output_dir}/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"💾 レポートを保存: {report_path}")
    
    # 結果表示
    print("\n" + "=" * 60)
    print("🎯 BACKTEST RESULTS")
    print("=" * 60)
    print(report)
    
    print("\n✅ バックテスト完了")
    return analysis


if __name__ == "__main__":
    main()
