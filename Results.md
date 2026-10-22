1_deploy_and_run_onchain.py:

[+] Connected to Ganache RPC: http://172.16.22.120:8545
[+] Active Deployer Address: 0x782282339c7c68DB709da39C8B02ae24c0256f36
[+] Initial Balance: 99.85332161382657292 ETH
[*] Installing solc 0.8.19 (evmVersion: paris)...
[*] Deploying PoAValidatorEscrow...
[+] PoAValidatorEscrow deployed at: 0x25abBC2A3131b1D658f40dFC13149f0112b7D2a5
[*] Deploying InvestmentSmartContract...
[+] InvestmentSmartContract deployed at: 0xfe0aC9620352Ed4f550c6EF8FE800d51F773FcAA

[*] Generating 1000 heterogeneous voter agents (Wealth & Behavioral Utility)...
[*] Submitting 1000 real on-chain voting transactions to Ganache...
[*] Progress: [==========] 100% Complete!
[+] Confirmed 1000 on-chain votes in 116.67s (Throughput: 8.6 tx/s)

[*] Finalizing On-Chain Voting Tally (Eq. 4b)...
[*] Committing Neural Model Hash on-chain: 0x80da611f...
[*] Executing Threshold ECDSA Attestation on-chain (4-of-5 signers)...
[+] Attestation confirmed on-chain for P-3 (Risk=0.06, ModelHash Bound)
[+] Attestation confirmed on-chain for P-2 (Risk=0.49, ModelHash Bound)
[+] Attestation confirmed on-chain for P-5 (Risk=0.39, ModelHash Bound)
[+] Attestation confirmed on-chain for P-4 (Risk=0.46, ModelHash Bound)
[+] Attestation confirmed on-chain for P-1 (Risk=0.35, ModelHash Bound)

[*] Triggering Pure Bayesian Odds Treasury Allocation (Eq. 8)...

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

[*] Measuring Scalability Workloads on Ganache...
[+] Benchmarking completed and saved to Table_5_1_Empirical_Scalability.csv

2_generate_verified_tables.py:

================================================================================
>>> ALL VERIFIED ON-CHAIN TABLES REPRODUCED:
================================================================================

[TABLE 3: COMPARATIVE PRIORITIZATION]
Proposal ID  Raw Token Votes (dPoS)  PoP-Adjusted Score V(p)  AI Risk Score R(p)  Traditional Rank  PoP Rank  AIPoX Rank
        P-3                 1867092                  2424173                0.06                 5         3           1
        P-1                 1869928                  2062547                0.35                 4         5           2
        P-5                 2344686                  2338687                0.39                 3         4           3
        P-2                 3837696                  3117614                0.49                 1         1           4
        P-4                 2530553                  2506929                0.46                 2         2           5

[TABLE 4: ALLOCATION OUTCOMES]
Proposal ID  Traditional Allocation (USD)  AIPoX Allocation (USD) Net Allocation Delta
        P-3                     149967.77               735239.55              390.27%
        P-1                     150195.56                74154.54              -50.63%
        P-5                     188328.87                70815.11               -62.4%
        P-2                     308249.79                62818.13              -79.62%
        P-4                     203258.00                56972.66              -71.97%

[TABLE 10: 4-WAY ABLATION STUDY]
            Architecture Variant P-3 Allocation ($) P-2 Allocation ($)  P-3 Rank  P-2 Rank P-3 Net Gain
1. Token-Only (Traditional dPoS)        $149,967.77        $308,249.79         5         1     Baseline
2. Token + PoP (No AI Risk Gate)        $194,713.47        $250,411.77         3         1       +29.8%
     3. Token + AI Gate (No PoP)        $674,670.38         $92,128.50         1         2      +349.9%
   4. Full AIPoX (PoP + AI Gate)        $735,239.55         $62,818.13         1         4      +390.3%

[+] Success: All tables derived directly from on-chain execution.

3_plot_publication_figures.py:

[+] Saved: Figure_4_Treasury_Reallocation.png
[+] Saved: Figure_5_Ablation_Decomposition.png
[+] Saved: Figure_6_Empirical_Blockchain_Scalability.png
