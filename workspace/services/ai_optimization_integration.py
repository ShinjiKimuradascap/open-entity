"""
AI Optimization Integration
Phase 2コンポーネント統合モジュール

統合構成:
- AIPerformanceMonitor: システム監視
- AIAutoScaler: 自動スケーリング
- AIAnomalyDetector: 異常検出・対応
"""

import asyncio
import logging
from typing import Optional, Dict, Any

from services.ai_performance_monitor import (
    AIPerformanceMonitor, 
    PerformanceThresholds,
    get_performance_monitor
)
from services.ai_auto_scaler import (
    AIAutoScaler,
    ScalingStrategy,
    get_auto_scaler
)
from services.ai_anomaly_detector import (
    AIAnomalyDetector,
    AnomalyDetectionConfig,
    AutoRecoveryAction,
    get_anomaly_detector
)

logger = logging.getLogger(__name__)


class AIOptimizationIntegration:
    """
    Phase 2 AI自動運用最適化統合クラス
    
    3つのコンポーネントを連携させ、自律的なシステム最適化を実現
    """
    
    def __init__(self):
        self.monitor: Optional[AIPerformanceMonitor] = None
        self.scaler: Optional[AIAutoScaler] = None
        self.detector: Optional[AIAnomalyDetector] = None
        self._running = False
    
    async def initialize(self):
        """統合の初期化"""
        logger.info("Initializing AI Optimization Integration...")
        
        # 1. Performance Monitor初期化
        self.monitor = get_performance_monitor()
        
        # 2. Auto-Scaler初期化（Monitor連携）
        scaling_strategy = ScalingStrategy(
            scale_up_threshold=75.0,
            scale_down_threshold=25.0,
            cooldown_period=300,
            min_instances=1,
            max_instances=10,
            prediction_enabled=True
        )
        self.scaler = get_auto_scaler(self.monitor)
        self.scaler.strategy = scaling_strategy
        
        # コールバック登録
        self.scaler.register_scale_up_callback(self._on_scale_up)
        self.scaler.register_scale_down_callback(self._on_scale_down)
        
        # 3. Anomaly Detector初期化（Monitor連携）
        detection_config = AnomalyDetectionConfig(
            z_score_threshold=3.0,
            iqr_multiplier=1.5,
            window_size=20,
            check_interval=30.0,
            auto_recovery_actions=[
                AutoRecoveryAction.LOG_ONLY,
                AutoRecoveryAction.ALERT_ADMIN
            ]
        )
        self.detector = get_anomaly_detector(self.monitor)
        self.detector.config = detection_config
        
        # コールバック登録
        self.detector.register_anomaly_callback(self._on_anomaly_detected)
        self.detector.register_recovery_callback(self._on_recovery_action)
        
        logger.info("AI Optimization Integration initialized successfully")
    
    async def start(self):
        """統合システム開始"""
        if self._running:
            return
        
        await self.initialize()
        
        logger.info("Starting AI Optimization Integration...")
        
        # 各コンポーネント開始
        await self.monitor.start()
        await self.scaler.start()
        await self.detector.start()
        
        self._running = True
        logger.info("AI Optimization Integration started")
    
    async def stop(self):
        """統合システム停止"""
        if not self._running:
            return
        
        logger.info("Stopping AI Optimization Integration...")
        
        await self.detector.stop()
        await self.scaler.stop()
        await self.monitor.stop()
        
        self._running = False
        logger.info("AI Optimization Integration stopped")
    
    # コールバックハンドラ
    async def _on_scale_up(self, metrics: Dict[str, Any]):
        """スケールアップ時の処理"""
        logger.info(f"Scale up triggered: {metrics}")
        # 実際のインフラ操作はここに実装
    
    async def _on_scale_down(self, metrics: Dict[str, Any]):
        """スケールダウン時の処理"""
        logger.info(f"Scale down triggered: {metrics}")
        # 実際のインフラ操作はここに実装
    
    async def _on_anomaly_detected(self, anomaly):
        """異常検出時の処理"""
        logger.warning(f"Anomaly detected: {anomaly}")
        # 異常に応じた追加処理
    
    async def _on_recovery_action(self, action, anomaly):
        """復旧アクション時の処理"""
        logger.info(f"Recovery action: {action} for {anomaly}")
    
    # 統合ステータス
    def get_status(self) -> Dict[str, Any]:
        """統合システムステータス取得"""
        return {
            "running": self._running,
            "monitor": self.monitor is not None,
            "scaler": self.scaler is not None,
            "detector": self.detector is not None
        }


# グローバルインスタンス
_optimization_integration: Optional[AIOptimizationIntegration] = None


def get_optimization_integration() -> AIOptimizationIntegration:
    """グローバル統合インスタンス取得"""
    global _optimization_integration
    if _optimization_integration is None:
        _optimization_integration = AIOptimizationIntegration()
    return _optimization_integration


# デモ
async def demo():
    """統合デモ"""
    integration = get_optimization_integration()
    
    # 開始
    await integration.start()
    
    # 30秒間監視
    print("Monitoring for 30 seconds...")
    await asyncio.sleep(30)
    
    # ステータス表示
    status = integration.get_status()
    print(f"Status: {status}")
    
    # 停止
    await integration.stop()
    print("Demo completed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo())
