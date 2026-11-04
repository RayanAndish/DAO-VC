"""
3_plot_publication_figures.py
=============================
Figures 4, 5 and 6 from the verified tables.

Revision notes
- No default values for missing proposal risks: a missing entry stops the script.
- The P-3 annotation is placed by looking up its row, not by assuming it is first.
- Figure 6 is drawn only if the scalability file contains real measurements. A file
  whose TPS, latency and gas are constant is refused with a message.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "Data"

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

for p in [PROJECT_DIR / "Table_4_Treasury_Allocation.csv",
          PROJECT_DIR / "Table_5_Ablation_Study.csv",
          DATA_DIR / "Table_Proposals_Feature_Profiles.csv"]:
    if not p.exists():
        sys.exit(f"[-] ERROR: {p.name} missing. Run the pipeline first.")

df_t4 = pd.read_csv(PROJECT_DIR / "Table_4_Treasury_Allocation.csv")
df_props = pd.read_csv(DATA_DIR / "Table_Proposals_Feature_Profiles.csv")
risk_map = dict(zip(df_props["Proposal_ID"], df_props["AI_Risk_Score_R_p"]))


def risk_of(pid):
    if pid not in risk_map:
        sys.exit(f"[-] ERROR: no risk score for {pid}")
    return float(risk_map[pid])


# ------------------------------------------------------------------------------
# FIGURE 4: CAPPED TREASURY ALLOCATION
# ------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5.5))
x = np.arange(len(df_t4))
width = 0.35

ax.bar(x - width / 2, df_t4["Traditional Allocation (USD)"], width,
       label="Traditional dPoS (token-weighted)", color="#d62728", alpha=0.85, edgecolor="black")
ax.bar(x + width / 2, df_t4["AIPoX Allocation (USD)"], width,
       label="AIPoX (40% per-proposal cap)", color="#2ca02c", alpha=0.9, edgecolor="black")

ax.set_ylabel("Allocated capital (USD)", fontsize=11, fontweight="bold")
ax.set_title("Treasury allocation under a 40% per-proposal cap ($1M pool)", fontsize=11.5,
             fontweight="bold", pad=15)
ax.set_xticks(x)
ax.set_xticklabels([f"{pid}\n(R={risk_of(pid):.2f})" for pid in df_t4["Proposal ID"]], fontsize=10)
ax.yaxis.set_major_formatter("${x:,.0f}")
ax.axhline(y=400000, color="blue", linestyle="--", alpha=0.7, label="Cap ($400,000 = 40%)")
ax.legend(frameon=True, fontsize=9.5, shadow=True)

idx_p3 = int(df_t4.index[df_t4["Proposal ID"] == "P-3"][0])
p3_alloc = float(df_t4.loc[idx_p3, "AIPoX Allocation (USD)"])
p3_trad = float(df_t4.loc[idx_p3, "Traditional Allocation (USD)"])
delta_pct = (p3_alloc - p3_trad) / p3_trad * 100
ax.annotate(f"{delta_pct:+.1f}% vs dPoS\n(capped at $400k)",
            xy=(idx_p3 + width / 2, p3_alloc), xytext=(idx_p3 + 0.6, 340000),
            arrowprops=dict(facecolor="black", shrink=0.08, width=1.5, headwidth=7), fontsize=9.5,
            fontweight="bold", bbox=dict(boxstyle="round,pad=0.4", facecolor="#e8f5e9", edgecolor="#2ca02c"))
plt.tight_layout()
plt.savefig(PROJECT_DIR / "Figure_4_Treasury_Reallocation.png", dpi=300)
print("[+] Figure_4_Treasury_Reallocation.png saved")

# ------------------------------------------------------------------------------
# FIGURE 5: ABLATION
# ------------------------------------------------------------------------------
df_t5 = pd.read_csv(PROJECT_DIR / "Table_5_Ablation_Study.csv")
variants = ["Token-only", "Token + PoP", "Token + AI", "Full AIPoX"]


def usd(v):
    return float(str(v).replace("$", "").replace(",", ""))


p3_vals = [usd(v) for v in df_t5["P-3 Allocation ($)"]]
p2_vals = [usd(v) for v in df_t5["P-2 Allocation ($)"]]

fig, ax2 = plt.subplots(figsize=(8.5, 5))
ax2.plot(variants, p3_vals, marker="o", linewidth=2.8, markersize=9, color="#2ca02c",
         label=f"P-3 (sound venture, R={risk_of('P-3'):.2f})")
ax2.plot(variants, p2_vals, marker="s", linewidth=2.5, markersize=8, color="#d62728",
         linestyle="--", label=f"P-2 (hyped venture, R={risk_of('P-2'):.2f})")
ax2.axhline(y=400000, color="blue", linestyle=":", alpha=0.6, label="Cap ($400,000)")
ax2.set_ylabel("Treasury allocation (USD)", fontsize=11, fontweight="bold")
ax2.set_title("Ablation: PoP contribution vs AI risk gate (40% cap)", fontsize=11.5, fontweight="bold", pad=15)
ax2.yaxis.set_major_formatter("${x:,.0f}")
ax2.legend(frameon=True, fontsize=9.5, shadow=True)
ax2.grid(True, linestyle=":", alpha=0.6)
plt.tight_layout()
plt.savefig(PROJECT_DIR / "Figure_5_Ablation_Decomposition.png", dpi=300)
print("[+] Figure_5_Ablation_Decomposition.png saved")

# ------------------------------------------------------------------------------
# FIGURE 6: SCALABILITY (only real measurements)
# ------------------------------------------------------------------------------
bench_path = PROJECT_DIR / "Table_5_1_Empirical_Scalability.csv"
if not bench_path.exists():
    print("[!] Figure 6 skipped: Table_5_1_Empirical_Scalability.csv not found")
else:
    df_bench = pd.read_csv(bench_path)
    constant = df_bench[["Measured_TPS", "Avg_Latency_ms", "Avg_Gas_Per_Tx"]].nunique().max() == 1
    if constant or len(df_bench) < 3:
        print("[!] Figure 6 skipped: scalability values are constant or too few points; "
              "re-measure before publishing this figure")
    else:
        fig, ax3 = plt.subplots(figsize=(8.5, 5))
        ax3.set_xscale("log")
        ax3.set_xlabel("Workload batch size N (transactions)", fontsize=11, fontweight="bold")
        ax3.set_ylabel("Average latency (ms)", color="#1f77b4", fontsize=11, fontweight="bold")
        ax3.plot(df_bench["Workload_Transactions"], df_bench["Avg_Latency_ms"], color="#1f77b4",
                 marker="o", linewidth=2.5, label="Latency (ms)")
        ax4 = ax3.twinx()
        ax4.set_ylabel("Measured throughput (TPS)", color="#ff7f0e", fontsize=11, fontweight="bold")
        ax4.plot(df_bench["Workload_Transactions"], df_bench["Measured_TPS"], color="#ff7f0e",
                 marker="s", linestyle="--", linewidth=2.5, label="TPS")
        plt.title("Empirical throughput and latency on Ganache (automine)", fontsize=11.5,
                  fontweight="bold", pad=15)
        plt.tight_layout()
        plt.savefig(PROJECT_DIR / "Figure_6_Empirical_Blockchain_Scalability.png", dpi=300)
        print("[+] Figure_6_Empirical_Blockchain_Scalability.png saved")
