"""
1_deploy_and_run_onchain.py
===========================
Executes live deployment, 1,000 discrete on-chain voting transactions under 
a Multinomial Logit Agent Choice Model, threshold ECDSA attestation, and 
pure Bayesian Odds-based Macro Treasury Allocation on Ganache.
Target RPC: http://172.16.22.120:8545
"""

from decimal import Decimal
import json
import time
from eth_account import Account
from eth_account.messages import encode_defunct
import numpy as np
import pandas as pd
from solcx import compile_standard, install_solc, set_solc_version
from web3 import Web3

Account.enable_unaudited_hdwallet_features()
np.random.seed(42)

# ------------------------------------------------------------------------------
# 1. NETWORK & DEPLOYER SETUP
# ------------------------------------------------------------------------------
GANACHE_URL = "http://172.16.22.120:8545"
TARGET_DEPLOYER = Web3.to_checksum_address(
    "0x782282339c7c68DB709da39C8B02ae24c0256f36"
)
MNEMONIC = (
    "ocean filter humble ready mention strategy curious image olympic pitch"
    " trick raccoon"
)

w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
assert w3.is_connected(), f"Failed to connect to Ganache at {GANACHE_URL}"
print(f"[+] Connected to Ganache RPC: {GANACHE_URL}")

deployer_account = None
for i in range(20):
    path = f"m/44'/60'/0'/0/{i}"
    acct = Account.from_mnemonic(MNEMONIC, account_path=path)
    if acct.address.lower() == TARGET_DEPLOYER.lower():
        deployer_account = acct
        break

if deployer_account is None:
    deployer_account = Account.from_mnemonic(
        MNEMONIC, account_path="m/44'/60'/0'/0/0"
    )

deployer_address = deployer_account.address
print(f"[+] Active Deployer Address: {deployer_address}")
print(
    f"[+] Initial Balance:"
    f" {Web3.from_wei(w3.eth.get_balance(deployer_address), 'ether')} ETH"
)


def send_signed_tx(tx_dict):
    tx_dict["nonce"] = w3.eth.get_transaction_count(deployer_address)
    tx_dict["chainId"] = w3.eth.chain_id

    if (
        "maxFeePerGas" in tx_dict
        or "maxPriorityFeePerGas" in tx_dict
        or tx_dict.get("type") in [2, "0x2", "0x02"]
    ):
        tx_dict.pop("gasPrice", None)
    elif "gasPrice" not in tx_dict:
        tx_dict["gasPrice"] = w3.eth.gas_price

    if "gas" not in tx_dict:
        tx_dict["gas"] = 3500000

    try:
        signed = deployer_account.sign_transaction(tx_dict)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    except Exception:
        tx_hash = w3.eth.send_transaction(tx_dict)

    return w3.eth.wait_for_transaction_receipt(tx_hash)


# ------------------------------------------------------------------------------
# 2. COMPILE CONTRACTS
# ------------------------------------------------------------------------------
print("[*] Installing solc 0.8.19 (evmVersion: paris)...")
install_solc("0.8.19")
set_solc_version("0.8.19")

with open("contracts/PoAValidatorEscrow.sol", "r") as f:
    escrow_source = f.read()
with open("contracts/InvestmentSmartContract.sol", "r") as f:
    investment_source = f.read()

compiled_sol = compile_standard(
    {
        "language": "Solidity",
        "sources": {
            "PoAValidatorEscrow.sol": {"content": escrow_source},
            "InvestmentSmartContract.sol": {"content": investment_source},
        },
        "settings": {
            "evmVersion": "paris",
            "optimizer": {"enabled": True, "runs": 200},
            "outputSelection": {"*": {"*": ["abi", "evm.bytecode"]}},
        },
    },
    solc_version="0.8.19",
)

escrow_abi = compiled_sol["contracts"]["PoAValidatorEscrow.sol"][
    "PoAValidatorEscrow"
]["abi"]
escrow_bin = compiled_sol["contracts"]["PoAValidatorEscrow.sol"][
    "PoAValidatorEscrow"
]["evm"]["bytecode"]["object"]

invest_abi = compiled_sol["contracts"]["InvestmentSmartContract.sol"][
    "InvestmentSmartContract"
]["abi"]
invest_bin = compiled_sol["contracts"]["InvestmentSmartContract.sol"][
    "InvestmentSmartContract"
]["evm"]["bytecode"]["object"]

# ------------------------------------------------------------------------------
# 3. DEPLOY CONTRACTS & CONFIGURE COMMITTEE
# ------------------------------------------------------------------------------
committee_signers = [Account.create() for _ in range(5)]
signer_addresses = [s.address for s in committee_signers]
THRESHOLD_K = 4

