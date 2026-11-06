"""
2_generate_verified_tables.py
=============================
Formats Table 3 and Table 4 from the on-chain state exported by 1_deploy_and_run_onchain.py.

Scope: this script formats values read from the chain. Ranks and percentage deltas are
derived from those values here; no allocation is recomputed.
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
RAW = PROJECT_DIR / "OnChain_Proposal_State_Raw.csv"
TREASURY = 1_000_000.0

if not RAW.exists():
    sys.exit("[-] ERROR: OnChain_Proposal_State_Raw.csv missing. Run 1_deploy_and_run_onchain.py first.")

df_raw = pd.read_csv(RAW)

# Table 3: comparative prioritisation
df_raw["Trad_Rank"] = df_raw["Raw_Token_Votes"].rank(ascending=False, method="min").astype(int)
df_raw["PoP_Rank"] = df_raw["Composite_Weight_Vp"].rank(ascending=False, method="min").astype(int)
df_raw["AIPoX_Rank"] = df_raw["Target_Allocation_USD"].rank(ascending=False, method="min").astype(int)

df_t3 = df_raw[["Proposal_ID", "Raw_Token_Votes", "Composite_Weight_Vp", "Risk_Score",
                "Trad_Rank", "PoP_Rank", "AIPoX_Rank"]].copy()
df_t3["Raw_Token_Votes"] = df_t3["Raw_Token_Votes"].astype("int64")
df_t3["Composite_Weight_Vp"] = df_t3["Composite_Weight_Vp"].astype("int64")
df_t3.columns = ["Proposal ID", "Raw Token Votes (dPoS)", "PoP-Adjusted Score V(p)",
                 "AI Risk Score R(p)", "Traditional Rank", "PoP Rank", "Final AIPoX Rank"]
df_t3 = df_t3.sort_values("Final AIPoX Rank").reset_index(drop=True)
df_t3.to_csv(PROJECT_DIR / "Table_3_Comparative_Prioritization.csv", index=False)
print("[+] Table_3_Comparative_Prioritization.csv written", flush=True)

# Table 4: treasury allocation
alloc_total = df_raw["Target_Allocation_USD"].sum()
if abs(alloc_total - TREASURY) > 1.0:
    print(f"[!] WARNING: allocations sum to {alloc_total:,.2f}, not {TREASURY:,.0f}", flush=True)

df_t4 = pd.DataFrame({
    "Proposal ID": df_raw["Proposal_ID"],
    "Traditional Allocation (USD)": df_raw["Traditional_Allocation_USD"].round(2),
    "AIPoX Allocation (USD)": df_raw["Target_Allocation_USD"].round(2),
})
delta = (df_t4["AIPoX Allocation (USD)"] - df_t4["Traditional Allocation (USD)"]) / df_t4["Traditional Allocation (USD)"] * 100
df_t4["Net Allocation Delta"] = delta.round(2).map(lambda x: f"{x:+.2f}%")
df_t4 = df_t4.sort_values("AIPoX Allocation (USD)", ascending=False).reset_index(drop=True)
df_t4.to_csv(PROJECT_DIR / "Table_4_Treasury_Allocation.csv", index=False)
print("[+] Table_4_Treasury_Allocation.csv written", flush=True)
