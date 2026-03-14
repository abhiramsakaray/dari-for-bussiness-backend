// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IDariSubscriptions
 * @notice Interface for the Dari for Business subscription contract
 */
interface IDariSubscriptions {
    // ============= STRUCTS =============

    /// @notice Gas-optimized subscription data (packed into 4 storage slots)
    struct SubscriptionData {
        address subscriber;       // slot 1: 20 bytes
        uint64  interval;         // slot 1: 8 bytes  (max ~584 billion seconds)
        bool    active;           // slot 1: 1 byte   (3 bytes padding)
        address merchant;         // slot 2: 20 bytes
        uint64  nextPayment;      // slot 2: 8 bytes
        uint32  paymentCount;     // slot 2: 4 bytes
        address token;            // slot 3: 20 bytes (12 bytes padding)
        uint128 amount;           // slot 4: 16 bytes (address+uint128=36>32, spills to slot 4)
    }

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

    // ============= FUNCTIONS =============

    function createSubscription(
        address subscriber,
        address merchant,
        address token,
        uint128 amount,
        uint64  interval,
        uint64  startTime
    ) external returns (uint256 subscriptionId);

    function executePayment(uint256 subscriptionId) external;

    function cancelSubscription(uint256 subscriptionId) external;

    function updateSubscription(
        uint256 subscriptionId,
        uint128 newAmount,
        uint64  newInterval
    ) external;

    function getSubscription(uint256 subscriptionId) external view returns (SubscriptionData memory);

    function isPaymentDue(uint256 subscriptionId) external view returns (bool);

    function getSubscriptionCount() external view returns (uint256);

    function getSubscriberSubscriptions(address subscriber) external view returns (uint256[] memory);

    function getMerchantSubscriptions(address merchant) external view returns (uint256[] memory);

    function checkAllowance(uint256 subscriptionId) external view returns (uint256);

    function checkBalance(uint256 subscriptionId) external view returns (uint256);
}
