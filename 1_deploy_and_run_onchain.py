"""
1_deploy_and_run_onchain.py
===========================
On-chain verification suite for AIPoX on a local Ganache node.

Configuration
  GANACHE_MNEMONIC  required, BIP-39 mnemonic of the Ganache accounts (no default is stored here)
  GANACHE_RPC       optional, default http://172.16.22.120:8545

Suites
  1  PoA validator escrow: bonding, minimum collateral, timelocked unbonding, k-of-M
     attested slashing, ejection, negative tests.
  2  Governance: four-way ablation over 1,000 honest voters, with negative tests for
     C1 (double vote), C2 (PoP bound), C3 (risk bound), C5 (phase lock), C7 (tranches).
  3  Sybil: 1,500 identities with 1,000 tokens and 0 PoP vote for P-4.
  4  Whale: one account with 60% of tokens. P = 0.28 (main) and P = 0.98 (worst case).

Outputs (project root)
  OnChain_Proposal_State_Raw.csv, Table_5_Ablation_Study.csv, Table_6_Sybil_Attack.csv,
  Table_7_Whale_Prioritization.csv, Table_8_Whale_Treasury_Distortion.csv,
  Table_8b_Whale_Worst_Case.csv, OnChain_Test_Log.csv

Revision notes
- registerProposal takes one argument, matching the contract (it was called with two).
- Escrow calls match the revised PoAValidatorEscrow.sol.
- Attestation digests use the same field order as the contract.
- No silent gas fallback: a revert stops the run and shows the reason.
- Every expected revert is tested and written to OnChain_Test_Log.csv.
- Table labels are derived from measured ranks, not written in advance.
- Voter generation keeps the original random-number order (same tokens and P-scores).
- The committee keys are generated per run; they are not persisted.
"""

import json
import os
import sys
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from eth_account import Account
from eth_account.messages import encode_defunct
from solcx import compile_standard, install_solc, set_solc_version
from web3 import Web3

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "Data"

SEED = 42
N_VOTERS = 1000
N_SYBIL = 1500
SYBIL_TOKENS = 1000
THRESHOLD_K = 4
N_COMMITTEE = 5
UNBOND_DELAY_BLOCKS = 20
WHALE_TOKEN_MULTIPLE = 1.5          # 1.5 x honest total => 60% of all tokens
WHALE_P_MAIN_BPS = 2800             # P = 0.28
WHALE_P_WORST_BPS = 9800            # P = 0.98 (maximum valid PoP)
VOTER_MIN_ETH, VOTER_TOP_ETH = 0.005, 0.01
SYBIL_MIN_ETH, SYBIL_TOP_ETH = 0.004, 0.005
ESCROW_BOND_ETH, ESCROW_MIN_ETH = 10, 10.5

GANACHE_URL = os.getenv("GANACHE_RPC", "http://172.16.22.120:8545")
def clean_mnemonic(raw):
    """Remove surrounding quotes and stray whitespace that cmd/PowerShell can leave in env vars."""
    if not raw:
        return None
    text = raw.strip().strip('"').strip("'")
    return " ".join(text.split()).lower()


MNEMONIC = clean_mnemonic(os.getenv("GANACHE_MNEMONIC"))
if not MNEMONIC or len(MNEMONIC.split()) not in (12, 15, 18, 21, 24):
    sys.exit("[ERROR] GANACHE_MNEMONIC is missing or is not a valid 12/15/18/21/24-word mnemonic. "
             "Set it without quotes: set \"GANACHE_MNEMONIC=word1 word2 ... word12\"")

Account.enable_unaudited_hdwallet_features()
np.random.seed(SEED)

w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
if not w3.is_connected():
    sys.exit(f"[ERROR] Cannot reach Ganache at {GANACHE_URL}")

deployer = Account.from_mnemonic(MNEMONIC, account_path="m/44'/60'/0'/0/0")
RESULTS = []   # (suite, test, outcome, detail)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def section(title):
    print("\n" + "=" * 80, flush=True)
    print(title, flush=True)
    print("=" * 80, flush=True)


def check(suite, name, condition, detail=""):
    if not condition:
        RESULTS.append((suite, name, "FAIL", detail))
        raise AssertionError(f"[FAIL] {suite}: {name} {detail}")
    RESULTS.append((suite, name, "PASS", detail))
    print(f"[PASS] {name} {detail}", flush=True)


