"""
3_plot_publication_figures.py
=============================
Generates high-resolution publication figures for Scientific Reports:
- Figure 4: Comparative Treasury Allocation (Traditional vs AIPoX).
- Figure 5: 4-Way Ablation Study (Organic stepped impact of PoP and AI).
- Figure 6: Empirical Blockchain Scalability (Latency & TPS on Ganache).
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

# ------------------------------------------------------------------------------
# FIGURE 4: TREASURY ALLOCATION COMPARISON
# ------------------------------------------------------------------------------
df_t4 = pd.read_csv("Table_4_Treasury_Allocation.csv")

fig, ax = plt.subplots(figsize=(9, 5.5))
x = np.arange(len(df_t4))
width = 0.35

rects1 = ax.bar(
    x - width / 2,
    df_t4["Traditional Allocation (USD)"],
    width,
    label="Traditional dPoS (Token-Weighted)",
    color="#d62728",
    alpha=0.85,
    edgecolor="black",
)
rects2 = ax.bar(
    x + width / 2,
    df_t4["AIPoX Allocation (USD)"],
    width,
    label="AIPoX (PoP + Bayesian Odds Gate)",
    color="#2ca02c",
    alpha=0.9,
    edgecolor="black",
)

ax.set_ylabel("Allocated Capital (USD)", fontsize=11, fontweight="bold")
ax.set_title(
    "Comparative Capital Allocation under $1,000,000 Treasury Pool",
    fontsize=12,
    fontweight="bold",
    pad=15,
)
ax.set_xticks(x)
ax.set_xticklabels(df_t4["Proposal ID"], fontsize=10)
ax.yaxis.set_major_formatter("${x:,.0f}")
ax.legend(frameon=True, fontsize=10, shadow=True)

# Annotate P-3 gain
p3_alloc = df_t4.loc[
    df_t4["Proposal ID"] == "P-3", "AIPoX Allocation (USD)"
].values[0]
p3_trad = df_t4.loc[
    df_t4["Proposal ID"] == "P-3", "Traditional Allocation (USD)"
].values[0]
gain_x = p3_alloc / p3_trad

ax.annotate(
    f"+{((p3_alloc-p3_trad)/p3_trad*100):.1f}% Reallocation\n({gain_x:.2f}x"
    " Increase)",
    xy=(0 + width / 2, p3_alloc),
    xytext=(0.35, p3_alloc * 0.85),
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
# FIGURE 5: ABLATION DECOMPOSITION
# ------------------------------------------------------------------------------
df_abl = pd.read_csv("Table_10_Ablation_Study.csv")
variants = ["Token-Only", "Token + PoP", "Token + AI", "Full AIPoX"]
p3_vals = [
    float(v.replace("$", "").replace(",", ""))
    for v in df_abl["P-3 Allocation ($)"]
]
p2_vals = [
    float(v.replace("$", "").replace(",", ""))
    for v in df_abl["P-2 Allocation ($)"]
]

fig, ax2 = plt.subplots(figsize=(8.5, 5))
ax2.plot(
    variants,
    p3_vals,
    marker="o",
    linewidth=2.8,
    markersize=9,
    color="#2ca02c",
    label="P-3 Allocation (Sound Venture, R=0.06)",
)
ax2.plot(
    variants,
    p2_vals,
    marker="s",
    linewidth=2.5,
    markersize=8,
    color="#d62728",
    linestyle="--",
    label="P-2 Allocation (Hyped Venture, R=0.49)",
)

ax2.set_ylabel("Treasury Allocation (USD)", fontsize=11, fontweight="bold")
ax2.set_title(
    "Ablation Analysis: Decomposing PoP Meritocracy vs. AI Risk Gating",
    fontsize=12,
    fontweight="bold",
    pad=15,
)
ax2.yaxis.set_major_formatter("${x:,.0f}")
ax2.legend(frameon=True, fontsize=10, shadow=True)
plt.grid(True, linestyle=":", alpha=0.6)

plt.tight_layout()
plt.savefig("Figure_5_Ablation_Decomposition.png", dpi=300)
print("[+] Saved: Figure_5_Ablation_Decomposition.png")

# ------------------------------------------------------------------------------
# FIGURE 6: EMPIRICAL BLOCKCHAIN BENCHMARK (GANACHE ON-CHAIN DATA)
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
line1 = ax3.plot(
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
line2 = ax4.plot(
    df_bench["Workload_Transactions"],
    df_bench["Measured_TPS"],
    color=color2,
    marker="s",
    linestyle="--",
    linewidth=2.5,
    label="Effective TPS",
)
ax4.tick_params(axis="y", labelcolor=color2)
ax4.set_ylim(0, 20)

plt.title(
    "Empirical Blockchain Performance on Ganache EVM (1,000+ Blocks Minted)",
    fontsize=12,
    fontweight="bold",
    pad=15,
)
plt.tight_layout()
plt.savefig("Figure_6_Empirical_Blockchain_Scalability.png", dpi=300)
print("[+] Saved: Figure_6_Empirical_Blockchain_Scalability.png")