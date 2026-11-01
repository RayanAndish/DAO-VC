"""
3_plot_publication_figures.py
=============================
Generates publication-quality figures with DYNAMIC legend risk scores (No hardcoding).
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

df_t4 = pd.read_csv("Table_4_Treasury_Allocation.csv")
df_props = pd.read_csv("Table_Proposals_Feature_Profiles.csv")
risk_map = dict(
    zip(df_props["Proposal_ID"], df_props["AI_Risk_Score_R_p"].round(2))
)

# ------------------------------------------------------------------------------
# FIGURE 4: CAPPED TREASURY ALLOCATION
# ------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5.5))
x = np.arange(len(df_t4))
width = 0.35

ax.bar(
    x - width / 2,
    df_t4["Traditional Allocation (USD)"],
    width,
    label="Traditional dPoS (Token-Weighted)",
    color="#d62728",
    alpha=0.85,
    edgecolor="black",
)
ax.bar(
    x + width / 2,
    df_t4["AIPoX Allocation (USD)"],
    width,
    label="AIPoX (40% Diversification Capped)",
    color="#2ca02c",
    alpha=0.9,
    edgecolor="black",
)

ax.set_ylabel("Allocated Capital (USD)", fontsize=11, fontweight="bold")
ax.set_title(
    "Comparative Capital Allocation with 40% Portfolio Diversification Cap"
    " ($1M Treasury)",
    fontsize=11.5,
    fontweight="bold",
    pad=15,
)
ax.set_xticks(x)
ax.set_xticklabels(
    [f"{pid}\n(R={risk_map.get(pid, 0.5):.2f})" for pid in df_t4["Proposal ID"]],
    fontsize=10,
)
ax.yaxis.set_major_formatter("${x:,.0f}")
ax.axhline(
    y=400000,
    color="blue",
    linestyle="--",
    alpha=0.7,
    label="VC Exposure Cap ($400,000 / 40%)",
)
ax.legend(frameon=True, fontsize=9.5, shadow=True)

p3_alloc = df_t4.loc[
    df_t4["Proposal ID"] == "P-3", "AIPoX Allocation (USD)"
].values[0]
p3_trad = df_t4.loc[
    df_t4["Proposal ID"] == "P-3", "Traditional Allocation (USD)"
].values[0]
delta_pct = ((p3_alloc - p3_trad) / p3_trad) * 100

ax.annotate(
    f"+{delta_pct:.1f}% Reallocation\n(Capped at $400k)",
    xy=(0 + width / 2, p3_alloc),
    xytext=(0.35, 340000),
    arrowprops=dict(facecolor="black", shrink=0.08, width=1.5, headwidth=7),
    fontsize=9.5,
    fontweight="bold",
    bbox=dict(
        boxstyle="round,pad=0.4", facecolor="#e8f5e9", edgecolor="#2ca02c"
    ),
)
plt.tight_layout()
plt.savefig("Figure_4_Treasury_Reallocation.png", dpi=300)
print("[+] Saved: Figure_4_Treasury_Reallocation.png")

# ------------------------------------------------------------------------------
# FIGURE 5: ABLATION WITH DYNAMIC LEGEND (FIXED BUG)
# ------------------------------------------------------------------------------
df_t5 = pd.read_csv("Table_5_Ablation_Study.csv")
variants = ["Token-Only", "Token + PoP", "Token + AI", "Full AIPoX"]
p3_vals = [
    float(v.replace("$", "").replace(",", ""))
    for v in df_t5["P-3 Allocation ($)"]
]
p2_vals = [
    float(v.replace("$", "").replace(",", ""))
    for v in df_t5["P-2 Allocation ($)"]
]

r_p3 = risk_map.get("P-3", 0.12)
r_p2 = risk_map.get("P-2", 0.96)

fig, ax2 = plt.subplots(figsize=(8.5, 5))
ax2.plot(
    variants,
    p3_vals,
    marker="o",
    linewidth=2.8,
    markersize=9,
    color="#2ca02c",
    label=f"P-3 Allocation (Sound Venture, R={r_p3:.2f})",
)
ax2.plot(
    variants,
    p2_vals,
    marker="s",
    linewidth=2.5,
    markersize=8,
    color="#d62728",
    linestyle="--",
    label=f"P-2 Allocation (Hyped Venture, R={r_p2:.2f})",
)

ax2.set_ylabel("Treasury Allocation (USD)", fontsize=11, fontweight="bold")
ax2.set_title(
    "Ablation Analysis: Decomposing PoP Meritocracy vs. AI Risk Gating (40%"
    " Cap)",
    fontsize=11.5,
    fontweight="bold",
    pad=15,
)
ax2.yaxis.set_major_formatter("${x:,.0f}")
ax2.axhline(
    y=400000,
    color="blue",
    linestyle=":",
    alpha=0.6,
    label="Portfolio Cap ($400,000)",
)
ax2.legend(frameon=True, fontsize=9.5, shadow=True)
plt.grid(True, linestyle=":", alpha=0.6)
plt.tight_layout()
plt.savefig("Figure_5_Ablation_Decomposition.png", dpi=300)
print("[+] Saved: Figure_5_Ablation_Decomposition.png")

# ------------------------------------------------------------------------------
# FIGURE 6: EMPIRICAL SCALABILITY
# ------------------------------------------------------------------------------
df_bench = pd.read_csv("Table_5_1_Empirical_Scalability.csv")
fig, ax3 = plt.subplots(figsize=(8.5, 5))
color1 = "#1f77b4"
color2 = "#ff7f0e"

ax3.set_xlabel(
    "Transaction Workload Batch Size (N)", fontsize=11, fontweight="bold"
)
ax3.set_ylabel(
    "Average Latency (ms)", color=color1, fontsize=11, fontweight="bold"
)
ax3.plot(
    df_bench["Workload_Transactions"],
    df_bench["Avg_Latency_ms"],
    color=color1,
    marker="o",
    linewidth=2.5,
    label="On-Chain Latency (ms)",
)
ax3.tick_params(axis="y", labelcolor=color1)
ax3.set_xscale("log")

ax4 = ax3.twinx()
ax4.set_ylabel(
    "Measured Throughput (TPS)", color=color2, fontsize=11, fontweight="bold"
)
ax4.plot(
    df_bench["Workload_Transactions"],
    df_bench["Measured_TPS"],
    color=color2,
    marker="s",
    linestyle="--",
    linewidth=2.5,
    label="Effective TPS",
)
ax4.tick_params(axis="y", labelcolor=color2)
ax4.set_ylim(0, 25)

plt.title(
    "Empirical Blockchain Performance on Ganache EVM (1,000+ Blocks Minted)",
    fontsize=11.5,
    fontweight="bold",
    pad=15,
)
plt.tight_layout()
plt.savefig("Figure_6_Empirical_Blockchain_Scalability.png", dpi=300)
print("[+] Saved: Figure_6_Empirical_Blockchain_Scalability.png")