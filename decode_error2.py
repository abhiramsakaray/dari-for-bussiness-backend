from web3 import Web3

candidates = [
    # Allowance / approval related
    "InsufficientAllowance()",
    "InsufficientAllowance(address)",
    "InsufficientAllowance(address,uint256)",
    "InsufficientAllowance(address,uint256,uint256)",
    "AllowanceTooLow()",
    "AllowanceTooLow(address,uint256,uint256)",
    "NotApproved()",
    "NotApproved(address)",
    # Balance related
    "InsufficientBalance()",
    "InsufficientBalance(address)",
    "InsufficientBalance(address,uint256)",
    "BalanceTooLow()",
    # Token transfer related
    "TransferFailed()",
    "TransferFailed(address)",
    "ERC20TransferFailed()",
    "SafeTransferFailed()",
    # Subscription related
    "SubscriptionAlreadyExists()",
    "DuplicateSubscription()",
    "AlreadySubscribed(address,address)",
    "SubscriptionExists(address,address)",
    # Amount related
    "InvalidAmount()",
    "InvalidAmount(uint256)",
    "AmountTooLow()",
    "AmountZero()",
    # Interval related
    "InvalidInterval()",
    "InvalidInterval(uint64)",
    # Start time related
    "InvalidStartTime()",
    "StartTimeInPast()",
    "InvalidStartTime(uint64)",
    # Merchant related
    "InvalidMerchant()",
    "InvalidMerchant(address)",
    "MerchantNotFound()",
    # Generic
    "InvalidParameters()",
    "NotInitialized()",
    "Paused()",
    "ContractPaused()",
]

target = "13be252b"
print(f"Looking for: 0x{target}\n")
found = False
for sig in candidates:
    h = Web3.keccak(text=sig).hex()[:8]
    if h == target:
        print(f"MATCH -> {sig}")
        found = True

if not found:
    print("No match found. All hashes:")
    for sig in candidates:
        h = Web3.keccak(text=sig).hex()[:8]
        print(f"  0x{h}  {sig}")