print("[*] Deploying PoAValidatorEscrow...")
EscrowContract = w3.eth.contract(abi=escrow_abi, bytecode=escrow_bin)
r_escrow = send_signed_tx(
    EscrowContract.constructor().build_transaction({"from": deployer_address})
)
print(f"[+] PoAValidatorEscrow deployed at: {r_escrow.contractAddress}")

print("[*] Deploying InvestmentSmartContract...")
InvestContract = w3.eth.contract(abi=invest_abi, bytecode=invest_bin)
r_invest = send_signed_tx(
    InvestContract.constructor(signer_addresses, THRESHOLD_K).build_transaction(
        {"from": deployer_address}
    )
)
invest_addr = r_invest.contractAddress
contract = w3.eth.contract(address=invest_addr, abi=invest_abi)
print(f"[+] InvestmentSmartContract deployed at: {invest_addr}")

# ------------------------------------------------------------------------------
# 4. MULTINOMIAL LOGIT VOTER AGENT MODEL (1,000 AGENTS)
# ------------------------------------------------------------------------------
proposals_meta = {
    "P-3": {"risk": Decimal("0.06"), "hype": 0.20, "quality": 0.94},
    "P-2": {"risk": Decimal("0.49"), "hype": 0.85, "quality": 0.51},
    "P-5": {"risk": Decimal("0.39"), "hype": 0.50, "quality": 0.61},
    "P-4": {"risk": Decimal("0.46"), "hype": 0.65, "quality": 0.54},
    "P-1": {"risk": Decimal("0.35"), "hype": 0.40, "quality": 0.65},
}

for pid in proposals_meta.keys():
    tx = contract.functions.registerProposal(pid).build_transaction(
        {"from": deployer_address}
    )
    send_signed_tx(tx)

tx = contract.functions.initVotingEpoch().build_transaction(
    {"from": deployer_address}
)
send_signed_tx(tx)

N_VOTERS = 1000
print(
    f"\n[*] Generating {N_VOTERS} heterogeneous voter agents (Wealth &"
    " Behavioral Utility)..."
)

# 1. Wealth distribution: Log-Normal(10.5, 1.2) - scaled to total ~12.45M tokens
raw_wealth = np.random.lognormal(mean=10.5, sigma=1.2, size=N_VOTERS)
wealth_scaling = 12_450_459.0 / raw_wealth.sum()
voter_tokens = (raw_wealth * wealth_scaling).astype(int)

# 2. Behavioral Participation: Truncated Normal
# Higher wealth correlates with lower governance participation (passive whales)
wealth_pct = pd.Series(voter_tokens).rank(pct=True).values
voter_p_scores = []
for wp in wealth_pct:
    if wp > 0.80:  # Top 20% wealthy
        p = np.clip(np.random.normal(0.28, 0.08), 0.05, 0.60)
    elif wp < 0.30:  # Retail / Technical contributors
        p = np.clip(np.random.normal(0.72, 0.12), 0.20, 0.98)
    else:  # General electorate
        p = np.clip(np.random.normal(0.50, 0.10), 0.10, 0.90)
    voter_p_scores.append(p)

voter_p_scores = np.array(voter_p_scores)

# 3. Multinomial Logit Voter Decisions
prop_ids = list(proposals_meta.keys())
voter_choices = []
for p_score in voter_p_scores:
    utilities = []
    for pid in prop_ids:
        # Technical contributors value intrinsic quality (1-R); passive voters value hype
        u = (
            2.5 * p_score * proposals_meta[pid]["quality"]
            + 2.0 * (1.0 - p_score) * proposals_meta[pid]["hype"]
            + np.random.gumbel(0, 0.25)  # Extreme value noise
        )
        utilities.append(u)
    utilities = np.array(utilities)
    exp_u = np.exp(utilities - np.max(utilities))
    probs = exp_u / exp_u.sum()
    chosen_pid = np.random.choice(prop_ids, p=probs)
    voter_choices.append(chosen_pid)

print(f"[*] Submitting {N_VOTERS} real on-chain voting transactions to Ganache...")
print("[*] Progress: [", end="", flush=True)

t_start_voting = time.time()
for idx in range(N_VOTERS):
    pid = voter_choices[idx]
    tokens = int(voter_tokens[idx])
    # Scaled to integer basis points for on-chain precision
    p_bps = int(voter_p_scores[idx] * 10000)

    tx = contract.functions.castVote(pid, tokens, p_bps).build_transaction(
        {"from": deployer_address}
    )
    send_signed_tx(tx)

    if (idx + 1) % 100 == 0:
        print("=", end="", flush=True)

print("] 100% Complete!")
t_end_voting = time.time()
total_vote_time = t_end_voting - t_start_voting
print(
    f"[+] Confirmed {N_VOTERS} on-chain votes in {total_vote_time:.2f}s"
    f" (Throughput: {N_VOTERS/max(total_vote_time, 0.001):.1f} tx/s)"
)

