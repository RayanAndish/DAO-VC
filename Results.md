# AIPoX Empirical Evaluation & Blockchain Verification Results

[![EVM Compatible](https://img.shields.io/badge/EVM-Ganache%20Testnet-orange?logo=ethereum)](https://trufflesuite.com/ganache/)
[![Transactions Confirmed](https://img.shields.io/badge/On--Chain%20Votes-1%2C000%20Tx-success)](https://github.com/)
[![Treasury Budget](https://img.shields.io/badge/Treasury%20Pool-%241%2C000%2C000-blue)](https://github.com/)
[![Verification Status](https://img.shields.io/badge/Status-100%25%20Reproducible-brightgreen)](https://github.com/)

This document logs the deterministic execution results and on-chain verification data for the **AIPoX** consensus and governance protocol. All experiments were conducted on a dedicated EVM testnet (Ganache RPC: `http://172.16.22.120:8545`) with 1,000 heterogeneous voter transactions, cryptographic threshold attestation, and empirical venture data.

---

## 1. On-Chain Deployment & Live Simulation Log

* **Target RPC:** `http://172.16.22.120:8545`
* **Active Deployer Account:** `0x782282339c7c68DB709da39C8B02ae24c0256f36`
* **Solidity Compiler:** `solc 0.8.19` (`evmVersion: paris`)
* **PoAValidatorEscrow Address:** `0x25abBC2A3131b1D658f40dFC13149f0112b7D2a5`
* **InvestmentSmartContract Address:** `0xfe0aC9620352Ed4f550c6EF8FE800d51F773FcAA`
* **Committed Neural ModelHash:** `0x80da611fc35ee2df69f6be29b8db7ac0a7e9d16f2b7d284a62b418406c8f1a82`

### Execution Summary
* **Total On-Chain Votes Cast:** 1,000 discrete transactions
* **Total Execution Time:** 116.67 seconds
* **Mean Throughput:** 8.6 tx/s
* **Attestation Scheme:** $(k\text{-of-}M)$ ECDSA Threshold Signatures ($k=4, M=5$)
* **Allocation Engine:** Pure Bayesian Odds Ratio ($\mathcal{O}(p) = \frac{1 - R(p)}{R(p)}$)

---

## 2. On-Chain Verified Macro Treasury Allocation (Table 4)

Total Competitive Treasury Pool: **$1,000,000.00 USD**  
Execution Trigger: `executeMacroTreasuryAllocation()` (Equation 8)

| Proposal ID | Traditional dPoS Allocation (USD) | AIPoX Allocation (USD) | Net Allocation Delta | Fiduciary Governance Status |
| :---: | :---: | :---: | :---: | :--- |
| **P-3** | $149,967.77 | **$735,239.55** | **+390.27%** | **Optimal Priority (4.90x Expansion)** |
| **P-1** | $150,195.56 | $74,154.54 | -50.63% | Preserved Technical Baseline |
| **P-5** | $188,328.87 | $70,815.11 | -62.40% | Balanced Exposure Reduction |
| **P-2** | $308,249.79 | $62,818.13 | -79.62% | Speculative Hype Demoted |
| **P-4** | $203,258.00 | $56,972.66 | -71.97% | High-Ask Venture Constrained |
| **Total** | **$1,000,000.00** | **$1,000,000.00** | — | **100% Capital Accounted For** |

---

## 3. Proposal Prioritization Breakdown (Table 3)

Comparison of raw token-weighted voting (dPoS) versus Proof-of-Participation adjusted governance and final AIPoX ranking:

| Proposal ID | Raw Token Votes (dPoS) | PoP-Adjusted Score $V(p)$ | AI Risk Score $R(p)$ | Traditional Rank | PoP Rank | Final AIPoX Rank |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **P-3** | 1,867,092 | 2,424,173 | 0.06 | 5 (Lowest) | 3 | **1 (Highest)** |
| **P-1** | 1,869,928 | 2,062,547 | 0.35 | 4 | 5 | **2** |
| **P-5** | 2,344,686 | 2,338,687 | 0.39 | 3 | 4 | **3** |
| **P-2** | 3,837,696 | 3,117,614 | 0.49 | 1 (Highest) | 1 | **4** |
| **P-4** | 2,530,553 | 2,506,929 | 0.46 | 2 | 2 | **5 (Lowest)** |

> **Key Observation:** In traditional dPoS, the capital-backed, high-risk venture P-2 captured 1st rank, whereas the sound venture P-3 was ranked last (5th). The PoP layer elevated P-3 to 3rd rank based on verified contributor support, and the Bayesian odds gate finalized it at 1st rank ($735,239.55 USD).

---

## 4. Multi-Layer Ablation Analysis (Table 5 / Table 10)

Isolating the independent governance contributions of the Proof of Participation mechanism ($\beta = 0.6$) and the Bayesian Odds AI Risk Gate:

| Architecture Variant | P-3 Allocation (USD) | P-2 Allocation (USD) | P-3 Rank | P-2 Rank | P-3 Net Gain |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Token-Only (Traditional dPoS)** | $149,967.77 | $308,249.79 | 5 | 1 | Baseline (0.0%) |
| **2. Token + PoP (No AI Risk Gate)** | $194,713.47 | $250,411.77 | 3 | 1 | **+29.84%** |
| **3. Token + AI Gate (No PoP)** | $674,670.38 | $92,128.50 | 1 | 2 | **+349.88%** |
| **4. Full AIPoX (PoP + AI Gate)** | **$735,239.55** | **$62,818.13** | **1** | **4** | **+390.27%** |

```text
Ablation Progression:
[Token-Only: $150k] ──(+29.8% via PoP)──> [Token+PoP: $195k] ──(+AI Odds Gate)──> [Full AIPoX: $735k]
```

---

## 5. Empirical Scalability & Consensus Benchmark

Measurements collected on the Ganache testnet across variable transaction workloads:

| Workload (Transactions) | Total Execution Time (s) | Measured Throughput (TPS) | Average Latency (ms) | Gas Cost Per Vote (Invariant) |
| :---: | :---: | :---: | :---: | :---: |
| **10** | 1.008 | 9.9 | 100.76 | 54,294 |
| **20** | 2.113 | 9.5 | 105.65 | 54,294 |
| **100** | 10.138 | 9.9 | 101.38 | 54,294 |
| **500** | 50.319 | 9.9 | 100.64 | 54,294 |
| **1000** | 100.512 | 9.9 | 100.51 | 54,294 |

* **Deterministic Voting Gas Overhead:** Constant at 54,294 gas per transaction.
* **Attestation Gas Cost:** ~108,194 gas per proposal for 4-of-5 ECDSA verification.

---

## 6. Generated Publication Figures

All visual assets were rendered from the verified on-chain datasets:
1. `Figure_4_Treasury_Reallocation.png`: Direct comparison of traditional vs. AIPoX treasury distributions ($1M pool).
2. `Figure_5_Ablation_Decomposition.png`: Stepped capital progression showing independent gains from PoP (+29.8%) and AI (+349.9%).
3. `Figure_6_Empirical_Blockchain_Scalability.png`: Latency and TPS scalability curves across transaction workloads on the EVM testnet.
4. `Data/Figure_7_AI_Anomaly_and_Risk_ROC.png`: Out-of-sample ROC curves confirming discriminatory AUC (0.992 for Autoencoder, 0.940 for Risk DNN).

---

## 7. Raw Console Execution Dump

```text
================================================================================
>>> ON-CHAIN VERIFIED TREASURY ALLOCATION (NO EPSILON, PURE ODDS RATIO):
================================================================================
Proposal_ID  Traditional_Allocation_USD  AIPoX_Allocation_USD Net_Allocation_Delta_Pct
        P-3                   149967.77             735239.55                 +390.27%
        P-1                   150195.56              74154.54                  -50.63%
        P-5                   188328.87              70815.11                  -62.40%
        P-2                   308249.79              62818.13                  -79.62%
        P-4                   203258.00              56972.66                  -71.97%
================================================================================

[+] Output Tables:
    ├── Table_3_Comparative_Prioritization.csv
    ├── Table_4_Treasury_Allocation.csv
    ├── Table_5_Ablation_Study.csv
    ├── Table_6_Sybil_Attack.csv
    ├── Table_7_Whale_Prioritization.csv
    ├── Table_8_Whale_Treasury_Distortion.csv
    └── Table_5_1_Empirical_Scalability.csv

[+] Artifacts Verified: All on-chain allocations sum to exactly $1,000,000.00 USD.
```
```