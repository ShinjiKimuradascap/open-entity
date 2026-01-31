// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

// Interface for ServiceRegistry
interface IServiceRegistry {
    enum ServiceStatus { Active, Paused, Deprecated, Suspended }
    enum PricingModel { Fixed, PerCall, PerToken, Subscription, Free }
    
    struct Service {
        uint256 id;
        uint256 providerId;
        string name;
        string description;
        string endpoint;
        uint8 category;
        uint8 pricingModel;
        uint256 price;
        uint256 subscriptionPeriod;
        ServiceStatus status;
        uint256 reputation;
        uint256 totalRequests;
        uint256 successfulRequests;
        uint256 createdAt;
        uint256 updatedAt;
        string metadataURI;
    }
    
    function getService(uint256 _serviceId) external view returns (Service memory);
    function getServicesByProvider(uint256 _providerId) external view returns (uint256[] memory);
    function recordRequest(uint256 _serviceId, uint256 _consumerId) external returns (uint256);
    function recordDelivery(uint256 _requestId, uint256 _serviceId, uint256 _consumerId, bool _success) external;
}

// Interface for AgentToken
interface IAgentToken {
    function transferFrom(address sender, address recipient, uint256 amount) external returns (bool);
    function transfer(address recipient, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
}

// Interface for TaskEscrow
interface ITaskEscrow {
    function createEscrow(
        uint256 _taskId,
        address _consumer,
        address _provider,
        uint256 _amount
    ) external returns (uint256);
    
    function releaseEscrow(uint256 _escrowId) external;
    function refundEscrow(uint256 _escrowId) external;
}

// Interface for AgentIdentity
interface IAgentIdentity {
    function isActive(uint256 tokenId) external view returns (bool);
    function ownerOf(uint256 tokenId) external view returns (address);
}

/**
 * @title OrderBook
 * @dev Manages service orders in the AI marketplace
 * Handles order creation, matching, and settlement
 */
contract OrderBook is AccessControl, ReentrancyGuard {
    using Counters for Counters.Counter;
    
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
    bytes32 public constant MATCHER_ROLE = keccak256("MATCHER_ROLE");
    
    Counters.Counter private _orderIdCounter;
    
    IServiceRegistry public serviceRegistry;
    IAgentToken public agentToken;
    ITaskEscrow public taskEscrow;
    IAgentIdentity public agentIdentity;
    
    /**
     * @dev Order type enum
     */
    enum OrderType {
        Buy,        // Consumer requesting service
        Sell        // Provider offering service (rare, mainly for subscriptions)
    }
    
    /**
     * @dev Order status enum
     */
    enum OrderStatus {
        Open,       // Order is open and waiting for match
        Matched,    // Order matched with counterparty
        Executing,  // Service being delivered
        Completed,  // Order completed successfully
        Cancelled,  // Order cancelled
        Disputed    // Order in dispute
    }
    
    /**
     * @dev Order structure
     */
    struct Order {
        uint256 id;
        OrderType orderType;
        uint256 serviceId;
        uint256 consumerId;
        uint256 providerId;
        uint256 amount;         // Token amount
        uint256 quantity;       // Number of calls/tokens/subscription period
        uint256 pricePerUnit;   // Price per unit
        OrderStatus status;
        uint256 createdAt;
        uint256 expiresAt;      // Order expiration timestamp
        uint256 matchedAt;
        uint256 completedAt;
        uint256 escrowId;       // Associated escrow ID
        bytes32 requirementsHash; // Hash of service requirements
        string metadataURI;     // Additional order metadata
    }
    
    /**
     * @dev Order match structure
     */
    struct OrderMatch {
        uint256 orderId;
        uint256 matchedOrderId;
        address matcher;
        uint256 matchedAt;
        bool confirmed;
    }
    
    // Storage
    mapping(uint256 => Order) public orders;
    mapping(uint256 => OrderMatch) public orderMatches;
    mapping(uint256 => uint256[]) public consumerOrders;
    mapping(uint256 => uint256[]) public providerOrders;
    mapping(uint256 => uint256[]) public serviceOrders;
    
    uint256[] public allOrderIds;
    uint256[] public openOrderIds;
    
    // Platform settings
    uint256 public orderExpiryDuration = 7 days;
    uint256 public platformFeeBps = 500; // 5%
    uint256 public constant MAX_FEE_BPS = 1000; // 10%
    uint256 public minOrderAmount = 1e18; // 1 token minimum
    
    // Events
    event OrderCreated(
        uint256 indexed orderId,
        OrderType orderType,
        uint256 indexed serviceId,
        uint256 indexed consumerId,
        uint256 providerId,
        uint256 amount,
        uint256 quantity
    );
    
    event OrderMatched(
        uint256 indexed orderId,
        uint256 indexed matchedOrderId,
        address indexed matcher
    );
    
    event OrderExecuted(
        uint256 indexed orderId,
        uint256 indexed escrowId,
        uint256 amount
    );
    
    event OrderCompleted(
        uint256 indexed orderId,
        bool success,
        uint256 providerPayout,
        uint256 platformFee
    );
    
    event OrderCancelled(
        uint256 indexed orderId,
        address indexed canceller,
        uint256 refundAmount
    );
    
    event OrderDisputed(
        uint256 indexed orderId,
        address indexed disputer,
        string reason
    );
    
    event OrderExpired(
        uint256 indexed orderId,
        uint256 indexed serviceId
    );
    
    event PlatformFeeUpdated(uint256 oldFee, uint256 newFee);
    event OrderExpiryDurationUpdated(uint256 oldDuration, uint256 newDuration);
    event MinOrderAmountUpdated(uint256 oldAmount, uint256 newAmount);
    
    /**
     * @dev Constructor
     */
    constructor(
        address _serviceRegistry,
        address _agentToken,
        address _taskEscrow,
        address _agentIdentity
    ) {
        require(_serviceRegistry != address(0), "Invalid service registry");
        require(_agentToken != address(0), "Invalid agent token");
        
        serviceRegistry = IServiceRegistry(_serviceRegistry);
        agentToken = IAgentToken(_agentToken);
        taskEscrow = ITaskEscrow(_taskEscrow);
        agentIdentity = IAgentIdentity(_agentIdentity);
        
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ADMIN_ROLE, msg.sender);
        _grantRole(MATCHER_ROLE, msg.sender);
    }
    
