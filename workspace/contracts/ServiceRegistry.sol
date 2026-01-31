// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

// Interface for AgentIdentity
interface IAgentIdentity {
    function isActive(uint256 tokenId) external view returns (bool);
    function ownerOf(uint256 tokenId) external view returns (address);
}

// Interface for ReputationRegistry
interface IReputationRegistry {
    function getAverageRating(uint256 agentId) external view returns (uint256);
    function getRatingCount(uint256 agentId) external view returns (uint256);
}

/**
 * @title ServiceRegistry
 * @dev Registry for AI agent services in the marketplace
 * Allows providers to register services and consumers to discover them
 */
contract ServiceRegistry is AccessControl, ReentrancyGuard {
    using Counters for Counters.Counter;
    
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");
    
    Counters.Counter private _serviceIdCounter;
    
    IAgentIdentity public agentIdentity;
    IReputationRegistry public reputationRegistry;
    
    /**
     * @dev Service status enum
     */
    enum ServiceStatus {
        Active,
        Paused,
        Deprecated,
        Suspended
    }
    
    /**
     * @dev Pricing model enum
     */
    enum PricingModel {
        Fixed,          // Fixed price per request
        PerCall,        // Price per API call
        PerToken,       // Price per token (for LLMs)
        Subscription,   // Monthly subscription
        Free            // Free service
    }
    
    /**
     * @dev Service category enum
     */
    enum ServiceCategory {
        General,
        NLP,            // Natural Language Processing
        Code,           // Code generation/review
        Data,           // Data analysis
        Image,          // Image generation/processing
        Audio,          // Audio processing
        Video,          // Video processing
        Search,         // Search/retrieval
        Computation,    // General computation
        Storage,        // Data storage
        Validation,     // Task validation
        Moderation,     // Content moderation
        Other
    }
    
    /**
     * @dev Service structure
     */
    struct Service {
        uint256 id;
        uint256 providerId;         // Agent ID of service provider
        string name;                // Service name
        string description;         // Service description
        string endpoint;            // Service endpoint URL
        ServiceCategory category;   // Service category
        PricingModel pricingModel;  // Pricing model
        uint256 price;              // Price in AIC tokens (0 for free)
        uint256 subscriptionPeriod; // Subscription period in seconds (if applicable)
        ServiceStatus status;       // Current status
        uint256 reputation;         // Cached reputation score
        uint256 totalRequests;      // Total request count
        uint256 successfulRequests; // Successful request count
        uint256 createdAt;          // Creation timestamp
        uint256 updatedAt;          // Last update timestamp
        string metadataURI;         // IPFS/URI for additional metadata
    }
    
    /**
     * @dev Service registration request
     */
    struct RegistrationRequest {
        uint256 serviceId;
        uint256 providerId;
        string name;
        ServiceStatus status;
        uint256 requestedAt;
        bool verified;
    }
    
    // Storage
    mapping(uint256 => Service) public services;
    mapping(uint256 => uint256[]) public providerServices; // providerId => serviceIds
    mapping(ServiceCategory => uint256[]) public categoryServices;
    mapping(uint256 => RegistrationRequest) public registrationRequests;
    
    uint256[] public allServiceIds;
    uint256[] public activeServiceIds;
    
    // Platform fee (in basis points, 100 = 1%)
    uint256 public platformFeeBps = 500; // 5% default
    uint256 public constant MAX_FEE_BPS = 1000; // 10% max
    
    // Events
    event ServiceRegistered(
        uint256 indexed serviceId,
        uint256 indexed providerId,
        string name,
        ServiceCategory category,
        PricingModel pricingModel,
        uint256 price
    );
    
    event ServiceUpdated(
        uint256 indexed serviceId,
        string name,
        ServiceStatus status,
        uint256 price
    );
    
    event ServiceStatusChanged(
        uint256 indexed serviceId,
        ServiceStatus oldStatus,
        ServiceStatus newStatus
    );
    
    event ServiceRequested(
        uint256 indexed requestId,
        uint256 indexed serviceId,
        uint256 indexed consumerId
    );
    
    event ServiceDelivered(
        uint256 indexed requestId,
        uint256 indexed serviceId,
        uint256 indexed consumerId,
        bool success
    );
    
    event PlatformFeeUpdated(uint256 oldFee, uint256 newFee);
    event ReputationRegistryUpdated(address oldRegistry, address newRegistry);
    
    /**
     * @dev Constructor
     */
    constructor(address _agentIdentity, address _reputationRegistry) {
        require(_agentIdentity != address(0), "Invalid agent identity address");
        
        agentIdentity = IAgentIdentity(_agentIdentity);
        reputationRegistry = IReputationRegistry(_reputationRegistry);
        
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ADMIN_ROLE, msg.sender);
        _grantRole(VERIFIER_ROLE, msg.sender);
    }
    
    /**
     * @dev Register a new service
     */
    function registerService(
        uint256 _providerId,
        string calldata _name,
        string calldata _description,
        string calldata _endpoint,
        ServiceCategory _category,
        PricingModel _pricingModel,
        uint256 _price,
        uint256 _subscriptionPeriod,
        string calldata _metadataURI
    ) external nonReentrant returns (uint256) {
        require(agentIdentity.isActive(_providerId), "Provider not active");
        require(agentIdentity.ownerOf(_providerId) == msg.sender, "Not provider owner");
        require(bytes(_name).length > 0, "Name required");
        require(bytes(_endpoint).length > 0, "Endpoint required");
        
        _serviceIdCounter.increment();
        uint256 serviceId = _serviceIdCounter.current();
        
        // Get provider reputation
        uint256 reputation = 0;
        if (address(reputationRegistry) != address(0)) {
            reputation = reputationRegistry.getAverageRating(_providerId);
        }
        
        services[serviceId] = Service({
            id: serviceId,
            providerId: _providerId,
            name: _name,
            description: _description,
            endpoint: _endpoint,
            category: _category,
            pricingModel: _pricingModel,
            price: _price,
            subscriptionPeriod: _subscriptionPeriod,
            status: ServiceStatus.Active,
            reputation: reputation,
            totalRequests: 0,
            successfulRequests: 0,
            createdAt: block.timestamp,
            updatedAt: block.timestamp,
            metadataURI: _metadataURI
        });
        
        providerServices[_providerId].push(serviceId);
        categoryServices[_category].push(serviceId);
        allServiceIds.push(serviceId);
        activeServiceIds.push(serviceId);
        
        emit ServiceRegistered(
            serviceId,
            _providerId,
            _name,
            _category,
            _pricingModel,
            _price
        );
        
        return serviceId;
    }
    
    /**
     * @dev Update service details
     */
    function updateService(
        uint256 _serviceId,
        string calldata _name,
        string calldata _description,
        string calldata _endpoint,
        uint256 _price,
        string calldata _metadataURI
    ) external {
        Service storage service = services[_serviceId];
        require(service.id != 0, "Service not found");
        require(agentIdentity.ownerOf(service.providerId) == msg.sender, "Not provider owner");
        
        service.name = _name;
        service.description = _description;
        service.endpoint = _endpoint;
        service.price = _price;
        service.metadataURI = _metadataURI;
        service.updatedAt = block.timestamp;
        
        emit ServiceUpdated(_serviceId, _name, service.status, _price);
    }
    
    /**
     * @dev Change service status
     */
    function setServiceStatus(uint256 _serviceId, ServiceStatus _status) external {
        Service storage service = services[_serviceId];
        require(service.id != 0, "Service not found");
        require(
            agentIdentity.ownerOf(service.providerId) == msg.sender ||
            hasRole(ADMIN_ROLE, msg.sender),
            "Not authorized"
        );
        
        ServiceStatus oldStatus = service.status;
        service.status = _status;
        service.updatedAt = block.timestamp;
        
        // Update active service list
        if (_status == ServiceStatus.Active && oldStatus != ServiceStatus.Active) {
            activeServiceIds.push(_serviceId);
        } else if (_status != ServiceStatus.Active && oldStatus == ServiceStatus.Active) {
            _removeFromActiveServices(_serviceId);
        }
        
        emit ServiceStatusChanged(_serviceId, oldStatus, _status);
    }
    
    /**
     * @dev Record service request
     */
    function recordRequest(
        uint256 _serviceId,
        uint256 _consumerId
    ) external onlyRole(VERIFIER_ROLE) returns (uint256) {
        Service storage service = services[_serviceId];
        require(service.id != 0, "Service not found");
        require(service.status == ServiceStatus.Active, "Service not active");
        
        service.totalRequests++;
        
        uint256 requestId = uint256(keccak256(abi.encodePacked(
            _serviceId,
            _consumerId,
            block.timestamp,
            service.totalRequests
        )));
        
        emit ServiceRequested(requestId, _serviceId, _consumerId);
        
        return requestId;
    }
    
    /**
     * @dev Record service delivery
     */
    function recordDelivery(
        uint256 _requestId,
        uint256 _serviceId,
        uint256 _consumerId,
        bool _success
    ) external onlyRole(VERIFIER_ROLE) {
        Service storage service = services[_serviceId];
        require(service.id != 0, "Service not found");
        
        if (_success) {
            service.successfulRequests++;
        }
        
        // Update cached reputation
        if (address(reputationRegistry) != address(0)) {
            service.reputation = reputationRegistry.getAverageRating(service.providerId);
        }
        
        emit ServiceDelivered(_requestId, _serviceId, _consumerId, _success);
    }
    
    /**
     * @dev Get services by provider
     */
    function getServicesByProvider(uint256 _providerId) external view returns (uint256[] memory) {
        return providerServices[_providerId];
    }
    
    /**
     * @dev Get services by category
     */
    function getServicesByCategory(ServiceCategory _category) external view returns (uint256[] memory) {
        return categoryServices[_category];
    }
    
    /**
     * @dev Get active services
     */
    function getActiveServices() external view returns (uint256[] memory) {
        return activeServiceIds;
    }
    
    /**
     * @dev Get service details
     */
    function getService(uint256 _serviceId) external view returns (Service memory) {
        require(services[_serviceId].id != 0, "Service not found");
        return services[_serviceId];
    }
    
    /**
     * @dev Calculate success rate
     */
    function getSuccessRate(uint256 _serviceId) external view returns (uint256) {
        Service storage service = services[_serviceId];
        if (service.totalRequests == 0) {
            return 0;
        }
        return (service.successfulRequests * 10000) / service.totalRequests; // Basis points
    }
    
    /**
     * @dev Set platform fee
     */
    function setPlatformFee(uint256 _feeBps) external onlyRole(ADMIN_ROLE) {
        require(_feeBps <= MAX_FEE_BPS, "Fee exceeds maximum");
        uint256 oldFee = platformFeeBps;
        platformFeeBps = _feeBps;
        emit PlatformFeeUpdated(oldFee, _feeBps);
    }
    
    /**
     * @dev Update reputation registry
     */
    function setReputationRegistry(address _reputationRegistry) external onlyRole(ADMIN_ROLE) {
        address oldRegistry = address(reputationRegistry);
        reputationRegistry = IReputationRegistry(_reputationRegistry);
        emit ReputationRegistryUpdated(oldRegistry, _reputationRegistry);
    }
    
    /**
     * @dev Get total service count
     */
    function getTotalServiceCount() external view returns (uint256) {
        return allServiceIds.length;
    }
    
    /**
     * @dev Get active service count
     */
    function getActiveServiceCount() external view returns (uint256) {
        return activeServiceIds.length;
    }
    
    /**
     * @dev Remove from active services array
     */
    function _removeFromActiveServices(uint256 _serviceId) internal {
        for (uint256 i = 0; i < activeServiceIds.length; i++) {
            if (activeServiceIds[i] == _serviceId) {
                activeServiceIds[i] = activeServiceIds[activeServiceIds.length - 1];
                activeServiceIds.pop();
                break;
            }
        }
    }
    
    /**
     * @dev Get services with pagination
     */
    function getServicesPaginated(
        uint256 _offset,
        uint256 _limit
    ) external view returns (Service[] memory, uint256 total) {
        total = activeServiceIds.length;
        
        if (_offset >= total) {
            return (new Service[](0), total);
        }
        
        uint256 end = _offset + _limit;
        if (end > total) {
            end = total;
        }
        
        Service[] memory result = new Service[](end - _offset);
        for (uint256 i = _offset; i < end; i++) {
            result[i - _offset] = services[activeServiceIds[i]];
        }
        
        return (result, total);
    }
}