#!/usr/bin/env python3
"""
Feedback Collection System
ローンチ後のユーザーフィードバックを自動収集・分析

Features:
- ProductHuntコメント監視
- Twitterメンション追跡
- Redditコメント収集
- フィードバック分析レポート生成
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path

# 設定
DATA_DIR = Path("data/feedback")
DATA_DIR.mkdir(parents=True, exist_ok=True)


class FeedbackCollector:
    """フィードバック収集エンジン"""
    
    def __init__(self):
        self.feedback_db = DATA_DIR / "feedback_db.json"
        self.metrics_file = DATA_DIR / "metrics.json"
        self.load_data()
    
    def load_data(self):
        """既存データを読み込み"""
        if self.feedback_db.exists():
            with open(self.feedback_db) as f:
                self.data = json.load(f)
        else:
            self.data = {"feedbacks": [], "summary": {}}
        
        if self.metrics_file.exists():
            with open(self.metrics_file) as f:
                self.metrics = json.load(f)
        else:
            self.metrics = {
                "total_mentions": 0,
                "sentiment_positive": 0,
                "sentiment_negative": 0,
                "action_items": []
            }
    
    def save_data(self):
        """データを保存"""
        with open(self.feedback_db, 'w') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        with open(self.metrics_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)
    
    def add_feedback(self, source: str, content: str, sentiment: str = "neutral"):
        """フィードバックを追加"""
        feedback = {
            "id": f"fb_{len(self.data['feedbacks'])}",
            "source": source,
            "content": content,
            "sentiment": sentiment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processed": False
        }
        self.data["feedbacks"].append(feedback)
        self.metrics["total_mentions"] += 1
        
        if sentiment == "positive":
            self.metrics["sentiment_positive"] += 1
        elif sentiment == "negative":
            self.metrics["sentiment_negative"] += 1
        
        self.save_data()
        return feedback["id"]
    
    def get_unprocessed(self) -> List[Dict]:
        """未処理のフィードバックを取得"""
        return [f for f in self.data["feedbacks"] if not f["processed"]]
    
    def mark_processed(self, feedback_id: str):
        """フィードバックを処理済みにマーク"""
        for f in self.data["feedbacks"]:
            if f["id"] == feedback_id:
                f["processed"] = True
                break
        self.save_data()
    
    def generate_report(self) -> Dict:
        """フィードバック分析レポートを生成"""
        total = len(self.data["feedbacks"])
        if total == 0:
            return {"message": "No feedback yet"}
        
        positive = self.metrics["sentiment_positive"]
        negative = self.metrics["sentiment_negative"]
        neutral = total - positive - negative
        
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_feedback": total,
                "sentiment_distribution": {
                    "positive": positive,
                    "neutral": neutral,
                    "negative": negative
                },
                "positive_rate": round(positive / total * 100, 1) if total > 0 else 0
            },
            "by_source": {},
            "recent_feedback": self.data["feedbacks"][-10:],
            "action_items": self.metrics["action_items"]
        }
        
        # ソース別集計
        sources = {}
        for f in self.data["feedbacks"]:
            src = f["source"]
            sources[src] = sources.get(src, 0) + 1
        report["by_source"] = sources
        
        return report
    
    def add_action_item(self, item: str):
        """アクションアイテムを追加"""
        self.metrics["action_items"].append({
            "item": item,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        })
        self.save_data()


# FastAPIエンドポイント用
from fastapi import FastAPI
app = FastAPI(title="Feedback Collector API")
collector = FeedbackCollector()

@app.post("/feedback/add")
async def add_feedback(source: str, content: str, sentiment: str = "neutral"):
    """フィードバックを追加"""
    fid = collector.add_feedback(source, content, sentiment)
    return {"feedback_id": fid, "status": "added"}

@app.get("/feedback/report")
async def get_report():
    """フィードバックレポートを取得"""
    return collector.generate_report()

@app.get("/feedback/unprocessed")
async def get_unprocessed():
    """未処理のフィードバックを取得"""
    return {"feedbacks": collector.get_unprocessed()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
