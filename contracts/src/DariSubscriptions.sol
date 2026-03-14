// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/PausableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./IDariSubscriptions.sol";

/**
 * @title DariSubscriptions
 * @author Dari for Business
 * @notice UUPS-upgradeable smart contract for managing stablecoin subscription payments.
 *
 *   Flow:
 *     1. User approves this contract to spend their stablecoins (USDC/USDT)
 *     2. Relayer calls createSubscription() on behalf of user
 *     3. Scheduler detects due payments, relayer calls executePayment()
 *     4. Contract transfers tokens from subscriber to merchant via transferFrom
 *
 *   Security:
 *     - Only authorized relayer can create/execute subscriptions
 *     - Subscribers and merchants can cancel
 *     - Owner can pause/unpause (circuit breaker)
 *     - ReentrancyGuard on all state-changing functions
 *     - Strict validation: interval elapsed, amount > 0, active status
 *     - Amount cannot be increased via updateSubscription (requires re-approval)
 */
contract DariSubscriptions is
    IDariSubscriptions,
    OwnableUpgradeable,
    PausableUpgradeable,
    ReentrancyGuardUpgradeable,
    UUPSUpgradeable
{
    using SafeERC20 for IERC20;

    // ============= STATE =============

    /// @notice Address authorized to create subscriptions and execute payments
    address public relayer;

    /// @notice Auto-incrementing subscription counter
    uint256 public subscriptionCount;

    /// @notice Subscription ID => SubscriptionData
    mapping(uint256 => SubscriptionData) public subscriptions;

    /// @notice Subscriber => list of subscription IDs (for lookup)
    mapping(address => uint256[]) public subscriberSubs;

    /// @notice Merchant => list of subscription IDs (for lookup)
    mapping(address => uint256[]) public merchantSubs;

    /// @notice Supported ERC20 tokens (whitelist)
    mapping(address => bool) public supportedTokens;

    // ============= ERRORS =============

    // NOTE: _subIndexed removed — was dead code (written but never read)

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

    // ============= MODIFIERS =============

    modifier onlyRelayer() {
        if (msg.sender != relayer) revert OnlyRelayer();
        _;
    }

    // ============= INITIALIZER =============

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initialize the contract (called once via proxy)
     * @param _owner Contract owner (can pause, upgrade, set relayer)
     * @param _relayer Initial relayer address
     */
    function initialize(address _owner, address _relayer) external initializer {
        if (_owner == address(0) || _relayer == address(0)) revert InvalidAddress();

        __Ownable_init(_owner);
        __Pausable_init();
        __ReentrancyGuard_init();

        relayer = _relayer;
    }

    // ============= ADMIN FUNCTIONS =============

    /**
     * @notice Update the relayer address
     * @param _newRelayer New relayer address
     */
    function setRelayer(address _newRelayer) external onlyOwner {
        if (_newRelayer == address(0)) revert InvalidAddress();
        address old = relayer;
        relayer = _newRelayer;
        emit RelayerUpdated(old, _newRelayer);
    }

    /**
     * @notice Add a supported ERC20 token
     * @param _token Token contract address
     */
    function addSupportedToken(address _token) external onlyOwner {
        if (_token == address(0)) revert InvalidAddress();
        supportedTokens[_token] = true;
        emit SupportedTokenAdded(_token);
    }

    /**
     * @notice Remove a supported ERC20 token
     * @param _token Token contract address
     */
    function removeSupportedToken(address _token) external onlyOwner {
        supportedTokens[_token] = false;
        emit SupportedTokenRemoved(_token);
    }

    /// @notice Pause all contract operations (emergency circuit breaker)
    function pause() external onlyOwner {
        _pause();
    }

    /// @notice Unpause contract operations
    function unpause() external onlyOwner {
        _unpause();
    }

    // ============= CORE FUNCTIONS =============

    /**
     * @notice Create a new subscription
     * @dev Only callable by relayer. User must have approved this contract first.
     * @param subscriber Address of the subscriber (payer)
     * @param merchant Address of the merchant (receiver)
     * @param token ERC20 token address (USDC/USDT)
     * @param amount Payment amount per interval (in token decimals)
     * @param interval Billing interval in seconds
     * @param startTime Unix timestamp for the first payment
     * @return subscriptionId The new subscription's ID
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
        override
        onlyRelayer
        whenNotPaused
        nonReentrant
        returns (uint256 subscriptionId)
    {
        // Validate inputs
        if (subscriber == address(0) || merchant == address(0)) revert InvalidAddress();
        if (amount == 0) revert InvalidAmount();
        if (interval < 1 hours) revert InvalidInterval(); // minimum 1 hour billing
        if (startTime < uint64(block.timestamp)) revert InvalidStartTime();
        if (!supportedTokens[token]) revert TokenNotSupported();

        // Verify subscriber has approved sufficient allowance
        uint256 allowance = IERC20(token).allowance(subscriber, address(this));
        if (allowance < amount) revert InsufficientAllowance();

        // Verify subscriber has sufficient balance
        uint256 balance = IERC20(token).balanceOf(subscriber);
        if (balance < amount) revert InsufficientBalance();

        // Create subscription
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

        // Index for lookups
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
     *      Validates: active status, interval elapsed, allowance, balance.
     * @param subscriptionId The subscription to execute payment for
     */
    function executePayment(uint256 subscriptionId)
        external
        override
        onlyRelayer
        whenNotPaused
        nonReentrant
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];

        // Strict validation (prevents relayer abuse)
        if (!sub.active) revert SubscriptionNotActive();
        if (sub.amount == 0) revert InvalidAmount();
        if (block.timestamp < sub.nextPayment) revert PaymentNotDue();

        IERC20 token = IERC20(sub.token);

        // Check allowance
        uint256 allowance = token.allowance(sub.subscriber, address(this));
        if (allowance < sub.amount) revert InsufficientAllowance();

        // Check balance
        uint256 balance = token.balanceOf(sub.subscriber);
        if (balance < sub.amount) revert InsufficientBalance();

        // Update state BEFORE transfer (CEI pattern)
        sub.paymentCount++;
        sub.nextPayment = uint64(block.timestamp) + sub.interval;

        // Transfer tokens from subscriber to merchant
        token.safeTransferFrom(sub.subscriber, sub.merchant, sub.amount);

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
     *      Intentionally NOT gated by whenNotPaused so users can always
     *      exit their subscriptions, even during an emergency pause.
     * @param subscriptionId The subscription to cancel
     */
    function cancelSubscription(uint256 subscriptionId)
        external
        override
        nonReentrant
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];

        if (!sub.active) revert SubscriptionNotActive();

        // Only subscriber, merchant, relayer, or owner can cancel
        if (
            msg.sender != sub.subscriber &&
            msg.sender != sub.merchant &&
            msg.sender != relayer &&
            msg.sender != owner()
        ) {
            revert NotAuthorizedToCancel();
        }

        sub.active = false;

        emit SubscriptionCancelled(subscriptionId, msg.sender, block.timestamp);
    }

    /**
     * @notice Update subscription parameters
     * @dev Only callable by relayer (on behalf of merchant).
     *      SECURITY: amount CANNOT be increased — user must re-approve and create new sub.
     * @param subscriptionId The subscription to update
     * @param newAmount New payment amount (must be <= current amount)
     * @param newInterval New billing interval in seconds
     */
    function updateSubscription(
        uint256 subscriptionId,
        uint128 newAmount,
        uint64  newInterval
    )
        external
        override
        onlyRelayer
        whenNotPaused
        nonReentrant
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];

        if (!sub.active) revert SubscriptionNotActive();
        if (newAmount == 0) revert InvalidAmount();
        if (newInterval < 1 hours) revert InvalidInterval();

        // CRITICAL: Amount cannot increase (prevents unauthorized drain)
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

    /**
     * @notice Get subscription data
     * @param subscriptionId The subscription to query
     * @return Subscription data struct
     */
    function getSubscription(uint256 subscriptionId)
        external
        view
        override
        returns (SubscriptionData memory)
    {
        return subscriptions[subscriptionId];
    }

    /**
     * @notice Check if a payment is due for a subscription
     * @param subscriptionId The subscription to check
     * @return True if payment is due and subscription is active
     */
    function isPaymentDue(uint256 subscriptionId)
        external
        view
        override
        returns (bool)
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];
        return sub.active && block.timestamp >= sub.nextPayment && sub.amount > 0;
    }

    /**
     * @notice Get total subscription count
     * @return Total number of subscriptions created
     */
    function getSubscriptionCount() external view override returns (uint256) {
        return subscriptionCount;
    }

    /**
     * @notice Get all subscription IDs for a subscriber
     * @param subscriber Address of the subscriber
     * @return Array of subscription IDs
     */
    function getSubscriberSubscriptions(address subscriber)
        external
        view
        override
        returns (uint256[] memory)
    {
        return subscriberSubs[subscriber];
    }

    /**
     * @notice Get all subscription IDs for a merchant
     * @param merchant Address of the merchant
     * @return Array of subscription IDs
     */
    function getMerchantSubscriptions(address merchant)
        external
        view
        override
        returns (uint256[] memory)
    {
        return merchantSubs[merchant];
    }

    /**
     * @notice Check remaining ERC20 allowance for a subscription
     * @param subscriptionId The subscription to check
     * @return Remaining allowance
     */
    function checkAllowance(uint256 subscriptionId)
        external
        view
        override
        returns (uint256)
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];
        return IERC20(sub.token).allowance(sub.subscriber, address(this));
    }

    /**
     * @notice Check subscriber's token balance for a subscription
     * @param subscriptionId The subscription to check
     * @return Subscriber's token balance
     */
    function checkBalance(uint256 subscriptionId)
        external
        view
        override
        returns (uint256)
    {
        SubscriptionData storage sub = subscriptions[subscriptionId];
        return IERC20(sub.token).balanceOf(sub.subscriber);
    }

    // ============= UUPS =============

    /**
     * @notice Authorize contract upgrades (only owner)
     */
    function _authorizeUpgrade(address newImplementation)
        internal
        override
        onlyOwner
    {}
}
