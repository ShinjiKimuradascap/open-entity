// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

// Interface for AgentIdentity contract
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

/**
 * @title ReputationRegistry
 * @dev ERC-8004 compliant Reputation Registry for AI Agents
 * Records ratings and calculates trust scores for registered agents
 */
contract ReputationRegistry is Ownable {
    using Counters for Counters.Counter;
    
    // Counter for rating IDs
    Counters.Counter private _ratingIdCounter;
    
    // Reference to AgentIdentity contract
    IAgentIdentity public agentIdentity;
    
    /**
     * @dev Rating structure
     */
    struct Rating {
        uint256 id;
        address rater;
        uint256 agentId;
        uint8 score;        // 1-5
        string comment;
        uint256 timestamp;
    }
    
    /**
     * @dev Rating summary for view functions
     */
    struct RatingSummary {
        uint256 id;
        address rater;
        uint8 score;
        string comment;
        uint256 timestamp;
    }
    
    // agentId => array of ratings
    mapping(uint256 => Rating[]) private _agentRatings;
    
    // Prevent duplicate ratings: agentId => rater => rated
    mapping(uint256 => mapping(address => bool)) private _hasRated;
    
    // agentId => average score (stored for efficiency)
    mapping(uint256 => uint256) private _averageScores;
    
    // agentId => total score sum
    mapping(uint256 => uint256) private _totalScoreSum;
    
    // agentId => rating count
    mapping(uint256 => uint256) private _ratingCounts;
    
    // Events
    event RatingSubmitted(
        uint256 indexed ratingId,
        uint256 indexed agentId,
        address indexed rater,
        uint8 score,
        uint256 timestamp
    );
    
    event AverageRatingUpdated(
        uint256 indexed agentId,
        uint256 averageScore,
        uint256 ratingCount
    );
    
    /**
     * @dev Constructor
     * @param agentIdentityAddress Address of the AgentIdentity contract
     */
    constructor(address agentIdentityAddress) Ownable(msg.sender) {
        require(agentIdentityAddress != address(0), "Invalid AgentIdentity address");
        agentIdentity = IAgentIdentity(agentIdentityAddress);
        // Start rating IDs at 1
        _ratingIdCounter.increment();
    }
    
    /**
     * @dev Modifier to check if agent exists and is active
     */
    modifier onlyActiveAgent(uint256 agentId) {
        require(_agentExists(agentId), "Agent does not exist");
        require(agentIdentity.isActive(agentId), "Agent is not active");
        _;
    }
    
    /**
     * @dev Submit a rating for an agent
     * @param agentId The token ID of the agent being rated
     * @param score The rating score (1-5)
     * @param comment Optional comment
     * @return ratingId The ID of the submitted rating
     */
    function submitRating(
        uint256 agentId,
        uint8 score,
        string calldata comment
    ) external onlyActiveAgent(agentId) returns (uint256) {
        // Validate score range (1-5)
        require(score >= 1 && score <= 5, "Score must be between 1 and 5");
        
        // Prevent self-rating
        IAgentIdentity.Agent memory agent = agentIdentity.getAgent(agentId);
        require(msg.sender != _getAgentOwner(agentId), "Cannot rate yourself");
        
        // Prevent duplicate ratings from the same rater
        require(!_hasRated[agentId][msg.sender], "Already rated this agent");
        
        uint256 ratingId = _ratingIdCounter.current();
        _ratingIdCounter.increment();
        
        Rating memory rating = Rating({
            id: ratingId,
            rater: msg.sender,
            agentId: agentId,
            score: score,
            comment: comment,
            timestamp: block.timestamp
        });
        
        _agentRatings[agentId].push(rating);
        _hasRated[agentId][msg.sender] = true;
        
        // Update average calculation
        _updateAverageRating(agentId, score);
        
        emit RatingSubmitted(ratingId, agentId, msg.sender, score, block.timestamp);
        
        return ratingId;
    }
    
    /**
     * @dev Get all ratings for an agent
     * @param agentId The token ID of the agent
     * @return Array of RatingSummary structs
     */
    function getRatings(uint256 agentId) external view returns (RatingSummary[] memory) {
        Rating[] storage ratings = _agentRatings[agentId];
        RatingSummary[] memory summaries = new RatingSummary[](ratings.length);
        
        for (uint256 i = 0; i < ratings.length; i++) {
            Rating storage r = ratings[i];
            summaries[i] = RatingSummary({
                id: r.id,
                rater: r.rater,
                score: r.score,
                comment: r.comment,
                timestamp: r.timestamp
            });
        }
        
        return summaries;
    }
    
    /**
     * @dev Get the average rating for an agent (scaled by 100 for 2 decimal precision)
     * @param agentId The token ID of the agent
     * @return averageScore The average score (e.g., 450 = 4.50)
     */
    function getAverageRating(uint256 agentId) external view returns (uint256) {
        uint256 count = _ratingCounts[agentId];
        if (count == 0) {
            return 0;
        }
        return _averageScores[agentId];
    }
    
    /**
     * @dev Get the average rating for an agent as a decimal
     * @param agentId The token ID of the agent
     * @return averageScore The average score with 2 decimal places
     */
    function getAverageRatingDecimal(uint256 agentId) external view returns (uint256 numerator, uint256 denominator) {
        uint256 count = _ratingCounts[agentId];
        if (count == 0) {
            return (0, 100);
        }
        return (_averageScores[agentId], 100);
    }
    
    /**
     * @dev Get the number of ratings for an agent
     * @param agentId The token ID of the agent
     * @return count The number of ratings
     */
    function getRatingCount(uint256 agentId) external view returns (uint256) {
        return _ratingCounts[agentId];
    }
    
    /**
     * @dev Check if an address has rated an agent
     * @param agentId The token ID of the agent
     * @param rater The address of the potential rater
     * @return bool True if the address has rated the agent
     */
    function hasRated(uint256 agentId, address rater) external view returns (bool) {
        return _hasRated[agentId][rater];
    }
    
    /**
     * @dev Get trust score (0-100) based on average rating
     * @param agentId The token ID of the agent
     * @return trustScore The trust score (0-100)
     */
    function getTrustScore(uint256 agentId) external view returns (uint256) {
        uint256 avgRating = _averageScores[agentId];
        // Convert from 100-scale (1-5) to 0-100 scale
        // avgRating is stored as score * 100, so (1-500)
        // Convert to 0-100: (avgRating / 100) * (100 / 5) = avgRating / 5
        return avgRating / 5;
    }
    
    /**
     * @dev Get total number of ratings submitted
     * @return count Total number of ratings
     */
    function getTotalRatings() external view returns (uint256) {
        return _ratingIdCounter.current() - 1;
    }
    
    /**
     * @dev Get rating by ID and agent
     * @param agentId The token ID of the agent
     * @param ratingIndex The index in the ratings array
     * @return RatingSummary struct
     */
    function getRatingByIndex(uint256 agentId, uint256 ratingIndex) external view returns (RatingSummary memory) {
        require(ratingIndex < _agentRatings[agentId].length, "Rating index out of bounds");
        Rating storage r = _agentRatings[agentId][ratingIndex];
        return RatingSummary({
            id: r.id,
            rater: r.rater,
            score: r.score,
            comment: r.comment,
            timestamp: r.timestamp
        });
    }
    
    /**
     * @dev Get rating statistics for an agent
     * @param agentId The token ID of the agent
     * @return ratingCount Number of ratings
     * @return averageScore Average score (scaled by 100)
     * @return trustScore Trust score (0-100)
     */
    function getRatingStats(uint256 agentId) external view returns (
        uint256 ratingCount,
        uint256 averageScore,
        uint256 trustScore
    ) {
        ratingCount = _ratingCounts[agentId];
        averageScore = _averageScores[agentId];
        trustScore = ratingCount > 0 ? averageScore / 5 : 0;
    }
    
    /**
     * @dev Update the AgentIdentity contract address (owner only)
     * @param newAddress The new contract address
     */
    function updateAgentIdentity(address newAddress) external onlyOwner {
        require(newAddress != address(0), "Invalid address");
        agentIdentity = IAgentIdentity(newAddress);
    }
    
    /**
     * @dev Internal function to update average rating
     * @param agentId The token ID
     * @param newScore The new score to add
     */
    function _updateAverageRating(uint256 agentId, uint8 newScore) internal {
        uint256 currentCount = _ratingCounts[agentId];
        uint256 newCount = currentCount + 1;
        
        // Store scores scaled by 100 for 2 decimal precision
        uint256 newScoreScaled = uint256(newScore) * 100;
        _totalScoreSum[agentId] += newScoreScaled;
        
        // Calculate new average: total / count
        _averageScores[agentId] = _totalScoreSum[agentId] / newCount;
        _ratingCounts[agentId] = newCount;
        
        emit AverageRatingUpdated(agentId, _averageScores[agentId], newCount);
    }
    
    /**
     * @dev Internal function to check if agent exists
     */
    function _agentExists(uint256 agentId) internal view returns (bool) {
        // Try to get agent - if it reverts, agent doesn't exist
        try agentIdentity.getAgent(agentId) returns (IAgentIdentity.Agent memory) {
            return true;
        } catch {
            return false;
        }
    }
    
    /**
     * @dev Internal function to get agent owner
     * Note: This is a workaround since AgentIdentity doesn't expose ownerOf
     * In production, consider adding ownerOf to the interface
     */
    function _getAgentOwner(uint256 agentId) internal view returns (address) {
        // This assumes the agent is an ERC-721 and we can get its owner
        // In practice, you might need to extend the interface
        (bool success, bytes memory result) = address(agentIdentity).staticcall(
            abi.encodeWithSignature("ownerOf(uint256)", agentId)
        );
        if (success && result.length >= 32) {
            return abi.decode(result, (address));
        }
        return address(0);
    }
}
