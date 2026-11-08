# AIPoX: Empirical Evaluation and On-Chain Verification Results

This document records the results of the final pipeline run for **AIPoX** (Proof of Participation with a risk-odds treasury allocation). Every number below is taken from the output files of that run: the training report, the threshold file, the on-chain proposal state, the test log and the Table 3 to Table 8 CSV files. All on-chain experiments were executed on a local Ganache EVM node (`http://172.16.22.120:8545`).

> **Scope.** These results come from a controlled simulation. The venture cohort is synthetic, and the telemetry is simulated. The Ganache run is a single-node EVM test. It does not evaluate distributed validator agreement, finality or Byzantine network behavior.

---

## 1. Deployment and Execution Summary

| Item | Value |
| :--- | :--- |
| RPC endpoint | `http://172.16.22.120:8545` (Ganache) |
| Compiler | `solc 0.8.19`, `evmVersion: paris` |
| PoAValidatorEscrow address | `0x25abBC2A3131b1D658f40dFC13149f0112b7D2a5` |
| InvestmentSmartContract address | `0xfe0aC9620352Ed4f550c6EF8FE800d51F773FcAA` |
| Committed ModelHash | `<MODEL_HASH_FINAL>` (read from `models/model_hash.json` of the final run) |
| Attestation scheme | $k$-of-$M$ ECDSA threshold, $k = 4$, $M = 5$ |
| Ejection threshold | $\tau = 0.435854$ (4359 basis points) |
| Treasury pool | $T_{\text{pool}} = \$1{,}000{,}000$ |
| Honest token supply in the vote, $T_{\text{active}}$ | 11,160,518 |
| Sybil run, $T_{\text{active}}$ | 12,660,518 |

**Allocation rule.** The treasury allocation is computed from the composite voting weight and the default risk score:

$$
W(p) = V(p)\cdot\frac{1 - R(p)}{R(p)}, \qquad A(p) = \min\left(\Omega_{\max}\cdot T_{\text{pool}},\; \lambda^{*}\cdot W(p)\right), \qquad \sum_{p} A(p) = T_{\text{pool}}
$$

---

## 2. AI Meta-Layer Validation (Held-Out Test Set)

Source: `train_report.json` and `threshold.json` of the final training run (protocol v2, seed 42, 70/15/15 split).

| Model | Target | Input | Test $n$ | ROC-AUC | 95% CI | Other metrics |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| Telemetry autoencoder $B(u)$ | `is_bot` (simulated) | $z_u \in \mathbb{R}^8$ | 90,000 | **1.0000** | — | TPR at $\tau$ = 100.00%, FPR at $\tau$ = 1.04% |
| Venture risk DNN $R(p)$ | default (synthetic cohort) | $X_p \in \mathbb{R}^6$ | 1,797 | **0.6394** | [0.6145, 0.6642] | Brier = 0.2294 (constant baseline 0.2347); MAE vs. truth = 0.184 |
| Six-feature benchmark | default (synthetic cohort) | $X_p \in \mathbb{R}^6$ | 1,797 | 0.6366 | [0.6108, 0.6640] | Oracle with observables: 0.7792 |

The autoencoder scores telemetry by reconstruction error:

$$
B(u) = \min\left(1, \tfrac{1}{8}\lVert z_u - \hat{z}_u \rVert^2\right)
$$

The cutoff is the 99th percentile of honest validation errors, $\tau = 0.435854$. A validator is ejected when $10000 \cdot B(u) \ge 4359$.

**Interpretation.** The autoencoder separates the simulated bot traffic almost perfectly. This reflects the simulation design, and it should not be read as evidence of real-world detection performance. The venture model's AUC is modest. It is close to the six-feature benchmark, and its calibration is imperfect.

**Calibration by decile** (mean predicted $R(p)$ vs. mean observed default, test split):

| Decile | Mean predicted | Mean observed | $n$ |
| :---: | :---: | :---: | :---: |
| 1 | 0.2778 | 0.3233 | 180 |
| 2 | 0.4112 | 0.5221 | 180 |
| 3 | 0.4642 | 0.5920 | 179 |
| 4 | 0.4989 | 0.5960 | 180 |
| 5 | 0.5286 | 0.6251 | 180 |
| 6 | 0.5559 | 0.6616 | 179 |
| 7 | 0.5840 | 0.6914 | 180 |
| 8 | 0.6133 | 0.7125 | 179 |
| 9 | 0.6419 | 0.7192 | 180 |
| 10 | 0.6871 | 0.7665 | 180 |

