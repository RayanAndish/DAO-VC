"""
1_deploy_and_run_onchain.py  (revision 2)
=========================================
On-chain verification suite for AIPoX on a local Ganache node.

Configuration
  GANACHE_MNEMONIC  required, BIP-39 mnemonic (no quotes; see the set command in the README)
  GANACHE_RPC       optional, default http://172.16.22.120:8545

Ganache start (deployer needs about 110 ETH):
  ganache --wallet.defaultBalance 1000 --chain.networkId 1337 --host 172.16.22.120 --port 8545

Suites
  1  PoA validator escrow: bonding, unbonding, k-of-M attested slashing, ejection, boundary tests.
  2  Governance: four-way ablation over 1,000 honest voters, negative tests C1-C7.
  3  Sybil: 1,500 identities, 1,000 tokens and 0 PoP each, all vote for the highest-R proposal.
  4  Whale: one identity with 60% of tokens, P = 0.28 (main) and P = 0.98 (worst case).

Outputs (project root)
  OnChain_Test_Log.csv, OnChain_Proposal_State_Raw.csv, Table_5_Ablation_Study.csv,
  Table_6_Sybil_onchain.csv, Sybil_Composition.csv,
  Table_7_Whale_onchain_P028.csv, Table_8_Whale_onchain_P028.csv,
  Table_7_Whale_onchain_P098.csv, Table_8b_Whale_onchain_P098.csv

Revision notes (rev 2)
- setMinVoteStake(0) is applied to every contract and read back before any vote.
  Without it, the default minVoteStake = 1000 rejects honest voters with fewer tokens.
- expect_revert() checks the revert reason where the reason is known.
- Baseline allocations are compared with the final expected values before the attacks.
- Sybil composition (raw tokens, PoP, composite weight, totalActiveTokens) is logged before
  and after the attack, so the paper can separate the direct and indirect contributions.
- Attack labels are plain ranks; no "contained" or "preserved" wording is written.
- The test log is written by atexit, so it is saved even when a check fails.
- Table 7b is removed; the worst case is written to its own Table 7/8 pair.
"""

import atexit
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
from web3.logs import DISCARD

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "Data"
LOG_PATH = PROJECT_DIR / "OnChain_Test_Log.csv"

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
MIN_VOTE_STAKE = 0                  # every honest voter may lock stake

EXPECTED_HONEST_TOKENS = 11_160_518
EXPECTED_HONEST_POP_BPS = 5_293_376
EXPECTED_BASELINE = {"P-1": 359604.95, "P-2": 250084.95, "P-3": 183625.88,
                     "P-4": 124268.00, "P-5": 82416.21}
ALLOC_TOL_USD = 0.05
ALPHA_BPS = 4000

VOTER_MIN_ETH, VOTER_TOP_ETH = 0.005, 0.01
SYBIL_MIN_ETH, SYBIL_TOP_ETH = 0.008, 0.01
WHALE_FUND_ETH = 0.1
ESCROW_BOND_ETH = 10
ESCROW_FUND_ETH = 11

GANACHE_URL = os.getenv("GANACHE_RPC", "http://172.16.22.120:8545")


def clean_mnemonic(raw):
    """Remove surrounding quotes and stray whitespace that cmd/PowerShell can leave in env vars."""
    if not raw:
        return None
    text = raw.strip().strip('"').strip("'")
    return " ".join(text.split()).lower()


MNEMONIC = clean_mnemonic(os.getenv("GANACHE_MNEMONIC"))
if not MNEMONIC or len(MNEMONIC.split()) not in (12, 15, 18, 21, 24):
    sys.exit("[ERROR] GANACHE_MNEMONIC is missing or not a valid 12/15/18/21/24-word mnemonic. "
             "Set it without quotes: set \"GANACHE_MNEMONIC=word1 word2 ... word12\"")

Account.enable_unaudited_hdwallet_features()
np.random.seed(SEED)

