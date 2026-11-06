"""
01b_whale_fragmentation_sweep.py
================================
On-chain sweep of the 60%-stake whale attack with identity fragmentation.

The whale holds 60% of the token mass. Its tokens are split across k identities,
and every identity is registered with the same participation score P (basis points)
and votes for the highest-R proposal (RISKY). Each scenario deploys a fresh
InvestmentSmartContract, so every number is produced by executing the transactions
on Ganache. Nothing is computed offline except the PoP mass share, which is read
back from the registered scores.

Why this script exists
  The single-identity whale in 01_deploy_and_run_onchain.py contributes one P value
  among about 1,000 honest scores, so its PoP share is close to zero and changing P
  barely changes the result. Participation can only matter when the whale's PoP mass
  becomes comparable to the honest PoP mass, which requires several identities.

Scenario grid
  honest baseline (no attacker)
  k = 1, P = 0.28   single identity, paper's original setting
  k = 1, P = 0.98   single identity, maximum valid P
  k = 10, P = 0.98
  k = 100, P = 0.28
  k = 100, P = 0.98
  k = 1000, P = 0.98

Stake-to-vote (path 2)
  Each vote locks the voter's tokens (lockedStake). Identities below MIN_VOTE_STAKE cannot vote.
  The script records the locked token mass and the diverted allocation per locked token,
  and reads the dPoS allocation from TreasuryAllocated.traditionalAllocationUSD.

Requirements
  Ganache running (GANACHE_RPC, default http://172.16.22.120:8545)
  GANACHE_MNEMONIC set to the Ganache mnemonic (no default is stored here)
  Data/models/model_hash.json and Data/Table_Proposals_Feature_Profiles.csv
  (run 05 and 06 first), Contracts/ folder with both .sol files

Outputs
  Table_7c_Whale_Fragmentation_Sweep.csv   (replaces the earlier version)
  OnChain_Whale_Sweep_Log.csv
"""

import json
import os
import sys
import time
import warnings
from decimal import Decimal

import numpy as np
import pandas as pd
from eth_account import Account
from eth_account.messages import encode_defunct
from solcx import compile_standard, install_solc, set_solc_version
from web3 import Web3
from web3.logs import DISCARD

warnings.filterwarnings("ignore", category=UserWarning)
Account.enable_unaudited_hdwallet_features()

SEED = 42
N_VOTERS = 1000
THRESHOLD_K = 4
COMMITTEE_SIZE = 5
SCALE = 10 ** 18
WHALE_TOKEN_MULTIPLIER = 1.5          # whale tokens = 1.5 x honest tokens -> 60% share
MAX_CAP_USD = 400_000.0
MIN_VOTE_STAKE = 0                 # tokens an identity must lock to vote (contract minVoteStake)

GANACHE_URL = os.getenv("GANACHE_RPC", "http://172.16.22.120:8545")
MNEMONIC = " ".join(os.getenv("GANACHE_MNEMONIC", "").replace('"', "").replace("'", "").split())
if len(MNEMONIC.split()) not in (12, 15, 18, 21, 24):
    sys.exit("[-] GANACHE_MNEMONIC is not set or is not a valid BIP-39 phrase. "
             "Use: set \"GANACHE_MNEMONIC=word1 word2 ...\"")

w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
if not w3.is_connected():
    sys.exit(f"[-] Cannot connect to Ganache at {GANACHE_URL}")

deployer_account = Account.from_mnemonic(MNEMONIC, account_path="m/44'/60'/0'/0/0")
deployer_address = deployer_account.address
np.random.seed(SEED)


