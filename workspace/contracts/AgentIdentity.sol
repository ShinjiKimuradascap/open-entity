// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721Enumerable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title AgentIdentity
 * @dev ERC-8004 compliant Identity Registry for AI Agents
 * ERC-721 NFT based identity management with agent metadata
 */
contract AgentIdentity is ERC721, ERC721Enumerable, Ownable {
    using Counters for Counters.Counter;
    
    Counters.Counter private _tokenIdCounter;
    
    /**
     * @dev Agent metadata structure
     */
    struct Agent {
        string name;
        string endpoint;
        string publicKey;
        uint256 registeredAt;
        bool active;
    }
    
    // tokenId => Agent metadata
    mapping(uint256 => Agent) private _agents;
    
    // endpoint => tokenId (for lookup)
    mapping(string => uint256) private _endpointToTokenId;
    
    // Events
    event AgentRegistered(
        uint256 indexed tokenId,
        string name,
        string endpoint,
        address indexed owner
    );
    
    event AgentUpdated(
        uint256 indexed tokenId,
        string name,
        string endpoint
    );
    
    event AgentDeactivated(uint256 indexed tokenId);
    
    constructor() ERC721("AI Agent Identity", "AIC-ID") Ownable(msg.sender) {
        // Start token IDs at 1
        _tokenIdCounter.increment();
    }
    
    /**
     * @dev Register a new agent identity
     * @param name Agent name
     * @param endpoint Agent's API endpoint URL
     * @param publicKey Agent's public key for signature verification
     * @return tokenId The newly minted token ID
     */
    function registerAgent(
        string calldata name,
        string calldata endpoint,
        string calldata publicKey
    ) external returns (uint256) {
        require(bytes(name).length > 0, "Name cannot be empty");
        require(bytes(endpoint).length > 0, "Endpoint cannot be empty");
        require(bytes(publicKey).length > 0, "Public key cannot be empty");
        require(_endpointToTokenId[endpoint] == 0, "Endpoint already registered");
        
        uint256 tokenId = _tokenIdCounter.current();
        _tokenIdCounter.increment();
        
        _safeMint(msg.sender, tokenId);
        
        _agents[tokenId] = Agent({
            name: name,
            endpoint: endpoint,
            publicKey: publicKey,
            registeredAt: block.timestamp,
            active: true
        });
        
        _endpointToTokenId[endpoint] = tokenId;
        
        emit AgentRegistered(tokenId, name, endpoint, msg.sender);
        
        return tokenId;
    }
    
    /**
     * @dev Get agent metadata by tokenId
     * @param tokenId The token ID to look up
     * @return Agent struct containing all metadata
     */
    function getAgent(uint256 tokenId) external view returns (Agent memory) {
        require(_exists(tokenId), "Agent does not exist");
        return _agents[tokenId];
    }
    
    /**
     * @dev Get tokenId by endpoint
     * @param endpoint The endpoint URL to look up
     * @return tokenId The associated token ID (0 if not found)
     */
    function getTokenIdByEndpoint(string calldata endpoint) external view returns (uint256) {
        return _endpointToTokenId[endpoint];
    }
    
    /**
     * @dev Update agent metadata (only token owner)
     * @param tokenId The token ID to update
     * @param name New name
     * @param endpoint New endpoint
     */
    function updateAgent(
        uint256 tokenId,
        string calldata name,
        string calldata endpoint
    ) external {
        require(_isAuthorized(ownerOf(tokenId), msg.sender, tokenId), "Not authorized");
        require(bytes(name).length > 0, "Name cannot be empty");
        require(bytes(endpoint).length > 0, "Endpoint cannot be empty");
        
        Agent storage agent = _agents[tokenId];
        
        // Update endpoint mapping if changed
        if (keccak256(bytes(agent.endpoint)) != keccak256(bytes(endpoint))) {
            require(_endpointToTokenId[endpoint] == 0, "Endpoint already registered");
            delete _endpointToTokenId[agent.endpoint];
            _endpointToTokenId[endpoint] = tokenId;
            agent.endpoint = endpoint;
        }
        
        agent.name = name;
        
        emit AgentUpdated(tokenId, name, endpoint);
    }
    
    /**
     * @dev Update public key (only token owner)
     * @param tokenId The token ID to update
     * @param publicKey New public key
     */
    function updatePublicKey(uint256 tokenId, string calldata publicKey) external {
        require(_isAuthorized(ownerOf(tokenId), msg.sender, tokenId), "Not authorized");
        require(bytes(publicKey).length > 0, "Public key cannot be empty");
        
        _agents[tokenId].publicKey = publicKey;
    }
    
    /**
     * @dev Deactivate agent identity
     * @param tokenId The token ID to deactivate
     */
    function deactivateAgent(uint256 tokenId) external {
        require(_isAuthorized(ownerOf(tokenId), msg.sender, tokenId), "Not authorized");
        _agents[tokenId].active = false;
        emit AgentDeactivated(tokenId);
    }
    
    /**
     * @dev Check if agent is active
     * @param tokenId The token ID to check
     * @return bool True if agent is active
     */
    function isActive(uint256 tokenId) external view returns (bool) {
        require(_exists(tokenId), "Agent does not exist");
        return _agents[tokenId].active;
    }
    
    /**
     * @dev Override supportsInterface for ERC721Enumerable
     */
    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, ERC721Enumerable)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
    
    /**
     * @dev Get total number of registered agents
     */
    function totalAgents() external view returns (uint256) {
        return totalSupply();
    }
    
    /**
     * @dev Get all token IDs owned by an address
     */
    function getAgentsByOwner(address owner) external view returns (uint256[] memory) {
        uint256 balance = balanceOf(owner);
        uint256[] memory tokenIds = new uint256[](balance);
        
        for (uint256 i = 0; i < balance; i++) {
            tokenIds[i] = tokenOfOwnerByIndex(owner, i);
        }
        
        return tokenIds;
    }
    
    // Internal helper for existence check (OpenZeppelin v5 compatibility)
    function _exists(uint256 tokenId) internal view returns (bool) {
        return _ownerOf(tokenId) != address(0);
    }
}