w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
if not w3.is_connected():
    sys.exit(f"[ERROR] Cannot reach Ganache at {GANACHE_URL}")

deployer = Account.from_mnemonic(MNEMONIC, account_path="m/44'/60'/0'/0/0")
RESULTS = []   # (suite, test, outcome, detail)


def _write_log():
    if RESULTS:
        pd.DataFrame(RESULTS, columns=["Suite", "Test", "Outcome", "Detail"]).to_csv(LOG_PATH, index=False)
        print(f"[log] {len(RESULTS)} rows written to {LOG_PATH}", flush=True)


atexit.register(_write_log)


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


def expect_revert(suite, name, fn, signer=None, value=0, must_contain=None):
    """Pass only if the call reverts. If must_contain is given, the revert reason must contain it."""
    signer = signer or deployer
    try:
        fn.build_transaction({"from": signer.address, "value": value})
    except Exception as exc:
        msg = str(exc)
        if must_contain and must_contain not in msg:
            RESULTS.append((suite, name, "FAIL", f"reason mismatch: {msg[:160]}"))
            raise AssertionError(f"[FAIL] {suite}: {name}: expected '{must_contain}', got: {msg[:200]}")
        reason = msg.splitlines()[0][:160]
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


def deploy_invest(label):
    """Deploy InvestmentSmartContract, set minVoteStake, and read the value back before use."""
    c = deploy(Invest, committee_addrs, THRESHOLD_K, MODEL_HASH)
    transact(c.functions.setMinVoteStake(MIN_VOTE_STAKE))
    applied = c.functions.minVoteStake().call()
    check("setup", f"{label}: minVoteStake read back", applied == MIN_VOTE_STAKE, f"on-chain={applied}")
    return c


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
    if receipt.status != 1:
        raise RuntimeError(f"funding transfer to {to} failed")


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
# Inputs: model hash, threshold, proposals, committee
# ------------------------------------------------------------------------------
hash_file = DATA_DIR / "models" / "model_hash.json"
if not hash_file.exists():
    sys.exit("[ERROR] Data/models/model_hash.json missing. Run the training script first.")
MODEL_HASH = bytes.fromhex(json.loads(hash_file.read_text(encoding="utf-8"))["model_hash"][2:])
check("setup", "ModelHash is 32 bytes", len(MODEL_HASH) == 32)

THRESHOLD_BPS = int(json.loads((DATA_DIR / "models" / "threshold.json")
                               .read_text(encoding="utf-8"))["threshold_bps"])
check("setup", "threshold file loaded", THRESHOLD_BPS > 0, f"{THRESHOLD_BPS} bps")

prop_file = DATA_DIR / "Table_Proposals_Feature_Profiles.csv"
if not prop_file.exists():
    sys.exit("[ERROR] Data/Table_Proposals_Feature_Profiles.csv missing. Run the proposal scoring script first.")
df_prop = pd.read_csv(prop_file)
PIDS = list(df_prop["Proposal_ID"].values)
RISK = dict(zip(df_prop["Proposal_ID"], df_prop["AI_Risk_Score_R_p"]))
SAFE = min(PIDS, key=lambda p: RISK[p])     # lowest R(p)
RISKY = max(PIDS, key=lambda p: RISK[p])    # highest R(p)
check("setup", "proposal roles from data", SAFE != RISKY, f"SAFE={SAFE} RISKY={RISKY}")


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
        evs = contract.events.AblationExecuted().process_receipt(rec, errors=DISCARD)
        out[v] = {str(e["args"]["proposalId"]): int(e["args"]["allocationUSD"]) for e in evs}
        receipts[v] = rec
        check("ablation", f"variant {v} emitted {len(PIDS)} allocations", len(out[v]) == len(PIDS))
        total = sum(out[v].values())
        check("ablation", f"variant {v} sums to the pool", abs(usd(total) - 1_000_000) < 0.05,
              f"sum {usd(total):,.2f} USD")
    return out, receipts


# ------------------------------------------------------------------------------
# Population: same generation order as the original script (same tokens and P)
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

