// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/**
 * @title SkillToken
 * @dev AIエージェントのスキル検証と信頼性をトークン化
 * スキルレベルに応じたトークン報酬、検証者報酬、ステーキング機能
 */
contract SkillToken is ERC20, Ownable, ReentrancyGuard {
    
    // スキルカテゴリ
    enum SkillCategory { PROGRAMMING, ANALYSIS, RESEARCH, REVIEW, DESIGN, TESTING }
    
    // スキルレコード
    struct Skill {
        address agent;
        SkillCategory category;
        uint8 level; // 1-5
        uint256 verifiedAt;
        address verifier;
        uint256 stakedAmount;
        bool isActive;
    }
    
    // 検証者情報
    struct Verifier {
        uint256 reputation;
        uint256 verifiedCount;
        bool isActive;
    }
    
    // スキルID => スキル情報
    mapping(bytes32 => Skill) public skills;
    
    // エージェント => スキルID[]
    mapping(address => bytes32[]) public agentSkills;
    
    // 検証者 => 情報
    mapping(address => Verifier) public verifiers;
    
    // カテゴリ別レベル報酬（レベル1-5）
    mapping(SkillCategory => uint256[5]) public levelRewards;
    
    // 最低ステーキング額
    uint256 public minStake = 100 * 10**18; // 100 SKILL
    
    // 検証者報酬率（10% = 1000）
    uint256 public verifierRewardRate = 1000;
    
    // イベント
    event SkillRegistered(bytes32 indexed skillId, address indexed agent, SkillCategory category, uint8 level);
    event SkillVerified(bytes32 indexed skillId, address indexed verifier);
    event SkillStaked(bytes32 indexed skillId, uint256 amount);
    event SkillUnstaked(bytes32 indexed skillId, uint256 amount);
    event VerifierRegistered(address indexed verifier);
    event RewardDistributed(bytes32 indexed skillId, uint256 amount);
    
    constructor() ERC20("Skill Token", "SKILL") {
        // 初期供給量: 1,000,000 SKILL
        _mint(msg.sender, 1_000_000 * 10**18);
        
        // レベル報酬設定（カテゴリ共通）
        // レベル1: 50, レベル2: 150, レベル3: 300, レベル4: 500, レベル5: 1000
        for (uint i = 0; i < 6; i++) {
            levelRewards[SkillCategory(i)] = [50, 150, 300, 500, 1000];
        }
    }
    
    /**
     * @dev スキルを登録（ステーキング付き）
     */
    function registerSkill(
        SkillCategory category,
        uint8 level,
        uint256 stakeAmount
    ) external nonReentrant returns (bytes32) {
        require(level >= 1 && level <= 5, "Invalid level");
        require(stakeAmount >= minStake, "Insufficient stake");
        require(balanceOf(msg.sender) >= stakeAmount, "Insufficient balance");
        
        // スキルID生成
        bytes32 skillId = keccak256(abi.encodePacked(
            msg.sender,
            category,
            level,
            block.timestamp
        ));
        
        // スキル情報保存
        skills[skillId] = Skill({
            agent: msg.sender,
            category: category,
            level: level,
            verifiedAt: 0,
            verifier: address(0),
            stakedAmount: stakeAmount,
            isActive: true
        });
        
        // ステーキング
        _transfer(msg.sender, address(this), stakeAmount);
        
        // エージェントのスキルリストに追加
        agentSkills[msg.sender].push(skillId);
        
        emit SkillRegistered(skillId, msg.sender, category, level);
        emit SkillStaked(skillId, stakeAmount);
        
        return skillId;
    }
    
    /**
     * @dev スキルを検証（検証者機能）
     */
    function verifySkill(bytes32 skillId) external {
        require(verifiers[msg.sender].isActive, "Not a verifier");
        Skill storage skill = skills[skillId];
        require(skill.isActive, "Skill not active");
        require(skill.verifier == address(0), "Already verified");
        
        skill.verifiedAt = block.timestamp;
        skill.verifier = msg.sender;
        
        // 検証者の実績更新
        verifiers[msg.sender].verifiedCount++;
        verifiers[msg.sender].reputation += skill.level * 10;
        
        emit SkillVerified(skillId, msg.sender);
    }
    
    /**
     * @dev 報酬を分配（検証後に実行）
     */
    function distributeReward(bytes32 skillId) external nonReentrant {
        Skill storage skill = skills[skillId];
        require(skill.verifiedAt > 0, "Not verified");
        require(skill.isActive, "Skill not active");
        
        uint256 reward = levelRewards[skill.category][skill.level - 1] * 10**18;
        uint256 verifierReward = (reward * verifierRewardRate) / 10000;
        uint256 agentReward = reward - verifierReward;
        
        // エージェントに報酬
        _mint(skill.agent, agentReward);
        
        // 検証者に報酬
        if (skill.verifier != address(0)) {
            _mint(skill.verifier, verifierReward);
        }
        
        emit RewardDistributed(skillId, reward);
    }
    
    /**
     * @dev スキルアンステーク
     */
    function unstakeSkill(bytes32 skillId) external nonReentrant {
        Skill storage skill = skills[skillId];
        require(skill.agent == msg.sender, "Not owner");
        require(skill.stakedAmount > 0, "No stake");
        require(skill.verifiedAt == 0, "Already verified - cannot unstake");
        
        uint256 amount = skill.stakedAmount;
        skill.stakedAmount = 0;
        skill.isActive = false;
        
        _transfer(address(this), msg.sender, amount);
        
        emit SkillUnstaked(skillId, amount);
    }
    
    /**
     * @dev 検証者として登録
     */
    function registerVerifier() external {
        require(!verifiers[msg.sender].isActive, "Already registered");
        require(balanceOf(msg.sender) >= minStake, "Insufficient balance");
        
        verifiers[msg.sender] = Verifier({
            reputation: 0,
            verifiedCount: 0,
            isActive: true
        });
        
        emit VerifierRegistered(msg.sender);
    }
    
    /**
     * @dev エージェントのスキル一覧取得
     */
    function getAgentSkills(address agent) external view returns (bytes32[] memory) {
        return agentSkills[agent];
    }
    
    /**
     * @dev スキル詳細取得
     */
    function getSkill(bytes32 skillId) external view returns (Skill memory) {
        return skills[skillId];
    }
    
    /**
     * @dev 総ステーキング量取得
     */
    function getTotalStaked() external view returns (uint256) {
        return balanceOf(address(this));
    }
}