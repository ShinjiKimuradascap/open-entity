#!/usr/bin/env python3
"""
AI Transaction Protocol - Peer Service Integration
AI間取引プロトコルのPeerService統合モジュール

This module provides message handlers for AI transaction protocol
that can be registered with PeerService.
"""

import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone

from .ai_transaction_protocol import (
    TaskProposal, TaskQuote, Agreement,
    TransactionStatus, AITransactionManager, get_transaction_manager
)

logger = logging.getLogger(__name__)


class AITransactionIntegration:
    """AIトランザクションプロトコルのPeerService統合クラス"""
    
    def __init__(self, peer_service=None):
        self.peer_service = peer_service
        self.tx_manager = get_transaction_manager()
        self._callbacks: Dict[str, Callable] = {}
        
    def register_with_peer_service(self, peer_service) -> None:
        """PeerServiceにハンドラを登録"""
        self.peer_service = peer_service
        
        # Register message handlers
        peer_service.register_handler("task_proposal", self._handle_task_proposal)
        peer_service.register_handler("task_quote", self._handle_task_quote)
        peer_service.register_handler("agreement", self._handle_agreement)
        peer_service.register_handler("task_complete", self._handle_task_complete)
        peer_service.register_handler("payment_release", self._handle_payment_release)
        peer_service.register_handler("dispute", self._handle_dispute)
        
        logger.info("AI Transaction handlers registered with PeerService")
    
    async def _handle_task_proposal(self, message: Dict[str, Any]) -> None:
        """task_proposalメッセージハンドラ"""
        try:
            payload = message.get("payload", {})
            proposal_data = payload.get("proposal", {})
            
            # Deserialize proposal
            proposal = TaskProposal.from_dict(proposal_data)
            
            # Store in manager
            self.tx_manager._proposals[proposal.proposal_id] = proposal
            
            logger.info(f"Received task proposal {proposal.proposal_id} from {proposal.client_id}")
            
            # Trigger callback if registered
            if "on_proposal" in self._callbacks:
                await self._callbacks["on_proposal"](proposal, message)
            
            # Send acknowledgment
            if self.peer_service:
                await self._send_ack(message, "proposal_received", {
                    "proposal_id": proposal.proposal_id,
                    "status": "accepted"
                })
                
        except Exception as e:
            logger.error(f"Error handling task_proposal: {e}")
            await self._send_error(message, f"Invalid proposal: {str(e)}")
    
    async def _handle_task_quote(self, message: Dict[str, Any]) -> None:
        """task_quoteメッセージハンドラ"""
        try:
            payload = message.get("payload", {})
            quote_data = payload.get("quote", {})
            
            # Deserialize quote
            quote = TaskQuote.from_dict(quote_data)
            
            # Store in manager
            self.tx_manager._quotes[quote.quote_id] = quote
            
            logger.info(f"Received task quote {quote.quote_id} from {quote.provider_id}")
            
            # Trigger callback if registered
            if "on_quote" in self._callbacks:
                await self._callbacks["on_quote"](quote, message)
            
            # Send acknowledgment
            if self.peer_service:
                await self._send_ack(message, "quote_received", {
                    "quote_id": quote.quote_id,
                    "status": "accepted"
                })
                
        except Exception as e:
            logger.error(f"Error handling task_quote: {e}")
            await self._send_error(message, f"Invalid quote: {str(e)}")
    
    async def _handle_agreement(self, message: Dict[str, Any]) -> None:
        """agreementメッセージハンドラ"""
        try:
            payload = message.get("payload", {})
            agreement_data = payload.get("agreement", {})
            
            # Deserialize agreement
            agreement = Agreement.from_dict(agreement_data)
            
            # Store in manager
            self.tx_manager._agreements[agreement.agreement_id] = agreement
            self.tx_manager.update_status(agreement.agreement_id, TransactionStatus.AGREED)
            
            logger.info(f"Received agreement {agreement.agreement_id} for task {agreement.task_id}")
            
            # Trigger callback if registered
            if "on_agreement" in self._callbacks:
                await self._callbacks["on_agreement"](agreement, message)
            
            # Send acknowledgment
            if self.peer_service:
                await self._send_ack(message, "agreement_received", {
                    "agreement_id": agreement.agreement_id,
                    "task_id": agreement.task_id,
                    "status": "confirmed"
                })
                
        except Exception as e:
            logger.error(f"Error handling agreement: {e}")
            await self._send_error(message, f"Invalid agreement: {str(e)}")
    
    async def _handle_task_complete(self, message: Dict[str, Any]) -> None:
        """task_completeメッセージハンドラ"""
        try:
            payload = message.get("payload", {})
            task_id = payload.get("task_id")
            agreement_id = payload.get("agreement_id")
            result = payload.get("result", {})
            
            if not task_id or not agreement_id:
                raise ValueError("Missing task_id or agreement_id")
            
            # Update status
            self.tx_manager.update_status(agreement_id, TransactionStatus.COMPLETED)
            
            logger.info(f"Task {task_id} marked as completed")
            
            # Trigger callback if registered
            if "on_task_complete" in self._callbacks:
                await self._callbacks["on_task_complete"](task_id, result, message)
            
            # Send acknowledgment
            if self.peer_service:
                await self._send_ack(message, "completion_received", {
                    "task_id": task_id,
                    "status": "verified"
                })
                
        except Exception as e:
            logger.error(f"Error handling task_complete: {e}")
            await self._send_error(message, f"Invalid completion: {str(e)}")
    
    async def _handle_payment_release(self, message: Dict[str, Any]) -> None:
        """payment_releaseメッセージハンドラ"""
        try:
            payload = message.get("payload", {})
            agreement_id = payload.get("agreement_id")
            amount = payload.get("amount")
            
            if not agreement_id:
                raise ValueError("Missing agreement_id")
            
            # Update status
            self.tx_manager.update_status(agreement_id, TransactionStatus.RELEASED)
            
            logger.info(f"Payment released for agreement {agreement_id}")
            
            # Trigger callback if registered
            if "on_payment_release" in self._callbacks:
                await self._callbacks["on_payment_release"](agreement_id, amount, message)
            
            # Send acknowledgment
            if self.peer_service:
                await self._send_ack(message, "payment_received", {
                    "agreement_id": agreement_id,
                    "amount": amount,
                    "status": "confirmed"
                })
                
        except Exception as e:
            logger.error(f"Error handling payment_release: {e}")
            await self._send_error(message, f"Invalid payment release: {str(e)}")
    
    async def _handle_dispute(self, message: Dict[str, Any]) -> None:
        """disputeメッセージハンドラ"""
        try:
            payload = message.get("payload", {})
            agreement_id = payload.get("agreement_id")
            reason = payload.get("reason", "No reason provided")
            
            if not agreement_id:
                raise ValueError("Missing agreement_id")
            
            # Update status
            self.tx_manager.update_status(agreement_id, TransactionStatus.DISPUTED)
            
            logger.warning(f"Dispute opened for agreement {agreement_id}: {reason}")
            
            # Trigger callback if registered
            if "on_dispute" in self._callbacks:
                await self._callbacks["on_dispute"](agreement_id, reason, message)
            
            # Send acknowledgment
            if self.peer_service:
                await self._send_ack(message, "dispute_received", {
                    "agreement_id": agreement_id,
                    "status": "under_review"
                })
                
        except Exception as e:
            logger.error(f"Error handling dispute: {e}")
            await self._send_error(message, f"Invalid dispute: {str(e)}")
    
    async def _send_ack(self, original_msg: Dict[str, Any], ack_type: str, data: Dict[str, Any]) -> None:
        """確認応答を送信"""
        if not self.peer_service:
            return
        
        sender = original_msg.get("sender")
        if not sender:
            return
        
        ack_message = {
            "type": ack_type,
            "payload": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "in_reply_to": original_msg.get("message_id")
        }
        
        # Use peer_service to send message
        await self.peer_service.send_to_peer(sender, ack_message)
    
    async def _send_error(self, original_msg: Dict[str, Any], error_msg: str) -> None:
        """エラー応答を送信"""
        if not self.peer_service:
            return
        
        sender = original_msg.get("sender")
        if not sender:
            return
        
        error_message = {
            "type": "error",
            "payload": {
                "error": error_msg,
                "original_type": original_msg.get("type")
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "in_reply_to": original_msg.get("message_id")
        }
        
        await self.peer_service.send_to_peer(sender, error_message)
    
    # === Callback Registration ===
    
    def on_proposal(self, callback: Callable) -> None:
        """提案受信時のコールバックを登録"""
        self._callbacks["on_proposal"] = callback
    
    def on_quote(self, callback: Callable) -> None:
        """見積もり受信時のコールバックを登録"""
        self._callbacks["on_quote"] = callback
    
    def on_agreement(self, callback: Callable) -> None:
        """合意受信時のコールバックを登録"""
        self._callbacks["on_agreement"] = callback
    
    def on_task_complete(self, callback: Callable) -> None:
        """タスク完了受信時のコールバックを登録"""
        self._callbacks["on_task_complete"] = callback
    
    def on_payment_release(self, callback: Callable) -> None:
        """支払い解放受信時のコールバックを登録"""
        self._callbacks["on_payment_release"] = callback
    
    def on_dispute(self, callback: Callable) -> None:
        """紛争受信時のコールバックを登録"""
        self._callbacks["on_dispute"] = callback
    
    # === Helper Methods for Sending ===
    
    async def send_task_proposal(self, recipient: str, proposal: TaskProposal) -> bool:
        """タスク提案を送信"""
        if not self.peer_service:
            logger.error("PeerService not available")
            return False
        
        message = {
            "type": "task_proposal",
            "payload": {
                "proposal": proposal.to_dict()
            }
        }
        
        return await self.peer_service.send_to_peer(recipient, message)
    
    async def send_task_quote(self, recipient: str, quote: TaskQuote) -> bool:
        """タスク見積もりを送信"""
        if not self.peer_service:
            logger.error("PeerService not available")
            return False
        
        message = {
            "type": "task_quote",
            "payload": {
                "quote": quote.to_dict()
            }
        }
        
        return await self.peer_service.send_to_peer(recipient, message)
    
    async def send_agreement(self, recipient: str, agreement: Agreement) -> bool:
        """取引合意を送信"""
        if not self.peer_service:
            logger.error("PeerService not available")
            return False
        
        message = {
            "type": "agreement",
            "payload": {
                "agreement": agreement.to_dict()
            }
        }
        
        return await self.peer_service.send_to_peer(recipient, message)
    
    async def send_task_complete(self, recipient: str, task_id: str, agreement_id: str, result: Dict[str, Any]) -> bool:
        """タスク完了を通知"""
        if not self.peer_service:
            logger.error("PeerService not available")
            return False
        
        message = {
            "type": "task_complete",
            "payload": {
                "task_id": task_id,
                "agreement_id": agreement_id,
                "result": result
            }
        }
        
        return await self.peer_service.send_to_peer(recipient, message)


# Global instance
_integration_instance: Optional[AITransactionIntegration] = None


def get_transaction_integration(peer_service=None) -> AITransactionIntegration:
    """グローバル統合インスタンスを取得"""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = AITransactionIntegration(peer_service)
    return _integration_instance