# ------------------------------------------------------------------------------
# 5. RECONCILE ON-CHAIN TALLY & THRESHOLD ATTESTATION
# ------------------------------------------------------------------------------
print("\n[*] Finalizing On-Chain Voting Tally (Eq. 4b)...")
tx = contract.functions.finalizeVotingTally().build_transaction(
    {"from": deployer_address}
)
send_signed_tx(tx)

print("[*] Executing Threshold ECDSA Attestation on-chain (4-of-5 signers)...")
for pid, meta in proposals_meta.items():
    risk_scaled = int(meta["risk"] * Decimal(10**18))
    digest = Web3.solidity_keccak(
        ["string", "uint256", "uint256", "uint256", "string"],
        [pid, risk_scaled, 1, 101, "v1.0.4-prod"],
    )
    signable = encode_defunct(digest)
    sigs = [
        s.sign_message(signable).signature for s in committee_signers[:THRESHOLD_K]
    ]

    tx = contract.functions.verifyAttestation(
        pid, risk_scaled, 1, 101, "v1.0.4-prod", sigs
    ).build_transaction({"from": deployer_address})
    send_signed_tx(tx)
    print(f"[+] Attestation confirmed on-chain for {pid} (Risk={meta['risk']})")

# ------------------------------------------------------------------------------
# 6. EXECUTE DETERMINISTIC ALLOCATION (PURE BAYESIAN ODDS RATIO)
# ------------------------------------------------------------------------------
print("\n[*] Triggering Pure Bayesian Odds Treasury Allocation (Eq. 8)...")
tx = contract.functions.executeMacroTreasuryAllocation().build_transaction(
    {"from": deployer_address}
)
receipt = send_signed_tx(tx)

events = contract.events.TreasuryAllocated().process_receipt(receipt)
results = []
for ev in events:
    args = ev["args"]
    pid = str(args["proposalId"])
    aipox_usd = float(args["allocationAmountUSD"]) / 1e18
    trad_usd = float(args["traditionalAllocationUSD"]) / 1e18
    delta = ((aipox_usd - trad_usd) / trad_usd) * 100
    results.append(
        {
            "Proposal_ID": pid,
            "Traditional_Allocation_USD": round(trad_usd, 2),
            "AIPoX_Allocation_USD": round(aipox_usd, 2),
            "Net_Allocation_Delta_Pct": f"{delta:+.2f}%",
        }
    )

df_table4 = (
    pd.DataFrame(results)
    .sort_values(by="AIPoX_Allocation_USD", ascending=False)
    .reset_index(drop=True)
)
df_table4.to_csv("OnChain_Extracted_Table_4.csv", index=False)

# Export raw proposal states for downstream verification
state_records = []
for pid in prop_ids:
    p_info = contract.functions.proposals(pid).call()
    state_records.append(
        {
            "Proposal_ID": pid,
            "Raw_Token_Votes": p_info[1],
            "Raw_PoP_Sum": p_info[2],
            "Composite_Weight_Vp": p_info[3],
            "Risk_Score": float(p_info[4]) / 1e18,
            "Target_Allocation_USD": float(p_info[6]) / 1e18,
        }
    )
pd.DataFrame(state_records).to_csv(
    "OnChain_Proposal_State_Raw.csv", index=False
)

print("\n" + "=" * 80)
print(">>> ON-CHAIN VERIFIED TREASURY ALLOCATION (NO EPSILON, PURE ODDS RATIO):")
print("=" * 80)
print(df_table4.to_string(index=False))
print("=" * 80)

# ------------------------------------------------------------------------------
# 7. EMPIRICAL BENCHMARK ON GANACHE (GAS & LATENCY)
# ------------------------------------------------------------------------------
print("\n[*] Measuring Scalability Workloads on Ganache...")
workloads = [10, 20, 100, 500, 1000]
b_logs = []
for load in workloads:
    t0 = time.time()
    t_gas = 0
    for _ in range(load):
        tx = contract.functions.castVote("P-3", 100, 5000).build_transaction(
            {"from": deployer_address}
        )
        r = send_signed_tx(tx)
        t_gas += r.gasUsed
    el = time.time() - t0
    b_logs.append(
        {
            "Workload_Transactions": load,
            "Total_Execution_Time_s": round(el, 3),
            "Measured_TPS": round(load / max(el, 0.001), 1),
            "Avg_Latency_ms": round((el / load) * 1000, 2),
            "Avg_Gas_Per_Tx": int(t_gas / load),
        }
    )

df_b = pd.DataFrame(b_logs)
df_b.to_csv("Table_5_1_Empirical_Scalability.csv", index=False)
print("[+] Benchmarking completed and saved to Table_5_1_Empirical_Scalability.csv")