def expect_revert(suite, name, fn, signer=None, value=0):
    signer = signer or deployer
    try:
        fn.build_transaction({"from": signer.address, "value": value})
    except Exception as exc:
        reason = str(exc).splitlines()[0][:160]
        RESULTS.append((suite, name, "REJECTED", reason))
        print(f"[PASS] {name}: rejected -> {reason}", flush=True)
        return
    RESULTS.append((suite, name, "NOT REJECTED", ""))
    raise AssertionError(f"[FAIL] {suite}: {name} was NOT rejected")


def transact(fn, signer=None, value=0):
    signer = signer or deployer
    tx = fn.build_transaction({
        "from": signer.address,
        "value": value,
        "nonce": w3.eth.get_transaction_count(signer.address, "pending"),
    })
    tx_hash = w3.eth.send_raw_transaction(signer.sign_transaction(tx).raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")
    return receipt


def deploy(factory, *args):
    receipt = transact(factory.constructor(*args))
    return w3.eth.contract(address=receipt.contractAddress, abi=factory.abi)


def send_eth(to, eth):
    tx = {
        "from": deployer.address,
        "to": to,
        "value": Web3.to_wei(eth, "ether"),
        "gas": 21000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(deployer.address, "pending"),
        "chainId": w3.eth.chain_id,
    }
    tx_hash = w3.eth.send_raw_transaction(deployer.sign_transaction(tx).raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    check("setup", "funding transfer succeeded", receipt.status == 1, f"to {to[:10]}...")


def fund_low(accounts, min_eth, top_eth):
    for acc in accounts:
        addr = acc.address if hasattr(acc, "address") else acc
        if w3.eth.get_balance(addr) < Web3.to_wei(min_eth, "ether"):
            send_eth(addr, top_eth)


def mine_blocks(n):
    for _ in range(n):
        send_eth(deployer.address, 0)


def usd(wei):
    return float((Decimal(int(wei)) / Decimal(10 ** 18)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def rank_of(values, pid):
    return int(pd.Series(values).rank(ascending=False, method="min")[pid])


# ------------------------------------------------------------------------------
# Compile
# ------------------------------------------------------------------------------
section("[SETUP] Compiling contracts with solc 0.8.19")
install_solc("0.8.19")
set_solc_version("0.8.19")

CONTRACT_DIR = PROJECT_DIR / "Contracts" if (PROJECT_DIR / "Contracts").exists() else PROJECT_DIR / "contracts"
sources = {name: {"content": (CONTRACT_DIR / name).read_text(encoding="utf-8")}
           for name in ["PoAValidatorEscrow.sol", "InvestmentSmartContract.sol"]}
compiled = compile_standard({
    "language": "Solidity",
    "sources": sources,
    "settings": {
        "evmVersion": "paris",
        "optimizer": {"enabled": True, "runs": 200},
        "outputSelection": {"*": {"*": ["abi", "evm.bytecode"]}},
    },
}, solc_version="0.8.19")

esc_art = compiled["contracts"]["PoAValidatorEscrow.sol"]["PoAValidatorEscrow"]
inv_art = compiled["contracts"]["InvestmentSmartContract.sol"]["InvestmentSmartContract"]
Escrow = w3.eth.contract(abi=esc_art["abi"], bytecode=esc_art["evm"]["bytecode"]["object"])
Invest = w3.eth.contract(abi=inv_art["abi"], bytecode=inv_art["evm"]["bytecode"]["object"])

# ------------------------------------------------------------------------------
# Inputs: model hash, proposals, committee
# ------------------------------------------------------------------------------
hash_file = DATA_DIR / "models" / "model_hash.json"
if not hash_file.exists():
    sys.exit("[ERROR] Data/models/model_hash.json missing. Run Data/1_train_models.py first.")
MODEL_HASH = bytes.fromhex(json.loads(hash_file.read_text(encoding="utf-8"))["model_hash"][2:])
check("setup", "ModelHash is 32 bytes", len(MODEL_HASH) == 32)

prop_file = DATA_DIR / "Table_Proposals_Feature_Profiles.csv"
if not prop_file.exists():
    sys.exit("[ERROR] Data/Table_Proposals_Feature_Profiles.csv missing. Run Data/3_score_proposals.py first.")
df_prop = pd.read_csv(prop_file)
PIDS = list(df_prop["Proposal_ID"].values)
RISK = dict(zip(df_prop["Proposal_ID"], df_prop["AI_Risk_Score_R_p"]))


def risk_wei(pid):
    return int(Decimal(str(RISK[pid])) * 10 ** 18)


committee = [Account.create() for _ in range(N_COMMITTEE)]
committee_addrs = [a.address for a in committee]
ATTEST_SIGNERS = committee[:THRESHOLD_K]

ESC_TYPES = ["address", "uint256", "address", "uint256", "uint256", "uint256", "bytes32"]
ATT_TYPES = ["address", "uint256", "string", "uint256", "uint256", "bytes32", "uint256"]


def sign_digest(types, values, signers=ATTEST_SIGNERS):
    digest = Web3.solidity_keccak(types, values)
    return [s.sign_message(encode_defunct(digest)).signature for s in signers]


def prop_state(contract, pid):
    p = contract.functions.proposals(pid).call()
    if p[0] != pid:
        raise RuntimeError(f"proposals() returned {p[0]} for {pid}; ABI layout changed")
    return {"raw_tokens": p[1], "raw_pop": p[2], "V": p[3], "risk": p[4],
            "target": p[6], "released": p[7]}


def register_voters(contract, addrs, tokens, bps):
    for b in range(0, len(addrs), 25):
        transact(contract.functions.registerVoterProfiles(
            addrs[b:b + 25], [int(t) for t in tokens[b:b + 25]], [int(p) for p in bps[b:b + 25]]))


def attest_all(contract, epoch, nonce_base):
    for k, pid in enumerate(PIDS):
        r = risk_wei(pid)
        nonce = nonce_base + k
        sigs = sign_digest(ATT_TYPES, [contract.address, w3.eth.chain_id, pid, epoch, nonce, MODEL_HASH, r])
        transact(contract.functions.verifyAttestation(pid, r, epoch, nonce, MODEL_HASH, sigs))
    check("attestation", f"{len(PIDS)} attestations accepted", True, f"nonce base {nonce_base}")


def run_ablation(contract, variants):
    out, receipts = {}, {}
    for v in variants:
        rec = transact(contract.functions.executeAblationAllocation(v))
        evs = contract.events.AblationExecuted().process_receipt(rec)
        out[v] = {str(e["args"]["proposalId"]): int(e["args"]["allocationUSD"]) for e in evs}
        receipts[v] = rec
        check("ablation", f"variant {v} emitted {len(PIDS)} allocations", len(out[v]) == len(PIDS))
    total = sum(out[variants[-1]].values())
    check("ablation", "full allocation does not exceed the pool",
          total <= 10 ** 24, f"sum {usd(total):,.2f} USD")
    return out, receipts


# ------------------------------------------------------------------------------
# Population: identical generation order to the original script (same tokens and P)
# ------------------------------------------------------------------------------
raw_wealth = np.random.lognormal(mean=8.8, sigma=1.0, size=N_VOTERS)
voter_tokens = raw_wealth.astype(int)
wealth_pct = pd.Series(voter_tokens).rank(pct=True).values

voter_p = []
for wp in wealth_pct:
    if wp > 0.80:
        p = np.clip(np.random.normal(0.28, 0.08), 0.05, 0.60)
    elif wp < 0.30:
        p = np.clip(np.random.normal(0.72, 0.12), 0.20, 0.98)
    else:
        p = np.clip(np.random.normal(0.50, 0.10), 0.10, 0.90)
    voter_p.append(p)
voter_p = np.array(voter_p)
voter_bps = [int(p * 10000) for p in voter_p]

voter_choices = []
for p in voter_p:
    utilities = [(1.0 - RISK[pid]) * p + np.random.uniform(0.1, 0.4) for pid in PIDS]
    probs = np.array(utilities) / sum(utilities)
    voter_choices.append(np.random.choice(PIDS, p=probs))

voter_accounts = [Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/0'/0/{i + 10}") for i in range(N_VOTERS)]
voter_addrs = [a.address for a in voter_accounts]
honest_total = int(voter_tokens.sum())

# Budget check before any transaction (Ganache default account balance is 100 ETH)
needed_eth = (5 * ESCROW_MIN_ETH + N_VOTERS * VOTER_TOP_ETH * 3          # voters topped up for three phases
              + N_SYBIL * SYBIL_TOP_ETH + 2 * 0.05 + 2)              # whales, gas margin
bal_eth = float(w3.from_wei(w3.eth.get_balance(deployer.address), "ether"))
print(f"[*] Deployer balance {bal_eth:.2f} ETH, estimated requirement {needed_eth:.2f} ETH", flush=True)
check("setup", "deployer balance sufficient", bal_eth > needed_eth, f"({bal_eth:.2f} > {needed_eth:.2f})")

# ==============================================================================
# SUITE 1: POA VALIDATOR ESCROW
# ==============================================================================
section("[SUITE 1] PoA validator escrow")
escrow = deploy(Escrow, committee_addrs, THRESHOLD_K, MODEL_HASH)

candidates = [Account.create() for _ in range(5)]
fund_low(candidates, ESCROW_MIN_ETH, ESCROW_MIN_ETH + 0.5)
for v in candidates:
    transact(escrow.functions.depositCollateral(), signer=v, value=Web3.to_wei(ESCROW_BOND_ETH, "ether"))
check("escrow", "5 validators bonded", escrow.functions.getActiveValidatorCount().call() == 5)

val1, val2, val5 = candidates[0], candidates[1], candidates[4]

transact(escrow.functions.requestUnbond(Web3.to_wei(2, "ether")), signer=val1)
expect_revert("escrow", "second unbond while one is pending", escrow.functions.requestUnbond(Web3.to_wei(1, "ether")), signer=val1)
expect_revert("escrow", "withdraw before unbonding delay", escrow.functions.withdrawStake(), signer=val1)
mine_blocks(UNBOND_DELAY_BLOCKS + 1)
transact(escrow.functions.withdrawStake(), signer=val1)
d1 = escrow.functions.getValidatorDetails(val1.address).call()
check("escrow", "withdrawal leaves 8 ETH bonded", d1[0] == Web3.to_wei(8, "ether"), f"bonded={d1[0]}")


def sign_escrow(validator, anomaly, epoch, nonce, signers=ATTEST_SIGNERS):
    return sign_digest(ESC_TYPES, [escrow.address, w3.eth.chain_id, validator, anomaly, epoch, nonce, MODEL_HASH], signers)


# Partial slash (anomaly 0.10): stake reduces, validator stays active
ep = w3.eth.block_number
transact(escrow.functions.slashValidatorWithAttestation(
    val2.address, 1000, ep, 1001, MODEL_HASH, sign_escrow(val2.address, 1000, ep, 1001)))
d2 = escrow.functions.getValidatorDetails(val2.address).call()
check("escrow", "partial slash (0.10) keeps validator active", d2[2] is True and d2[0] == Web3.to_wei(9, "ether"))

# Replay of the same attestation is rejected
expect_revert("escrow", "replay of attested slash (stale nonce)",
              escrow.functions.slashValidatorWithAttestation(
                  val2.address, 1000, ep, 1001, MODEL_HASH, sign_escrow(val2.address, 1000, ep, 1001)))

# Attestation from a non-committee key is rejected
rogue = [Account.create() for _ in range(THRESHOLD_K)]
ep2 = w3.eth.block_number
expect_revert("escrow", "slash signed by non-committee keys",
              escrow.functions.slashValidatorWithAttestation(
                  val2.address, 2000, ep2, 1002, MODEL_HASH,
                  sign_escrow(val2.address, 2000, ep2, 1002, signers=rogue)))

# Zero anomaly is rejected (E3)
expect_revert("escrow", "zero anomaly rejected",
              escrow.functions.slashValidatorWithAttestation(
                  val2.address, 0, ep2, 1003, MODEL_HASH, sign_escrow(val2.address, 0, ep2, 1003)))

# Ejecting slash (anomaly 0.75 >= 0.65) for val5
ep3 = w3.eth.block_number
transact(escrow.functions.slashValidatorWithAttestation(
    val5.address, 7500, ep3, 2001, MODEL_HASH, sign_escrow(val5.address, 7500, ep3, 2001)))
check("escrow", "active set contracted to 4", escrow.functions.getActiveValidatorCount().call() == 4)
d5 = escrow.functions.getValidatorDetails(val5.address).call()
check("escrow", "ejected validator is inactive and blacklisted", d5[2] is False and d5[3] is True)
check("escrow", "75% of bond burned, 2.5 ETH remaining", d5[0] == Web3.to_wei(2.5, "ether"), f"bonded={d5[0]}")

# ==============================================================================
# SUITE 2: GOVERNANCE AND 4-WAY ABLATION
# ==============================================================================
section("[SUITE 2] Governance, 4-way ablation and negative tests C1-C7")
fund_low(voter_accounts, VOTER_MIN_ETH, VOTER_TOP_ETH)

# C2 on a fresh contract still in Idle: PoP above 10000 bps must be rejected
probe = deploy(Invest, committee_addrs, THRESHOLD_K, MODEL_HASH)
expect_revert("governance", "C2: PoP above 10000 bps rejected",
              probe.functions.registerVoterProfiles([voter_addrs[0]], [1], [10001]))

contract_base = deploy(Invest, committee_addrs, THRESHOLD_K, MODEL_HASH)
for pid in PIDS:
    transact(contract_base.functions.registerProposal(pid))
register_voters(contract_base, voter_addrs, voter_tokens, voter_bps)

epoch_base = w3.eth.block_number
transact(contract_base.functions.initVotingEpoch(epoch_base))

t0 = time.time()
for i, pid in enumerate(voter_choices):
    transact(contract_base.functions.castVote(pid), signer=voter_accounts[i])
print(f"[+] {N_VOTERS} votes cast in {time.time() - t0:.1f}s", flush=True)
check("governance", "1,000 honest votes recorded", contract_base.functions.totalVotesCastCount().call() == N_VOTERS)

expect_revert("governance", "C1: second vote by the same voter (other proposal)",
              contract_base.functions.castVote(PIDS[0] if voter_choices[0] != PIDS[0] else PIDS[1]),
              signer=voter_accounts[0])

transact(contract_base.functions.finalizeVotingTally())
expect_revert("governance", "C5: re-open voting after finalisation",
              contract_base.functions.initVotingEpoch(epoch_base + 1))
expect_revert("governance", "C5: vote after finalisation",
              contract_base.functions.castVote(PIDS[0]), signer=voter_accounts[1])

attest_all(contract_base, epoch_base, nonce_base=101)

# C3: R = 0 must be rejected before any division happens
bad_sigs = sign_digest(ATT_TYPES, [contract_base.address, w3.eth.chain_id, "P-1", epoch_base, 9001, MODEL_HASH, 0])
expect_revert("governance", "C3: R = 0 rejected",
              contract_base.functions.verifyAttestation("P-1", 0, epoch_base, 9001, MODEL_HASH, bad_sigs))

ablation_base, _ = run_ablation(contract_base, [1, 2, 3, 4])
v1, v2, v3, v4 = ablation_base[1], ablation_base[2], ablation_base[3], ablation_base[4]
check("ablation", "variant 4 cap respected for every proposal",
      all(a <= 400_000 * 10 ** 18 for a in v4.values()))
check("ablation", "P-3 receives the cap in variants 3 and 4",
      v3["P-3"] == 400_000 * 10 ** 18 and v4["P-3"] == 400_000 * 10 ** 18)

# C7: tranches are sequential and cumulative-capped
p3_target = prop_state(contract_base, "P-3")["target"]
transact(contract_base.functions.disburseMilestoneTranche("P-3", 1, 2500, 10000))
expected = p3_target * 2500 // 10000
check("tranche", "tranche 1 releases exactly 25% of target",
      prop_state(contract_base, "P-3")["released"] == expected, f"{usd(expected):,.2f} USD")
expect_revert("tranche", "C7: tranche 1 repeated", contract_base.functions.disburseMilestoneTranche("P-3", 1, 2500, 10000))
expect_revert("tranche", "C7: tranches exceed 100% budget",
              contract_base.functions.disburseMilestoneTranche("P-3", 2, 8000, 10000))

base_rows = []
for pid in PIDS:
    st = prop_state(contract_base, pid)
    base_rows.append({
        "Proposal_ID": pid,
        "Raw_Token_Votes": st["raw_tokens"],
        "Raw_PoP_Sum": st["raw_pop"],
        "Composite_Weight_Vp": st["V"],
        "Risk_Score": st["risk"] / 1e18,
        "Target_Allocation_USD": usd(st["target"]),
        "Traditional_Allocation_USD": usd(v1[pid]),
    })
df_base = pd.DataFrame(base_rows)
df_base.to_csv(PROJECT_DIR / "OnChain_Proposal_State_Raw.csv", index=False)
baseline_alloc = dict(zip(df_base["Proposal_ID"], df_base["Target_Allocation_USD"]))
trad_tokens = {pid: prop_state(contract_base, pid)["raw_tokens"] for pid in PIDS}

variants_list = [v1, v2, v3, v4]
p3_usd = [usd(v["P-3"]) for v in variants_list]
p2_usd = [usd(v["P-2"]) for v in variants_list]
table5 = pd.DataFrame({
    "Architecture Variant": ["1. Token-only (traditional dPoS)", "2. Token + PoP (no AI gate)",
                             "3. Token + AI gate (no PoP)", "4. Full AIPoX (PoP + AI gate)"],
    "P-3 Allocation ($)": [f"${x:,.2f}" for x in p3_usd],
    "P-2 Allocation ($)": [f"${x:,.2f}" for x in p2_usd],
    "P-3 Rank": [rank_of({p: v[p] for p in PIDS}, "P-3") for v in variants_list],
    "P-2 Rank": [rank_of({p: v[p] for p in PIDS}, "P-2") for v in variants_list],
    "P-3 Net Gain": ["Baseline (0.0%)"] + [f"{(x - p3_usd[0]) / p3_usd[0] * 100:+.2f}%" for x in p3_usd[1:]],
})
table5.to_csv(PROJECT_DIR / "Table_5_Ablation_Study.csv", index=False)
print(table5.to_string(index=False), flush=True)

# ==============================================================================
# SUITE 3: SYBIL ATTACK ON P-4
# ==============================================================================
section("[SUITE 3] 1,500-identity Sybil attack on P-4")
contract_sybil = deploy(Invest, committee_addrs, THRESHOLD_K, MODEL_HASH)
for pid in PIDS:
    transact(contract_sybil.functions.registerProposal(pid))
register_voters(contract_sybil, voter_addrs, voter_tokens, voter_bps)

sybil_accounts = [Account.create() for _ in range(N_SYBIL)]
fund_low(sybil_accounts, SYBIL_MIN_ETH, SYBIL_TOP_ETH)
register_voters(contract_sybil, [a.address for a in sybil_accounts],
                [SYBIL_TOKENS] * N_SYBIL, [0] * N_SYBIL)
check("sybil", "1,500 Sybil profiles registered", True, f"{SYBIL_TOKENS} tokens, 0 PoP each")

fund_low(voter_accounts, VOTER_MIN_ETH, VOTER_TOP_ETH)      # top up before the second voting phase
epoch_s = w3.eth.block_number
transact(contract_sybil.functions.initVotingEpoch(epoch_s))
for i, pid in enumerate(voter_choices):
    transact(contract_sybil.functions.castVote(pid), signer=voter_accounts[i])
for a in sybil_accounts:
    transact(contract_sybil.functions.castVote("P-4"), signer=a)
transact(contract_sybil.functions.finalizeVotingTally())
attest_all(contract_sybil, epoch_s, nonce_base=201)
_, rec_s = run_ablation(contract_sybil, [4])

sybil_events = contract_sybil.events.TreasuryAllocated().process_receipt(rec_s[4])
check("sybil", "TreasuryAllocated emitted for all proposals", len(sybil_events) == len(PIDS))
s_alloc = {str(e["args"]["proposalId"]): int(e["args"]["allocationAmountUSD"]) for e in sybil_events}
s_tokens = {pid: prop_state(contract_sybil, pid)["raw_tokens"] for pid in PIDS}


def label_trad(pid, rank, target):
    if rank == 1:
        return "1 (Compromised)" if pid == target else "1"
    return str(rank)


def label_aipox(pid, rank, target, preserved):
    if rank == 1 and pid == preserved:
        return "1 (Preserved)"
    if pid == target:
        return f"{rank} (Attack contained)" if rank > 1 else "1 (Not contained)"
    return str(rank)


s_trad_rank = {p: rank_of(s_tokens, p) for p in PIDS}
s_aipox_rank = {p: rank_of(s_alloc, p) for p in PIDS}
table6 = pd.DataFrame({
    "Proposal ID": PIDS,
    "Traditional Rank (Under Attack)": [label_trad(p, s_trad_rank[p], "P-4") for p in PIDS],
    "AIPoX Rank (Under Attack)": [label_aipox(p, s_aipox_rank[p], "P-4", "P-3") for p in PIDS],
    "Post-Attack Allocation (USD)": [usd(s_alloc[p]) for p in PIDS],
}).sort_values("Post-Attack Allocation (USD)", ascending=False).reset_index(drop=True)
table6.to_csv(PROJECT_DIR / "Table_6_Sybil_Attack.csv", index=False)
print(table6.to_string(index=False), flush=True)

p4_base = baseline_alloc["P-4"]
p4_attack = usd(s_alloc["P-4"])
print(f"[*] P-4 allocation change under Sybil attack: {(p4_attack - p4_base) / p4_base * 100:+.2f}%", flush=True)

# ==============================================================================
# SUITE 4: WHALE ATTACK (main P = 0.28 and worst-case P = 0.98)
# ==============================================================================
section("[SUITE 4] 60% whale attack on P-2")


def run_whale(p_bps, t7_name, t8_name, tag):
    contract_w = deploy(Invest, committee_addrs, THRESHOLD_K, MODEL_HASH)
    for pid in PIDS:
        transact(contract_w.functions.registerProposal(pid))
    register_voters(contract_w, voter_addrs, voter_tokens, voter_bps)

    whale = Account.create()
    fund_low([whale], 0.05, 0.05)
    whale_tokens = int(WHALE_TOKEN_MULTIPLE * honest_total)
    register_voters(contract_w, [whale.address], [whale_tokens], [p_bps])
    share = whale_tokens / (whale_tokens + honest_total)
    check("whale", f"[{tag}] whale holds 60% of tokens", abs(share - 0.6) < 1e-9, f"share={share:.6f}")

    fund_low(voter_accounts, VOTER_MIN_ETH, VOTER_TOP_ETH)  # top up before each voting phase
    epoch_w = w3.eth.block_number
    transact(contract_w.functions.initVotingEpoch(epoch_w))
    for i, pid in enumerate(voter_choices):
        transact(contract_w.functions.castVote(pid), signer=voter_accounts[i])
    transact(contract_w.functions.castVote("P-2"), signer=whale)
    transact(contract_w.functions.finalizeVotingTally())
    attest_all(contract_w, epoch_w, nonce_base=301)
    _, rec_w = run_ablation(contract_w, [4])

    events = contract_w.events.TreasuryAllocated().process_receipt(rec_w[4])
    check("whale", f"[{tag}] TreasuryAllocated emitted for all proposals", len(events) == len(PIDS))
    w_alloc = {str(e["args"]["proposalId"]): int(e["args"]["allocationAmountUSD"]) for e in events}
    w_tokens = {pid: prop_state(contract_w, pid)["raw_tokens"] for pid in PIDS}
    w_trad_rank = {p: rank_of(w_tokens, p) for p in PIDS}
    w_aipox_rank = {p: rank_of(w_alloc, p) for p in PIDS}

    t7 = pd.DataFrame({
        "Proposal ID": PIDS,
        "Traditional Rank (Under Attack)": [label_trad(p, w_trad_rank[p], "P-2") for p in PIDS],
        "AIPoX Rank (Under Attack)": [label_aipox(p, w_aipox_rank[p], "P-2", "P-3") for p in PIDS],
    })
    t7.to_csv(PROJECT_DIR / t7_name, index=False)

    t8 = pd.DataFrame({
        "Proposal ID": PIDS,
        "Baseline AIPoX Allocation": [baseline_alloc[p] for p in PIDS],
        "AIPoX Allocation (Post-Attack)": [usd(w_alloc[p]) for p in PIDS],
    })
    t8["Net Distortion"] = [f"{(a - b) / b * 100:+.2f}%" for a, b in
                            zip(t8["AIPoX Allocation (Post-Attack)"], t8["Baseline AIPoX Allocation"])]
    t8.to_csv(PROJECT_DIR / t8_name, index=False)
    print(t8.to_string(index=False), flush=True)
    return t8


whale_main = run_whale(WHALE_P_MAIN_BPS, "Table_7_Whale_Prioritization.csv",
                       "Table_8_Whale_Treasury_Distortion.csv", "P=0.28")
run_whale(WHALE_P_WORST_BPS, "Table_7b_Whale_Worst_Case_Prioritization.csv",
          "Table_8b_Whale_Worst_Case.csv", "P=0.98")

# ==============================================================================
# OUTPUT
# ==============================================================================
pd.DataFrame(RESULTS, columns=["Suite", "Test", "Outcome", "Detail"]).to_csv(
    PROJECT_DIR / "OnChain_Test_Log.csv", index=False)

section("[DONE] All checks passed")
n_pass = sum(1 for r in RESULTS if r[2] in ("PASS", "REJECTED"))
print(f"{n_pass} of {len(RESULTS)} recorded checks passed. Log: OnChain_Test_Log.csv", flush=True)
