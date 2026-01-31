// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Address.sol";

// Interface for AIC Token
interface IAICToken {
    function balanceOf(address account) external view returns (uint256);
    function delegate(address delegatee) external;
    function delegates(address account) external view returns (address);
    function getVotes(address account) external view returns (uint256);
}

// Interface for ReputationRegistry
interface IReputationRegistry {
    function getTrustScore(uint256 agentId) external view returns (uint256);
    function getRatingCount(uint256 agentId) external view returns (uint256);
}

// Interface for AgentIdentity
interface IAgentIdentity {
    function ownerOf(uint256 tokenId) external view returns (address);
    function isActive(uint256 tokenId) external view returns (bool);
}

/**
 * @title Governance
 * @dev Decentralized governance for AI Collaboration Platform
 * Voting power = AIC balance + reputation multiplier
 */
contract Governance is AccessControl, ReentrancyGuard {
    using Address for address;
    
    bytes32 public constant PROPOSER_ROLE = keccak256("PROPOSER_ROLE");
    bytes32 public constant EXECUTOR_ROLE = keccak256("EXECUTOR_ROLE");
    
    IAICToken public aicToken;
    IReputationRegistry public reputationRegistry;
    IAgentIdentity public agentIdentity;
    
    /**
     * @dev Proposal status
     */
    enum ProposalStatus {
        Pending,
        Active,
        Canceled,
        Defeated,
        Succeeded,
        Queued,
        Executed
    }
    
    /**
     * @dev Proposal type
     */
    enum ProposalType {
        ParameterChange,    // Change platform parameters
        Upgrade,            // Contract upgrade
        Treasury,           // Treasury allocation
        Policy              // Policy change
    }
    
    /**
     * @dev Vote type
     */
    enum VoteType {
        Against,
        For,
        Abstain
    }
    
    /**
     * @dev Proposal structure
     */
    struct Proposal {
        uint256 id;
        address proposer;
        string title;
        string description;
        ProposalType proposalType;
        ProposalStatus status;
        uint256 forVotes;
        uint256 againstVotes;
        uint256 abstainVotes;
        uint256 startBlock;
        uint256 endBlock;
        uint256 eta;            // Execution time (for timelock)
        bytes callData;         // Execution data
        address target;         // Target contract
        uint256 requiredQuorum;
    }
    
    /**
     * @dev Vote receipt
     */
    struct Receipt {
        bool hasVoted;
        VoteType vote;
        uint256 votes;
    }
    
    // Proposal ID => Proposal
    mapping(uint256 => Proposal) public proposals;
    
    // Proposal ID => Voter => Receipt
    mapping(uint256 => mapping(address => Receipt)) public votes;
    
    // Agent ID => voting power multiplier (based on reputation)
    mapping(uint256 => uint256) public reputationMultiplier;
    
    // Proposal ID => has been executed
    mapping(uint256 => bool) public executed;
    
    // Proposal counter
    uint256 public proposalCount;
    
    // Voting parameters
    uint256 public votingDelay = 1;              // Blocks before voting starts
    uint256 public votingPeriod = 40320;         // Blocks voting lasts (~1 week)
    uint256 public proposalThreshold = 1000e18;  // 1000 AIC to propose
    uint256 public quorumNumerator = 400;        // 4% (basis points)
    uint256 public quorumDenominator = 10000;
    
    // Timelock
    uint256 public timelockDelay = 2 days;
    
    // Reputation weight (how much reputation affects voting power)
    uint256 public reputationWeight = 20;        // 20% bonus max
    
    // Events
    event ProposalCreated(
        uint256 indexed id,
        address indexed proposer,
        string title,
        ProposalType proposalType
    );
    
    event VoteCast(
        uint256 indexed proposalId,
        address indexed voter,
        VoteType vote,
        uint256 votes
    );
    
    event ProposalCanceled(uint256 indexed id);
    event ProposalQueued(uint256 indexed id, uint256 eta);
    event ProposalExecuted(uint256 indexed id);
    
    event ParameterChanged(string param, uint256 oldValue, uint256 newValue);
    
    /**
     * @dev Constructor
     */
    constructor(
        address _aicToken,
        address _reputationRegistry,
        address _agentIdentity
    ) {
        require(_aicToken != address(0), "Invalid token address");
        
        aicToken = IAICToken(_aicToken);
        reputationRegistry = IReputationRegistry(_reputationRegistry);
        agentIdentity = IAgentIdentity(_agentIdentity);
        
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(PROPOSER_ROLE, msg.sender);
        _grantRole(EXECUTOR_ROLE, msg.sender);
    }
    
    /**
     * @dev Create new proposal
     */
    function propose(
        string calldata title,
        string calldata description,
        ProposalType proposalType,
        address target,
        bytes calldata callData
    ) external returns (uint256) {
        require(
            hasRole(PROPOSER_ROLE, msg.sender) || 
            aicToken.balanceOf(msg.sender) >= proposalThreshold,
            "Below proposal threshold"
        );
        
        proposalCount++;
        uint256 proposalId = proposalCount;
        
        uint256 startBlock = block.number + votingDelay;
        uint256 endBlock = startBlock + votingPeriod;
        
        // Calculate required quorum
        uint256 totalSupply = getTotalVotingPower();
        uint256 requiredQuorum = (totalSupply * quorumNumerator) / quorumDenominator;
        
        proposals[proposalId] = Proposal({
            id: proposalId,
            proposer: msg.sender,
            title: title,
            description: description,
            proposalType: proposalType,
            status: ProposalStatus.Active,
            forVotes: 0,
            againstVotes: 0,
            abstainVotes: 0,
            startBlock: startBlock,
            endBlock: endBlock,
            eta: 0,
            callData: callData,
            target: target,
            requiredQuorum: requiredQuorum
        });
        
        emit ProposalCreated(proposalId, msg.sender, title, proposalType);
        
        return proposalId;
    }
    
    /**
     * @dev Cast vote
     */
    function castVote(
        uint256 proposalId,
        VoteType voteType,
        uint256 agentId
    ) external {
        require(agentIdentity.isActive(agentId), "Agent not active");
        require(
            msg.sender == agentIdentity.ownerOf(agentId),
            "Not agent owner"
        );
        
        Proposal storage proposal = proposals[proposalId];
        require(proposal.status == ProposalStatus.Active, "Not active");
        require(block.number >= proposal.startBlock, "Voting not started");
        require(block.number <= proposal.endBlock, "Voting ended");
        
        Receipt storage receipt = votes[proposalId][msg.sender];
        require(!receipt.hasVoted, "Already voted");
        
        uint256 votingPower = getVotingPower(agentId);
        require(votingPower > 0, "No voting power");
        
        receipt.hasVoted = true;
        receipt.vote = voteType;
        receipt.votes = votingPower;
        
        if (voteType == VoteType.For) {
            proposal.forVotes += votingPower;
        } else if (voteType == VoteType.Against) {
            proposal.againstVotes += votingPower;
        } else {
            proposal.abstainVotes += votingPower;
        }
        
        emit VoteCast(proposalId, msg.sender, voteType, votingPower);
    }
    
    /**
     * @dev Queue proposal for execution (after voting succeeds)
     */
    function queue(uint256 proposalId) external {
        Proposal storage proposal = proposals[proposalId];
        require(proposal.status == ProposalStatus.Active, "Not active");
        require(block.number > proposal.endBlock, "Voting ongoing");
        
        uint256 totalVotes = proposal.forVotes + proposal.againstVotes + proposal.abstainVotes;
        require(totalVotes >= proposal.requiredQuorum, "Quorum not reached");
        require(proposal.forVotes > proposal.againstVotes, "Not succeeded");
        
        proposal.status = ProposalStatus.Queued;
        proposal.eta = block.timestamp + timelockDelay;
        
        emit ProposalQueued(proposalId, proposal.eta);
    }
    
    /**
     * @dev Execute queued proposal
     */
    function execute(uint256 proposalId) external nonReentrant onlyRole(EXECUTOR_ROLE) {
        Proposal storage proposal = proposals[proposalId];
        require(proposal.status == ProposalStatus.Queued, "Not queued");
        require(block.timestamp >= proposal.eta, "Timelock active");
        require(!executed[proposalId], "Already executed");
        
        executed[proposalId] = true;
        proposal.status = ProposalStatus.Executed;
        
        // Execute the proposal call
        if (proposal.target != address(0) && proposal.callData.length > 0) {
            (bool success, ) = proposal.target.call(proposal.callData);
            require(success, "Execution failed");
        }
        
        emit ProposalExecuted(proposalId);
    }
    
    /**
     * @dev Cancel proposal (proposer only, before execution)
     */
    function cancel(uint256 proposalId) external {
        Proposal storage proposal = proposals[proposalId];
        require(proposal.proposer == msg.sender, "Not proposer");
        require(
            proposal.status == ProposalStatus.Pending || 
            proposal.status == ProposalStatus.Active,
            "Cannot cancel"
        );
        
        proposal.status = ProposalStatus.Canceled;
        emit ProposalCanceled(proposalId);
    }
    
    /**
     * @dev Get voting power for agent (AIC balance + reputation bonus)
     */
    function getVotingPower(uint256 agentId) public view returns (uint256) {
        address owner = agentIdentity.ownerOf(agentId);
        uint256 balance = aicToken.balanceOf(owner);
        
        // Get reputation bonus
        uint256 trustScore = reputationRegistry.getTrustScore(agentId);
        uint256 ratingCount = reputationRegistry.getRatingCount(agentId);
        
        // Minimum 3 ratings to get reputation bonus
        if (ratingCount < 3) {
            return balance;
        }
        
        // Calculate bonus: trustScore is 0-100, weight is 20% max
        uint256 bonus = (balance * trustScore * reputationWeight) / (100 * 100);
        
        return balance + bonus;
    }
    
    /**
     * @dev Get total voting power
     */
    function getTotalVotingPower() public view returns (uint256) {
        // Simplified: use token total supply
        // In production, might want to track separately
        return aicToken.balanceOf(address(this)) + getCirculatingSupply();
    }
    
    /**
     * @dev Get proposal state
     */
    function state(uint256 proposalId) external view returns (ProposalStatus) {
        Proposal storage proposal = proposals[proposalId];
        
        if (proposal.status == ProposalStatus.Canceled) {
            return ProposalStatus.Canceled;
        }
        if (executed[proposalId]) {
            return ProposalStatus.Executed;
        }
        if (proposal.status == ProposalStatus.Queued) {
            return ProposalStatus.Queued;
        }
        if (block.number <= proposal.startBlock) {
            return ProposalStatus.Pending;
        }
        if (block.number <= proposal.endBlock) {
            return ProposalStatus.Active;
        }
        if (proposal.forVotes <= proposal.againstVotes || 
            (proposal.forVotes + proposal.againstVotes + proposal.abstainVotes) < proposal.requiredQuorum) {
            return ProposalStatus.Defeated;
        }
        return ProposalStatus.Succeeded;
    }
    
    /**
     * @dev Update voting parameters (governance only)
     */
    function updateVotingDelay(uint256 newDelay) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit ParameterChanged("votingDelay", votingDelay, newDelay);
        votingDelay = newDelay;
    }
    
    function updateVotingPeriod(uint256 newPeriod) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit ParameterChanged("votingPeriod", votingPeriod, newPeriod);
        votingPeriod = newPeriod;
    }
    
    function updateProposalThreshold(uint256 newThreshold) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit ParameterChanged("proposalThreshold", proposalThreshold, newThreshold);
        proposalThreshold = newThreshold;
    }
    
    function updateQuorum(uint256 newNumerator) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newNumerator <= quorumDenominator, "Invalid quorum");
        emit ParameterChanged("quorumNumerator", quorumNumerator, newNumerator);
        quorumNumerator = newNumerator;
    }
    
    function updateReputationWeight(uint256 newWeight) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newWeight <= 50, "Max 50%");
        emit ParameterChanged("reputationWeight", reputationWeight, newWeight);
        reputationWeight = newWeight;
    }
    
    /**
     * @dev Get circulating supply placeholder
     * Override in production with actual supply tracking
     */
    function getCirculatingSupply() internal view returns (uint256) {
        // This should be replaced with actual supply tracking
        return 1_000_000_000e18; // Placeholder: 1B tokens
    }
}