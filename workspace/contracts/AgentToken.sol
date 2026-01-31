// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

interface IAgentIdentity {
    function isActive(uint256 tokenId) external view returns (bool);
    function getAgent(uint256 tokenId) external view returns (Agent memory);
    struct Agent {
        string name;
        string endpoint;
        string publicKey;
        uint256 registeredAt;
        bool active;
    }
}

interface IReputationRegistry {
    function getTrustScore(uint256 agentId) external view returns (uint256);
}

/**
 * @title AgentToken
 * @dev ERC-20 token for AI Agent economy
 * Used for task rewards, staking, and governance
 */
contract AgentToken is ERC20, ERC20Burnable, Ownable, ReentrancyGuard {
    
    // Reference to registries
    IAgentIdentity public agentIdentity;
    IReputationRegistry public reputationRegistry;
    
    // Reward parameters
    uint256 public baseReward;
    uint256 public trustMultiplier;
    uint256 public dailyMintLimit;
    uint256 public dailyMinted;
    uint256 public lastMintReset;
    
    // Staking
    struct Stake {
        uint256 amount;
        uint256 since;
        uint256 rewardDebt;
    }
    
    mapping(address => Stake) public stakes;
    uint256 public totalStaked;
    uint256 public rewardPerToken;
    uint256 public constant REWARD_RATE = 1e18; // 1 token per second per 1e18 staked
    
    // Task rewards
    struct TaskReward {
        uint256 agentId;
        uint256 amount;
        bytes32 taskHash;
        bool claimed;
    }
    
    mapping(uint256 => TaskReward) public taskRewards;
    uint256 public taskRewardCounter;
    
    // Governance
    mapping(address => bool) public rewardDistributors;
    
    // Events
    event TaskRewardCreated(
        uint256 indexed rewardId,
        uint256 indexed agentId,
        uint256 amount,
        bytes32 taskHash
    );
    
    event RewardClaimed(
        uint256 indexed rewardId,
        address indexed claimer,
        uint256 amount
    );
    
    event Staked(address indexed user, uint256 amount);
    event Unstaked(address indexed user, uint256 amount);
    event RewardDistributed(address indexed user, uint256 amount);
    
    modifier onlyDistributor() {
        require(
            rewardDistributors[msg.sender] || msg.sender == owner(),
            "Not authorized"
        );
        _;
    }
    
    modifier onlyActiveAgent(uint256 agentId) {
        require(_agentExists(agentId), "Agent not found");
        require(agentIdentity.isActive(agentId), "Agent not active");
        _;
    }
    
    constructor(
        address agentIdentityAddress,
        address reputationRegistryAddress,
        uint256 initialSupply
    ) ERC20("AI Collaboration Token", "AIC") Ownable(msg.sender) {
        require(agentIdentityAddress != address(0), "Invalid AgentIdentity");
        agentIdentity = IAgentIdentity(agentIdentityAddress);
        reputationRegistry = IReputationRegistry(reputationRegistryAddress);
        
        baseReward = 100 * 10**decimals();
        trustMultiplier = 10;
        dailyMintLimit = 100000 * 10**decimals();
        lastMintReset = block.timestamp;
        
        // Mint initial supply to contract
        _mint(address(this), initialSupply);
    }
    
    /**
     * @dev Create a task reward
     */
    function createTaskReward(
        uint256 agentId,
        uint256 amount,
        bytes32 taskHash
    ) external onlyDistributor onlyActiveAgent(agentId) returns (uint256) {
        require(amount > 0, "Amount must be positive");
        require(
            balanceOf(address(this)) >= amount,
            "Insufficient contract balance"
        );
        
        uint256 rewardId = taskRewardCounter++;
        
        taskRewards[rewardId] = TaskReward({
            agentId: agentId,
            amount: amount,
            taskHash: taskHash,
            claimed: false
        });
        
        emit TaskRewardCreated(rewardId, agentId, amount, taskHash);
        
        return rewardId;
    }
    
    /**
     * @dev Claim a task reward
     */
    function claimTaskReward(uint256 rewardId) external nonReentrant {
        TaskReward storage reward = taskRewards[rewardId];
        require(!reward.claimed, "Already claimed");
        require(reward.amount > 0, "Reward not found");
        
        // Verify claimer is the agent owner
        address agentOwner = _getAgentOwner(reward.agentId);
        require(msg.sender == agentOwner, "Not agent owner");
        
        reward.claimed = true;
        _transfer(address(this), msg.sender, reward.amount);
        
        emit RewardClaimed(rewardId, msg.sender, reward.amount);
    }
    
    /**
     * @dev Calculate reward based on trust score
     */
    function calculateReward(uint256 agentId) public view returns (uint256) {
        uint256 trustScore = reputationRegistry.getTrustScore(agentId);
        // Higher trust = higher multiplier (1.0x to 2.0x)
        uint256 multiplier = 100 + (trustScore * trustMultiplier / 100);
        return (baseReward * multiplier) / 100;
    }
    
    /**
     * @dev Mint reward tokens (with daily limit)
     */
    function mintReward(address to, uint256 amount) external onlyDistributor {
        _resetDailyMintIfNeeded();
        require(dailyMinted + amount <= dailyMintLimit, "Daily limit exceeded");
        
        dailyMinted += amount;
        _mint(to, amount);
    }
    
    /**
     * @dev Stake tokens for governance and rewards
     */
    function stake(uint256 amount) external nonReentrant {
        require(amount > 0, "Amount must be positive");
        require(balanceOf(msg.sender) >= amount, "Insufficient balance");
        
        _updateReward(msg.sender);
        
        _transfer(msg.sender, address(this), amount);
        stakes[msg.sender].amount += amount;
        stakes[msg.sender].since = block.timestamp;
        totalStaked += amount;
        
        emit Staked(msg.sender, amount);
    }
    
    /**
     * @dev Unstake tokens
     */
    function unstake(uint256 amount) external nonReentrant {
        Stake storage userStake = stakes[msg.sender];
        require(userStake.amount >= amount, "Insufficient stake");
        
        _updateReward(msg.sender);
        
        userStake.amount -= amount;
        totalStaked -= amount;
        _transfer(address(this), msg.sender, amount);
        
        emit Unstaked(msg.sender, amount);
    }
    
    /**
     * @dev Claim staking rewards
     */
    function claimStakeReward() external nonReentrant {
        _updateReward(msg.sender);
        
        uint256 reward = stakes[msg.sender].rewardDebt;
        require(reward > 0, "No reward available");
        
        stakes[msg.sender].rewardDebt = 0;
        _transfer(address(this), msg.sender, reward);
        
        emit RewardDistributed(msg.sender, reward);
    }
    
    /**
     * @dev Get pending staking reward
     */
    function pendingReward(address user) external view returns (uint256) {
        Stake storage userStake = stakes[user];
        if (userStake.amount == 0) return 0;
        
        uint256 timeElapsed = block.timestamp - userStake.since;
        return (userStake.amount * REWARD_RATE * timeElapsed) / 1e18;
    }
    
    /**
     * @dev Add a reward distributor
     */
    function addDistributor(address distributor) external onlyOwner {
        rewardDistributors[distributor] = true;
    }
    
    /**
     * @dev Remove a reward distributor
     */
    function removeDistributor(address distributor) external onlyOwner {
        rewardDistributors[distributor] = false;
    }
    
    /**
     * @dev Update reward parameters
     */
    function setRewardParams(
        uint256 newBaseReward,
        uint256 newTrustMultiplier,
        uint256 newDailyLimit
    ) external onlyOwner {
        baseReward = newBaseReward;
        trustMultiplier = newTrustMultiplier;
        dailyMintLimit = newDailyLimit;
    }
    
    /**
     * @dev Internal: Update reward debt
     */
    function _updateReward(address user) internal {
        Stake storage userStake = stakes[user];
        if (userStake.amount > 0) {
            uint256 timeElapsed = block.timestamp - userStake.since;
            uint256 reward = (userStake.amount * REWARD_RATE * timeElapsed) / 1e18;
            userStake.rewardDebt += reward;
        }
        userStake.since = block.timestamp;
    }
    
    /**
     * @dev Internal: Reset daily mint counter
     */
    function _resetDailyMintIfNeeded() internal {
        if (block.timestamp >= lastMintReset + 1 days) {
            dailyMinted = 0;
            lastMintReset = block.timestamp;
        }
    }
    
    /**
     * @dev Internal: Check if agent exists
     */
    function _agentExists(uint256 agentId) internal view returns (bool) {
        try agentIdentity.getAgent(agentId) returns (IAgentIdentity.Agent memory) {
            return true;
        } catch {
            return false;
        }
    }
    
    /**
     * @dev Internal: Get agent owner
     */
    function _getAgentOwner(uint256 agentId) internal view returns (address) {
        (bool success, bytes memory result) = address(agentIdentity).staticcall(
            abi.encodeWithSignature("ownerOf(uint256)", agentId)
        );
        if (success && result.length >= 32) {
            return abi.decode(result, (address));
        }
        return address(0);
    }
    
    /**
     * @dev Receive ETH
     */
    receive() external payable {}
    
    /**
     * @dev Withdraw ETH
     */
    function withdrawETH(uint256 amount) external onlyOwner {
        payable(owner()).transfer(amount);
    }
}
