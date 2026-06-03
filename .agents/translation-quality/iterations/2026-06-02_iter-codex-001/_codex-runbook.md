# Codex Runbook

1. Validate the scaffold:
   `python scripts/validate_translation_iteration.py --iter-dir .agents/translation-quality/iterations/2026-06-02_iter-codex-001`
2. Run the baseline pipeline:
   `python scripts/run_iteration.py --iter .agents/translation-quality/iterations/2026-06-02_iter-codex-001`
3. Delegate Prompt Auditor / Mock Scenario Curator / Regression Verifier tasks.
4. Apply prompt or validator changes.
5. Re-run the same iteration and compare scores.