voter_accounts = [Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/0'/0/{i + 10}")
                  for i in range(N_VOTERS)]
voter_addrs = [a.address for a in voter_accounts]
honest_total = int(voter_tokens.sum())
honest_pop_total = int(sum(voter_bps))

check("setup", "honest token total matches the final run", honest_total == EXPECTED_HONEST_TOKENS,
      f"{honest_total:,}")
check("setup", "honest PoP total matches the final run", honest_pop_total == EXPECTED_HONEST_POP_BPS,
      f"{honest_pop_total:,}")

# Budget check before any transaction
needed_eth = (5 * ESCROW_FUND_ETH + N_VOTERS * VOTER_TOP_ETH * 3
              + N_SYBIL * SYBIL_TOP_ETH + 3 * WHALE_FUND_ETH + 5)
bal_eth = float(w3.from_wei(w3.eth.get_balance(deployer.address), "ether"))
print(f"[*] Deployer balance {bal_eth:.2f} ETH, estimated requirement {needed_eth:.2f} ETH", flush=True)
check("setup", "deployer balance sufficient", bal_eth > needed_eth, f"({bal_eth:.2f} > {needed_eth:.2f})")

# ==============================================================================
# SUITE 1: POA VALIDATOR ESCROW
# ==============================================================================
section("[SUITE 1] PoA validator escrow")
escrow = deploy(Escrow, committee_addrs, THRESHOLD_K, MODEL_HASH)
ejection_onchain = escrow.functions.EJECTION_BPS().call()
check("setup", "escrow EJECTION_BPS equals threshold.json", ejection_onchain == THRESHOLD_BPS,
      f"contract={ejection_onchain} file={THRESHOLD_BPS}")

candidates = [Account.create() for _ in range(5)]
fund_low(candidates, ESCROW_BOND_ETH + 0.5, ESCROW_FUND_ETH)
for v in candidates:
    transact(escrow.functions.depositCollateral(), signer=v, value=Web3.to_wei(ESCROW_BOND_ETH, "ether"))
check("escrow", "5 validators bonded", escrow.functions.getActiveValidatorCount().call() == 5)

val1, val2, val5 = candidates[0], candidates[1], candidates[4]

transact(escrow.functions.requestUnbond(Web3.to_wei(2, "ether")), signer=val1)
expect_revert("escrow", "second unbond while one is pending",
              escrow.functions.requestUnbond(Web3.to_wei(1, "ether")), signer=val1)
expect_revert("escrow", "withdraw before unbonding delay", escrow.functions.withdrawStake(), signer=val1)
mine_blocks(UNBOND_DELAY_BLOCKS + 1)
transact(escrow.functions.withdrawStake(), signer=val1)
d1 = escrow.functions.getValidatorDetails(val1.address).call()
check("escrow", "withdrawal leaves 8 ETH bonded", d1[0] == Web3.to_wei(8, "ether"), f"bonded={d1[0]}")


def sign_escrow(validator, anomaly, epoch, nonce, signers=ATTEST_SIGNERS):
    return sign_digest(ESC_TYPES, [escrow.address, w3.eth.chain_id, validator, anomaly, epoch, nonce, MODEL_HASH],
                       signers)


# Partial slash (anomaly 0.10): stake reduces by 10%, validator stays active
ep = w3.eth.block_number
transact(escrow.functions.slashValidatorWithAttestation(
    val2.address, 1000, ep, 1001, MODEL_HASH, sign_escrow(val2.address, 1000, ep, 1001)))
d2 = escrow.functions.getValidatorDetails(val2.address).call()
check("escrow", "partial slash (0.10) keeps validator active",
      d2[2] is True and d2[0] == Web3.to_wei(9, "ether"), f"bonded={d2[0]}")

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

# Zero anomaly is rejected
expect_revert("escrow", "zero anomaly rejected",
              escrow.functions.slashValidatorWithAttestation(
                  val2.address, 0, ep2, 1003, MODEL_HASH, sign_escrow(val2.address, 0, ep2, 1003)),
              must_contain="Invalid anomaly bounds")