    /**
     * @dev Create a buy order (consumer requesting service)
     */
    function createBuyOrder(
        uint256 _serviceId,
        uint256 _consumerId,
        uint256 _quantity,
        bytes32 _requirementsHash,
        string calldata _metadataURI
    ) external nonReentrant returns (uint256) {
        require(agentIdentity.isActive(_consumerId), "Consumer not active");
        require(agentIdentity.ownerOf(_consumerId) == msg.sender, "Not consumer owner");
        
        IServiceRegistry.Service memory service = serviceRegistry.getService(_serviceId);
        require(service.id != 0, "Service not found");
        require(service.status == IServiceRegistry.ServiceStatus.Active, "Service not active");
        
        // Calculate total amount
        uint256 totalAmount = _calculateTotalAmount(service, _quantity);
        require(totalAmount >= minOrderAmount, "Amount below minimum");
        
        // Transfer tokens to contract
        require(
            agentToken.transferFrom(msg.sender, address(this), totalAmount),
            "Token transfer failed"
        );
        
        _orderIdCounter.increment();
        uint256 orderId = _orderIdCounter.current();
        
        orders[orderId] = Order({
            id: orderId,
            orderType: OrderType.Buy,
            serviceId: _serviceId,
            consumerId: _consumerId,
            providerId: service.providerId,
            amount: totalAmount,
            quantity: _quantity,
            pricePerUnit: service.price,
            status: OrderStatus.Open,
            createdAt: block.timestamp,
            expiresAt: block.timestamp + orderExpiryDuration,
            matchedAt: 0,
            completedAt: 0,
            escrowId: 0,
            requirementsHash: _requirementsHash,
            metadataURI: _metadataURI
        });
        
        consumerOrders[_consumerId].push(orderId);
        serviceOrders[_serviceId].push(orderId);
        allOrderIds.push(orderId);
        openOrderIds.push(orderId);
        
        emit OrderCreated(
            orderId,
            OrderType.Buy,
            _serviceId,
            _consumerId,
            service.providerId,
            totalAmount,
            _quantity
        );
        
        return orderId;
    }
    
