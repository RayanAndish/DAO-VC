"""
patch_labels.py
===============
Replaces hard-coded proposal IDs with role-based names:
  SAFE  = proposal with the lowest R(p)   (replaces the old "sound" P-3)
  RISKY = proposal with the highest R(p)  (replaces the old "hyped" P-2 and attacked P-4)

Dry-run by default. Pass --apply to write.
Each file is written only if every pattern matched; a backup <file>.bak is created first.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPLY = "--apply" in sys.argv

RISK_01 = 'RISK = dict(zip(df_prop["Proposal_ID"], df_prop["AI_Risk_Score_R_p"]))'
ROLES_01 = ('\nSAFE = min(PIDS, key=lambda p: RISK[p])    # lowest R(p): role fixed by data\n'
            'RISKY = max(PIDS, key=lambda p: RISK[p])   # highest R(p): role fixed by data\n')

RISK_03 = 'risk_map = dict(zip(df_props["Proposal_ID"], df_props["AI_Risk_Score_R_p"]))'
ROLES_03 = ('\nSAFE = min(risk_map, key=risk_map.get)\n'
            'RISKY = max(risk_map, key=risk_map.get)\n')

PATCHES = {
    "01_deploy_and_run_onchain.py": [
        (RISK_01, RISK_01 + ROLES_01),
        ('"P-3"', 'SAFE'),
        ('"P-2"', 'RISKY'),
        ('"P-4"', 'RISKY'),
        ('"P-3 Allocation ($)"', '"Lowest-R Allocation ($)"'),
        ('"P-2 Allocation ($)"', '"Highest-R Allocation ($)"'),
        ('"P-3 Rank"', '"Lowest-R Rank"'),
        ('"P-2 Rank"', '"Highest-R Rank"'),
        ('"P-3 Net Gain"', '"Lowest-R Net Gain"'),
        ('"[SUITE 3] 1,500-identity Sybil attack on P-4"',
         '"[SUITE 3] 1,500-identity Sybil attack on the highest-R proposal"'),
        ('"[SUITE 4] 60% whale attack on P-2"',
         '"[SUITE 4] 60% whale attack on the highest-R proposal"'),
        ('vote for P-4.', 'vote for the highest-R proposal.'),
        ('[*] P-4 allocation change', '[*] {RISKY} allocation change'),
    ],
    "03_plot_publication_figures.py": [
        (RISK_03, RISK_03 + ROLES_03),
        ('"P-3"', 'SAFE'),
        ("risk_of('P-3')", "risk_of(SAFE)"),
        ("risk_of('P-2')", "risk_of(RISKY)"),
        ('"P-3 Allocation ($)"', '"Lowest-R Allocation ($)"'),
        ('"P-2 Allocation ($)"', '"Highest-R Allocation ($)"'),
        ('f"P-3 (sound venture', 'f"{SAFE} (lowest R'),
        ('f"P-2 (hyped venture', 'f"{RISKY} (highest R'),
    ],
}


def patch_file(name, patches):
    path = ROOT / name
    if not path.is_file():
        sys.exit(f"[-] {name} not found")
    text = path.read_text(encoding="utf-8")
    for old, new in patches:
        n = text.count(old)
        if n == 0:
            sys.exit(f"[-] {name}: pattern not found, nothing written: {old!r}")
        print(f"  {n:2d} x {old!r} -> {new!r}", flush=True)
        text = text.replace(old, new)
    leftover = [ln.strip() for ln in text.splitlines() if '"P-' in ln or "'P-" in ln]
    print(f"  remaining quoted P-IDs (review manually): {len(leftover)}", flush=True)
    for ln in leftover:
        print(f"    {ln}", flush=True)
    if APPLY:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text(text, encoding="utf-8")
        print(f"[+] {name} patched (backup: {name}.bak)", flush=True)
    else:
        print(f"[dry-run] {name} not written", flush=True)


def main():
    print(f"[mode] {'APPLY' if APPLY else 'DRY-RUN'}", flush=True)
    for name, patches in PATCHES.items():
        print(f"\n[file] {name}", flush=True)
        patch_file(name, patches)


if __name__ == "__main__":
    main()