# Ejecting slash (anomaly 0.75 >= tau) for val5: 75% burned, 2.5 ETH remains
ep3 = w3.eth.block_number
transact(escrow.functions.slashValidatorWithAttestation(
    val5.address, 7500, ep3, 2001, MODEL_HASH, sign_escrow(val5.address, 7500, ep3, 2001)))
d5 = escrow.functions.getValidatorDetails(val5.address).call()
check("escrow", "ejected validator is inactive and blacklisted", d5[2] is False and d5[3] is True)
check("escrow", "75% of bond burned, 2.5 ETH remaining", d5[0] == Web3.to_wei(2.5, "ether"), f"bonded={d5[0]}")

# Threshold boundary: one bps below tau must not eject; exactly tau must eject
val6, val7 = candidates[2], candidates[3]
ep4 = w3.eth.block_number
transact(escrow.functions.slashValidatorWithAttestation(
    val6.address, THRESHOLD_BPS - 1, ep4, 3001, MODEL_HASH,
    sign_escrow(val6.address, THRESHOLD_BPS - 1, ep4, 3001)))
d6 = escrow.functions.getValidatorDetails(val6.address).call()
check("escrow", f"anomaly {THRESHOLD_BPS - 1} bps (one below tau) does not eject",
      d6[2] is True and d6[3] is False)

ep5 = w3.eth.block_number
transact(escrow.functions.slashValidatorWithAttestation(
    val7.address, THRESHOLD_BPS, ep5, 3002, MODEL_HASH,
    sign_escrow(val7.address, THRESHOLD_BPS, ep5, 3002)))
d7 = escrow.functions.getValidatorDetails(val7.address).call()
check("escrow", f"anomaly {THRESHOLD_BPS} bps (equal to tau) ejects", d7[2] is False and d7[3] is True)

# ==============================================================================
# SUITE 2: GOVERNANCE AND 4-WAY ABLATION
# ==============================================================================
section("[SUITE 2] Governance, 4-way ablation and negative tests C1-C7")
fund_low(voter_accounts, VOTER_MIN_ETH, VOTER_TOP_ETH)

# C2: PoP above 10000 bps is rejected
probe = deploy_invest("probe")
expect_revert("governance", "C2: PoP above 10000 bps rejected",
              probe.functions.registerVoterProfiles([voter_addrs[0]], [1], [10001]))

contract_base = deploy_invest("base")
for pid in PIDS:
    transact(contract_base.functions.registerProposal(pid))
register_voters(contract_base, voter_addrs, voter_tokens, voter_bps)

epoch_base = w3.eth.block_number
transact(contract_base.functions.initVotingEpoch(epoch_base))

t0 = time.time()
for i, pid in enumerate(voter_choices):
    transact(contract_base.functions.castVote(pid), signer=voter_accounts[i])
print(f"[+] {N_VOTERS} votes cast in {time.time() - t0:.1f}s", flush=True)
check("governance", "1,000 honest votes recorded",
      contract_base.functions.totalVotesCastCount().call() == N_VOTERS)

# C1: second vote by the same voter
second_pid = PIDS[0] if voter_choices[0] != PIDS[0] else PIDS[1]
expect_revert("governance", "C1: second vote by the same voter",
              contract_base.functions.castVote(second_pid), signer=voter_accounts[0],
              must_contain="One vote per voter per epoch")

transact(contract_base.functions.finalizeVotingTally())
expect_revert("governance", "C5: re-open voting after finalisation",
              contract_base.functions.initVotingEpoch(epoch_base + 1))
expect_revert("governance", "C5: vote after finalisation",
              contract_base.functions.castVote(PIDS[0]), signer=voter_accounts[1])

attest_all(contract_base, epoch_base, nonce_base=101)