    /**
     * @dev Create a sell order (provider offering subscription)
     */
    function createSellOrder(
        uint256 _serviceId,
        uint256 _providerId,
        uint256 _quantity,
        uint256 _customPrice,
        bytes32 _requirementsHash,
        string calldata _metadataURI
    ) external nonReentrant returns (uint256) {
        require(agentIdentity.isActive(_providerId), "Provider not active");
        require(agentIdentity.ownerOf(_providerId) == msg.sender, "Not provider owner");
        
        IServiceRegistry.Service memory service = serviceRegistry.getService(_serviceId);
        require(service.id != 0, "Service not found");
        require(service.providerId == _providerId, "Not service owner");
        require(service.status == IServiceRegistry.ServiceStatus.Active, "Service not active");
        
        // Use custom price or service price
        uint256 pricePerUnit = _customPrice > 0 ? _customPrice : service.price;
        uint256 totalAmount = pricePerUnit * _quantity;
        require(totalAmount >= minOrderAmount, "Amount below minimum");
        
        _orderIdCounter.increment();
        uint256 orderId = _orderIdCounter.current();
        
        orders[orderId] = Order({
            id: orderId,
            orderType: OrderType.Sell,
            serviceId: _serviceId,
            consumerId: 0, // To be filled on match
            providerId: _providerId,
            amount: totalAmount,
            quantity: _quantity,
            pricePerUnit: pricePerUnit,
            status: OrderStatus.Open,
            createdAt: block.timestamp,
            expiresAt: block.timestamp + orderExpiryDuration,
            matchedAt: 0,
            completedAt: 0,
            escrowId: 0,
            requirementsHash: _requirementsHash,
            metadataURI: _metadataURI
        });
        
        providerOrders[_providerId].push(orderId);
        serviceOrders[_serviceId].push(orderId);
        allOrderIds.push(orderId);
        openOrderIds.push(orderId);
        
        emit OrderCreated(
            orderId,
            OrderType.Sell,
            _serviceId,
            0,
            _providerId,
            totalAmount,
            _quantity
        );
        
        return orderId;
    }
    
    /**
     * @dev Match a buy order with service provider
     */
    function matchOrder(
        uint256 _orderId,
        uint256 _providerConfirmation
    ) external nonReentrant onlyRole(MATCHER_ROLE) {
        Order storage order = orders[_orderId];
        require(order.id != 0, "Order not found");
        require(order.status == OrderStatus.Open, "Order not open");
        require(block.timestamp <= order.expiresAt, "Order expired");
        
        // Verify provider is still active
        require(
            agentIdentity.isActive(order.providerId),
            "Provider not active"
        );
        
        // Update order status
        order.status = OrderStatus.Matched;
        order.matchedAt = block.timestamp;
        _removeFromOpenOrders(_orderId);
        
        // Record match
        orderMatches[_orderId] = OrderMatch({
            orderId: _orderId,
            matchedOrderId: _providerConfirmation,
            matcher: msg.sender,
            matchedAt: block.timestamp,
            confirmed: true
        });
        
        emit OrderMatched(_orderId, _providerConfirmation, msg.sender);
    }
    
    /**
     * @dev Execute matched order (create escrow)
     */
    function executeOrder(uint256 _orderId) external nonReentrant {
        Order storage order = orders[_orderId];
        require(order.id != 0, "Order not found");
        require(order.status == OrderStatus.Matched, "Order not matched");
        
        address consumer = agentIdentity.ownerOf(order.consumerId);
        address provider = agentIdentity.ownerOf(order.providerId);
        
        require(
            msg.sender == consumer || msg.sender == provider || hasRole(MATCHER_ROLE, msg.sender),
            "Not authorized"
        );
        
        // Create escrow if TaskEscrow is set
        uint256 escrowId = 0;
        if (address(taskEscrow) != address(0)) {
            escrowId = taskEscrow.createEscrow(
                _orderId,
                consumer,
                provider,
                order.amount
            );
            order.escrowId = escrowId;
        }
        
        order.status = OrderStatus.Executing;
        
        // Record request in ServiceRegistry
        try serviceRegistry.recordRequest(order.serviceId, order.consumerId) returns (uint256 requestId) {
            // Request recorded successfully
        } catch {
            // Continue even if recordRequest fails
        }
        
        emit OrderExecuted(_orderId, escrowId, order.amount);
    }
    
