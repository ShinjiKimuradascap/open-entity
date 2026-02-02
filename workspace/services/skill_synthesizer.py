#!/usr/bin/env python3
"""
Skill Synthesizer
分析されたパターンから新しいスキルを自動生成するシステム

Features:
- スキル生成（成功パターンから新スキル提案）
- スキル改善（既存スキルの改良提案）
- スキル統合（関連スキルの統合提案）
- スキル評価（生成スキルの品質評価）
- SkillRegistryとの連携
"""

import json
import logging
import uuid
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Set
from pathlib import Path

from services.skill_registry import SkillRegistry, SkillCategory, SkillRecord
from services.pattern_analyzer import PatternAnalyzer, IdentifiedPattern, PatternType

logger = logging.getLogger(__name__)


class SynthesisType(Enum):
    """合成タイプ"""
    GENERATION = "generation"      # 新規生成
    IMPROVEMENT = "improvement"    # 改善提案
    INTEGRATION = "integration"    # 統合提案
    COMPOSITION = "composition"    # 合成（複数スキルの組み合わせ）


class SkillQualityLevel(Enum):
    """スキル品質レベル"""
    DRAFT = "draft"           # 草案
    EXPERIMENTAL = "experimental"  # 実験的
    BETA = "beta"             # ベータ
    PRODUCTION = "production" # 本番-ready
    REFERENCE = "reference"   # 参考実装


@dataclass
class SynthesizedSkill:
    """合成されたスキル
    
    Attributes:
        skill_id: スキル一意ID
        name: スキル名
        category: スキルカテゴリ
        level: 推奨スキルレベル (1-5)
        description: スキル説明
        synthesis_type: 合成タイプ
        source_patterns: 元になったパターンIDリスト
        source_skills: 元になった既存スキルIDリスト
        quality_score: 品質スコア (0.0-1.0)
        quality_level: 品質レベル
        generated_at: 生成日時
        prerequisites: 前提スキルリスト
        estimated_success_rate: 推定成功率
        use_cases: 使用例リスト
        implementation_hints: 実装ヒント
        confidence: 信頼度 (0.0-1.0)
    """
    skill_id: str
    name: str
    category: SkillCategory
    level: int
    description: str
    synthesis_type: SynthesisType
    source_patterns: List[str] = field(default_factory=list)
    source_skills: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    quality_level: SkillQualityLevel = SkillQualityLevel.DRAFT
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    prerequisites: List[str] = field(default_factory=list)
    estimated_success_rate: float = 0.0
    use_cases: List[str] = field(default_factory=list)
    implementation_hints: List[str] = field(default_factory=list)
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category.value,
            "level": self.level,
            "description": self.description,
            "synthesis_type": self.synthesis_type.value,
            "source_patterns": self.source_patterns,
            "source_skills": self.source_skills,
            "quality_score": self.quality_score,
            "quality_level": self.quality_level.value,
            "generated_at": self.generated_at,
            "prerequisites": self.prerequisites,
            "estimated_success_rate": self.estimated_success_rate,
            "use_cases": self.use_cases,
            "implementation_hints": self.implementation_hints,
            "confidence": self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SynthesizedSkill":
        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            category=SkillCategory(data["category"]),
            level=data["level"],
            description=data["description"],
            synthesis_type=SynthesisType(data["synthesis_type"]),
            source_patterns=data.get("source_patterns", []),
            source_skills=data.get("source_skills", []),
            quality_score=data.get("quality_score", 0.0),
            quality_level=SkillQualityLevel(data.get("quality_level", "draft")),
            generated_at=data.get("generated_at", datetime.now(timezone.utc).isoformat()),
            prerequisites=data.get("prerequisites", []),
            estimated_success_rate=data.get("estimated_success_rate", 0.0),
            use_cases=data.get("use_cases", []),
            implementation_hints=data.get("implementation_hints", []),
            confidence=data.get("confidence", 0.0)
        )


@dataclass
class ImprovementSuggestion:
    """改善提案
    
    Attributes:
        suggestion_id: 提案ID
        target_skill_id: 対象スキルID
        current_level: 現在のレベル
        suggested_level: 推奨レベル
        improvements: 改善点リスト
        rationale: 改善理由
        confidence: 信頼度
        generated_at: 生成日時
    """
    suggestion_id: str
    target_skill_id: str
    current_level: int
    suggested_level: int
    improvements: List[str]
    rationale: str
    confidence: float
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "target_skill_id": self.target_skill_id,
            "current_level": self.current_level,
            "suggested_level": self.suggested_level,
            "improvements": self.improvements,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "generated_at": self.generated_at
        }