# C3: R = 0 is rejected
bad_sigs = sign_digest(ATT_TYPES, [contract_base.address, w3.eth.chain_id, "P-1", epoch_base, 9001,
                                   MODEL_HASH, 0])
expect_revert("governance", "C3: R = 0 rejected",
              contract_base.functions.verifyAttestation("P-1", 0, epoch_base, 9001, MODEL_HASH, bad_sigs),
              must_contain="Risk out of bounds")

ablation_base, _ = run_ablation(contract_base, [1, 2, 3, 4])
v1, v2, v3, v4 = ablation_base[1], ablation_base[2], ablation_base[3], ablation_base[4]
check("ablation", "variant 4 does not exceed the 40% cap (cap non-binding in this run)",
      all(a <= 400_000 * 10 ** 18 for a in v4.values()))
check("ablation", f"lowest-R proposal {SAFE} gets the largest allocation in variants 3 and 4",
      v3[SAFE] == max(v3.values()) and v4[SAFE] == max(v4.values()))

# C7: tranches are sequential and cumulative-capped
target_safe = prop_state(contract_base, SAFE)["target"]
transact(contract_base.functions.disburseMilestoneTranche(SAFE, 1, 2500, 10000))
expected_release = target_safe * 2500 // 10000
check("tranche", "tranche 1 releases exactly 25% of target",
      prop_state(contract_base, SAFE)["released"] == expected_release,
      f"{usd(expected_release):,.2f} USD")
expect_revert("tranche", "C7: tranche 1 repeated",
              contract_base.functions.disburseMilestoneTranche(SAFE, 1, 2500, 10000),
              must_contain="Tranche out of sequence")
expect_revert("tranche", "C7: tranches exceed 100% budget",
              contract_base.functions.disburseMilestoneTranche(SAFE, 2, 8000, 10000),
              must_contain="Tranches exceed budget")

# Baseline table and its check against the final expected values
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
for pid, expected in EXPECTED_BASELINE.items():
    check("baseline", f"{pid} baseline matches the final run",
          abs(baseline_alloc[pid] - expected) < ALLOC_TOL_USD,
          f"on-chain={baseline_alloc[pid]:,.2f} expected={expected:,.2f}")

variants_list = [v1, v2, v3, v4]
p_safe_usd = [usd(v[SAFE]) for v in variants_list]
p_risky_usd = [usd(v[RISKY]) for v in variants_list]
table5 = pd.DataFrame({
    "Architecture Variant": ["1. Token-only (traditional dPoS)", "2. Token + PoP (no AI gate)",
                             "3. Token + AI gate (no PoP)", "4. Full AIPoX (PoP + AI gate)"],
    "Lowest-R Allocation ($)": [f"${x:,.2f}" for x in p_safe_usd],
    "Highest-R Allocation ($)": [f"${x:,.2f}" for x in p_risky_usd],
    "Lowest-R Rank": [rank_of({p: v[p] for p in PIDS}, SAFE) for v in variants_list],
    "Highest-R Rank": [rank_of({p: v[p] for p in PIDS}, RISKY) for v in variants_list],
    "Lowest-R Net Gain": ["Baseline (0.00%)"] + [f"{(x - p_safe_usd[0]) / p_safe_usd[0] * 100:+.2f}%"
                                                 for x in p_safe_usd[1:]],
})
table5.to_csv(PROJECT_DIR / "Table_5_Ablation_Study.csv", index=False)
print(table5.to_string(index=False), flush=True)

# ==============================================================================
# SUITE 3: SYBIL ATTACK ON THE HIGHEST-R PROPOSAL
# ==============================================================================
section(f"[SUITE 3] 1,500-identity Sybil attack on {RISKY} (highest R)")
contract_sybil = deploy_invest("sybil")
for pid in PIDS:
    transact(contract_sybil.functions.registerProposal(pid))
register_voters(contract_sybil, voter_addrs, voter_tokens, voter_bps)