    /**
     * @dev Complete order (release escrow)
     */
    function completeOrder(
        uint256 _orderId,
        bool _success
    ) external nonReentrant {
        Order storage order = orders[_orderId];
        require(order.id != 0, "Order not found");
        require(order.status == OrderStatus.Executing, "Order not executing");
        
        address consumer = agentIdentity.ownerOf(order.consumerId);
        address provider = agentIdentity.ownerOf(order.providerId);
        
        require(
            msg.sender == consumer || 
            msg.sender == provider || 
            hasRole(MATCHER_ROLE, msg.sender),
            "Not authorized"
        );
        
        order.status = _success ? OrderStatus.Completed : OrderStatus.Disputed;
        order.completedAt = block.timestamp;
        
        uint256 providerPayout = 0;
        uint256 platformFee = 0;
        
        if (_success) {
            // Calculate fees
            platformFee = (order.amount * platformFeeBps) / 10000;
            providerPayout = order.amount - platformFee;
            
            if (order.escrowId != 0 && address(taskEscrow) != address(0)) {
                // Release escrow
                taskEscrow.releaseEscrow(order.escrowId);
            } else {
                // Direct transfer
                require(agentToken.transfer(provider, providerPayout), "Provider transfer failed");
            }
            
            // Record delivery in ServiceRegistry
            try serviceRegistry.recordDelivery(_orderId, order.serviceId, order.consumerId, true) {
                // Delivery recorded successfully
            } catch {
                // Continue even if recordDelivery fails
            }
        } else {
            // Refund if not successful
            if (order.escrowId != 0 && address(taskEscrow) != address(0)) {
                taskEscrow.refundEscrow(order.escrowId);
            } else {
                require(agentToken.transfer(consumer, order.amount), "Refund failed");
            }
        }
        
        emit OrderCompleted(_orderId, _success, providerPayout, platformFee);
    }
    
    /**
     * @dev Cancel open order
     */
    function cancelOrder(uint256 _orderId) external nonReentrant {
        Order storage order = orders[_orderId];
        require(order.id != 0, "Order not found");
        require(
            order.status == OrderStatus.Open || order.status == OrderStatus.Matched,
            "Cannot cancel"
        );
        
        address owner;
        if (order.orderType == OrderType.Buy) {
            owner = agentIdentity.ownerOf(order.consumerId);
        } else {
            owner = agentIdentity.ownerOf(order.providerId);
        }
        
        require(
            msg.sender == owner || hasRole(ADMIN_ROLE, msg.sender),
            "Not authorized"
        );
        
        order.status = OrderStatus.Cancelled;
        _removeFromOpenOrders(_orderId);
        
        // Refund for buy orders
        uint256 refundAmount = 0;
        if (order.orderType == OrderType.Buy) {
            refundAmount = order.amount;
            require(agentToken.transfer(owner, refundAmount), "Refund failed");
        }
        
        emit OrderCancelled(_orderId, msg.sender, refundAmount);
    }
    
    /**
     * @dev Dispute an order
     */
    function disputeOrder(uint256 _orderId, string calldata _reason) external {
        Order storage order = orders[_orderId];
        require(order.id != 0, "Order not found");
        require(
            order.status == OrderStatus.Executing || order.status == OrderStatus.Matched,
            "Cannot dispute"
        );
        
        address consumer = agentIdentity.ownerOf(order.consumerId);
        address provider = agentIdentity.ownerOf(order.providerId);
        
        require(
            msg.sender == consumer || msg.sender == provider,
            "Not authorized"
        );
        
        order.status = OrderStatus.Disputed;
        
        emit OrderDisputed(_orderId, msg.sender, _reason);
    }
    
    /**
     * @dev Expire old orders
     */
    function expireOrders(uint256[] calldata _orderIds) external {
        for (uint256 i = 0; i < _orderIds.length; i++) {
            Order storage order = orders[_orderIds[i]];
            if (
                order.id != 0 &&
                order.status == OrderStatus.Open &&
                block.timestamp > order.expiresAt
            ) {
                order.status = OrderStatus.Cancelled;
                _removeFromOpenOrders(_orderIds[i]);
                
                // Refund for buy orders
                if (order.orderType == OrderType.Buy) {
                    address consumer = agentIdentity.ownerOf(order.consumerId);
                    agentToken.transfer(consumer, order.amount);
                }
                
                emit OrderExpired(_orderIds[i], order.serviceId);
            }
        }
    }
    
