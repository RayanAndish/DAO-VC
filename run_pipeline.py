"""
run_pipeline.py
===============
Master runner for the AIPoX reproducibility pipeline. Stops at the first failing step.

Steps
  1. Data/1_train_models.py      train R(p) and B(u), compute ModelHash
  2. Data/2_evaluate_test_metrics.py
  3. Data/3_score_proposals.py   five proposals from the held-out test split
  4. 1_deploy_and_run_onchain.py Ganache suites (requires GANACHE_MNEMONIC)
  5. 2_generate_verified_tables.py
  6. 3_plot_publication_figures.py

Before running, stale generated outputs are removed so that nothing from an older run
can be used silently.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "Data"

GENERATED = [
    DATA_DIR / "models" / "model_hash.json",
    DATA_DIR / "Table_Proposals_Feature_Profiles.csv",
    DATA_DIR / "Table_3_AI_Validation_Metrics.csv",
    PROJECT_DIR / "OnChain_Proposal_State_Raw.csv",
    PROJECT_DIR / "OnChain_Test_Log.csv",
    PROJECT_DIR / "Table_3_Comparative_Prioritization.csv",
    PROJECT_DIR / "Table_4_Treasury_Allocation.csv",
    PROJECT_DIR / "Table_5_Ablation_Study.csv",
    PROJECT_DIR / "Table_6_Sybil_Attack.csv",
    PROJECT_DIR / "Table_7_Whale_Prioritization.csv",
    PROJECT_DIR / "Table_8_Whale_Treasury_Distortion.csv",
    PROJECT_DIR / "Table_8b_Whale_Worst_Case.csv",
]


def run_step(label, script, cwd):
    path = Path(cwd) / script
    print("\n" + "=" * 80, flush=True)
    print(f"[STEP] {label}: {script}  (cwd={cwd})", flush=True)
    print("=" * 80, flush=True)
    if not path.is_file():
        sys.exit(f"[ERROR] script not found: {path}")
    result = subprocess.run([sys.executable, str(path)], cwd=str(cwd), check=False)
    if result.returncode != 0:
        print(f"[FAILED] {script} exit code {result.returncode}. Pipeline stopped.", file=sys.stderr, flush=True)
        sys.exit(result.returncode)
    print(f"[OK] {script}", flush=True)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not DATA_DIR.is_dir():
        sys.exit(f"[ERROR] Data directory not found: {DATA_DIR}")
    if not os.getenv("GANACHE_MNEMONIC"):
        sys.exit("[ERROR] GANACHE_MNEMONIC is not set. Export it before running the pipeline.")

    removed = []
    for p in GENERATED:
        if p.exists():
            p.unlink()
            removed.append(p.name)
    print(f"[*] removed {len(removed)} stale generated file(s)", flush=True)

    run_step("AI training", "1_train_models.py", DATA_DIR)
    run_step("AI evaluation", "2_evaluate_test_metrics.py", DATA_DIR)
    run_step("Proposal scoring", "3_score_proposals.py", DATA_DIR)
    run_step("Ganache execution", "1_deploy_and_run_onchain.py", PROJECT_DIR)
    run_step("Verified tables", "2_generate_verified_tables.py", PROJECT_DIR)
    run_step("Publication figures", "3_plot_publication_figures.py", PROJECT_DIR)

    print("\n" + "=" * 80, flush=True)
    print("[DONE] Pipeline finished. Provenance (SHA-256):", flush=True)
    for p in GENERATED:
        if p.exists():
            print(f"  {sha256(p)}  {p.relative_to(PROJECT_DIR)}", flush=True)
    print("=" * 80, flush=True)


if __name__ == "__main__":
    main()
