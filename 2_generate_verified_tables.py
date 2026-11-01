"""
2_generate_verified_tables.py
=============================
Formats and exports Table 3 and Table 4 directly from On-Chain state.
Zero offline calculations.
"""

import pandas as pd

print("=" * 80, flush=True)
print("[STAGE 3] FORMATTING VERIFIED PUBLICATION TABLES FROM ON-CHAIN STATE", flush=True)
print("=" * 80, flush=True)

df_raw = pd.read_csv("OnChain_Proposal_State_Raw.csv")
total_tokens = float(df_raw["Raw_Token_Votes"].sum())

df_raw["Trad_Rank"] = df_raw["Raw_Token_Votes"].rank(ascending=False).astype(int)
df_raw["PoP_Rank"] = df_raw["Composite_Weight_Vp"].rank(ascending=False).astype(int)
df_raw["AIPoX_Rank"] = df_raw["Target_Allocation_USD"].rank(ascending=False).astype(int)

# Table 3: Comparative Prioritization
df_table3 = df_raw[[
    "Proposal_ID", "Raw_Token_Votes", "Composite_Weight_Vp", "Risk_Score",
    "Trad_Rank", "PoP_Rank", "AIPoX_Rank"
]].copy()
df_table3["Raw_Token_Votes"] = df_table3["Raw_Token_Votes"].astype(int)
df_table3["Composite_Weight_Vp"] = df_table3["Composite_Weight_Vp"].astype(int)
df_table3.columns = [
    "Proposal ID", "Raw Token Votes (dPoS)", "PoP-Adjusted Score V(p)",
    "AI Risk Score R(p)", "Traditional Rank", "PoP Rank", "Final AIPoX Rank"
]
df_table3 = df_table3.sort_values(by="Final AIPoX Rank").reset_index(drop=True)
df_table3.to_csv("Table_3_Comparative_Prioritization.csv", index=False)
print("[+] Table_3_Comparative_Prioritization.csv formatted.", flush=True)

# Table 4: Treasury Capital Allocation
df_table4 = pd.DataFrame({
    "Proposal ID": df_raw["Proposal_ID"],
    "Traditional Allocation (USD)": df_raw["Traditional_Allocation_USD"].round(2),
    "AIPoX Allocation (USD)": df_raw["Target_Allocation_USD"].round(2)
})
df_table4["Net Allocation Delta"] = (((df_table4["AIPoX Allocation (USD)"] - df_table4["Traditional Allocation (USD)"]) / df_table4["Traditional Allocation (USD)"]) * 100).round(2).astype(str) + "%"
df_table4 = df_table4.sort_values(by="AIPoX Allocation (USD)", ascending=False).reset_index(drop=True)
df_table4.to_csv("Table_4_Treasury_Allocation.csv", index=False)
print("[+] Table_4_Treasury_Allocation.csv formatted.", flush=True)
print("=" * 80, flush=True)