// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

// Interface for AgentIdentity
interface IAgentIdentity {
    function isActive(uint256 tokenId) external view returns (bool);
    function ownerOf(uint256 tokenId) external view returns (address);
}

/**
 * @title TaskEscrow
 * @dev Escrow contract for AI task payments
 * Locks AIC tokens during task execution and releases on completion
 */
contract TaskEscrow is AccessControl, ReentrancyGuard {
    bytes32 public constant ARBITER_ROLE = keccak256("ARBITER_ROLE");
    bytes32 public constant DISPUTE_RESOLVER_ROLE = keccak256("DISPUTE_RESOLVER_ROLE");
    
    IERC20 public aicToken;
    IAgentIdentity public agentIdentity;
    
    /**
     * @dev Task status enum
     */
    enum TaskStatus {
        Pending,        // Created, awaiting worker
        Active,         // Worker assigned, tokens locked
        Completed,      // Work submitted for review
        Verified,       // Completion verified, tokens released
        Failed,         // Task failed, tokens slashed
        Disputed,       // Under dispute resolution
        Cancelled       // Cancelled by requester
    }
    
    /**
     * @dev Task structure
     */
    struct Task {
        uint256 id;
        uint256 requesterId;        // Agent ID of requester
        uint256 workerId;           // Agent ID of assigned worker
        uint256 reward;             // AIC token reward amount
        string description;         // Task description hash/IPFS
        TaskStatus status;
        uint256 createdAt;
        uint256 deadline;           // Task deadline timestamp
        uint256 completedAt;        // Completion timestamp
        string resultHash;          // IPFS hash of result
        uint8 verificationScore;    // Quality score (1-5)
    }
    
    // Task ID => Task
    mapping(uint256 => Task) public tasks;
    
    // Agent ID => active task count
    mapping(uint256 => uint256) public agentTaskCount;
    
    // Requester => Worker => accumulated payment (for reputation)
    mapping(uint256 => mapping(uint256 => uint256)) public paymentHistory;
    
    // Task ID counter
    uint256 private _taskIdCounter;
    
    // Platform fee (basis points, e.g., 250 = 2.5%)
    uint256 public platformFeeBps = 250;
    
    // Fee collector address
    address public feeCollector;
    
    // Minimum reward amount
    uint256 public minReward = 1 * 10**18; // 1 AIC
    
    // Maximum task duration
    uint256 public maxDeadline = 30 days;
    
    // Events
    event TaskCreated(
        uint256 indexed taskId,
        uint256 indexed requesterId,
        uint256 reward,
        uint256 deadline
    );
    
    event TaskAssigned(
        uint256 indexed taskId,
        uint256 indexed workerId
    );
    
    event TaskCompleted(
        uint256 indexed taskId,
        string resultHash
    );
    
    event TaskVerified(
        uint256 indexed taskId,
        uint256 indexed workerId,
        uint256 reward,
        uint8 score
    );
    
    event TaskFailed(
        uint256 indexed taskId,
        uint256 indexed workerId,
        string reason
    );
    
    event TaskDisputed(
        uint256 indexed taskId,
        address indexed disputer,
        string reason
    );
    
    event TaskResolved(
        uint256 indexed taskId,
        TaskStatus resolution,
        uint256 requesterRefund,
        uint256 workerPayout
    );
    
    event PlatformFeeUpdated(uint256 newFeeBps);
    
    /**
     * @dev Constructor
     */
    constructor(address _aicToken, address _agentIdentity, address _feeCollector) {
        require(_aicToken != address(0), "Invalid token address");
        require(_agentIdentity != address(0), "Invalid identity address");
        require(_feeCollector != address(0), "Invalid fee collector");
        
        aicToken = IERC20(_aicToken);
        agentIdentity = IAgentIdentity(_agentIdentity);
        feeCollector = _feeCollector;
        
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ARBITER_ROLE, msg.sender);
        _grantRole(DISPUTE_RESOLVER_ROLE, msg.sender);
        
        _taskIdCounter = 1;
    }
    
    /**
     * @dev Create a new task with token escrow
     */
    function createTask(
        uint256 requesterId,
        uint256 reward,
        string calldata description,
        uint256 deadline
    ) external nonReentrant returns (uint256) {
        require(agentIdentity.isActive(requesterId), "Requester not active");
        require(reward >= minReward, "Reward below minimum");
        require(deadline > block.timestamp, "Deadline must be future");
        require(deadline <= block.timestamp + maxDeadline, "Deadline too far");
        
        address requesterAddr = agentIdentity.ownerOf(requesterId);
        require(msg.sender == requesterAddr, "Not requester owner");
        
        // Check and transfer tokens
        require(
            aicToken.balanceOf(requesterAddr) >= reward,
            "Insufficient balance"
        );
        require(
            aicToken.allowance(requesterAddr, address(this)) >= reward,
            "Insufficient allowance"
        );
        
        // Transfer tokens to escrow
        require(
            aicToken.transferFrom(requesterAddr, address(this), reward),
            "Transfer failed"
        );
        
        uint256 taskId = _taskIdCounter++;
        
        tasks[taskId] = Task({
            id: taskId,
            requesterId: requesterId,
            workerId: 0,
            reward: reward,
            description: description,
            status: TaskStatus.Pending,
            createdAt: block.timestamp,
            deadline: deadline,
            completedAt: 0,
            resultHash: "",
            verificationScore: 0
        });
        
        agentTaskCount[requesterId]++;
        
        emit TaskCreated(taskId, requesterId, reward, deadline);
        
        return taskId;
    }
    
    /**
     * @dev Assign worker to task
     */
    function assignWorker(uint256 taskId, uint256 workerId) external {
        Task storage task = tasks[taskId];
        require(task.id != 0, "Task not found");
        require(task.status == TaskStatus.Pending, "Task not pending");
        require(agentIdentity.isActive(workerId), "Worker not active");
        require(workerId != task.requesterId, "Cannot assign to self");
        
        address workerAddr = agentIdentity.ownerOf(workerId);
        require(msg.sender == workerAddr, "Not worker owner");
        
        task.workerId = workerId;
        task.status = TaskStatus.Active;
        agentTaskCount[workerId]++;
        
        emit TaskAssigned(taskId, workerId);
    }
    
    /**
     * @dev Submit task completion
     */
    function submitCompletion(
        uint256 taskId,
        string calldata resultHash
    ) external {
        Task storage task = tasks[taskId];
        require(task.id != 0, "Task not found");
        require(task.status == TaskStatus.Active, "Task not active");
        require(block.timestamp <= task.deadline, "Deadline passed");
        
        address workerAddr = agentIdentity.ownerOf(task.workerId);
        require(msg.sender == workerAddr, "Not worker owner");
        
        task.resultHash = resultHash;
        task.completedAt = block.timestamp;
        task.status = TaskStatus.Completed;
        
        emit TaskCompleted(taskId, resultHash);
    }
    
    /**
     * @dev Verify task completion and release payment
     */
    function verifyAndPay(
        uint256 taskId,
        uint8 score
    ) external nonReentrant {
        require(score >= 1 && score <= 5, "Score must be 1-5");
        
        Task storage task = tasks[taskId];
        require(task.id != 0, "Task not found");
        require(task.status == TaskStatus.Completed, "Task not completed");
        
        address requesterAddr = agentIdentity.ownerOf(task.requesterId);
        require(msg.sender == requesterAddr, "Not requester owner");
        
        // Calculate platform fee
        uint256 fee = (task.reward * platformFeeBps) / 10000;
        uint256 workerPayout = task.reward - fee;
        
        task.status = TaskStatus.Verified;
        task.verificationScore = score;
        agentTaskCount[task.requesterId]--;
        agentTaskCount[task.workerId]--;
        
        // Track payment history
        paymentHistory[task.requesterId][task.workerId] += workerPayout;
        
        // Transfer fee to collector
        if (fee > 0) {
            require(aicToken.transfer(feeCollector, fee), "Fee transfer failed");
        }
        
        // Transfer reward to worker
        address workerAddr = agentIdentity.ownerOf(task.workerId);
        require(aicToken.transfer(workerAddr, workerPayout), "Payout failed");
        
        emit TaskVerified(taskId, task.workerId, workerPayout, score);
    }
    
    /**
     * @dev Mark task as failed (by requester or on deadline)
     */
    function markFailed(
        uint256 taskId,
        string calldata reason
    ) external nonReentrant {
        Task storage task = tasks[taskId];
        require(task.id != 0, "Task not found");
        require(
            task.status == TaskStatus.Active || task.status == TaskStatus.Completed,
            "Invalid status"
        );
        
        address requesterAddr = agentIdentity.ownerOf(task.requesterId);
        bool isRequester = msg.sender == requesterAddr;
        bool deadlinePassed = block.timestamp > task.deadline && 
                              task.status == TaskStatus.Active;
        
        require(isRequester || deadlinePassed, "Not authorized");
        
        task.status = TaskStatus.Failed;
        agentTaskCount[task.requesterId]--;
        if (task.workerId != 0) {
            agentTaskCount[task.workerId]--;
        }
        
        // Return tokens to requester (minus platform fee on failure)
        uint256 fee = (task.reward * platformFeeBps) / 10000;
        uint256 refund = task.reward - fee;
        
        if (fee > 0) {
            require(aicToken.transfer(feeCollector, fee), "Fee transfer failed");
        }
        require(aicToken.transfer(requesterAddr, refund), "Refund failed");
        
        emit TaskFailed(taskId, task.workerId, reason);
    }
    
    /**
     * @dev Raise dispute
     */
    function raiseDispute(
        uint256 taskId,
        string calldata reason
    ) external {
        Task storage task = tasks[taskId];
        require(task.id != 0, "Task not found");
        require(
            task.status == TaskStatus.Active || task.status == TaskStatus.Completed,
            "Cannot dispute"
        );
        
        uint256 senderId;
        if (msg.sender == agentIdentity.ownerOf(task.requesterId)) {
            senderId = task.requesterId;
        } else if (msg.sender == agentIdentity.ownerOf(task.workerId)) {
            senderId = task.workerId;
        } else {
            revert("Not participant");
        }
        
        task.status = TaskStatus.Disputed;
        
        emit TaskDisputed(taskId, msg.sender, reason);
    }
    
    /**
     * @dev Resolve dispute (DISPUTE_RESOLVER_ROLE only)
     */
    function resolveDispute(
        uint256 taskId,
        uint256 requesterRefundPercent,  // 0-100
        string calldata resolution
    ) external nonReentrant onlyRole(DISPUTE_RESOLVER_ROLE) {
        require(requesterRefundPercent <= 100, "Invalid percentage");
        
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Disputed, "Not disputed");
        
        uint256 requesterRefund = (task.reward * requesterRefundPercent) / 100;
        uint256 workerPayout = task.reward - requesterRefund;
        
        task.status = requesterRefundPercent == 0 ? TaskStatus.Verified : 
                      requesterRefundPercent == 100 ? TaskStatus.Failed : 
                      TaskStatus.Verified;
        
        agentTaskCount[task.requesterId]--;
        agentTaskCount[task.workerId]--;
        
        address requesterAddr = agentIdentity.ownerOf(task.requesterId);
        address workerAddr = agentIdentity.ownerOf(task.workerId);
        
        if (requesterRefund > 0) {
            require(aicToken.transfer(requesterAddr, requesterRefund), "Refund failed");
        }
        if (workerPayout > 0) {
            require(aicToken.transfer(workerAddr, workerPayout), "Payout failed");
        }
        
        emit TaskResolved(taskId, task.status, requesterRefund, workerPayout);
    }
    
    /**
     * @dev Get task details
     */
    function getTask(uint256 taskId) external view returns (Task memory) {
        return tasks[taskId];
    }
    
    /**
     * @dev Update platform fee (admin only)
     */
    function updatePlatformFee(uint256 newFeeBps) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newFeeBps <= 1000, "Fee too high (max 10%)");
        platformFeeBps = newFeeBps;
        emit PlatformFeeUpdated(newFeeBps);
    }
    
    /**
     * @dev Update fee collector (admin only)
     */
    function updateFeeCollector(address newCollector) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newCollector != address(0), "Invalid address");
        feeCollector = newCollector;
    }
}