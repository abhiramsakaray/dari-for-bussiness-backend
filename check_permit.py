from web3 import Web3
from app.core.config import settings

w3 = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))
token = Web3.to_checksum_address('0x8B0180f2101c8260d49339abfEe87927412494B4')

# Check for permit() support (EIP-2612)
permit_abi = [{
    "inputs": [
        {"name": "owner",    "type": "address"},
        {"name": "spender",  "type": "address"},
        {"name": "value",    "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
        {"name": "v",        "type": "uint8"},
        {"name": "r",        "type": "bytes32"},
        {"name": "s",        "type": "bytes32"},
    ],
    "name": "permit",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function",
}]

# Check for nonces() — required by EIP-2612
nonces_abi = [{
    "inputs": [{"name": "owner", "type": "address"}],
    "name": "nonces",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function",
}]

# Check name/symbol/decimals
info_abi = [
    {"inputs": [], "name": "name",     "outputs": [{"name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "symbol",   "outputs": [{"name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}],  "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "DOMAIN_SEPARATOR", "outputs": [{"name": "", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
]

c = w3.eth.contract(address=token, abi=info_abi)
try:
    print("Token name    :", c.functions.name().call())
    print("Token symbol  :", c.functions.symbol().call())
    print("Token decimals:", c.functions.decimals().call())
except Exception as e:
    print("Token info failed:", e)

try:
    ds = c.functions.DOMAIN_SEPARATOR().call()
    print("DOMAIN_SEPARATOR:", ds.hex())
    print("=> Token has DOMAIN_SEPARATOR (likely supports permit)")
except Exception as e:
    print("DOMAIN_SEPARATOR: not found —", e)

try:
    nc = w3.eth.contract(address=token, abi=nonces_abi)
    n = nc.functions.nonces(token).call()
    print("nonces() works => EIP-2612 permit IS supported")
except Exception as e:
    print("nonces(): not found —", e)
    print("=> Token may NOT support permit()")

# Check current allowance for the contract
allowance_abi = [{
    "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
    "name": "allowance",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function",
}]
subscriber = '0x05e0555a49faea2e16cf4f3520db0e4a774aa4fe'
contract   = settings.SUBSCRIPTION_CONTRACT_POLYGON
try:
    ac = w3.eth.contract(address=token, abi=allowance_abi)
    allowance = ac.functions.allowance(
        Web3.to_checksum_address(subscriber),
        Web3.to_checksum_address(contract),
    ).call()
    print(f"\nCurrent allowance: {allowance} (raw)")
    print(f"Current allowance: {allowance / 1e6} USDC")
    print("=> Needs to be >= 1080964 (1.08 USDC)" )
except Exception as e:
    print("allowance() failed:", e)