---

## 3. Proposal Selection and Scoring

Five anonymised proposals were selected from the held-out test split, one at each of the 10th, 30th, 50th, 70th and 90th percentiles of $R(p)$. IDs follow ascending $R(p)$. The selection does not use the outcome label.

**Table 3. Comparative prioritization (dPoS vs. PoP-adjusted vs. AIPoX)**

| Proposal ID | Raw Token Votes (dPoS) | PoP-Adjusted Score $V(p)$ | AI Risk Score $R(p)$ | Traditional Rank | PoP Rank | Final AIPoX Rank |
| :---: | ---: | ---: | :---: | :---: | :---: | :---: |
| **P-1** | 2,074,886 | 2,354,361 | 0.371357 | 4 | 3 | **1** |
| **P-2** | 2,883,507 | 2,584,415 | 0.482516 | 1 | 1 | **2** |
| **P-3** | 2,421,054 | 2,406,251 | 0.541779 | 2 | 2 | **3** |
| **P-4** | 2,164,144 | 2,060,302 | 0.599348 | 3 | 4 | **4** |
| **P-5** | 1,616,927 | 1,755,183 | 0.657715 | 5 | 5 | **5** |

The composite weight is $w_u = \alpha \bar{T}_u + \beta \bar{P}_u$ with $\alpha = 0.4$ and $\beta = 0.6$. The proposal score is

$$
V(p) = \alpha \sum_{u \in \mathcal{V}_p} T_{\text{tokens},u} + \beta \cdot T_{\text{active}} \sum_{u \in \mathcal{V}_p} \bar{P}_u
$$

---

## 4. Treasury Allocation Outcomes ($1,000,000 Pool)

**Table 4. dPoS allocation vs. AIPoX allocation**

| Proposal ID | $R(p)$ | Traditional Allocation (USD) | AIPoX Allocation (USD) | Net Allocation Delta |
| :---: | :---: | ---: | ---: | :---: |
| **P-1** | 0.371357 | $185,913.06 | **$359,604.95** | **+93.43%** |
| **P-2** | 0.482516 | $258,366.77 | $250,084.95 | −3.21% |
| **P-3** | 0.541779 | $216,930.25 | $183,625.88 | −15.35% |
| **P-4** | 0.599348 | $193,910.71 | $124,268.00 | −35.91% |
| **P-5** | 0.657715 | $144,879.21 | $82,416.21 | −43.11% |
| **Total** | — | **$1,000,000.00** | **$1,000,000.00** | — |

Both columns sum to the pool. The largest change is the increase for the proposal with the lowest default risk (P-1). The largest decrease is for the highest-risk proposal (P-5).

---

## 5. Ablation: Contribution of Proof of Participation and the Risk-Odds Gate

**Table 5. Four-way ablation (lowest-risk and highest-risk proposals)**

| Architecture Variant | Lowest-$R$ Allocation (P-1, USD) | Highest-$R$ Allocation (P-5, USD) | Lowest-$R$ Rank | Highest-$R$ Rank | Lowest-$R$ Net Gain |
| :--- | ---: | ---: | :---: | :---: | :---: |
| **1. Token-only (traditional dPoS)** | $185,913.06 | $144,879.21 | 4 | 5 | Baseline (0.00%) |
| **2. Token + PoP (no AI gate)** | $210,954.57 | $157,267.25 | 3 | 5 | +13.47% |
| **3. Token + AI gate (no PoP)** | $321,041.42 | $76,912.08 | 1 | 5 | +72.68% |
| **4. Full AIPoX (PoP + AI gate)** | **$359,604.95** | **$82,416.21** | **1** | **5** | **+93.43%** |

The on-chain test log confirms that the full variant's allocation sums to $1,000,000. The two mechanisms contribute in the same direction: PoP alone raises the lowest-risk proposal by 13.47%, and the AI gate alone raises it by 72.68%. Their combination gives +93.43%. This decomposition is specific to the simulated voter behavior described in Section 5.1 of the manuscript.

---

## 6. Sybil Attack (Target P-5)

The attacker controls 1,500 identities, each holding 1,000 tokens. This is 1,500,000 tokens, or 13.44% of the honest supply. All Sybil votes are cast on-chain for P-5.

