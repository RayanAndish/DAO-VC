"""
03_plot_publication_figures.py
==============================
Builds the publication figures from the verified tables written by the pipeline.
No proposal ID is hard-coded: SAFE is the proposal with the lowest R(p) and RISKY
the proposal with the highest R(p), both read from Table_Proposals_Feature_Profiles.csv.

Inputs (working directory = project root)
  Table_4_Treasury_Allocation.csv        (02_generate_verified_tables.py)
  Table_5_Ablation_Study.csv             (01_deploy_and_run_onchain.py)
  Data/Table_Proposals_Feature_Profiles.csv   (Data/06_score_proposals.py)
  Table_7c_Whale_Fragmentation_Sweep.csv (01b_whale_fragmentation_sweep.py), optional

Outputs
  Figure_4_Treasury_Reallocation.png
  Figure_5_Ablation_Decomposition.png
  Figure_6_Whale_Fragmentation.png       (only if Table_7c exists)

Figure 6 replaces the earlier scalability figure. Scalability was not measured
in this study, so no scalability figure is produced.
"""

import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

CAP_USD = 400_000.0


def first_existing(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    sys.exit(f"[-] None of these files exist: {paths}")


def to_usd(v):
    return float(str(v).replace("$", "").replace(",", ""))


def to_pct(v):
    return float(str(v).replace("%", "").replace("+", ""))


# ------------------------------------------------------------------------------
# Roles from the risk scores
# ------------------------------------------------------------------------------
df_props = pd.read_csv(first_existing("Data/Table_Proposals_Feature_Profiles.csv",
                                      "Table_Proposals_Feature_Profiles.csv"))
RISK = dict(zip(df_props["Proposal_ID"], df_props["AI_Risk_Score_R_p"]))
SAFE = min(RISK, key=RISK.get)
RISKY = max(RISK, key=RISK.get)
print(f"[+] SAFE (lowest R) = {SAFE} ({RISK[SAFE]:.2f}) | RISKY (highest R) = {RISKY} ({RISK[RISKY]:.2f})", flush=True)

# ------------------------------------------------------------------------------
# FIGURE 4: treasury allocation, dPoS vs AIPoX
# ------------------------------------------------------------------------------
df_t4 = pd.read_csv("Table_4_Treasury_Allocation.csv")
order = list(df_t4["Proposal ID"])
trad = df_t4["Traditional Allocation (USD)"].values
aipox = df_t4["AIPoX Allocation (USD)"].values

fig, ax = plt.subplots(figsize=(9, 5.5))
x = np.arange(len(order))
w = 0.38
ax.bar(x - w / 2, trad, w, label="Token-weighted dPoS", color="#c44e52", edgecolor="black", linewidth=0.7)
ax.bar(x + w / 2, aipox, w, label="AIPoX (40% per-proposal cap)", color="#55a868", edgecolor="black", linewidth=0.7)
ax.axhline(CAP_USD, color="#4c72b0", linestyle="--", linewidth=1.2, label="Cap: $400,000 (40%)")

ax.set_xticks(x)
ax.set_xticklabels([f"{pid}\nR = {RISK[pid]:.2f}" for pid in order], fontsize=10)
ax.set_ylabel("Allocated capital (USD)", fontsize=11)
ax.set_ylim(0, 450_000)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
ax.set_title("Treasury allocation by proposal ($1M pool)", fontsize=11.5)
ax.legend(frameon=False, fontsize=9.5, loc="upper right")

i_safe = order.index(SAFE)
delta_safe = (aipox[i_safe] - trad[i_safe]) / trad[i_safe] * 100
ax.annotate(
    f"{SAFE}: {delta_safe:+.1f}% vs dPoS\n(below the cap)",
    xy=(i_safe + w / 2, aipox[i_safe]),
    xytext=(i_safe + 0.9, aipox[i_safe] + 45_000),
    fontsize=9.5,
    arrowprops=dict(arrowstyle="->", lw=1),
)
fig.tight_layout()
fig.savefig("Figure_4_Treasury_Reallocation.png", dpi=300)
plt.close(fig)
print("[+] Figure_4_Treasury_Reallocation.png", flush=True)

# ------------------------------------------------------------------------------
# FIGURE 5: four-way ablation, SAFE and RISKY allocations
# ------------------------------------------------------------------------------
df_t5 = pd.read_csv("Table_5_Ablation_Study.csv")
assert len(df_t5) == 4, "Table 5 must contain the four ablation variants"
variants = ["Token-only", "Token + PoP", "Token + AI", "Full AIPoX"]
safe_vals = [to_usd(v) for v in df_t5["Lowest-R Allocation ($)"]]
risky_vals = [to_usd(v) for v in df_t5["Highest-R Allocation ($)"]]

fig, ax = plt.subplots(figsize=(8.5, 5))
ax.plot(variants, safe_vals, marker="o", linewidth=2.2, color="#55a868",
        label=f"{SAFE} (lowest R = {RISK[SAFE]:.2f})")
ax.plot(variants, risky_vals, marker="s", linewidth=2.2, linestyle="--", color="#c44e52",
        label=f"{RISKY} (highest R = {RISK[RISKY]:.2f})")
ax.axhline(CAP_USD, color="#4c72b0", linestyle=":", linewidth=1.2, label="Cap: $400,000")
ax.set_ylabel("Allocated capital (USD)", fontsize=11)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
ax.set_ylim(0, 450_000)
ax.set_title("Ablation: PoP term and AI risk gate (40% cap)", fontsize=11.5)
ax.legend(frameon=False, fontsize=9.5, loc="center left")
ax.grid(True, linestyle=":", alpha=0.6)
fig.tight_layout()
fig.savefig("Figure_5_Ablation_Decomposition.png", dpi=300)
plt.close(fig)
print("[+] Figure_5_Ablation_Decomposition.png", flush=True)

# ------------------------------------------------------------------------------
# FIGURE 6: whale fragmentation sweep (on-chain)
# ------------------------------------------------------------------------------
if os.path.exists("Table_7c_Whale_Fragmentation_Sweep.csv"):
    df7 = pd.read_csv("Table_7c_Whale_Fragmentation_Sweep.csv")
    col_change = f"{RISKY} change (%)"
    attacks = df7[df7["Identities (k)"] > 0].copy()
    attacks["change"] = attacks[col_change].map(to_pct)
    attacks["pop"] = attacks["Whale PoP share"].str.replace("%", "").astype(float)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    for p_val, style, color in [(0.28, "o-", "#8172b2"), (0.98, "s--", "#c44e52")]:
        sub = attacks[np.isclose(attacks["P per identity"].astype(float), p_val)].sort_values("Identities (k)")
        ax.plot(sub["Identities (k)"], sub["change"], style, color=color, linewidth=2,
                label=f"P = {p_val:.2f} per identity")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("Number of whale identities k (60% of tokens, split evenly)", fontsize=11)
    ax.set_ylabel(f"Change in {RISKY} allocation vs honest run (%)", fontsize=11)
    ax.set_title("On-chain whale attack with identity fragmentation", fontsize=11.5)
    ax.legend(frameon=False, fontsize=9.5)
    ax.grid(True, which="both", linestyle=":", alpha=0.6)
    fig.tight_layout()
    fig.savefig("Figure_6_Whale_Fragmentation.png", dpi=300)
    plt.close(fig)
    print("[+] Figure_6_Whale_Fragmentation.png", flush=True)
else:
    print("[i] Table_7c_Whale_Fragmentation_Sweep.csv not found: Figure 6 not produced", flush=True)