sybil_accounts = [Account.create() for _ in range(N_SYBIL)]
fund_low(sybil_accounts, SYBIL_MIN_ETH, SYBIL_TOP_ETH)
register_voters(contract_sybil, [a.address for a in sybil_accounts],
                [SYBIL_TOKENS] * N_SYBIL, [0] * N_SYBIL)

sybil_total = N_SYBIL * SYBIL_TOKENS
check("sybil", "Sybil tokens equal 13.4% of honest supply", abs(sybil_total / honest_total - 0.134) < 0.001,
      f"{sybil_total:,} tokens, {sybil_total / honest_total:.4%} of honest supply")

fund_low(voter_accounts, VOTER_MIN_ETH, VOTER_TOP_ETH)
epoch_s = w3.eth.block_number
transact(contract_sybil.functions.initVotingEpoch(epoch_s))
for i, pid in enumerate(voter_choices):
    transact(contract_sybil.functions.castVote(pid), signer=voter_accounts[i])
for a in sybil_accounts:
    transact(contract_sybil.functions.castVote(RISKY), signer=a)
transact(contract_sybil.functions.finalizeVotingTally())
attest_all(contract_sybil, epoch_s, nonce_base=201)
_, rec_s = run_ablation(contract_sybil, [4])

sybil_events = contract_sybil.events.TreasuryAllocated().process_receipt(rec_s[4], errors=DISCARD)
check("sybil", "TreasuryAllocated emitted for all proposals", len(sybil_events) == len(PIDS))
s_alloc = {str(e["args"]["proposalId"]): int(e["args"]["allocationAmountUSD"]) for e in sybil_events}
s_tokens = {pid: prop_state(contract_sybil, pid)["raw_tokens"] for pid in PIDS}

# Composition of the attacked proposal: direct and indirect contributions to V(p)
before = prop_state(contract_base, RISKY)
after = prop_state(contract_sybil, RISKY)
tot_before = contract_base.functions.totalActiveTokens().call()
tot_after = contract_sybil.functions.totalActiveTokens().call()
direct_term = ALPHA_BPS * sybil_total // 10000
indirect_term = int(after["V"]) - int(before["V"]) - direct_term
comp = pd.DataFrame([
    ["Raw token votes", before["raw_tokens"], after["raw_tokens"]],
    ["Raw PoP sum (bps)", before["raw_pop"], after["raw_pop"]],
    ["totalActiveTokens", tot_before, tot_after],
    ["Composite V(p)", before["V"], after["V"]],
    ["Direct token term (alpha x Sybil tokens)", "", direct_term],
    ["Indirect term via totalActiveTokens", "", indirect_term],
    ["Relative increase of V(p) (%)", "", f"{(int(after['V']) / int(before['V']) - 1) * 100:.2f}"],
], columns=["Quantity", "Before attack", "After attack"])
comp.to_csv(PROJECT_DIR / "Sybil_Composition.csv", index=False)
print(comp.to_string(index=False), flush=True)

s_trad_rank = {p: rank_of(s_tokens, p) for p in PIDS}
s_aipox_rank = {p: rank_of(s_alloc, p) for p in PIDS}
table6 = pd.DataFrame({
    "Proposal ID": PIDS,
    "Baseline AIPoX Allocation (USD)": [baseline_alloc[p] for p in PIDS],
    "Traditional Rank (Under Attack)": [s_trad_rank[p] for p in PIDS],
    "AIPoX Rank (Under Attack)": [s_aipox_rank[p] for p in PIDS],
    "Post-Attack AIPoX Allocation (USD)": [usd(s_alloc[p]) for p in PIDS],
})
table6["Change (%)"] = [f"{(a - b) / b * 100:+.2f}%" for a, b in
                        zip(table6["Post-Attack AIPoX Allocation (USD)"],
                            table6["Baseline AIPoX Allocation (USD)"])]
table6.to_csv(PROJECT_DIR / "Table_6_Sybil_onchain.csv", index=False)
print(table6.to_string(index=False), flush=True)


