// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/PausableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title IDariSubscriptions
 * @notice Interface for the Dari for Business subscription contract
 */
interface IDariSubscriptions {
    // ============= STRUCTS =============

    /// @notice Gas-optimized subscription data (packed into 2 storage slots)
    struct SubscriptionData {
        address subscriber;       // slot 1: 20 bytes
        uint64  interval;         // slot 1: 8 bytes  (max ~584 billion seconds)
        bool    active;           // slot 1: 1 byte
        address merchant;         // slot 2: 20 bytes
        uint64  nextPayment;      // slot 2: 8 bytes
        uint32  paymentCount;     // slot 2: 4 bytes
        address token;            // slot 3: 20 bytes
        uint128 amount;           // slot 3: 16 bytes (max ~340 undecillion)
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
}