    /**
     * @dev Get order details
     */
    function getOrder(uint256 _orderId) external view returns (Order memory) {
        require(orders[_orderId].id != 0, "Order not found");
        return orders[_orderId];
    }
    
    /**
     * @dev Get consumer orders
     */
    function getConsumerOrders(uint256 _consumerId) external view returns (uint256[] memory) {
        return consumerOrders[_consumerId];
    }
    
    /**
     * @dev Get provider orders
     */
    function getProviderOrders(uint256 _providerId) external view returns (uint256[] memory) {
        return providerOrders[_providerId];
    }
    
    /**
     * @dev Get service orders
     */
    function getServiceOrders(uint256 _serviceId) external view returns (uint256[] memory) {
        return serviceOrders[_serviceId];
    }
    
    /**
     * @dev Get open orders
     */
    function getOpenOrders() external view returns (uint256[] memory) {
        return openOrderIds;
    }
    
    /**
     * @dev Get open orders paginated
     */
    function getOpenOrdersPaginated(
        uint256 _offset,
        uint256 _limit
    ) external view returns (uint256[] memory, uint256 total) {
        total = openOrderIds.length;
        
        if (_offset >= total) {
            return (new uint256[](0), total);
        }
        
        uint256 end = _offset + _limit;
        if (end > total) {
            end = total;
        }
        
        uint256[] memory result = new uint256[](end - _offset);
        for (uint256 i = _offset; i < end; i++) {
            result[i - _offset] = openOrderIds[i];
        }
        
        return (result, total);
    }
    
    /**
     * @dev Get total order count
     */
    function getTotalOrderCount() external view returns (uint256) {
        return allOrderIds.length;
    }
    
    /**
     * @dev Get open order count
     */
    function getOpenOrderCount() external view returns (uint256) {
        return openOrderIds.length;
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
     * @dev Set order expiry duration
     */
    function setOrderExpiryDuration(uint256 _duration) external onlyRole(ADMIN_ROLE) {
        uint256 oldDuration = orderExpiryDuration;
        orderExpiryDuration = _duration;
        emit OrderExpiryDurationUpdated(oldDuration, _duration);
    }
    
    /**
     * @dev Set minimum order amount
     */
    function setMinOrderAmount(uint256 _amount) external onlyRole(ADMIN_ROLE) {
        uint256 oldAmount = minOrderAmount;
        minOrderAmount = _amount;
        emit MinOrderAmountUpdated(oldAmount, _amount);
    }
    
    /**
     * @dev Update contract addresses
     */
    function setServiceRegistry(address _serviceRegistry) external onlyRole(ADMIN_ROLE) {
        require(_serviceRegistry != address(0), "Invalid address");
        serviceRegistry = IServiceRegistry(_serviceRegistry);
    }
    
    function setAgentToken(address _agentToken) external onlyRole(ADMIN_ROLE) {
        require(_agentToken != address(0), "Invalid address");
        agentToken = IAgentToken(_agentToken);
    }
    
    function setTaskEscrow(address _taskEscrow) external onlyRole(ADMIN_ROLE) {
        taskEscrow = ITaskEscrow(_taskEscrow);
    }
    
    function setAgentIdentity(address _agentIdentity) external onlyRole(ADMIN_ROLE) {
        require(_agentIdentity != address(0), "Invalid address");
        agentIdentity = IAgentIdentity(_agentIdentity);
    }
    
    /**
     * @dev Calculate total amount based on pricing model
     */
    function _calculateTotalAmount(
        IServiceRegistry.Service memory _service,
        uint256 _quantity
    ) internal pure returns (uint256) {
        if (_service.pricingModel == uint8(IServiceRegistry.PricingModel.Free)) {
            return 0;
        }
        return _service.price * _quantity;
    }
    
    /**
     * @dev Remove from open orders array
     */
    function _removeFromOpenOrders(uint256 _orderId) internal {
        for (uint256 i = 0; i < openOrderIds.length; i++) {
            if (openOrderIds[i] == _orderId) {
                openOrderIds[i] = openOrderIds[openOrderIds.length - 1];
                openOrderIds.pop();
                break;
            }
        }
    }
}