# ==============================================================================
# SUITE 4: WHALE ATTACK (main P = 0.28 and worst-case P = 0.98)
# ==============================================================================
section(f"[SUITE 4] 60% whale attack on {RISKY} (highest R)")


def run_whale(p_bps, tag, rank_name, alloc_name):
    contract_w = deploy_invest(f"whale {tag}")
    for pid in PIDS:
        transact(contract_w.functions.registerProposal(pid))
    register_voters(contract_w, voter_addrs, voter_tokens, voter_bps)

    whale = Account.create()
    fund_low([whale], WHALE_FUND_ETH, WHALE_FUND_ETH)
    whale_tokens = int(WHALE_TOKEN_MULTIPLE * honest_total)
    register_voters(contract_w, [whale.address], [whale_tokens], [p_bps])
    share = whale_tokens / (whale_tokens + honest_total)
    check("whale", f"[{tag}] whale holds 60% of tokens", abs(share - 0.6) < 1e-9, f"share={share:.6f}")
    pop_share = p_bps / (honest_pop_total + p_bps)
    check("whale", f"[{tag}] whale PoP share computed", pop_share > 0, f"{pop_share:.4%}")

    fund_low(voter_accounts, VOTER_MIN_ETH, VOTER_TOP_ETH)
    epoch_w = w3.eth.block_number
    transact(contract_w.functions.initVotingEpoch(epoch_w))
    for i, pid in enumerate(voter_choices):
        transact(contract_w.functions.castVote(pid), signer=voter_accounts[i])
    transact(contract_w.functions.castVote(RISKY), signer=whale)
    transact(contract_w.functions.finalizeVotingTally())
    attest_all(contract_w, epoch_w, nonce_base=301)
    _, rec_w = run_ablation(contract_w, [4])

    events = contract_w.events.TreasuryAllocated().process_receipt(rec_w[4], errors=DISCARD)
    check("whale", f"[{tag}] TreasuryAllocated emitted for all proposals", len(events) == len(PIDS))
    w_alloc = {str(e["args"]["proposalId"]): int(e["args"]["allocationAmountUSD"]) for e in events}
    w_tokens = {pid: prop_state(contract_w, pid)["raw_tokens"] for pid in PIDS}

    ranks = pd.DataFrame({
        "Proposal ID": PIDS,
        "Traditional Rank (Under Attack)": [rank_of(w_tokens, p) for p in PIDS],
        "AIPoX Rank (Under Attack)": [rank_of(w_alloc, p) for p in PIDS],
    })
    ranks.to_csv(PROJECT_DIR / rank_name, index=False)

    alloc = pd.DataFrame({
        "Proposal ID": PIDS,
        "Baseline AIPoX Allocation (USD)": [baseline_alloc[p] for p in PIDS],
        "AIPoX Allocation Under Attack (USD)": [usd(w_alloc[p]) for p in PIDS],
    })
    alloc["Net Distortion"] = [f"{(a - b) / b * 100:+.2f}%" for a, b in
                               zip(alloc["AIPoX Allocation Under Attack (USD)"],
                                   alloc["Baseline AIPoX Allocation (USD)"])]
    alloc.to_csv(PROJECT_DIR / alloc_name, index=False)
    print(f"[{tag}] whale PoP share {pop_share:.4%}", flush=True)
    print(alloc.to_string(index=False), flush=True)
    return alloc


run_whale(WHALE_P_MAIN_BPS, "P=0.28", "Table_7_Whale_onchain_P028.csv", "Table_8_Whale_onchain_P028.csv")
run_whale(WHALE_P_WORST_BPS, "P=0.98", "Table_7_Whale_onchain_P098.csv", "Table_8b_Whale_onchain_P098.csv")

# ==============================================================================
# DONE
# ==============================================================================
section("[DONE] All checks passed")
n_pass = sum(1 for r in RESULTS if r[2] in ("PASS", "REJECTED"))
print(f"{n_pass} of {len(RESULTS)} recorded checks passed. Log: {LOG_PATH}", flush=True)
