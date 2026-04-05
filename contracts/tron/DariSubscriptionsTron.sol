// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

/**
 * @title ITRC20
 * @notice TRC-20 token interface (identical to ERC-20 ABI on TVM)
 */
interface ITRC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/**
 * @title DariSubscriptionsTron
 * @author Dari for Business
 * @notice TVM-compatible recurring subscription contract for Tron network.
 *
 *   Flow:
 *     1. User approves this contract to spend their TRC-20 stablecoins (USDT/USDC)
 *     2. Relayer calls createSubscription() on behalf of user
 *     3. Scheduler detects due payments, relayer calls executePayment()
 *     4. Contract transfers tokens from subscriber to merchant via transferFrom
 *
 *   Security:
 *     - Only authorized relayer can create/execute subscriptions
 *     - Subscribers and merchants can cancel
 *     - Owner can pause/unpause (circuit breaker)
 *     - ReentrancyGuard on all state-changing functions
 *     - Amount cannot be increased via updateSubscription
 *
 *   Note: TVM Solidity fork is ~v0.8.18, no UUPS/OZ upgradeable support.
 *         This contract is deployed directly (non-upgradeable).
 */
contract DariSubscriptionsTron {

    // ============= STRUCTS =============

    struct SubscriptionData {
        address subscriber;
        uint64  interval;
        bool    active;
        address merchant;
        uint64  nextPayment;
        uint32  paymentCount;
        address token;
        uint128 amount;
    }

    // ============= STATE =============

    address public owner;
    address public relayer;
    bool    public paused;
    bool    private _locked; // reentrancy guard

    uint256 public subscriptionCount;

    mapping(uint256 => SubscriptionData) public subscriptions;
    mapping(address => uint256[]) public subscriberSubs;
    mapping(address => uint256[]) public merchantSubs;
    mapping(address => bool) public supportedTokens;

    // ============= EVENTS =============

    event SubscriptionCreated(
        uint256 indexed subscriptionId,
        address indexed subscriber,
        address indexed merchant,
        address token,
        uint128 amount,
        uint64  interval,
        uint64  startTime
    );

    event PaymentExecuted(
        uint256 indexed subscriptionId,
        address indexed subscriber,
        address indexed merchant,
        uint128 amount,
        uint256 timestamp,
        uint32  paymentNumber
    );

    event SubscriptionCancelled(
        uint256 indexed subscriptionId,
        address indexed cancelledBy,
        uint256 timestamp
    );

    event SubscriptionUpdated(
        uint256 indexed subscriptionId,
        uint128 oldAmount,
        uint128 newAmount,
        uint64  oldInterval,
        uint64  newInterval
    );

    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);
    event SupportedTokenAdded(address indexed token);
    event SupportedTokenRemoved(address indexed token);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    // ============= ERRORS =============

    error OnlyOwner();
    error OnlyRelayer();
    error InvalidAddress();
    error InvalidAmount();
    error InvalidInterval();
    error InvalidStartTime();
    error SubscriptionNotActive();
    error PaymentNotDue();
    error InsufficientAllowance();
    error InsufficientBalance();
    error TokenNotSupported();
    error NotAuthorizedToCancel();
    error AmountCannotIncrease();
    error ContractPaused();
    error ReentrancyGuardError();

    // ============= MODIFIERS =============

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    modifier onlyRelayer() {
        if (msg.sender != relayer) revert OnlyRelayer();
        _;
    }

    modifier whenNotPaused() {
        if (paused) revert ContractPaused();
        _;
    }

    modifier nonReentrant() {
        if (_locked) revert ReentrancyGuardError();
        _locked = true;
        _;
        _locked = false;
    }

    // ============= CONSTRUCTOR =============

    constructor(address _owner, address _relayer) {
        if (_owner == address(0) || _relayer == address(0)) revert InvalidAddress();
        owner = _owner;
        relayer = _relayer;
    }

    // ============= ADMIN FUNCTIONS =============

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidAddress();
        address oldOwner = owner;
        owner = newOwner;
        emit OwnershipTransferred(oldOwner, newOwner);
    }

    function setRelayer(address _newRelayer) external onlyOwner {
        if (_newRelayer == address(0)) revert InvalidAddress();
        address old = relayer;
        relayer = _newRelayer;
        emit RelayerUpdated(old, _newRelayer);
    }

    function addSupportedToken(address _token) external onlyOwner {
        if (_token == address(0)) revert InvalidAddress();
        supportedTokens[_token] = true;
        emit SupportedTokenAdded(_token);
    }

    function removeSupportedToken(address _token) external onlyOwner {
        supportedTokens[_token] = false;
        emit SupportedTokenRemoved(_token);
    }

    function pause() external onlyOwner {
        paused = true;
    }

    function unpause() external onlyOwner {
        paused = false;
    }

    // ============= CORE FUNCTIONS =============

    /**
     * @notice Create a new subscription
     * @dev Only callable by relayer. User must have approved this contract first.
     */
    function createSubscription(
        address subscriber,
        address merchant,
        address token,
        uint128 amount,
        uint64  interval,
        uint64  startTime
    )
        external
        onlyRelayer
        whenNotPaused
        nonReentrant
        returns (uint256 subscriptionId)
    {
        if (subscriber == address(0) || merchant == address(0)) revert InvalidAddress();
        if (amount == 0) revert InvalidAmount();
        if (interval < 3600) revert InvalidInterval(); // minimum 1 hour
        if (startTime < uint64(block.timestamp)) revert InvalidStartTime();
        if (!supportedTokens[token]) revert TokenNotSupported();

        // Verify allowance
        uint256 allowance = ITRC20(token).allowance(subscriber, address(this));
        if (allowance < amount) revert InsufficientAllowance();

        // Verify balance
        uint256 balance = ITRC20(token).balanceOf(subscriber);
        if (balance < amount) revert InsufficientBalance();

        subscriptionCount++;
        subscriptionId = subscriptionCount;

        subscriptions[subscriptionId] = SubscriptionData({
            subscriber: subscriber,
            interval: interval,
            active: true,
            merchant: merchant,
            nextPayment: startTime,
            paymentCount: 0,
            token: token,
            amount: amount
        });

        subscriberSubs[subscriber].push(subscriptionId);
        merchantSubs[merchant].push(subscriptionId);

        emit SubscriptionCreated(
            subscriptionId,
            subscriber,
            merchant,
            token,
            amount,
            interval,
            startTime
        );
    }

    /**
     * @notice Execute a due payment for a subscription
     * @dev Only callable by relayer. Transfers tokens from subscriber to merchant.
     */
    function executePayment(uint256 subscriptionId)
        external
        onlyRelayer
        whenNotPaused
        nonReentrant
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];

        if (!sub.active) revert SubscriptionNotActive();
        if (sub.amount == 0) revert InvalidAmount();
        if (block.timestamp < sub.nextPayment) revert PaymentNotDue();

        ITRC20 token = ITRC20(sub.token);

        uint256 allowance = token.allowance(sub.subscriber, address(this));
        if (allowance < sub.amount) revert InsufficientAllowance();

        uint256 balance = token.balanceOf(sub.subscriber);
        if (balance < sub.amount) revert InsufficientBalance();

        // Update state BEFORE transfer (CEI pattern)
        sub.paymentCount++;
        sub.nextPayment = uint64(block.timestamp) + sub.interval;

        // Transfer tokens
        bool success = token.transferFrom(sub.subscriber, sub.merchant, sub.amount);
        require(success, "TRC20 transferFrom failed");

        emit PaymentExecuted(
            subscriptionId,
            sub.subscriber,
            sub.merchant,
            sub.amount,
            block.timestamp,
            sub.paymentCount
        );
    }

    /**
     * @notice Cancel a subscription
     * @dev Callable by subscriber, merchant, relayer, or owner.
     *      NOT gated by whenNotPaused so users can always exit.
     */
    function cancelSubscription(uint256 subscriptionId)
        external
        nonReentrant
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];

        if (!sub.active) revert SubscriptionNotActive();

        if (
            msg.sender != sub.subscriber &&
            msg.sender != sub.merchant &&
            msg.sender != relayer &&
            msg.sender != owner
        ) {
            revert NotAuthorizedToCancel();
        }

        sub.active = false;

        emit SubscriptionCancelled(subscriptionId, msg.sender, block.timestamp);
    }

    /**
     * @notice Update subscription parameters
     * @dev Only callable by relayer. Amount CANNOT increase.
     */
    function updateSubscription(
        uint256 subscriptionId,
        uint128 newAmount,
        uint64  newInterval
    )
        external
        onlyRelayer
        whenNotPaused
        nonReentrant
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];

        if (!sub.active) revert SubscriptionNotActive();
        if (newAmount == 0) revert InvalidAmount();
        if (newInterval < 3600) revert InvalidInterval();
        if (newAmount > sub.amount) revert AmountCannotIncrease();

        uint128 oldAmount = sub.amount;
        uint64  oldInterval = sub.interval;

        sub.amount = newAmount;
        sub.interval = newInterval;

        emit SubscriptionUpdated(
            subscriptionId,
            oldAmount,
            newAmount,
            oldInterval,
            newInterval
        );
    }

    // ============= VIEW FUNCTIONS =============

    function getSubscription(uint256 subscriptionId)
        external
        view
        returns (SubscriptionData memory)
    {
        return subscriptions[subscriptionId];
    }

    function isPaymentDue(uint256 subscriptionId)
        external
        view
        returns (bool)
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];
        return sub.active && block.timestamp >= sub.nextPayment && sub.amount > 0;
    }

    function getSubscriptionCount() external view returns (uint256) {
        return subscriptionCount;
    }

    function getSubscriberSubscriptions(address subscriber)
        external
        view
        returns (uint256[] memory)
    {
        return subscriberSubs[subscriber];
    }

    function getMerchantSubscriptions(address merchant)
        external
        view
        returns (uint256[] memory)
    {
        return merchantSubs[merchant];
    }

    function checkAllowance(uint256 subscriptionId)
        external
        view
        returns (uint256)
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];
        return ITRC20(sub.token).allowance(sub.subscriber, address(this));
    }

    function checkBalance(uint256 subscriptionId)
        external
        view
        returns (uint256)
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];
        return ITRC20(sub.token).balanceOf(sub.subscriber);
    }
}