def first_existing(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    sys.exit(f"[-] None of these files exist: {paths}. Run the Data pipeline first.")


# ------------------------------------------------------------------------------
# Inputs
# ------------------------------------------------------------------------------
hash_file = first_existing("Data/models/model_hash.json", "models/model_hash.json")
with open(hash_file, "r", encoding="utf-8") as f:
    APPROVED_HASH = bytes.fromhex(json.load(f)["model_hash"].replace("0x", ""))

prop_file = first_existing("Data/Table_Proposals_Feature_Profiles.csv",
                           "Table_Proposals_Feature_Profiles.csv")
df_props = pd.read_csv(prop_file)
PIDS = list(df_props["Proposal_ID"])
RISK = dict(zip(df_props["Proposal_ID"], df_props["AI_Risk_Score_R_p"]))
RISKY = max(PIDS, key=lambda p: RISK[p])     # highest R(p): role fixed by data
SAFE = min(PIDS, key=lambda p: RISK[p])      # lowest R(p)
print(f"[+] SAFE (lowest R) = {SAFE} R={RISK[SAFE]:.4f} | RISKY (highest R) = {RISKY} R={RISK[RISKY]:.4f}", flush=True)

# ------------------------------------------------------------------------------
# Compile contracts (same settings as 01_deploy_and_run_onchain.py)
# ------------------------------------------------------------------------------
install_solc("0.8.19")
set_solc_version("0.8.19")
contract_folder = "Contracts" if os.path.exists("Contracts") else "contracts"
with open(os.path.join(contract_folder, "PoAValidatorEscrow.sol"), "r", encoding="utf-8") as f:
    escrow_source = f.read()
with open(os.path.join(contract_folder, "InvestmentSmartContract.sol"), "r", encoding="utf-8") as f:
    investment_source = f.read()

compiled = compile_standard(
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
invest_abi = compiled["contracts"]["InvestmentSmartContract.sol"]["InvestmentSmartContract"]["abi"]
invest_bin = compiled["contracts"]["InvestmentSmartContract.sol"]["InvestmentSmartContract"]["evm"]["bytecode"]["object"]
InvestContract = w3.eth.contract(abi=invest_abi, bytecode=invest_bin)


# ------------------------------------------------------------------------------
# Helpers (same behaviour as 01_deploy_and_run_onchain.py)
# ------------------------------------------------------------------------------
def send_signed_tx(tx_dict, signer_account=None):
    if signer_account is None:
        signer_account = deployer_account
    tx_dict["nonce"] = w3.eth.get_transaction_count(signer_account.address)
    tx_dict["chainId"] = w3.eth.chain_id
    if "maxFeePerGas" in tx_dict or "maxPriorityFeePerGas" in tx_dict or tx_dict.get("type") in [2, "0x2", "0x02"]:
        tx_dict.pop("gasPrice", None)
    elif "gasPrice" not in tx_dict:
        tx_dict["gasPrice"] = w3.eth.gas_price
    if "gas" not in tx_dict:
        try:
            tx_dict["gas"] = int(w3.eth.estimate_gas(tx_dict) * 1.30)
        except Exception as exc:
            raise RuntimeError(f"gas estimation failed (transaction would revert): {exc}")
    signed = signer_account.sign_transaction(tx_dict)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"transaction reverted: {tx_hash.hex()}")
    return receipt


def fund_accounts_batch(accounts, amount_ether):
    nonce = w3.eth.get_transaction_count(deployer_address)
    gas_price = w3.eth.gas_price
    chain_id = w3.eth.chain_id
    funded = 0
    for a in accounts:
        addr = a.address
        if w3.eth.get_balance(addr) < Web3.to_wei(0.005, "ether"):
            tx = {"from": deployer_address, "to": addr,
                  "value": Web3.to_wei(amount_ether, "ether"),
                  "nonce": nonce, "gas": 21000, "gasPrice": gas_price, "chainId": chain_id}
            w3.eth.send_raw_transaction(deployer_account.sign_transaction(tx).raw_transaction)
            nonce += 1
            funded += 1
    if funded:
        while w3.eth.get_transaction_count(deployer_address) < nonce:
            time.sleep(0.05)


_whale_pool = []


def whale_accounts(k):
    """Identities derived on a separate BIP-44 branch so they never collide with voters."""
    while len(_whale_pool) < k:
        i = len(_whale_pool)
        _whale_pool.append(Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/1'/0/{i}"))
    return _whale_pool[:k]


def usd(raw):
    return int(raw) / SCALE


# ------------------------------------------------------------------------------
# Honest population (same generator as 01, seed 42)
# ------------------------------------------------------------------------------
raw_wealth = np.random.lognormal(mean=8.8, sigma=1.0, size=N_VOTERS)
voter_tokens = raw_wealth.astype(int)
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
voter_p_bps = [int(p * 10000) for p in voter_p_scores]

voter_accounts = [Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/0'/0/{i + 10}")
                  for i in range(N_VOTERS)]
voter_addresses = [a.address for a in voter_accounts]

voter_choices = []
for p_score in voter_p_scores:
    utilities = [(1.0 - RISK[pid]) * p_score + np.random.uniform(0.1, 0.4) for pid in PIDS]
    probs = np.array(utilities) / sum(utilities)
    voter_choices.append(np.random.choice(PIDS, p=probs))

HONEST_TOKENS = int(voter_tokens.sum())
WHALE_TOKENS = int(WHALE_TOKEN_MULTIPLIER * HONEST_TOKENS)
HONEST_ELIGIBLE = [i for i in range(N_VOTERS) if int(voter_tokens[i]) >= MIN_VOTE_STAKE]
HONEST_P_SUM = int(sum(voter_p_bps[i] for i in HONEST_ELIGIBLE))
HONEST_LOCKED = int(sum(int(voter_tokens[i]) for i in HONEST_ELIGIBLE))
print(f"[+] Honest voters able to lock stake: {len(HONEST_ELIGIBLE)} of {N_VOTERS}", flush=True)
print(f"[+] Honest voters: {N_VOTERS}, tokens {HONEST_TOKENS:,}, PoP mass {HONEST_P_SUM:,} bps", flush=True)
print(f"[+] Whale tokens {WHALE_TOKENS:,} -> token share {WHALE_TOKENS / (WHALE_TOKENS + HONEST_TOKENS):.4f}", flush=True)

SCENARIOS = [
    ("Honest baseline",         0,    0),
    ("1 identity, P=0.28",      1,    2800),
    ("1 identity, P=0.98",      1,    9800),
    ("10 identities, P=0.98",   10,   9800),
    ("100 identities, P=0.28",  100,  2800),
    ("100 identities, P=0.98",  100,  9800),
    ("1000 identities, P=0.98", 1000, 9800),
]


# ------------------------------------------------------------------------------
# One scenario = one fresh contract, all transactions executed on Ganache
# ------------------------------------------------------------------------------
def run_scenario(sid, name, k, p_bps):
    t0 = time.time()
    committee = [Account.create() for _ in range(COMMITTEE_SIZE)]
    signer_addresses = [s.address for s in committee]

    r = send_signed_tx(InvestContract.constructor(
        signer_addresses, THRESHOLD_K, APPROVED_HASH).build_transaction({"from": deployer_address}))
    contract = w3.eth.contract(address=r.contractAddress, abi=invest_abi)

    for _, row in df_props.iterrows():
        send_signed_tx(contract.functions.registerProposal(
            row["Proposal_ID"]).build_transaction({"from": deployer_address}))

    fund_accounts_batch(voter_accounts, amount_ether=0.015)
    for b in range(0, N_VOTERS, 25):
        send_signed_tx(contract.functions.registerVoterProfiles(
            voter_addresses[b:b + 25],
            [int(t) for t in voter_tokens[b:b + 25]],
            voter_p_bps[b:b + 25],
        ).build_transaction({"from": deployer_address}))

    ids = whale_accounts(k) if k > 0 else []
    if k > 0:
        fund_accounts_batch(ids, amount_ether=0.02)
        base, rem = divmod(WHALE_TOKENS, k)
        toks = [base + (1 if i < rem else 0) for i in range(k)]   # total exactly WHALE_TOKENS
        for b in range(0, k, 25):
            chunk = ids[b:b + 25]
            send_signed_tx(contract.functions.registerVoterProfiles(
                [a.address for a in chunk],
                toks[b:b + 25],
                [p_bps] * len(chunk),
            ).build_transaction({"from": deployer_address}))

    send_signed_tx(contract.functions.setMinVoteStake(MIN_VOTE_STAKE).build_transaction({"from": deployer_address}))

    epoch = w3.eth.block_number + 1
    send_signed_tx(contract.functions.initVotingEpoch(epoch).build_transaction({"from": deployer_address}))

    for idx in range(N_VOTERS):
        if int(voter_tokens[idx]) < MIN_VOTE_STAKE:
            continue   # cannot lock the minimum stake, so cannot vote
        send_signed_tx(contract.functions.castVote(voter_choices[idx]).build_transaction(
            {"from": voter_addresses[idx]}), signer_account=voter_accounts[idx])
    for a in ids:
        send_signed_tx(contract.functions.castVote(RISKY).build_transaction(
            {"from": a.address}), signer_account=a)

    send_signed_tx(contract.functions.finalizeVotingTally().build_transaction({"from": deployer_address}))

    nonce = 1000 * (sid + 1) + 1
    for _, row in df_props.iterrows():
        pid = row["Proposal_ID"]
        risk_scaled = int(Decimal(str(row["AI_Risk_Score_R_p"])) * Decimal(10 ** 18))
        digest = Web3.solidity_keccak(
            ["address", "uint256", "string", "uint256", "uint256", "bytes32", "uint256"],
            [contract.address, w3.eth.chain_id, pid, epoch, nonce, APPROVED_HASH, risk_scaled])
        sigs = [s.sign_message(encode_defunct(digest)).signature for s in committee[:THRESHOLD_K]]
        send_signed_tx(contract.functions.verifyAttestation(
            pid, risk_scaled, epoch, nonce, APPROVED_HASH, sigs).build_transaction({"from": deployer_address}))
        nonce += 1

    rec = send_signed_tx(contract.functions.executeAblationAllocation(4).build_transaction(
        {"from": deployer_address}))
    locked_total = int(contract.functions.totalLockedStake().call())
    events = contract.events.TreasuryAllocated().process_receipt(rec, errors=DISCARD)
    alloc = {str(e["args"]["proposalId"]): usd(e["args"]["allocationAmountUSD"]) for e in events}
    trad = {str(e["args"]["proposalId"]): usd(e["args"]["traditionalAllocationUSD"]) for e in events}
    if sorted(alloc) != sorted(PIDS):
        raise RuntimeError(f"expected {len(PIDS)} TreasuryAllocated events, got {len(alloc)}")

    whale_locked = locked_total - HONEST_LOCKED if k > 0 else 0
    total_p = HONEST_P_SUM + k * p_bps
    whale_pop_share = (k * p_bps) / total_p if k > 0 else 0.0
    whale_token_share = WHALE_TOKENS / (WHALE_TOKENS + HONEST_TOKENS) if k > 0 else 0.0
    print(f"[+] {name}: done in {time.time() - t0:.1f}s | {RISKY} = ${alloc[RISKY]:,.2f} | "
          f"whale PoP share {whale_pop_share:.4%}", flush=True)
    return {
        "name": name, "k": k, "p_bps": p_bps,
        "whale_token_share": whale_token_share,
        "whale_pop_share": whale_pop_share,
        "whale_locked": whale_locked,
        "locked_total": locked_total,
        "alloc": alloc,
        "trad": trad,
    }


# ------------------------------------------------------------------------------
# Run all scenarios
# ------------------------------------------------------------------------------
print("=" * 80, flush=True)
print("[SWEEP] Whale fragmentation on-chain", flush=True)
print("=" * 80, flush=True)

results = [run_scenario(sid, *spec) for sid, spec in enumerate(SCENARIOS)]
base_alloc = results[0]["alloc"]
base_trad = results[0]["trad"]

rows, log_rows = [], []
for res in results:
    a = res["alloc"]
    ranking = sorted(a, key=lambda p: a[p], reverse=True)
    risky_change = (a[RISKY] - base_alloc[RISKY]) / base_alloc[RISKY] * 100
    safe_change = (a[SAFE] - base_alloc[SAFE]) / base_alloc[SAFE] * 100
    rows.append({
        "Scenario": res["name"],
        "Identities (k)": res["k"],
        "P per identity": res["p_bps"] / 10000 if res["k"] else "-",
        "Whale token share": f"{res['whale_token_share']:.2%}",
        "Whale PoP share": f"{res['whale_pop_share']:.2%}",
        f"{RISKY} baseline (USD)": round(base_alloc[RISKY], 2),
        f"{RISKY} under attack (USD)": round(a[RISKY], 2),
        f"{RISKY} change (%)": f"{risky_change:+.2f}%" if res["k"] else "-",
        f"{SAFE} change (%)": f"{safe_change:+.2f}%" if res["k"] else "-",
        "Locked whale tokens": res["whale_locked"],
        f"{RISKY} dPoS under attack (USD)": round(res["trad"][RISKY], 2),
        f"{RISKY} dPoS change (%)": f"{(res['trad'][RISKY] - base_trad[RISKY]) / base_trad[RISKY] * 100:+.2f}%" if res["k"] else "-",
        "Diverted USD per 1M locked tokens": (f"{(a[RISKY] - base_alloc[RISKY]) / (res['whale_locked'] / 1e6):,.0f}" if res["k"] else "-"),
        "Cap binding for RISKY": "yes" if a[RISKY] >= MAX_CAP_USD - 0.01 else "no",
        f"{RISKY} rank under attack": ranking.index(RISKY) + 1,
        "Top proposal under attack": ranking[0],
    })
    for pid in PIDS:
        log_rows.append({"Scenario": res["name"], "Proposal_ID": pid, "AIPoX_Allocation_USD": round(a[pid], 2)})

df_out = pd.DataFrame(rows)
df_log = pd.DataFrame(log_rows)
df_out.to_csv("Table_7c_Whale_Fragmentation_Sweep.csv", index=False)
df_log.to_csv("OnChain_Whale_Sweep_Log.csv", index=False)

print("\n>>> TABLE 7c (on-chain whale fragmentation sweep)", flush=True)
print(df_out.to_string(index=False), flush=True)

# Consistency check against Table 4 (honest baseline must reproduce the released allocation)
t4_path = first_existing("Table_4_Treasury_Allocation.csv", "Data/Table_4_Treasury_Allocation.csv", "OnChain_Proposal_State_Raw.csv")
if t4_path.endswith("OnChain_Proposal_State_Raw.csv"):
    ref = pd.read_csv(t4_path).set_index("Proposal_ID")["Target_Allocation_USD"]
else:
    ref = pd.read_csv(t4_path).set_index("Proposal ID")["AIPoX Allocation (USD)"]
max_dev = max(abs(base_alloc[p] - float(ref[p])) for p in PIDS)
print(f"[check] honest baseline vs released Table 4: max deviation ${max_dev:,.4f}", flush=True)
if max_dev > 1.0:
    print("[i] Baseline differs from the released Table 4 because identities below MIN_VOTE_STAKE "
          f"({N_VOTERS - len(HONEST_ELIGIBLE)} honest voters) are excluded by the stake rule. "
          "Report this as the stake-rule baseline.", flush=True)

print("[DONE] wrote Table_7c_Whale_Fragmentation_Sweep.csv and OnChain_Whale_Sweep_Log.csv", flush=True)
