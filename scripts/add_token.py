from web3 import Web3
from app.core.config import settings
from eth_account import Account

w3 = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))
addr = Web3.to_checksum_address(settings.SUBSCRIPTION_CONTRACT_POLYGON)
token = Web3.to_checksum_address('0x8B0180f2101c8260d49339abfEe87927412494B4')
owner_key = settings.RELAYER_PRIVATE_KEY
owner = Account.from_key(owner_key)

print("Contract :", addr)
print("Token    :", token)
print("Owner    :", owner.address)
print()

candidates = [
    "addSupportedToken",
    "addToken",
    "setSupportedToken",
    "whitelistToken",
    "enableToken",
    "registerToken",
]

found_fn = None

for name in candidates:
    abi = [{
        "inputs": [{"name": "token", "type": "address"}],
        "name": name,
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }]
    try:
        contract = w3.eth.contract(address=addr, abi=abi)
        fn = getattr(contract.functions, name)(token)
        gas = fn.estimate_gas({"from": owner.address})
        print(f"FOUND: {name}()  gas estimate = {gas}")
        found_fn = fn
        found_name = name
        break
    except Exception as e:
        print(f"  {name}() -> {e}")

if not found_fn:
    print("\nNone of the candidate function names worked.")
    print("Please share your contract's Solidity source so we can find the exact function name.")
else:
    print(f"\nCalling {found_name}({token}) ...")
    nonce = w3.eth.get_transaction_count(owner.address)
    tx = found_fn.build_transaction({
        "from": owner.address,
        "nonce": nonce,
        "gas": int(gas * 1.3),
        "gasPrice": int(w3.eth.gas_price * 1.2),
        "chainId": 80002,
    })
    signed = w3.eth.account.sign_transaction(tx, owner.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"TX sent : {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    status = "SUCCESS" if receipt["status"] == 1 else "REVERTED"
    print(f"Status  : {status}")
    if receipt["status"] == 1:
        print("\nToken whitelisted! Try creating a subscription now.")
    else:
        print("\nTransaction reverted. You may not be the contract owner, or the token is already added.")
