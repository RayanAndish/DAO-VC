"""
1_deploy_and_run_onchain.py
===========================
Executes live deployment, reads attested proposal profiles from Data/,
commits authentic ModelHash on-chain, submits 1,000 voting transactions to Ganache,
and triggers Bayesian Odds macro treasury allocation.
Target RPC: http://172.16.22.120:8545
"""

from decimal import Decimal
import json
import os
import time
from eth_account import Account
from eth_account.messages import encode_defunct
import numpy as np
import pandas as pd
from solcx import compile_standard, install_solc, set_solc_version
from web3 import Web3

Account.enable_unaudited_hdwallet_features()
np.random.seed(42)

# 1. Ganache Setup
GANACHE_URL = "http://172.16.22.120:8545"
TARGET_DEPLOYER = Web3.to_checksum_address(
    "0x1bEBD13E645623836843A184bEE52f03329bd20D"
)
MNEMONIC = (
    "swallow measure bright square universe truth unlock jelly round develop carbon naive"
)

w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
assert w3.is_connected(), f"Failed to connect to Ganache at {GANACHE_URL}"

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
print(f"[+] Active Deployer: {deployer_address}")


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


# 2. Compile and Deploy
install_solc("0.8.19")
set_solc_version("0.8.19")

contract_folder = "Contracts" if os.path.exists("Contracts") else "contracts"
with open(os.path.join(contract_folder, "PoAValidatorEscrow.sol"), "r") as f:
    escrow_source = f.read()
with open(os.path.join(contract_folder, "InvestmentSmartContract.sol"), "r") as f:
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

committee_signers = [Account.create() for _ in range(5)]
signer_addresses = [s.address for s in committee_signers]
THRESHOLD_K = 4

EscrowContract = w3.eth.contract(abi=escrow_abi, bytecode=escrow_bin)
r_escrow = send_signed_tx(
    EscrowContract.constructor().build_transaction({"from": deployer_address})
)
InvestContract = w3.eth.contract(abi=invest_abi, bytecode=invest_bin)
r_invest = send_signed_tx(
    InvestContract.constructor(signer_addresses, THRESHOLD_K).build_transaction(
        {"from": deployer_address}
    )
)
contract = w3.eth.contract(address=r_invest.contractAddress, abi=invest_abi)
print(f"[+] Contracts Deployed. Investment Contract: {r_invest.contractAddress}")

# 3. Read Proposals directly from AI stage (Zero Hardcoding)
prop_file = (
    "Table_Proposals_Feature_Profiles.csv"
    if os.path.exists("Table_Proposals_Feature_Profiles.csv")
    else "Data/Table_Proposals_Feature_Profiles.csv"
)
df_proposals = pd.read_csv(prop_file)

for _, r in df_proposals.iterrows():
    tx = contract.functions.registerProposal(
        r["Proposal_ID"]
    ).build_transaction({"from": deployer_address})
    send_signed_tx(tx)

tx = contract.functions.initVotingEpoch().build_transaction(
    {"from": deployer_address}
)
send_signed_tx(tx)

# 4. Generate 1,000 Heterogeneous Voters and Cast On-Chain Votes
N_VOTERS = 1000
raw_wealth = np.random.lognormal(mean=10.5, sigma=1.2, size=N_VOTERS)
wealth_scaling = 12_450_459.0 / raw_wealth.sum()
voter_tokens = (raw_wealth * wealth_scaling).astype(int)

wealth_pct = pd.Series(voter_tokens).rank(pct=True).values
voter_p_scores = []
for wp in wealth_pct:
    if wp > 0.80:
        p = np.clip(np.random.normal(0.28, 0.08), 0.05, 0.60)
    elif wp < 0.30:
        p = np.clip(np.random.normal(0.72, 0.12), 0.20, 0.98)
    else:
        p = np.clip(np.random.normal(0.50, 0.10), 0.10, 0.90)
    voter_p_scores.append(p)
voter_p_scores = np.array(voter_p_scores)

prop_ids = list(df_proposals["Proposal_ID"].values)
risk_map = dict(
    zip(df_proposals["Proposal_ID"], df_proposals["AI_Risk_Score_R_p"])
)
hype_map = {"P-2": 0.85, "P-4": 0.65, "P-5": 0.50, "P-1": 0.40, "P-3": 0.20}

voter_choices = []
for p_score in voter_p_scores:
    utilities = []
    for pid in prop_ids:
        quality = 1.0 - risk_map[pid]
        hype = hype_map[pid]
        u = (
            2.5 * p_score * quality
            + 2.0 * (1.0 - p_score) * hype
            + np.random.gumbel(0, 0.25)
        )
        utilities.append(u)
    exp_u = np.exp(np.array(utilities) - np.max(utilities))
    voter_choices.append(np.random.choice(prop_ids, p=exp_u / exp_u.sum()))

print(f"[*] Submitting {N_VOTERS} real on-chain voting transactions to Ganache...")
for idx in range(N_VOTERS):
    pid = voter_choices[idx]
    tokens = int(voter_tokens[idx])
    p_bps = int(voter_p_scores[idx] * 10000)
    tx = contract.functions.castVote(pid, tokens, p_bps).build_transaction(
        {"from": deployer_address}
    )
    send_signed_tx(tx)

tx = contract.functions.finalizeVotingTally().build_transaction(
    {"from": deployer_address}
)
send_signed_tx(tx)

# 5. Attestation with Authentic ModelHash
hash_file = (
    "models/model_hash.json"
    if os.path.exists("models/model_hash.json")
    else "Data/models/model_hash.json"
)
with open(hash_file, "r") as f:
    MODEL_HASH = json.load(f)["model_hash"]

print(f"[+] Committing Authentic ModelHash on-chain: {MODEL_HASH[:12]}...")

for _, r in df_proposals.iterrows():
    pid = r["Proposal_ID"]
    risk_scaled = int(Decimal(str(r["AI_Risk_Score_R_p"])) * Decimal(10**18))
    digest = Web3.solidity_keccak(
        ["string", "uint256", "uint256", "uint256", "string"],
        [pid, risk_scaled, 1, 101, MODEL_HASH],
    )
    signable = encode_defunct(digest)
    sigs = [
        s.sign_message(signable).signature
        for s in committee_signers[:THRESHOLD_K]
    ]

    tx = contract.functions.verifyAttestation(
        pid, risk_scaled, 1, 101, MODEL_HASH, sigs
    ).build_transaction({"from": deployer_address})
    send_signed_tx(tx)

# 6. Execute Allocation
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

# 7. Scalability Benchmark
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
pd.DataFrame(b_logs).to_csv("Table_5_1_Empirical_Scalability.csv", index=False)
print("[+] On-chain execution complete. Real blockchain artifacts exported.")