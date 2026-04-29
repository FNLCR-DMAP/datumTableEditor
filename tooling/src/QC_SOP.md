# QC Standard Operating Procedure (Agent Reference)

## Quick Run

```bash
bash tooling/sop_qc.sh            # full 8-step pipeline
bash tooling/sop_qc.sh --step 5   # single step only
```

## Pipeline Steps

| Step | Script | What it does | Fails on |
|------|--------|--------------|----------|
| 1 | `tooling/src/qc/generate_qc.py` | AST-based function extraction per module → `qcmetric/*.json` | Parse errors |
| 2 | `tooling/src/qc/check_test_coverage.py` | Cross-ref public functions vs test file tokens | — (report only) |
| 3 | `tooling/src/sql/extract_golden_sql.py` | Snapshot all QueryBuilder + DataFetcher SQL → `qcmetric/sql_golden.json` | Import errors |
| 4 | `pytest tests/test_sql_golden.py` | Pin SQL strings against golden snapshot | SQL drift |
| 5 | `pytest tests/ --cov=src` | Full test suite + line coverage | Test failures |
| 6 | `tooling/src/qc/check_frontend.py` | JS/CSS syntax validation → `qcmetric/frontend_qc.json` | JS errors (not warnings) |
| 7 | `tooling/src/qc/generate_type_qc.py` | Type annotation coverage → `qcmetric/server_variable_type_qc.json` | — (report only) |
| 8 | `tooling/src/qc/generate_mapping.py` | Unused function detection → `qcmetric/server_function_qc.json` | — (report only) |

## When to Run

- **Before commit**: Run full pipeline. All 8 steps must pass.
- **After modifying SQL/query logic**: Re-extract golden SQL (step 3), then verify (step 4).
- **After modifying JS/CSS**: Run step 6 alone for fast feedback.
- **After adding new public functions**: Run step 2 to check test coverage gap.

## Commit & Deploy

```bash
bash commit_and_deploy.sh "message" [lp|igv|all|none]
```

This script already runs `pytest` internally before committing. The SOP QC pipeline is a superset — use it for deeper validation.

## Git Commit Hook Setup

To enforce QC before every commit:

```bash
cat > .git/hooks/pre-commit << 'EOF'
#!/usr/bin/env bash
set -e
echo "Running QC gate (steps 4-5)..."
python -m pytest tests/test_sql_golden.py -x -q
python -m pytest tests/ -x -q
echo "QC passed."
EOF
chmod +x .git/hooks/pre-commit
```

For the full pipeline as a hook (slower, ~3s):

```bash
cat > .git/hooks/pre-commit << 'EOF'
#!/usr/bin/env bash
set -e
bash tooling/sop_qc.sh
EOF
chmod +x .git/hooks/pre-commit
```

## Agent Workflow

1. Make code changes
2. Run `bash tooling/sop_qc.sh`
3. If step 3 (golden SQL) fails after intentional SQL changes, re-run step 3 to update the snapshot, then step 4 will pass
4. If step 6 (frontend) reports warnings — acceptable. Only errors block.
5. Commit with `bash commit_and_deploy.sh "message" none` (no deploy) or with a target

## Known Limitations

- Step 2 (function coverage) is token-based, not execution-based. The real line coverage comes from step 5.
- Step 6 (frontend QC) does not run ESLint — it's a heuristic checker. Regex/string content can occasionally confuse brace counting.
- Steps 7-8 are informational reports. They don't gate the pipeline.
- `server.py` and `ui.py` have low line coverage (~1-12%) because they're Shiny runtime — only e2e tests cover them.

## Output Artifacts

All QC outputs land in `qcmetric/`:

```
qcmetric/
  server_qc.json              # step 1
  ui_qc.json                  # step 1
  app_qc.json                 # step 1
  config_qc.json              # step 1
  utils_qc.json               # step 1
  db_qc.json                  # step 1
  data_qc.json                # step 1
  processing_qc.json          # step 1
  sql_golden.json             # step 3
  frontend_qc.json            # step 6
  server_variable_type_qc.json # step 7
  server_function_qc.json     # step 8
  app_mapping.json            # step 8
```