@dataclass
class IntegrationProposal:
    """統合提案
    
    Attributes:
        proposal_id: 提案ID
        skill_ids: 統合対象スキルIDリスト
        proposed_name: 提案スキル名
        proposed_category: 提案カテゴリ
        proposed_level: 提案レベル
        description: 説明
        benefits: 統合のメリット
        challenges: 統合の課題
        confidence: 信頼度
        generated_at: 生成日時
    """
    proposal_id: str
    skill_ids: List[str]
    proposed_name: str
    proposed_category: SkillCategory
    proposed_level: int
    description: str
    benefits: List[str]
    challenges: List[str]
    confidence: float
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "skill_ids": self.skill_ids,
            "proposed_name": self.proposed_name,
            "proposed_category": self.proposed_category.value,
            "proposed_level": self.proposed_level,
            "description": self.description,
            "benefits": self.benefits,
            "challenges": self.challenges,
            "confidence": self.confidence,
            "generated_at": self.generated_at
        }


class SkillSynthesizer:
    """スキル合成エンジン
    
    分析されたパターンから新しいスキルを自動生成・評価・提案するシステム。
    SkillRegistryと連携して、生成したスキルを登録できる。
    """
    
    def __init__(
        self,
        pattern_analyzer: Optional[PatternAnalyzer] = None,
        skill_registry: Optional[SkillRegistry] = None,
        data_dir: str = "data/skill_synthesizer"
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 依存コンポーネント
        self.pattern_analyzer = pattern_analyzer or PatternAnalyzer()
        self.skill_registry = skill_registry
        
        # 生成されたスキル: skill_id -> SynthesizedSkill
        self.synthesized_skills: Dict[str, SynthesizedSkill] = {}
        
        # 改善提案: suggestion_id -> ImprovementSuggestion
        self.improvement_suggestions: Dict[str, ImprovementSuggestion] = {}
        
        # 統合提案: proposal_id -> IntegrationProposal
        self.integration_proposals: Dict[str, IntegrationProposal] = {}
        
        # カテゴリ別キーワードマッピング
        self._category_keywords = {
            SkillCategory.PROGRAMMING: [
                "code", "programming", "development", "software", "algorithm",
                "implementation", "function", "class", "module", "api"
            ],
            SkillCategory.ANALYSIS: [
                "analysis", "analytics", "data", "statistics", "metrics",
                "evaluation", "assessment", "review", "inspection"
            ],
            SkillCategory.RESEARCH: [
                "research", "investigation", "study", "exploration",
                "discovery", "experiment", "hypothesis", "survey"
            ],
            SkillCategory.REVIEW: [
                "review", "audit", "check", "verification", "validation",
                "quality", "inspection", "assessment"
            ],
            SkillCategory.DESIGN: [
                "design", "architecture", "pattern", "structure",
                "layout", "interface", "user experience", "ui", "ux"
            ],
            SkillCategory.TESTING: [
                "test", "testing", "verification", "validation",
                "quality assurance", "qa", "automation", "coverage"
            ]
        }
        
        self._load()
        logger.info(f"SkillSynthesizer initialized with {len(self.synthesized_skills)} synthesized skills")
    
    def generate_skills_from_patterns(
        self,
        min_confidence: float = 0.7,
        min_occurrences: int = 3,
        days_back: int = 90
    ) -> List[SynthesizedSkill]:
        """成功パターンから新しいスキルを生成
        
        Args:
            min_confidence: 最小信頼度
            min_occurrences: 最小出現回数
            days_back: 何日前までのデータを分析するか
            
        Returns:
            生成されたSynthesizedSkillのリスト
        """
        logger.info(f"Generating skills from patterns (min_confidence={min_confidence})")
        
        # 成功パターンを取得
        success_patterns = self.pattern_analyzer.identify_success_patterns(
            min_occurrences=min_occurrences,
            min_confidence=min_confidence,
            days_back=days_back
        )
        
        generated_skills = []
        
        for pattern in success_patterns:
            # パターンからスキルを生成
            skill = self._pattern_to_skill(pattern)
            if skill and skill.quality_score >= min_confidence:
                self.synthesized_skills[skill.skill_id] = skill
                generated_skills.append(skill)
                logger.info(f"Generated skill: {skill.name} (quality: {skill.quality_score:.2f})")
        
        self._save()
        logger.info(f"Generated {len(generated_skills)} skills from {len(success_patterns)} patterns")
        return generated_skills
    
    def _pattern_to_skill(self, pattern: IdentifiedPattern) -> Optional[SynthesizedSkill]:
        """パターンをスキルに変換"""
        try:
            # カテゴリを推定
            category = self._infer_category(pattern)
            
            # スキル名を生成
            name = self._generate_skill_name(pattern)
            
            # レベルを推定
            level = self._estimate_skill_level(pattern)
            
            # 説明を生成
            description = self._generate_description(pattern)
            
            # 品質スコアを計算
            quality_score = self._calculate_quality_score(pattern)
            
            # 品質レベルを決定
            quality_level = self._determine_quality_level(quality_score)
            
            # 前提スキルを推定
            prerequisites = self._infer_prerequisites(pattern, category)
            
            # 使用例を生成
            use_cases = self._generate_use_cases(pattern)
            
            # 実装ヒントを生成
            implementation_hints = self._generate_implementation_hints(pattern)
            
            # 推定成功率
            estimated_success_rate = pattern.success_rate if hasattr(pattern, 'success_rate') else 0.7
            
            skill = SynthesizedSkill(
                skill_id=str(uuid.uuid4()),
                name=name,
                category=category,
                level=level,
                description=description,
                synthesis_type=SynthesisType.GENERATION,
                source_patterns=[pattern.pattern_id],
                quality_score=quality_score,
                quality_level=quality_level,
                prerequisites=prerequisites,
                estimated_success_rate=estimated_success_rate,
                use_cases=use_cases,
                implementation_hints=implementation_hints,
                confidence=pattern.confidence
            )
            
            return skill
            
        except Exception as e:
            logger.error(f"Error converting pattern to skill: {e}")
            return None
    
    def _infer_category(self, pattern: IdentifiedPattern) -> SkillCategory:
        """パターンからカテゴリを推定"""
        pattern_text = f"{pattern.pattern_type.value} {pattern.description}".lower()
        
        category_scores = {}
        for category, keywords in self._category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in pattern_text)
            category_scores[category] = score
        
        # 最高スコアのカテゴリを返す
        if category_scores:
            best_category = max(category_scores.items(), key=lambda x: x[1])
            if best_category[1] > 0:
                return best_category[0]
        
        # デフォルトはPROGRAMMING
        return SkillCategory.PROGRAMMING
    
    def _generate_skill_name(self, pattern: IdentifiedPattern) -> str:
        """スキル名を生成"""
        # パターンデータから名前を生成
        if hasattr(pattern, 'metadata') and pattern.metadata:
            if 'task_type' in pattern.metadata:
                task_type = pattern.metadata['task_type'].replace('_', ' ').title()
                return f"{task_type} Optimization"
            if 'category' in pattern.metadata:
                category = pattern.metadata['category'].title()
                return f"Advanced {category}"
        
        # パターンタイプに基づく名前
        type_names = {
            PatternType.SUCCESS: "Success Strategy",
            PatternType.PERFORMANCE: "Performance Optimization",
            PatternType.RESOURCE: "Resource Management",
            PatternType.TEMPORAL: "Timing Strategy"
        }
        
        return type_names.get(pattern.pattern_type, "Synthesized Skill")
    
    def _estimate_skill_level(self, pattern: IdentifiedPattern) -> int:
        """スキルレベルを推定"""
        base_level = 3  # デフォルト中級
        
        # 信頼度でレベルを調整
        if pattern.confidence >= 0.9:
            base_level += 1
        elif pattern.confidence < 0.5:
            base_level -= 1
        
        # 出現頻度で調整
        if hasattr(pattern, 'occurrence_count'):
            if pattern.occurrence_count >= 10:
                base_level += 1
            elif pattern.occurrence_count < 3:
                base_level -= 1
        
        # 範囲内に収める
        return max(1, min(5, base_level))
    
    def _generate_description(self, pattern: IdentifiedPattern) -> str:
        """スキル説明を生成"""
        parts = [
            f"Automatically synthesized skill based on {pattern.occurrence_count} successful executions.",
            f"Pattern type: {pattern.pattern_type.value}.",
            pattern.description
        ]
        
        if hasattr(pattern, 'characteristics') and pattern.characteristics:
            chars = ", ".join(pattern.characteristics[:3])
            parts.append(f"Key characteristics: {chars}.")
        
        return " ".join(parts)
    
    def _calculate_quality_score(self, pattern: IdentifiedPattern) -> float:
        """品質スコアを計算"""
        score = pattern.confidence * 0.4  # 信頼度40%
        
        # 出現回数ボーナス
        if hasattr(pattern, 'occurrence_count'):
            if pattern.occurrence_count >= 10:
                score += 0.3
            elif pattern.occurrence_count >= 5:
                score += 0.2
            elif pattern.occurrence_count >= 3:
                score += 0.1
        
        # 成功率ボーナス
        if hasattr(pattern, 'success_rate'):
            score += pattern.success_rate * 0.3
        
        return min(1.0, score)
    
    def _determine_quality_level(self, score: float) -> SkillQualityLevel:
        """品質レベルを決定"""
        if score >= 0.9:
            return SkillQualityLevel.PRODUCTION
        elif score >= 0.75:
            return SkillQualityLevel.BETA
        elif score >= 0.6:
            return SkillQualityLevel.EXPERIMENTAL
        elif score >= 0.4:
            return SkillQualityLevel.DRAFT
        else:
            return SkillQualityLevel.REFERENCE
    
    def _infer_prerequisites(self, pattern: IdentifiedPattern, category: SkillCategory) -> List[str]:
        """前提スキルを推定"""
        prerequisites = []
        
        # カテゴリ別の基本前提スキル
        category_basics = {
            SkillCategory.PROGRAMMING: ["Basic Programming", "Code Reading"],
            SkillCategory.ANALYSIS: ["Data Interpretation", "Critical Thinking"],
            SkillCategory.RESEARCH: ["Information Gathering", "Documentation"],
            SkillCategory.REVIEW: ["Code Reading", "Quality Awareness"],
            SkillCategory.DESIGN: ["Pattern Recognition", "System Thinking"],
            SkillCategory.TESTING: ["Basic Testing", "Code Reading"]
        }
        
        return category_basics.get(category, [])
    
    def _generate_use_cases(self, pattern: IdentifiedPattern) -> List[str]:
        """使用例を生成"""
        use_cases = [
            f"Apply to similar {pattern.pattern_type.value} scenarios",
            "Use as reference for optimization"
        ]
        
        if hasattr(pattern, 'metadata') and pattern.metadata:
            if 'task_type' in pattern.metadata:
                use_cases.append(f"Optimize {pattern.metadata['task_type']} tasks")
        
        return use_cases
    
    def _generate_implementation_hints(self, pattern: IdentifiedPattern) -> List[str]:
        """実装ヒントを生成"""
        hints = [
            f"Focus on {pattern.pattern_type.value} aspects",
            "Monitor success metrics during implementation"
        ]
        
        if hasattr(pattern, 'characteristics') and pattern.characteristics:
            hints.append(f"Key factors: {', '.join(pattern.characteristics[:2])}")
        
        return hints
    
    def suggest_skill_improvements(
        self,
        agent_id: str,
        min_confidence: float = 0.6
    ) -> List[ImprovementSuggestion]:
        """既存スキルの改善を提案
        
        Args:
            agent_id: 対象エージェントID
            min_confidence: 最小信頼度
            
        Returns:
            改善提案のリスト
        """
        if not self.skill_registry:
            logger.warning("SkillRegistry not available for improvement suggestions")
            return []
        
        logger.info(f"Generating improvement suggestions for agent {agent_id}")
        
        # エージェントのスキルを取得
        agent_skills = self.skill_registry.get_agent_skills(agent_id)
        
        suggestions = []
        
        for skill in agent_skills:
            # パターン分析から改善点を特定
            improvement = self._analyze_skill_improvement(skill, min_confidence)
            if improvement:
                self.improvement_suggestions[improvement.suggestion_id] = improvement
                suggestions.append(improvement)
                logger.info(f"Generated improvement for {skill.name}: level {skill.level} -> {improvement.suggested_level}")
        
        self._save()
        return suggestions
    
    def _analyze_skill_improvement(
        self,
        skill: SkillRecord,
        min_confidence: float
    ) -> Optional[ImprovementSuggestion]:
        """スキルの改善可能性を分析"""
        try:
            # カテゴリ内のパターンを分析
            category_patterns = self.pattern_analyzer.identify_success_patterns(
                min_occurrences=3,
                min_confidence=min_confidence
            )
            
            # スキルに関連するパターンをフィルタリング
            related_patterns = [
                p for p in category_patterns
                if self._is_pattern_related_to_skill(p, skill)
            ]
            
            if not related_patterns:
                return None
            
            # 改善レベルを計算
            avg_confidence = sum(p.confidence for p in related_patterns) / len(related_patterns)
            suggested_level = min(5, skill.level + 1)
            
            # 高いレベルへの改善が必要か判定
            if avg_confidence < min_confidence or skill.level >= 5:
                return None
            
            # 改善点を特定
            improvements = self._extract_improvements(related_patterns)
            
            return ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                target_skill_id=skill.skill_id,
                current_level=skill.level,
                suggested_level=suggested_level,
                improvements=improvements,
                rationale=f"Based on {len(related_patterns)} related success patterns",
                confidence=avg_confidence
            )
            
        except Exception as e:
            logger.error(f"Error analyzing skill improvement: {e}")
            return None
    
    def _is_pattern_related_to_skill(self, pattern: IdentifiedPattern, skill: SkillRecord) -> bool:
        """パターンがスキルに関連するか判定"""
        skill_terms = set(skill.name.lower().split() + skill.description.lower().split())
        pattern_text = f"{pattern.description} {pattern.pattern_type.value}".lower()
        
        # 共通する単語があるか
        for term in skill_terms:
            if len(term) > 3 and term in pattern_text:  # 短すぎる単語は除外
                return True
        
        return False
    
    def _extract_improvements(self, patterns: List[IdentifiedPattern]) -> List[str]:
        """パターンから改善点を抽出"""
        improvements = []
        
        for pattern in patterns:
            if hasattr(pattern, 'characteristics'):
                for char in pattern.characteristics[:2]:
                    if char not in improvements:
                        improvements.append(f"Incorporate {char}")
        
        return improvements[:5]  # 最大5つ
    
    def propose_skill_integrations(
        self,
        agent_id: str,
        min_similarity: float = 0.7
    ) -> List[IntegrationProposal]:
        """スキル統合を提案
        
        Args:
            agent_id: 対象エージェントID
            min_similarity: 最小類似度
            
        Returns:
            統合提案のリスト
        """
        if not self.skill_registry:
            logger.warning("SkillRegistry not available for integration proposals")
            return []
        
        logger.info(f"Generating integration proposals for agent {agent_id}")
        
        # エージェントのスキルを取得
        agent_skills = self.skill_registry.get_agent_skills(agent_id)
        
        if len(agent_skills) < 2:
            logger.info(f"Not enough skills to propose integrations for {agent_id}")
            return []
        
        proposals = []
        
        # スキルペアの類似性を分析
        for i, skill1 in enumerate(agent_skills):
            for skill2 in agent_skills[i+1:]:
                similarity = self._calculate_skill_similarity(skill1, skill2)
                
                if similarity >= min_similarity:
                    proposal = self._create_integration_proposal(
                        [skill1.skill_id, skill2.skill_id],
                        [skill1, skill2],
                        similarity
                    )
                    if proposal:
                        self.integration_proposals[proposal.proposal_id] = proposal
                        proposals.append(proposal)
                        logger.info(f"Generated integration proposal: {proposal.proposed_name}")
        
        self._save()
        return proposals
    
    def _calculate_skill_similarity(self, skill1: SkillRecord, skill2: SkillRecord) -> float:
        """2つのスキルの類似度を計算"""
        # 同じカテゴリか
        if skill1.category != skill2.category:
            return 0.0
        
        # テキスト類似性
        text1 = f"{skill1.name} {skill1.description}".lower()
        text2 = f"{skill2.name} {skill2.description}".lower()
        
        # 単語の重複度を計算
        words1 = set(re.findall(r'\b\w+\b', text1))
        words2 = set(re.findall(r'\b\w+\b', text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _create_integration_proposal(
        self,
        skill_ids: List[str],
        skills: List[SkillRecord],
        confidence: float
    ) -> Optional[IntegrationProposal]:
        """統合提案を作成"""
        try:
            # 統合後の名前を生成
            names = [s.name for s in skills]
            proposed_name = self._generate_integrated_name(names)
            
            # カテゴリは同じはず
            proposed_category = skills[0].category
            
            # レベルは最大値
            proposed_level = max(s.level for s in skills)
            
            # 説明を生成
            description = self._generate_integration_description(skills)
            
            # メリットと課題
            benefits = [
                f"Combines {len(skills)} related skills",
                "Reduces context switching",
                "More comprehensive solution"
            ]
            
            challenges = [
                "Requires understanding of all component skills",
                "May increase complexity"
            ]
            
            return IntegrationProposal(
                proposal_id=str(uuid.uuid4()),
                skill_ids=skill_ids,
                proposed_name=proposed_name,
                proposed_category=proposed_category,
                proposed_level=proposed_level,
                description=description,
                benefits=benefits,
                challenges=challenges,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"Error creating integration proposal: {e}")
            return None
    
    def _generate_integrated_name(self, names: List[str]) -> str:
        """統合後のスキル名を生成"""
        if len(names) == 2:
            return f"{names[0]} & {names[1]} Integration"
        else:
            return f"Multi-Skill Integration ({len(names)} skills)"
    
    def _generate_integration_description(self, skills: List[SkillRecord]) -> str:
        """統合スキルの説明を生成"""
        descriptions = [s.description for s in skills]
        combined = " ".join(descriptions)
        
        return f"Integrated skill combining: {'; '.join([s.name for s in skills])}. {combined[:100]}..."
    
    def evaluate_skill_quality(
        self,
        skill_id: str,
        test_scenarios: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """生成スキルの品質を評価
        
        Args:
            skill_id: 評価対象スキルID
            test_scenarios: テストシナリオ（オプション）
            
        Returns:
            評価結果の辞書
        """
        if skill_id not in self.synthesized_skills:
            return {"error": "Skill not found"}
        
        skill = self.synthesized_skills[skill_id]
        
        evaluation = {
            "skill_id": skill_id,
            "skill_name": skill.name,
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_score": skill.quality_score,
            "quality_level": skill.quality_level.value,
            "confidence": skill.confidence,
            "estimated_success_rate": skill.estimated_success_rate,
            "dimensions": {}
        }
        
        # 各評価次元
        evaluation["dimensions"]["completeness"] = self._evaluate_completeness(skill)
        evaluation["dimensions"]["clarity"] = self._evaluate_clarity(skill)
        evaluation["dimensions"]["feasibility"] = self._evaluate_feasibility(skill)
        evaluation["dimensions"]["utility"] = self._evaluate_utility(skill)
        
        # 総合評価
        dim_scores = [v["score"] for v in evaluation["dimensions"].values()]
        evaluation["overall_score"] = sum(dim_scores) / len(dim_scores) if dim_scores else 0.0
        
        # 推奨アクション
        evaluation["recommendations"] = self._generate_evaluation_recommendations(evaluation)
        
        logger.info(f"Evaluated skill {skill.name}: score={evaluation['overall_score']:.2f}")
        return evaluation
    
    def _evaluate_completeness(self, skill: SynthesizedSkill) -> Dict[str, Any]:
        """完全性を評価"""
        score = 0.0
        checks = []
        
        if skill.description and len(skill.description) > 50:
            score += 0.25
            checks.append("description_complete")
        
        if skill.use_cases:
            score += 0.25
            checks.append("use_cases_present")
        
        if skill.implementation_hints:
            score += 0.25
            checks.append("implementation_hints_present")
        
        if skill.prerequisites:
            score += 0.25
            checks.append("prerequisites_defined")
        
        return {"score": score, "checks": checks}
    
    def _evaluate_clarity(self, skill: SynthesizedSkill) -> Dict[str, Any]:
        """明確性を評価"""
        score = 0.0
        checks = []
        
        # 名前の明確性
        if skill.name and len(skill.name) > 3 and len(skill.name) < 50:
            score += 0.33
            checks.append("name_clear")
        
        # 説明の明確性
        if skill.description and len(skill.description) > 20:
            score += 0.33
            checks.append("description_clear")
        
        # カテゴリの明確性
        if skill.category:
            score += 0.34
            checks.append("category_defined")
        
        return {"score": score, "checks": checks}
    
    def _evaluate_feasibility(self, skill: SynthesizedSkill) -> Dict[str, Any]:
        """実現可能性を評価"""
        score = skill.confidence * 0.5
        
        # レベルの適切さ
        if 1 <= skill.level <= 5:
            score += 0.25
        
        # 前提スキルの有無
        if skill.prerequisites:
            score += 0.25
        
        return {"score": min(1.0, score), "checks": ["confidence_based", "level_appropriate"]}
    
    def _evaluate_utility(self, skill: SynthesizedSkill) -> Dict[str, Any]:
        """有用性を評価"""
        score = skill.estimated_success_rate * 0.5
        
        # 使用例の充実度
        if len(skill.use_cases) >= 3:
            score += 0.25
        elif skill.use_cases:
            score += 0.15
        
        # パターンソースの信頼性
        if skill.source_patterns:
            score += 0.25
        
        return {"score": min(1.0, score), "checks": ["success_rate_based", "use_cases_present"]}
    
    def _generate_evaluation_recommendations(self, evaluation: Dict[str, Any]) -> List[str]:
        """評価に基づく推奨アクションを生成"""
        recommendations = []
        
        dims = evaluation.get("dimensions", {})
        
        if dims.get("completeness", {}).get("score", 0) < 0.7:
            recommendations.append("Add more details to skill description and use cases")
        
        if dims.get("clarity", {}).get("score", 0) < 0.7:
            recommendations.append("Clarify skill name and description")
        
        if dims.get("feasibility", {}).get("score", 0) < 0.6:
            recommendations.append("Review prerequisites and skill level")
        
        if dims.get("utility", {}).get("score", 0) < 0.6:
            recommendations.append("Add more practical use cases")
        
        if evaluation["overall_score"] >= 0.8:
            recommendations.append("Skill is ready for registration")
        
        return recommendations
    
    def register_synthesized_skill(
        self,
        skill_id: str,
        agent_id: str,
        auto_evaluate: bool = True
    ) -> Optional[str]:
        """合成スキルをSkillRegistryに登録
        
        Args:
            skill_id: 合成スキルID
            agent_id: 登録先エージェントID
            auto_evaluate: 登録前に自動評価を行うか
            
        Returns:
            登録されたスキルID、失敗時はNone
        """
        if not self.skill_registry:
            logger.error("SkillRegistry not available for registration")
            return None
        
        if skill_id not in self.synthesized_skills:
            logger.error(f"Synthesized skill not found: {skill_id}")
            return None
        
        skill = self.synthesized_skills[skill_id]
        
        # 品質評価
        if auto_evaluate:
            evaluation = self.evaluate_skill_quality(skill_id)
            if evaluation.get("overall_score", 0) < 0.5:
                logger.warning(f"Skill quality too low for registration: {evaluation['overall_score']:.2f}")
                return None
        
        # SkillRegistryに登録
        registered_id = self.skill_registry.register_skill(
            agent_id=agent_id,
            category=skill.category,
            name=skill.name,
            level=skill.level,
            description=skill.description
        )
        
        if registered_id:
            logger.info(f"Successfully registered synthesized skill: {skill.name} -> {registered_id}")
            # 品質レベルを更新
            skill.quality_level = SkillQualityLevel.PRODUCTION
            self._save()
        
        return registered_id
    
    def get_synthesis_report(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """合成レポートを生成
        
        Args:
            agent_id: 特定エージェントのレポート（Noneで全体）
            
        Returns:
            レポート辞書
        """
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {},
            "synthesized_skills": [],
            "improvement_suggestions": [],
            "integration_proposals": []
        }
        
        # サマリー
        report["summary"]["total_synthesized"] = len(self.synthesized_skills)
        report["summary"]["total_improvements"] = len(self.improvement_suggestions)
        report["summary"]["total_integrations"] = len(self.integration_proposals)
        
        # 品質レベル別カウント
        quality_counts = {}
        for skill in self.synthesized_skills.values():
            level = skill.quality_level.value
            quality_counts[level] = quality_counts.get(level, 0) + 1
        report["summary"]["quality_distribution"] = quality_counts
        
        # スキル一覧
        for skill in self.synthesized_skills.values():
            report["synthesized_skills"].append({
                "skill_id": skill.skill_id,
                "name": skill.name,
                "category": skill.category.value,
                "quality_score": skill.quality_score,
                "quality_level": skill.quality_level.value,
                "confidence": skill.confidence
            })
        
        # 改善提案一覧
        for suggestion in self.improvement_suggestions.values():
            report["improvement_suggestions"].append({
                "suggestion_id": suggestion.suggestion_id,
                "target_skill": suggestion.target_skill_id,
                "current_level": suggestion.current_level,
                "suggested_level": suggestion.suggested_level,
                "confidence": suggestion.confidence
            })
        
        # 統合提案一覧
        for proposal in self.integration_proposals.values():
            report["integration_proposals"].append({
                "proposal_id": proposal.proposal_id,
                "proposed_name": proposal.proposed_name,
                "skill_count": len(proposal.skill_ids),
                "confidence": proposal.confidence
            })
        
        return report
    
    def export_synthesis_data(self, file_path: Optional[str] = None) -> str:
        """合成データをエクスポート
        
        Args:
            file_path: 出力ファイルパス（Noneで自動生成）
            
        Returns:
            エクスポートされたファイルパス
        """
        if file_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = str(self.data_dir / f"synthesis_export_{timestamp}.json")
        
        export_data = {
            "export_info": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0"
            },
            "synthesized_skills": [s.to_dict() for s in self.synthesized_skills.values()],
            "improvement_suggestions": [s.to_dict() for s in self.improvement_suggestions.values()],
            "integration_proposals": [p.to_dict() for p in self.integration_proposals.values()]
        }
        
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Synthesis data exported to {file_path}")
        return file_path
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "synthesized_skills": {
                k: v.to_dict() for k, v in self.synthesized_skills.items()
            },
            "improvement_suggestions": {
                k: v.to_dict() for k, v in self.improvement_suggestions.items()
            },
            "integration_proposals": {
                k: v.to_dict() for k, v in self.integration_proposals.items()
            }
        }
    
    def _save(self):
        """データを保存"""
        file_path = self.data_dir / "skill_synthesizer.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        file_path = self.data_dir / "skill_synthesizer.json"
        if not file_path.exists():
            return
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # 合成スキル復元
            for skill_id, skill_data in data.get("synthesized_skills", {}).items():
                self.synthesized_skills[skill_id] = SynthesizedSkill.from_dict(skill_data)
            
            # 改善提案復元
            for sug_id, sug_data in data.get("improvement_suggestions", {}).items():
                self.improvement_suggestions[sug_id] = ImprovementSuggestion(**sug_data)
            
            # 統合提案復元
            for prop_id, prop_data in data.get("integration_proposals", {}).items():
                self.integration_proposals[prop_id] = IntegrationProposal(**prop_data)
            
            logger.info(f"Loaded synthesis data: {len(self.synthesized_skills)} skills")
        except Exception as e:
            logger.error(f"Error loading synthesis data: {e}")


# グローバルインスタンス管理
_synthesizer_instance: Optional[SkillSynthesizer] = None


def get_skill_synthesizer(
    pattern_analyzer: Optional[PatternAnalyzer] = None,
    skill_registry: Optional[SkillRegistry] = None
) -> SkillSynthesizer:
    """スキル合成エンジンのグローバルインスタンスを取得"""
    global _synthesizer_instance
    if _synthesizer_instance is None:
        _synthesizer_instance = SkillSynthesizer(
            pattern_analyzer=pattern_analyzer,
            skill_registry=skill_registry
        )
    return _synthesizer_instance


def reset_synthesizer():
    """合成エンジンをリセット（テスト用）"""
    global _synthesizer_instance
    _synthesizer_instance = None


def synthesize_skills_from_experience(
    min_confidence: float = 0.7,
    auto_register: bool = False,
    agent_id: Optional[str] = None
) -> List[SynthesizedSkill]:
    """経験データからスキルを合成（ショートカット関数）
    
    Args:
        min_confidence: 最小信頼度
        auto_register: 自動的にSkillRegistryに登録するか
        agent_id: 登録先エージェントID（auto_register=True時に必要）
        
    Returns:
        生成されたスキルのリスト
    """
    synthesizer = get_skill_synthesizer()
    
    skills = synthesizer.generate_skills_from_patterns(
        min_confidence=min_confidence
    )
    
    if auto_register and agent_id:
        for skill in skills:
            synthesizer.register_synthesized_skill(skill.skill_id, agent_id)
    
    return skills


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    synthesizer = SkillSynthesizer()
    
    print("\n=== SkillSynthesizer テスト ===")
    
    # スキル生成テスト（ダミーパターンで）
    print("\n1. スキル生成テスト")
    # 注意: PatternAnalyzerにデータがない場合は空のリストが返る
    skills = synthesizer.generate_skills_from_patterns(min_confidence=0.5)
    print(f"Generated {len(skills)} skills")
    
    # レポート取得
    print("\n2. レポート取得")
    report = synthesizer.get_synthesis_report()
    print(f"Total synthesized: {report['summary']['total_synthesized']}")
    
    print("\n=== テスト完了 ===")