**Table 6. Sybil attack outcomes**

| Proposal ID | Baseline AIPoX Allocation (USD) | Traditional Rank (Under Attack) | AIPoX Rank (Under Attack) | Post-Attack AIPoX Allocation (USD) | Change |
| :---: | ---: | :---: | :---: | ---: | :---: |
| **P-1** | $359,604.95 | 5 | 1 (Preserved) | $352,318.10 | −2.03% |
| **P-2** | $250,084.95 | 2 | 2 | $242,176.61 | −3.16% |
| **P-3** | $183,625.88 | 3 | 3 | $178,794.10 | −2.63% |
| **P-4** | $124,268.00 | 4 | 4 | $120,731.63 | −2.85% |
| **P-5 (Target)** | $82,416.21 | **1 (Compromised)** | **5 (Attack contained)** | $105,979.56 | **+28.59%** |

**Decomposition of the increase in $V(p)$ for P-5** (on-chain values):

| Quantity | Before attack | After attack |
| :--- | ---: | ---: |
| Raw token votes for P-5 | 1,616,927 | 3,116,927 |
| Raw PoP sum (bps) | 876,191 | 876,191 |
| $T_{\text{active}}$ | 11,160,518 | 12,660,518 |
| Composite $V(p)$ | 1,755,183 | 2,504,156 |

The increase of $V(p)$ is 748,973 (+42.67%). It comes from two terms:

- Direct token term, $\alpha \times$ Sybil tokens: **600,000**
- Indirect term through $T_{\text{active}}$: **148,973**

Under the dPoS baseline, the same attack lifts P-5 to rank 1, and the AIPoX rule restrains it to a rank of 5. The restraint is partial: the attack still increases the allocation of P-5 by 28.59%.

---

## 7. Whale Attack (One Identity Holding 60% of Supply)

One identity holds 16,740,777 tokens, which is 60% of the supply. It votes for P-5 with a participation share given in the tables below. Each row is an on-chain run.

**Table 7. Whale ranking under attack**

| Proposal ID | Traditional Rank (Under Attack) | AIPoX Rank (Under Attack) |
| :---: | :---: | :---: |
| **P-1** | 5 | **1 (Preserved)** |
| **P-2** | 2 | 3 |
| **P-3** | 3 | 4 |
| **P-4** | 4 | 5 |
| **P-5 (Target)** | **1 (Compromised)** | 2 |

**Table 8. Treasury distortion under the whale attack (whale PoP share 0.05%, $P = 0.28$)**

| Proposal ID | Baseline AIPoX Allocation (USD) | Post-Attack Allocation (USD) | Net Distortion |
| :---: | ---: | ---: | :---: |
| P-1 | $359,604.95 | $318,916.48 | −11.31% |
| P-2 | $250,084.95 | $205,969.40 | −17.64% |
| P-3 | $183,625.88 | $156,662.96 | −14.68% |
| P-4 | $124,268.00 | $104,537.22 | −15.88% |
| **P-5 (Target)** | $82,416.21 | **$213,913.94** | **+159.55%** |

**Table 8b. Treasury distortion under the whale attack (whale PoP share 0.18%, $P = 0.98$)**

| Proposal ID | Baseline AIPoX Allocation (USD) | Post-Attack Allocation (USD) | Net Distortion |
| :---: | ---: | ---: | :---: |
| P-1 | $359,604.95 | $318,708.39 | −11.37% |
| P-2 | $250,084.95 | $205,852.68 | −17.69% |
| P-3 | $183,625.88 | $156,567.62 | −14.74% |
| P-4 | $124,268.00 | $104,475.37 | −15.93% |
| **P-5 (Target)** | $82,416.21 | **$214,395.94** | **+160.14%** |

The whale attack raises P-5 by about 160% in both cases, and every other proposal loses between 11% and 18% of its baseline allocation.

---

## 8. Whale Fragmentation Sweep (Table 7c)

The same locked token budget is split across $k$ identities. Each identity has participation $P$ per identity. For $k = 1000$ and $P = 0.98$, the cap on the proposal is binding.

