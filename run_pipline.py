
"""
run_pipeline.py
===============
Master automation runner for the complete AIPoX research pipeline.

Steps:
1. Train and evaluate AI models using datasets in Data.
2. Score proposals.
3. Deploy contracts and execute on-chain transactions on Ganache.
4. Generate verified manuscript tables.
5. Generate publication figures.

The pipeline stops immediately if any step fails.
"""

import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "Data"


def run_command(script_name, working_dir=PROJECT_DIR):
    """Execute a Python script and stop the pipeline on failure."""

    script_path = Path(working_dir) / script_name

    print("\n" + "=" * 80, flush=True)
    print(f"[RUNNING] {script_name}", flush=True)
    print(f"[DIRECTORY] {working_dir}", flush=True)
    print("=" * 80, flush=True)

    if not script_path.is_file():
        print(
            f"[ERROR] Script not found: {script_path}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    command = [sys.executable, str(script_path)]

    try:
        result = subprocess.run(
            command,
            cwd=str(working_dir),
            check=False,
        )
    except OSError as exc:
        print(
            f"[ERROR] Could not start {script_name}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    if result.returncode != 0:
        print(
            f"\n[FAILED] {script_name} "
            f"(exit code: {result.returncode})",
            file=sys.stderr,
            flush=True,
        )
        print(
            "[STOPPED] Remaining pipeline steps were not executed.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(result.returncode or 1)

    print(f"[SUCCESS] {script_name}", flush=True)


def main():
    """Run the complete AIPoX pipeline in sequence."""

    print("=" * 80)
    print("EXECUTING COMPLETE AIPoX REPRODUCIBILITY PIPELINE")
    print(f"Project directory: {PROJECT_DIR}")
    print("=" * 80, flush=True)

    # Validate the Data directory.
    if not DATA_DIR.is_dir():
        print(
            f"[ERROR] Data directory not found: {DATA_DIR}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    # Step 1: AI training, evaluation, and proposal scoring.
    print("\n[STEP 1/4] AI TRAINING AND PROPOSAL EVALUATION", flush=True)

    run_command("1_train_models.py", working_dir=DATA_DIR)
    run_command("2_evaluate_test_metrics.py", working_dir=DATA_DIR)
    run_command("3_score_proposals.py", working_dir=DATA_DIR)

    # Step 2: Blockchain deployment and on-chain execution.
    print("\n[STEP 2/4] GANACHE BLOCKCHAIN EXECUTION", flush=True)

    run_command(
        "1_deploy_and_run_onchain.py",
        working_dir=PROJECT_DIR,
    )

    # Step 3: Generate manuscript tables.
    print("\n[STEP 3/4] GENERATING VERIFIED TABLES", flush=True)

    run_command(
        "2_generate_verified_tables.py",
        working_dir=PROJECT_DIR,
    )

    # Step 4: Generate publication figures.
    print("\n[STEP 4/4] GENERATING PUBLICATION FIGURES", flush=True)

    run_command(
        "3_plot_publication_figures.py",
        working_dir=PROJECT_DIR,
    )

    # Pipeline completed successfully.
    print("\n" + "=" * 80)
    print("[SUCCESS] PIPELINE EXECUTION COMPLETED")
    print("[SUCCESS] All configured stages finished without reported errors.")
    print("=" * 80, flush=True)


if __name__ == "__main__":
    main()
