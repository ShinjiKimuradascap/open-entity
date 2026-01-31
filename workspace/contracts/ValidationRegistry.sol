// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

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
 * @title ValidationRegistry
 * @dev ERC-8004 compliant Validation Registry for AI Agent task verification
 * Records cryptographic proofs of task completion on-chain
 */
contract ValidationRegistry is Ownable {
    using Counters for Counters.Counter;
    
    Counters.Counter private _validationIdCounter;
    
    // Reference to other registries
    IAgentIdentity public agentIdentity;
    IReputationRegistry public reputationRegistry;
    
    /**
     * @dev Validation status enum
     */
    enum ValidationStatus {
        Pending,
        Validated,
        Rejected,
        Disputed
    }
    
    /**
     * @dev Validation record structure
     */
    struct Validation {
        uint256 id;
        uint256 agentId;
        bytes32 taskHash;
        bytes32 resultHash;
        bytes signature;
        uint256 timestamp;
        ValidationStatus status;
        address validator;
        uint256 stakeAmount;
    }
    
    /**
     * @dev Validation request structure
     */
    struct ValidationRequest {
        uint256 agentId;
        bytes32 taskHash;
        bytes32 resultHash;
        uint256 stakeAmount;
        uint256 requestedAt;
    }
    
    // validationId => Validation
    mapping(uint256 => Validation) private _validations;
    
    // agentId => validationIds
    mapping(uint256 => uint256[]) private _agentValidations;
    
    // taskHash => validationId
    mapping(bytes32 => uint256) private _taskValidations;
    
    // Pending validation requests
    mapping(uint256 => ValidationRequest) private _pendingRequests;
    uint256[] private _pendingRequestIds;
    
    // Minimum stake for validation
    uint256 public minimumStake;
    
    // Validation timeout
    uint256 public validationTimeout;
    
    // Events
    event ValidationRequested(
        uint256 indexed requestId,
        uint256 indexed agentId,
        bytes32 taskHash,
        uint256 stakeAmount
    );
    
    event ValidationSubmitted(
        uint256 indexed validationId,
        uint256 indexed agentId,
        bytes32 taskHash,
        address validator
    );
    
    event ValidationStatusChanged(
        uint256 indexed validationId,
        ValidationStatus newStatus
    );
    
    event ValidationDisputed(
        uint256 indexed validationId,
        address disputant,
        string reason
    );
    
    /**
     * @dev Constructor
     */
    constructor(
        address agentIdentityAddress,
        address reputationRegistryAddress
    ) Ownable(msg.sender) {
        require(agentIdentityAddress != address(0), "Invalid AgentIdentity");
        agentIdentity = IAgentIdentity(agentIdentityAddress);
        reputationRegistry = IReputationRegistry(reputationRegistryAddress);
        minimumStake = 0.01 ether;
        validationTimeout = 1 days;
        _validationIdCounter.increment();
    }
    
    /**
     * @dev Modifier: Only active agent
     */
    modifier onlyActiveAgent(uint256 agentId) {
        require(_agentExists(agentId), "Agent does not exist");
        require(agentIdentity.isActive(agentId), "Agent not active");
        _;
    }
    
    /**
     * @dev Request validation for a task
     */
    function requestValidation(
        uint256 agentId,
        bytes32 taskHash,
        bytes32 resultHash
    ) external payable onlyActiveAgent(agentId) returns (uint256) {
        require(msg.value >= minimumStake, "Insufficient stake");
        require(taskHash != bytes32(0), "Invalid task hash");
        require(_taskValidations[taskHash] == 0, "Task already validated");
        
        uint256 requestId = _validationIdCounter.current();
        
        _pendingRequests[requestId] = ValidationRequest({
            agentId: agentId,
            taskHash: taskHash,
            resultHash: resultHash,
            stakeAmount: msg.value,
            requestedAt: block.timestamp
        });
        
        _pendingRequestIds.push(requestId);
        _validationIdCounter.increment();
        
        emit ValidationRequested(requestId, agentId, taskHash, msg.value);
        
        return requestId;
    }
    
    /**
     * @dev Submit validation with cryptographic proof
     */
    function submitValidation(
        uint256 requestId,
        bytes calldata signature,
        bool isValid
    ) external returns (uint256) {
        ValidationRequest storage request = _pendingRequests[requestId];
        require(request.agentId != 0, "Request not found");
        require(
            block.timestamp <= request.requestedAt + validationTimeout,
            "Validation timeout"
        );
        
        // Verify validator's authority based on trust score
        uint256 validatorAgentId = _getAgentIdByAddress(msg.sender);
        require(validatorAgentId != 0, "Validator not registered");
        
        uint256 trustScore = reputationRegistry.getTrustScore(validatorAgentId);
        require(trustScore >= 60, "Insufficient trust score");
        
        uint256 validationId = requestId;
        
        _validations[validationId] = Validation({
            id: validationId,
            agentId: request.agentId,
            taskHash: request.taskHash,
            resultHash: request.resultHash,
            signature: signature,
            timestamp: block.timestamp,
            status: isValid ? ValidationStatus.Validated : ValidationStatus.Rejected,
            validator: msg.sender,
            stakeAmount: request.stakeAmount
        });
        
        _agentValidations[request.agentId].push(validationId);
        _taskValidations[request.taskHash] = validationId;
        
        // Remove from pending
        _removePendingRequest(requestId);
        delete _pendingRequests[requestId];
        
        // Refund stake if valid
        if (isValid) {
            payable(request.agentId).transfer(request.stakeAmount);
        }
        
        emit ValidationSubmitted(
            validationId,
            request.agentId,
            request.taskHash,
            msg.sender
        );
        
        emit ValidationStatusChanged(
            validationId,
            isValid ? ValidationStatus.Validated : ValidationStatus.Rejected
        );
        
        return validationId;
    }
    
    /**
     * @dev Dispute a validation
     */
    function disputeValidation(
        uint256 validationId,
        string calldata reason
    ) external payable {
        require(msg.value >= minimumStake, "Insufficient dispute stake");
        require(bytes(reason).length > 0, "Reason required");
        
        Validation storage validation = _validations[validationId];
        require(validation.id != 0, "Validation not found");
        require(
            validation.status == ValidationStatus.Validated,
            "Cannot dispute this validation"
        );
        
        validation.status = ValidationStatus.Disputed;
        
        emit ValidationDisputed(validationId, msg.sender, reason);
        emit ValidationStatusChanged(validationId, ValidationStatus.Disputed);
    }
    
    /**
     * @dev Get validation by ID
     */
    function getValidation(uint256 validationId)
        external
        view
        returns (Validation memory)
    {
        return _validations[validationId];
    }
    
    /**
     * @dev Get all validations for an agent
     */
    function getAgentValidations(uint256 agentId)
        external
        view
        returns (uint256[] memory)
    {
        return _agentValidations[agentId];
    }
    
    /**
     * @dev Get validation by task hash
     */
    function getValidationByTask(bytes32 taskHash)
        external
        view
        returns (Validation memory)
    {
        return _validations[_taskValidations[taskHash]];
    }
    
    /**
     * @dev Check if task is validated
     */
    function isValidated(bytes32 taskHash) external view returns (bool) {
        uint256 validationId = _taskValidations[taskHash];
        if (validationId == 0) return false;
        return _validations[validationId].status == ValidationStatus.Validated;
    }
    
    /**
     * @dev Get validation count for agent
     */
    function getValidationCount(uint256 agentId)
        external
        view
        returns (uint256)
    {
        return _agentValidations[agentId].length;
    }
    
    /**
     * @dev Get pending request IDs
     */
    function getPendingRequests() external view returns (uint256[] memory) {
        return _pendingRequestIds;
    }
    
    /**
     * @dev Update minimum stake
     */
    function setMinimumStake(uint256 newStake) external onlyOwner {
        minimumStake = newStake;
    }
    
    /**
     * @dev Update validation timeout
     */
    function setValidationTimeout(uint256 newTimeout) external onlyOwner {
        validationTimeout = newTimeout;
    }
    
    /**
     * @dev Internal: Remove from pending requests
     */
    function _removePendingRequest(uint256 requestId) internal {
        for (uint256 i = 0; i < _pendingRequestIds.length; i++) {
            if (_pendingRequestIds[i] == requestId) {
                _pendingRequestIds[i] = _pendingRequestIds[_pendingRequestIds.length - 1];
                _pendingRequestIds.pop();
                break;
            }
        }
    }
    
    /**
     * @dev Internal: Get agent ID by address
     */
    function _getAgentIdByAddress(address agentAddress)
        internal
        view
        returns (uint256)
    {
        // This would need to be implemented based on AgentIdentity
        // For now, return 0 (not found)
        return 0;
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
}