| Scenario | Identities $k$ | $P$ per identity | Whale PoP share | P-5 under attack (USD) | P-5 change | P-1 change | Cap binding | P-5 rank under attack | Top proposal under attack |
| :--- | ---: | :---: | ---: | ---: | ---: | ---: | :---: | :---: | :---: |
| Honest baseline | 0 | — | 0.00% | $82,416.21 | — | — | no | 5 | P-1 |
| 1 identity, $P = 0.28$ | 1 | 0.28 | 0.05% | $213,913.94 | +159.55% | −11.31% | no | 2 | P-1 |
| 1 identity, $P = 0.98$ | 1 | 0.98 | 0.18% | $214,395.94 | +160.14% | −11.37% | no | 2 | P-1 |
| 10 identities, $P = 0.98$ | 10 | 0.98 | 1.82% | $220,396.93 | +167.42% | −12.09% | no | 2 | P-1 |
| 100 identities, $P = 0.28$ | 100 | 0.28 | 5.02% | $232,369.11 | +181.95% | −13.53% | no | 2 | P-1 |
| 100 identities, $P = 0.98$ | 100 | 0.98 | 15.62% | $273,824.97 | +232.25% | −18.51% | no | 2 | P-1 |
| 1000 identities, $P = 0.98$ | 1000 | 0.98 | 64.93% | $400,000.00 | +385.34% | −35.00% | **yes** | **1** | **P-5** |

The whale's locked tokens are 16,740,777 in every row. The dPoS allocation to P-5 under the same attack is $657,951.68 (+354.14%). The effect on P-5 grows with $k$. At $k = 1000$ the cap is reached, and P-5 becomes the top proposal.

---

## 9. On-Chain Test Suite

The suite runs 66 checks. Each check either confirms an expected state or confirms that an invalid action is rejected.

| Category | Result |
| :--- | :--- |
| Total checks | 66 |
| Passed | 54 |
| Failed | 0 |
| Expected reverts (rejected as designed) | 12 |

Examples of the 12 expected reverts:

| Area | Attempted action | Revert reason |
| :--- | :--- | :--- |
| Escrow | Second unbond while one is pending | `Unbond already pending` |
| Escrow | Withdraw before the unbonding delay | `Unbonding in progress` |
| Escrow | Replay of an attested slash (stale nonce) | `Stale nonce` |
| Escrow | Slash signed by non-committee keys | `Unauthorized committee signer` |
| Escrow | Zero anomaly score | `Invalid anomaly bounds` |
| Governance | PoP above 10,000 bps | `PoP out of range` |
| Governance | Second vote by the same voter in one epoch | `One vote per voter per epoch` |
| Governance | Risk $R = 0$ | `Risk out of bounds` |
| Governance | Re-open voting after finalisation | `Invalid phase` |
| Governance | Vote after finalisation | `Invalid phase` |
| Tranche | Tranche 1 repeated | `Tranche out of sequence` |
| Tranche | Tranches exceeding 100% of budget | `Tranches exceed budget` |

All five attestations in each run were accepted. Each run emitted one allocation per proposal, and the full variant's allocation sums to $1,000,000.

---

## 10. Figures

| Figure | File | Content |
| :---: | :--- | :--- |
| 1 | `figures/Figure_1_Operational_Architecture.svg` | Layered architecture and data flow |
| 2 | `figures/Figure_2_ROC_AI_Meta_Layer.png` | Held-out ROC curves for $B(u)$ and $R(p)$ (generated by `Data/fig2_roc.py`) |
| 3 | `figures/Figure_3_AI_Layer.svg` | Dual-stream AI layer and inference pipeline |
| 4 | `figures/Figure_4_Governance_Workflow.svg` | Governance workflow |
| 5 | `figures/Figure_5_Treasury_Reallocation.png` | dPoS vs. AIPoX treasury allocation |
| 6 | `figures/Figure_6_Ablation_Decomposition.png` | Ablation decomposition |
| 7 | `figures/Figure_7_Whale_Fragmentation.png` | Whale fragmentation sweep (Table 7c) |

Figure 2 is written only when its recomputed metrics match `train_report.json`.

---

## 11. Reproducibility Notes

- Random seed: 42 for all splits and model initialisation.
- Model protocol v2: early stopping on validation loss, with no test-set decisions.
- The honest run and the whale runs use `minVoteStake` read back from the contract. The read-back check passes in every run.
- The Ganache results come from one run on one node. Repeated seeds and repeated chain runs are not reported.
- Scalability (throughput and latency) was not re-measured in the final run. It is therefore not reported here.
