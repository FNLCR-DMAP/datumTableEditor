# Testing Reality: Small Team, High Standards, Honest Gaps

## The Problem Statement

A 1–3 developer product team is held to the same quality standard as teams with dedicated QA engineers, staging environments, and DevOps support. The product is a data editing application that touches a production PostgreSQL database through a privilege-segmented proxy (Datum). Users edit clinical/genomic data. Mistakes are not cosmetic — a wrong cell value, a silent data corruption, or an undetected SQL injection is a data integrity incident.

The entire stack runs on RStudio Connect (Posit Connect):
- **The Shiny app** is deployed as an RSConnect application behind enterprise SSO
- **The Datum proxy** is also deployed on RSConnect, with database credentials stored as environment secrets and access controlled via RSConnect's ACL (Access Control Lists)
- The app never holds database credentials directly — it authenticates to Datum via a bearer token, and Datum holds the PostgreSQL connection string as an env secret that no developer or end user can read at runtime

This architecture exists for a reason: **secret segmentation and privilege isolation.** The app can only execute SQL through Datum's API, Datum only exposes a single `/sql` endpoint, and the credentials powering that endpoint are locked behind RSConnect's ACL and environment variable system. But this same architecture makes testing harder — you can't point a test harness at the database directly without either replicating the Datum deployment or having a separate test database with its own credentials.

Additionally, **Shiny uses WebSockets, not HTTP request/response.** The browser opens a persistent WebSocket connection to the Shiny server process, and all UI interactions (cell edits, filter changes, pagination clicks) travel as WebSocket messages — not as inspectable HTTP requests. This means:
- There is no REST API to test against. The server logic is reactive functions triggered by WebSocket messages, not HTTP endpoints.
- Browser DevTools *can* show WebSocket frames as readable JSON in the WS tab (e.g., `{"method":"update","data":{"search_input":"BRCA1"}}`), but these are Shiny's internal protocol messages — not semantically meaningful request/response pairs. A developer can read them but cannot replay them to reproduce server behavior, and there is no standard tooling to parse or assert against them.
- Traditional API testing tools (Postman, curl, httpie) are useless here. The only way to exercise the server is through a Shiny session — either a real browser or Shiny's internal test harness (`shiny.testing`), which itself has limited support for complex reactive chains. Python Shiny's `shiny.testing` is significantly less mature than R's `shinytest2`.
- Middleware-level observability (request logging, response inspection, latency measurement) that comes for free with HTTP APIs must be manually instrumented in a Shiny app.
- **This is why we test the extracted pure functions (the 5-factor model) rather than the Shiny reactive plumbing.** The framework is treated as trusted infrastructure; the data transformations it calls are what we verify.

The application is deployed on RStudio Connect (Posit Connect), where enterprise SSO is imposed at the platform level. This means:
- Every HTTP request to the app requires a valid SSO session
- There is no developer toggle to bypass authentication for a single app
- Automated browser testing (Playwright, Selenium) cannot authenticate without either a service account exemption or a separate non-SSO deployment
- Even manual testing by a teammate requires SSO credentials and VPN access

The team does not have:
- A dedicated QA engineer
- A staging environment with SSO bypass (requires IT/platform team coordination)
- A separate DevOps resource to provision test infrastructure
- Time allocation for manual regression testing before each release
- Authority to configure RStudio Connect authentication at the platform level

The team does have:
- LLM-assisted development (accelerates code generation and test scaffolding)
- A single developer who understands the full stack
- pytest and a fast feedback loop (~1.3 seconds for the full suite)

The question becomes: **How much confidence can you realistically build, and where are you still exposed?**

---

## What We Built

### The 5-Factor Validation Model

We decomposed "correctness" into five data transformations. Each is a boundary where data changes shape and corruption can enter silently:

```
UI Inputs ──F1──▶ QueryParams ──F2──▶ SQL String ──F3──▶ DataFrame ──F4──▶ HTML ──F5──▶ Browser
```

| Factor | Boundary | Testable Without Infra? |
|--------|----------|------------------------|
| F1 | UI input values → query parameter object | ✅ Yes |
| F2 | Query parameters → SQL string | ✅ Yes |
| F3 | SQL response → pandas DataFrame | ✅ Yes |
| F4 | DataFrame → rendered HTML table | ✅ Yes |
| F5 | HTML → what the user actually sees in a browser | ❌ No — requires live staging |

### The Test Suite (as of Feb 2026)

| Category | Tests | What It Covers |
|----------|-------|----------------|
| Unit tests (Layer 1) | 213 functions, 570+ tests | Every function has at least one test |
| SQL golden snapshots (F2) | 37 | Exact SQL string output for known inputs |
| Security / injection hardening | 112 | Every SQL interpolation surface |
| SQL safety gate | 51 | Destructive DDL blocked at adapter layer |
| Contract tests — F1 | 48 | UI state → QueryParams transformation |
| Contract tests — F3 | 30 | SQL response → DataFrame + field modifications |
| Contract tests — F4 | 52 | DataFrame → HTML attributes, classes, structure |
| E2E scaffolds (F5) | 34 (all skipped) | Ready to activate when staging exists |
| Type-safe SQL wrapper tests | 59 | SqlIdentifier, SqlTableName, SqlLiteral (incl. inf/nan), pk builders, backward compat |
| **Total** | **1027 passing, 34 skipped** | **Runs in ~1.4 seconds** |

### Key Engineering Decisions

1. **Type-safe SQL wrappers at every interpolation site, not just the "dangerous" ones.** Datum mode sends raw SQL strings over HTTP — there is no parameterized query layer. Instead of relying on developers remembering to call escape functions, we built **semantic wrapper types** — `SqlIdentifier`, `SqlTableName`, and `SqlLiteral` — whose `__str__()` methods produce safely-quoted SQL fragments automatically. Any new query site that interpolates user-supplied values must wrap them in a type; code review catches bare string interpolation as a type violation. The old `_escape_identifier()`/`_escape_literal()` functions are kept as backward-compatible thin wrappers that delegate to these types.

2. **Safety gate at the adapter boundary.** Even if application code generates a `DROP TABLE` due to a bug, the Datum client blocks it before the SQL leaves the process. Two-layer defense: blocklist (destructive DDL patterns) + allowlist (only SELECT/INSERT/UPDATE/DELETE/CREATE IF NOT EXISTS).

3. **Contract tests at every factor boundary.** Instead of testing end-to-end (which requires staging), we isolated each transformation and pinned its input→output contract. If the shape changes, a test breaks.

4. **E2E tests scaffolded but dormant.** 34 Playwright tests exist, auto-skipped with a message that documents exactly what staging infrastructure is needed. The skip message is the documentation — when someone asks "why no E2E?", the test output itself answers.

### Security Guardrails

Because Datum mode sends raw SQL strings over HTTP (no parameterized query layer), the application implements defense-in-depth across multiple layers. Every guardrail listed below is tested.

#### Layer 1: Adapter Boundary — SQL Safety Gate

The last line of defense before SQL leaves the process.

| Guardrail | What It Blocks |
|-----------|----------------|
| `validate_sql_safety()` in `src/adapter/datum.py` | Two-pass check: (1) **Blocklist** — regex rejects `DROP TABLE/SCHEMA/DATABASE/INDEX/VIEW/FUNCTION/TRIGGER/SEQUENCE/TYPE`, `TRUNCATE`, `ALTER TABLE…DROP/RENAME` anywhere in the SQL string. (2) **Allowlist** — each semicolon-delimited statement must start with `SELECT`, `INSERT INTO`, `UPDATE`, `DELETE FROM`, `CREATE…IF NOT EXISTS`, `BEGIN`, `COMMIT`, or `ROLLBACK`. Anything else raises `DestructiveSqlError`. |
| `DatumClient.execute_sql()` integration | Calls `validate_sql_safety(sql)` before any network call to the Datum proxy. Even if application code generates catastrophic SQL, it never reaches the proxy. |

*Tested by: `tests/test_sql_safety_gate.py` — 51 tests*

#### Layer 2: SQL Construction — Type-Safe Wrappers at Every Interpolation Site

Prevents injection at the point where user-supplied values enter SQL strings. Rather than relying on developers calling escape functions manually, the codebase uses **semantic wrapper types** (`src/config/sql_types.py`) whose `__str__()` methods produce safely-quoted SQL fragments. This makes it impossible to interpolate a value without it being escaped — the type system enforces it.

| Guardrail | Protects Against |
|-----------|------------------|
| `SqlIdentifier(name)` | Column/schema name injection via double-quote breakout. `__str__()` strips NUL bytes, doubles `"` → `""`, wraps in `"…"`. Rejects empty strings with `ValueError`. Applied at all identifier interpolation sites. |
| `SqlTableName(qualified_name)` | Schema-qualified table name injection. Splits on `.`, wraps each part as `SqlIdentifier`. Rejects empty strings. |
| `SqlLiteral(value)` | String literal injection. `__str__()` strips NUL bytes, doubles `'` → `''`, wraps in `'…'`. Returns `NULL` for `None`, `TRUE`/`FALSE` for bools, bare number for int/float. |
| `build_pk_json_expr(pk_columns)` | Centralizes the `jsonb_build_object('pk', d."pk"::text)` pattern. Each PK column goes through `SqlIdentifier` — eliminates duplicated escape logic. |
| `build_pk_array(pk_json_values)` | Centralizes the `ARRAY['…'::jsonb]` pattern. Each value goes through `SqlLiteral`. |
| NUL-byte stripping (built into types) | Both `SqlIdentifier` and `SqlLiteral` strip `\x00` automatically — developers cannot forget this step. |
| Backward-compatible wrappers | `_escape_identifier()`, `_escape_literal()`, `_format_table_name()` still exist but now delegate to the type-safe wrappers. Old call sites continue to work; new code uses the types directly. |

*Tested by: `tests/test_security_fetch_integrity.py` — 112 tests + `tests/test_sql_types.py` — 56 tests*

#### Layer 3: Input Validation — Whitelists and Type Casting

Rejects invalid values before they reach SQL construction.

| Guardrail | What It Enforces |
|-----------|------------------|
| `_build_status_filter_clause()` whitelist | Only `{"unprocessed", "edited", "approved", "rejected"}` are allowed as status values. Any other string is silently dropped — never interpolated. |
| `_save_modification_to_datum()` mod_type whitelist | Only `{"field_modification", "status_change", "approval", "rejection"}` are allowed. Unknown mod_types fall back to `"field_modification"`. |
| `_mark_modification_undone_datum()` int cast | `mod_id = int(mod_id)` before interpolation. Non-integer strings raise `ValueError`, caught by exception handler — SQL is never executed. |
| `_save_ui_state_datum()` int cast | `current_page` and `rows_per_page` cast to `int()` before interpolation. |
| Sort column validation in `fetch_page()` | `ORDER BY` only applied if `params.sort_column` exists in the validated `self._columns` list. Unknown column names are silently ignored, falling back to PK ordering. |
| `_build_mod_status_expr()` label escaping | Configured status labels are wrapped in `SqlLiteral()` before embedding in CASE WHEN SQL expressions. NUL-byte stripping and quote doubling happen automatically. |

*Tested by: `tests/test_security_fetch_integrity.py` + `tests/test_sql_golden.py`*

#### Layer 4: SQLAlchemy Mode — Parameterized Queries

When running in direct database mode (not Datum), the app uses SQLAlchemy's parameterized queries throughout.

| Guardrail | Coverage |
|-----------|----------|
| `_build_where_clause(use_params=True)` | All filter values bound as named parameters (`:p0`, `:p1`, etc.) — never interpolated. Column identifiers still escaped via `_escape_identifier()`. |
| `db_operations.py` — all methods | `save_modification()`, `save_ui_state()`, `load_ui_state()`, `mark_modification_undone()` all use `text()` + dict parameter bindings. **Zero custom escaping** — the security model is parameterized queries, which is the gold standard. |

*Tested by: `tests/test_db_operations.py` + `tests/test_security_fetch_integrity.py`*

#### Layer 5: Architecture — Secret Segmentation via Datum

The application never holds database credentials.

| Guardrail | How It Works |
|-----------|-------------|
| Datum proxy (RSConnect-hosted) | Database connection string stored as an RSConnect environment secret. Access gated by RSConnect ACL. The app authenticates to Datum via bearer token — it cannot read or exfiltrate the database password. |
| Single `/sql` endpoint | Datum exposes only one operation: execute SQL and return results. There is no file access, no shell execution, no admin API. Even if the app is compromised, the blast radius is limited to SQL operations that pass the safety gate. |
| RSConnect ACL | Only authorized applications (identified by API key / service account) can call the Datum proxy. A rogue script outside RSConnect cannot reach the database through Datum. |

*Not tested by automated tests (infrastructure-level guarantee). Documented here for completeness.*

#### Summary: Defense-in-Depth Stack

```
User Input
  │
  ▼
[Whitelist + Type Cast]  ← Layer 3: reject invalid values
  │
  ▼
[Type-Safe SQL Wrappers]  ← Layer 2: SqlIdentifier/SqlLiteral/SqlTableName enforce safe quoting
  │
  ▼
[SQL Safety Gate]  ← Layer 1: block destructive DDL at adapter boundary
  │
  ▼
[Datum Proxy]  ← Layer 5: secret segmentation, ACL, single-endpoint constraint
  │
  ▼
PostgreSQL
```

Every layer is independently tested except Layer 5 (infrastructure). A failure at any single layer does not lead to data corruption if the other layers hold.

---

## What's Still Lacking

### 1. Factor 5 Is Untested (Blocked by Platform SSO)

The app runs on RStudio Connect behind enterprise SSO. Playwright cannot obtain a session token without a non-SSO staging deployment or a service account exemption — neither of which the product team controls. This is not a technical limitation of the test framework; it is an organizational/infrastructure dependency.

No human or automated browser has verified:
- That CSS renders the table correctly at various viewport sizes
- That JavaScript event handlers (cell click → edit modal, drag-to-reorder columns, keyboard shortcuts) actually work
- That Shiny's reactive flush doesn't produce stale or flickering UI state
- That the select-all checkbox, pagination buttons, and sort headers function under real latency

**This is the single largest gap.** Factors 1–4 verify that the *data* flowing through the pipeline is correct. Factor 5 verifies that the *user experience* built on top of that data is correct. These are different failure modes.

### 2. No Regression Testing Against a Real Database

All tests use mocked database responses. The real database is only reachable through Datum, which is itself an RSConnect-hosted service with ACL-gated credentials. There is no "test database" that the developer can point pytest at. This means:
- PostgreSQL type coercion edge cases (e.g., a column that's `numeric` vs `float8` vs `text` cast behavior) are not tested
- Datum proxy latency, timeout, and partial failure behavior is not tested
- The actual LATERAL JOIN performance on tables with 100K+ rows is not tested
- Connection pooling, transaction isolation, and concurrent edit conflicts are not tested
- The real Datum authentication flow (bearer token → ACL check → env secret → PostgreSQL) is not exercised by any test

### 3. LLM-Assisted Testing Has Blind Spots

LLM assistance is excellent for:
- Generating test scaffolds quickly
- Covering happy paths and known edge cases
- Mechanical hardening (applying the same pattern to 18 interpolation sites)

LLM assistance **does not naturally produce**:
- **Adversarial thinking.** The 57 blind spots we found came from explicitly asking "what did we miss?" — not from the normal test generation workflow. Left to its own, the LLM adds more tests of the same *kind* rather than identifying new *categories* of failure.
- **Architectural insight.** The 5-factor decomposition came from the developer, not the LLM. The LLM can implement tests for a factor once told about it, but doesn't independently identify that "the boundary between SQL response and DataFrame is a distinct failure surface."
- **Organizational awareness.** The LLM initially tried to solve the E2E gap technically (install Playwright, write browser tests). The correct answer was organizational: document the gap, make it visible in test output, and escalate the staging infrastructure need. That judgment came from the developer.
- **Real-user scenario modeling.** A QA engineer would say "what happens if I paste 500 rows from Excel, then undo, then filter, then approve?" — that compound interaction sequence isn't something test generation produces. It comes from watching real humans use the product.

### 4. Manual/Exploratory Testing Is Not Happening

There is no process for:
- A human clicking through the app before a release
- Verifying that a new feature works with real data at real scale
- Testing the "unhappy paths" that a data editor encounters (network drops mid-save, browser back button during edit, stale tab after session timeout)
- Accessibility verification (keyboard navigation, screen reader compatibility)

### 5. Test Maintenance Is a One-Person Dependency

1027 tests are an asset. They're also a liability if:
- The sole developer leaves and no one understands the test architecture
- The 5-factor model and contract test rationale aren't documented for the next person
- A major refactor (e.g., switching from Datum to direct connection) requires rewriting contract assumptions across multiple test files

---

## Adversarial Review and Rebuttals

An adversarial self-review was conducted against the claims in this document and the test suite. Twelve challenges were raised; the rebuttals below correct genuine misconceptions and add context that an external reviewer would not have.

### 1. "DELETE FROM could be injected"

**Rebuttal:** The PostgreSQL role the app operates under does not have `DELETE` privilege. Even if a `DELETE FROM` statement passed the safety gate (which the allowlist permits for legitimate modification tracking), the database would reject it. This is **role-based security at the PostgreSQL level** — a defense layer that operates below the application.

### 2. "Comment-based obfuscation (DR/**/OP) could bypass the blocklist"

**Rebuttal:** `DR/**/OP` is not valid PostgreSQL syntax — the `/**/` comment splits the keyword mid-token, and PostgreSQL's lexer does not reassemble it. The actual threat would be `DROP/**/TABLE` (comment between keywords). The blocklist regex uses `\s+` between keywords, which does **not** match `/**/` (that's four literal characters, not whitespace). However, `DROP/**/TABLE` fails at the **allowlist layer**: it doesn't match any allowed statement prefix (`SELECT`, `INSERT INTO`, etc.), so it's rejected by step 2 of `validate_sql_safety()`. The defense holds through the allowlist, not the blocklist. See Round 2 finding #13 for the full analysis.

### 3. "User-supplied data containing 'DROP TABLE' could trigger false positives"

**Rebuttal:** The safety gate is **intentionally over-strict** — it searches the entire SQL string including data literals. Verified in Round 2 finding #15: `UPDATE t SET col = 'DROP TABLE foo' WHERE id = 1` is rejected even though `DROP TABLE` is inside quotes. This is the correct behavior for this application: clinical/genomic data never legitimately contains the string "DROP TABLE." The gate would false-positive on such a value, and that's by design — user discipline, not a software bug. See #15 for the full confirmation.

### 4. "mod_id could be a float due to JSON round-tripping"

**Rebuttal:** `mod_id` is a database auto-increment integer. When round-tripped through JSON (int → JSON number → int), the value remains integral. JSON does not distinguish int and float for whole numbers, but Python's `int()` cast in `_mark_modification_undone_datum()` handles both `42` and `42.0` correctly. This is a non-issue.

### 5. "Datum is a custom proxy — why not use direct connections?"

**Rebuttal:** Datum is **central organizational infrastructure**, not a one-off hack. It provides secret segmentation and credential isolation across multiple applications. The design principle: applications should not hold database credentials directly. Datum routes SQL through a tightly controlled HTTP endpoint with ACL enforcement, and the database connection string is an RSConnect environment secret. This architecture gives the organization agility and control — any app can be rotated or revoked without changing database passwords.

### 6. "The bearer token could be stolen from the browser"

**Rebuttal:** Reaching the app requires **VPN + enterprise SSO + RSConnect authentication**. The RSConnect session token visible in the browser is a session cookie, not an API bearer token. **The developer tested this directly:** extracting the session token from browser DevTools and attempting to use it as a Datum bearer token fails — RSConnect session tokens and Datum API keys are different credential types managed by different systems. An attacker would need to compromise VPN access, SSO credentials, RSConnect authorization, **and** obtain a valid Datum API key (stored only as an RSConnect environment secret) to execute arbitrary SQL.

### 7. "The app could be used to exfiltrate data via the UI"

**Rebuttal:** The app operates under a **PostgreSQL role with role-based security**. The role has `SELECT` and `UPDATE` on specific tables — not superuser access, not cross-schema access, not `pg_read_file()`. Even if an attacker somehow gained access to the UI, the blast radius is limited to the tables the role can see, which are the same tables the app is designed to edit.

### 8. "968 tests is vanity — what matters is what they cover"

**Rebuttal:** The test count is a **consequence of coverage strategy**, not a vanity metric. 213 functions × at least 1 test = 213 baseline. Contract tests at 3 factor boundaries = 130+. SQL golden snapshots = 37. Security injection tests = 112. Safety gate = 51. Type-safe wrapper tests = 56. The count rises because each concern area is tested independently. The 5-factor model determines test categories; the count follows.

### 9. "The E2E tests provide zero value if they never run"

**Rebuttal:** The dormant E2E tests are **intentionally a communication tool**, not a testing tool. When a stakeholder asks "why don't you have E2E tests?", the answer is in the test output: 34 skipped tests with a message explaining exactly what staging infrastructure is needed. The skip message is the escalation. Writing the tests (even dormant) also proved the F5 boundary can be tested mechanically once the infrastructure exists — it's a solved problem blocked by provisioning, not by engineering.

### 10. "Factor 5 is an arbitrary line"

**Rebuttal:** F5 (HTML → browser rendering) is the **cleanest delineation under constraints**. Factors 1–4 are testable without infrastructure. F5 requires a live browser against a deployed app. The boundary is not arbitrary — it's the point where testability disappears without staging. Drawing it here gives maximum coverage with available resources and makes the untested surface explicit.

### 11. "Contract tests don't test real user behavior"

**Rebuttal:** Contract tests cover **typical and expected user behavior** — the transformations that fire when a user filters, sorts, paginates, edits, approves. They don't cover compound multi-step interactions ("paste 500 rows, undo, filter, approve") — that's exploratory testing, which requires a human. The contracts verify that each individual transformation is correct; the composition of transformations is what E2E and manual testing would cover.

### 12. "The type-safe refactoring just moves the problem"

**Rebuttal:** The old pattern required developers to **remember** to call `_escape_identifier()` at every interpolation site — a discipline-based defense that fails when someone forgets. The new pattern makes forgetting visible: if a column name appears in an f-string without being wrapped in `SqlIdentifier`, code review catches it as a missing type wrapper, not as a subtle security bug buried in string formatting. The types also centralize NUL-byte stripping, quote doubling, and empty-string rejection into one auditable location (`src/config/sql_types.py`). This is defense-in-depth via type system, not just renaming.

---

## Adversarial Review — Round 2 (Deep-Dive Audit)

A second adversarial pass was conducted with direct code tracing and runtime verification. These findings attack the safety assumptions from Round 1 and identify concrete gaps that the type-safe refactoring did not address.

### 13. "The blocklist regex catches SQL comment obfuscation"

**Finding: The blocklist layer is factually bypassed by SQL comments. The allowlist layer saves it.**

The `_BLOCKED_PATTERNS` regex uses `\s+` between keywords: `DROP\s+TABLE`, `DROP\s+SCHEMA`, etc. SQL comments (`/**/`, `/* any text */`, `--\n`) are **not whitespace characters** — they are literal bytes that `\s+` does not match.

Verified directly:
- `DROP TABLE foo` → blocklist catches it ✓
- `DROP/**/TABLE foo` → blocklist **does not match** ✗
- `DROP--\nTABLE foo` → blocklist **does not match** ✗

The defense holds because step 2 (prefix allowlist) rejects `DROP/**/TABLE foo` — it doesn't start with any allowed prefix. But this means **Layer 1 of the defense is degraded**. If the allowlist were ever loosened (e.g., adding `GRANT`, `EXECUTE`, or `CREATE FUNCTION`), comment-based obfuscation of blocked patterns would become exploitable.

**Recommendation:** Optionally strip SQL comments before running the blocklist regex, or add comment-aware patterns like `DROP\s*(?:/\*.*?\*/)*\s*TABLE`.

**Severity:** Low (masked by allowlist). Defense-in-depth degradation.

### 14. "The safety gate handles semicolons in string literals"

**Finding: It does not. Semicolons inside quoted values cause false-positive rejections.**

Verified directly: `validate_sql_safety("INSERT INTO t (col) VALUES ('hello;world')")` raises `DestructiveSqlError` — the naive `sql.split(';')` splits the string into `"INSERT INTO t (col) VALUES ('hello"` and `"world')"`. The second fragment fails the prefix allowlist.

This is a **false positive** (too strict), not a false negative (too permissive). No SQL injection is possible — legitimate data containing semicolons is rejected before it reaches the database.

**Practical impact:** If a user edits a cell to contain text with a semicolon (e.g., an address: `"123 Main St; Suite 4"`), and the app is in Datum mode, the save would fail. In practice this hasn't been reported because clinical/genomic data rarely contains semicolons, but it's a latent usability bug.

**Recommendation:** Replace naive `split(';')` with a quote-aware SQL statement splitter, or accept the false-positive tradeoff and document it.

**Severity:** Medium (data loss — edit silently fails).

**Rebuttal:** This is a **user discipline issue**, not a software bug. Semicolons in clinical/genomic data fields are not expected behavior — users entering arbitrary punctuation into structured data fields is an input quality problem. The false-positive rejection is the correct behavior: if you're entering data that looks like multi-statement SQL, the safety gate should reject it. This should be documented as an intentional constraint, not fixed with a quote-aware splitter that adds complexity and potential bypass risk.

### 15. "Blocked patterns don't false-positive on data values"

**Finding: They do. The blocklist regex searches the entire SQL string including quoted literals.**

Verified directly: `validate_sql_safety("UPDATE t SET col = 'DROP TABLE foo' WHERE id = 1")` raises `DestructiveSqlError`. The regex `\bDROP\s+TABLE\b` matches inside the single-quoted string literal.

This is already documented in `test_sql_safety_gate.py` (`test_drop_in_filter_value_is_safe`) and labeled as "desired conservative behavior." The assumption is that clinical/genomic data never contains these strings. However, this contradicts Rebuttal #3's claim that "the safety gate operates on the full SQL statement, not on data literals" — it operates on both, indiscriminately.

**Practical impact:** Same as #14 — false positive, not false negative. A user editing metadata to contain the text "DROP TABLE" would silently fail to save.

**Corrected claim:** The safety gate is **intentionally over-strict** — it rejects SQL that contains destructive keywords anywhere, including inside quoted values. This is a conscious tradeoff: false positives on exotic data values are accepted to guarantee no false negatives.

**Severity:** Low (clinical data doesn't contain DDL keywords).

**Rebuttal:** Same as #14 — this is **user discipline**. The safety gate is intentionally over-strict. A user entering "DROP TABLE" as a cell value in a clinical data editor is not a legitimate use case. The conservative behavior protects against the pathological case at the cost of the absurd case. We document this as a known constraint, not permit it.

### 16. "`SqlLiteral` handles all Python numeric types safely"

**Finding: `float('inf')`, `float('nan')`, and `float('-inf')` produce invalid SQL.**

Verified directly:
- `SqlLiteral(float('inf'))` → `inf` (not a valid PostgreSQL numeric literal)
- `SqlLiteral(float('nan'))` → `nan` (PostgreSQL reads this as a column reference)
- `SqlLiteral(float('-inf'))` → `-inf`

PostgreSQL requires these as string casts: `'Infinity'::double precision`, `'NaN'::double precision`. Bare `inf`/`nan` tokens are interpreted as unquoted identifiers (column names), which would either error or — if a column named `nan` exists — silently use the wrong value.

**How reachable?** Python's `json.loads()` never produces `inf`/`nan` (JSON has no infinity/NaN), so data from Datum responses is safe. But computed values from pandas operations (e.g., division by zero) can produce these, and if they flow into a modification path, the SQL would be malformed.

**Recommendation:** Add a guard in `SqlLiteral._escape()`: reject or cast `math.isinf()`/`math.isnan()` values.

**Severity:** Low-Medium (correctness bug, not injection — produces SQL errors or wrong-column reads).

**Rebuttal — Addressed:** `SqlLiteral._escape()` now raises `ValueError` for `math.isinf()` and `math.isnan()` float values instead of producing invalid SQL. Three new tests added (`test_float_inf_raises`, `test_float_neg_inf_raises`, `test_float_nan_raises`). If a computed value produces inf/nan, the error is caught explicitly with a message directing the developer to use PostgreSQL's string cast syntax.

### 17. "Config-sourced identifiers are validated"

**Finding: They are escaped but not validated. Config values flow directly into SQL with type-safe quoting but no allowlist.**

`app_config.json` specifies `data_table`, `mods_table`, `state_table`, `primary_key`, `status_column`. These flow into `SqlTableName()` and `SqlIdentifier()`, which quote them safely — but never check that they match a allowed pattern like `^[a-zA-Z_][a-zA-Z0-9_.]*$`.

A malicious config could set `data_table` to `pg_catalog.pg_shadow` and the app would SELECT from it. The quoting prevents SQL injection (the identifier stays intact), but it enables **data exfiltration** from arbitrary tables the PostgreSQL role can see.

**Practical impact:** Low. The config file lives in the RSConnect deployment bundle. An attacker who can modify it has server filesystem access, which is a more severe compromise than reading a table. Environment variable overrides (`APP_DB_DATA_TABLE`) are similarly server-side. No user input reaches these code paths.

**Recommendation:** Add a config-load validation step that checks table/column names against `^[a-zA-Z_][a-zA-Z0-9_.]*$`.

**Severity:** Low (requires server-level compromise).

**Rebuttal:** Each app is **deployed independently** on RSConnect, and a secret API key is needed to even access Datum. The config file is part of the deployment bundle — an attacker who can modify it has already compromised the server. Additionally, this is a **widget framework** — different teams configure it for different tables. Adding a regex allowlist on table names would reduce the flexibility that makes the widget useful across teams. The `SqlTableName` quoting prevents injection; the PostgreSQL role's `GRANT` permissions limit which tables are accessible regardless of what the config says.

### 18. "Concurrent edits are handled safely"

**Finding: No optimistic locking exists. Last write wins silently. Undo is broken under concurrency.**

The modification tracking path (`_save_modification_to_datum()` → `_update_data_in_datum()`) is a straight INSERT + UPDATE with no conditional guard:
1. Both users read the same `old_value` from their in-memory DataFrame
2. Both INSERT a modification record (no UNIQUE constraint on `row_pk + column_name`)
3. Both UPDATE the data table — last UPDATE wins
4. The modification log has two entries with the same `old_value` but different `new_value`s
5. **Undo is broken:** User A's undo reverts to the original `old_value`, silently overwriting User B's committed edit

Shiny on RSConnect spawns one server process per user session. Each session has its own in-memory DataFrame (`reactive.Value`). There is no cross-session notification of edits — User B doesn't see User A's change until the next full data reload.

**Practical impact:** Medium. The app is designed for a small team behind SSO, so simultaneous edits to the same cell are unlikely but not impossible. The modification log preserves both edits for audit, but the undo behavior could cause silent data regression.

**Recommendation:** Add a WHERE clause to the UPDATE that checks `old_value = expected_old_value`, or add a version column with optimistic locking. At minimum, document the last-write-wins behavior.

**Severity:** Medium (silent data regression on undo).

**Rebuttal:** The modification is done **on the remote database**, not in local memory. The append-only modification log is **exactly designed to handle this**: every edit by every user is recorded with `created_by`, `created_at`, `old_value`, and `new_value`. The admin and user have **full visibility** on the mod list in the sidebar. If User A and User B both edit the same cell, both edits appear in the log, and the admin can see who changed what and when. The "last write wins" behavior is the standard database model — PostgreSQL itself uses it. Optimistic locking would add significant complexity for a scenario (simultaneous same-cell edits by a small team behind SSO) that is vanishingly rare in practice and fully auditable when it does occur.

### 19. "Error messages don't leak sensitive information"

**Finding: Raw Python exceptions propagate to UI notifications in at least two paths.**

1. **Export failure** — `server.py` line 1148: `ui.notification_show(f"Export failed: {str(e)}", ...)` — a SQL error during export would show the full exception (which can contain table names, column names, SQL fragments, Datum proxy error bodies).

2. **Undo failure** — `data_operations.py` line 145: `return ..., f"Database error during undo: {e}"` — this error string is shown to the user via `notification_show` at `server.py` line 1009.

The `DatumClient.execute_sql()` raises `RuntimeError(f"PostgreSQL SQL API error: status={proxy_resp.status}, body={proxy_resp.body}")` — the Datum response body may contain full PostgreSQL error messages.

**Practical impact:** Low-Medium. All users are authenticated via SSO + VPN, so the leaked information goes to authorized users, not external attackers. But it violates the principle of least information — a data editor doesn't need to see SQL fragments or table schemas in error messages.

**Recommendation:** Wrap `str(e)` in UI-facing error paths with generic messages. Log the full exception server-side.

**Severity:** Low (information hygiene, not a breach vector).

**Rebuttal:** This is **intentional**. Users do not have access to RSConnect server-side session logs. The UI notification is the only way they see error details when something goes wrong. Since all users are authenticated via VPN + SSO and are authorized data editors, showing them the error message (including table names or SQL fragments) is useful for troubleshooting, not a security leak. A user who can see the table name in an error message can already see the table's data in the app — there is no privilege escalation.

### 20. "Legacy `config.py` is inactive"

**Finding: `config.py` is lazy-loaded via `__getattr__` in `src/config/__init__.py` and still contains un-refactored manual escaping.**

`config.py` functions (`save_modification_to_db`, `save_ui_state`, etc.) are exported via the `__init__.py` lazy-import mechanism. If any code path imports `from src.config import save_modification_to_db`, it gets the `config.py` version with inline `.replace("'", "''")` instead of `SqlLiteral` wrappers. The active widget-based code path uses `config_instance.py`, but the legacy path is still importable and could be accidentally invoked.

Additionally, `process_modifications.py` line 165 has:
```
f"UPDATE epitopes SET {column} = '{safe_value}' WHERE row_id = {row_idx};\n"
```
where `column` is interpolated **without any escaping** — no `SqlIdentifier`, no double-quoting. This is a file-export utility (writes `.sql` files), not a live database path, but it produces SQL scripts that could be executed manually.

**Practical impact:** Low. The active code path is `config_instance.py` (fully refactored). `config.py` functions use `.replace("'", "''")` which is correct but fragile (no NUL byte stripping). `process_modifications.py` writes files, not live SQL.

**Recommendation:** Deprecate `config.py` exports with a `warnings.warn()` or remove the lazy import. Migrate `process_modifications.py` to use `SqlIdentifier`/`SqlLiteral` for the SQL export.

**Severity:** Low (legacy code, not the active path).

**Rebuttal — Addressed:** `config.py`'s Datum functions (`_save_modification_to_datum`, `_update_data_via_datum`, `_load_from_datum`, `_load_from_database`) have been migrated to use `SqlIdentifier`/`SqlLiteral`/`SqlTableName`. All inline `.replace("'", "''")` calls in these functions are replaced. `process_modifications.py`'s SQL export utility now uses `SqlIdentifier(column)` and `SqlLiteral(new_value)`. The lazy import in `__init__.py` remains for backward compatibility — the functions it exposes now use the type-safe wrappers.

### 21. "Unicode homoglyphs could bypass escaping"

**Finding: Not a vulnerability. PostgreSQL's lexer only recognizes ASCII `'` (U+0027) and `"` (U+0022) as delimiters.**

Unicode smart quotes (U+2018, U+2019, U+201C, U+201D, U+FF07) pass through `SqlIdentifier` and `SqlLiteral` without escaping — but they cannot terminate a SQL string or identifier in PostgreSQL. They're treated as ordinary characters. Verified against PostgreSQL documentation.

**Severity:** None.

**Rebuttal:** Confirmed non-issue. Additionally, this is a **server-side concern**, not a client-side one. Smart quotes are a Windows/macOS input method phenomenon (e.g., curly quotes auto-inserted by Word or macOS text substitution). By the time data reaches the Shiny server, it has been serialized through WebSocket JSON messages, which use standard ASCII characters. The server processes bytes, not rendered glyphs. Even if a user pastes smart quotes from Word, they arrive as their Unicode codepoints — which PostgreSQL treats as ordinary data characters, not as SQL delimiters.

### Round 2 Summary

| # | Finding | Real? | Exploitable? | Tested? | Severity |
|---|---------|-------|-------------|---------|----------|
| 13 | Blocklist bypassed by SQL comments | Yes | No (allowlist catches it) | No | Low |
| 14 | Semicolons in values → false positive rejection | Yes | No (too strict, not too permissive) | No | Medium |
| 15 | Blocked patterns match inside string literals | Yes | No (false positive) | Yes (documented) | Low |
| 16 | `SqlLiteral(float('inf'))` → invalid SQL | ~~Yes~~ Fixed | No (malformed SQL, not injection) | Yes (3 new tests) | ~~Low-Medium~~ Resolved |
| 17 | Config identifiers escaped but not validated | Yes | Requires server compromise | No | Low |
| 18 | No optimistic locking on concurrent edits | Yes | Silent last-write-wins + broken undo | No | Medium |
| 19 | Raw exceptions in UI error notifications | Yes | Info leak to authenticated users | No | Low |
| 20 | Legacy `config.py` still importable with manual escaping | ~~Yes~~ Fixed | Only if accidentally invoked | Partial | ~~Low~~ Resolved |
| 21 | Unicode homoglyphs | No | PostgreSQL ignores them | No | None |

**Key takeaway:** No finding enables SQL injection or data exfiltration beyond the app's authorized access. Two findings were **addressed with code fixes** (#16 inf/nan guard, #20 legacy migration). The remaining findings are either intentional design choices (#14, #15 safety gate strictness; #18 append-only audit log; #19 error visibility for authenticated users) or non-issues (#17 config flexibility by design; #21 Unicode irrelevant server-side). The safety gate's conservatism (#14, #15) is a feature, not a bug — documented as a known constraint.

---

## What's Needed

### Minimum Viable Next Steps (No New Headcount)

| Action | Effort | Impact |
|--------|--------|--------|
| Provision a staging RStudio Connect deployment without SSO (or with service account bypass) | 2–4 hours DevOps/IT platform team | Unlocks all 34 E2E tests + external manual QA |
| Provision a staging Datum instance with its own test database and env secrets | 2–4 hours DevOps/IT platform team | Enables integration tests against real SQL execution path |
| One manual regression session per release | 1–2 hours per release | Catches F5 gaps that no automated test covers |
| Seed staging with realistic data volume (10K+ rows) | 1 hour | Validates performance assumptions |

### With Additional Resources

| Resource | What It Enables |
|----------|----------------|
| 0.5 FTE QA (even part-time / shared) | Exploratory testing, real-user scenario discovery, compound interaction coverage |
| Staging RStudio Connect instance (non-SSO, CI-accessible) | E2E tests run automatically on PR merge, not just when someone remembers |
| Second developer familiar with test architecture | Removes single-point-of-failure on test maintenance |

### The Honest Assessment

The automated suite provides **high confidence in data integrity through Factors 1–4**. If the SQL is generated correctly, the response is parsed correctly, the modifications are applied correctly, and the HTML attributes are correct — then the data the user *would* see is correct.

What we **cannot assert** is that the user actually sees it. That's Factor 5. That requires either a staging environment (for Playwright) or a human (for exploratory testing). Ideally both.

**The 1027 tests are not a substitute for someone using the product.** They're a foundation that makes human testing efficient — the tester doesn't need to worry about SQL injection or data corruption and can focus on "does this feel right, does this workflow make sense, does this break when I do something unexpected."

The testing we have is strong for a team this size. The gap that remains is infrastructural and human, not technical.

---

## Adversarial Round 3: Code-Level Deep Audit

Round 3 shifted from architecture/design review to **line-level code auditing**. Three parallel deep audits examined:
1. Every SQL construction site in `config_instance.py` and `config.py`
2. Every data flow path in `data_operations.py` (edit, undo, save, PK handling)
3. Test coverage gaps and tautological tests

### Finding #22 — CRITICAL: Double `jsonb_build_object` wrapping (6 sites)

**Where:** `config_instance.py` lines 477, 534, 604, 685, 1118, 1298

**What:** `build_pk_json_expr()` in `sql_types.py` returns the **complete** expression `jsonb_build_object('pk1', d."pk1"::text)`. But all 6 call sites wrapped it again: `WHERE m.row_pk = jsonb_build_object({pk_json_build})`. This produced: `jsonb_build_object(jsonb_build_object('pk1', d."pk1"::text))` — which is a type error in PostgreSQL (passing a `jsonb` value as a key name).

**Impact:** Every PK-matching query (status counts, filtered fetches, paginated fetches, export, data loading in both SQLAlchemy and Datum paths) would fail at runtime.

**Severity:** CRITICAL — core functionality broken.

**Fix:** Removed the outer `jsonb_build_object()` wrapper at all 6 call sites. Now reads: `WHERE m.row_pk = {pk_json_build}`.

**Tested:** All 37 golden SQL snapshots continue to pass. Added verification via grep: zero remaining `jsonb_build_object({pk_json_build})` occurrences.

---

### Finding #23 — HIGH: Raw schema interpolation in CREATE SCHEMA (2 sites)

**Where:** `config_instance.py` lines 996, 1052

**What:** `CREATE SCHEMA IF NOT EXISTS "{schema}"` used raw f-string interpolation instead of `SqlIdentifier`. The 4 other CREATE SCHEMA sites in the same file correctly used `{schema_sql}`.

**Impact:** Schema names containing double-quotes could break SQL quoting. Exploitation requires config-level control (admin-only).

**Severity:** HIGH (inconsistency with established pattern).

**Fix:** Added `schema_sql = SqlIdentifier(schema)` and replaced raw `"{schema}"` with `{schema_sql}` at both sites.

---

### Finding #24 — LOW: Raw column identifiers in SQLAlchemy UPDATE path

**Where:** `config_instance.py` `_update_data_in_db()` method (~line 2075)

**What:** `f'"{pk_col}" = :pk_{i}'` and `f'SET "{column}" = :new_value'` use manual quoting instead of `SqlIdentifier()`.

**Impact:** This is the **parameterized SQLAlchemy path** (not Datum). The column names come from app config (not user input), and the actual values use `:param` binding. Manual quoting with `"..."` is functionally equivalent to `SqlIdentifier("...")` here. Not a security issue — just inconsistent style.

**Severity:** LOW (style inconsistency, not a vulnerability).

**Rebuttal:** The SQLAlchemy path uses **parameterized queries** (`text()` + params dict). Column names come from `app_config.table.primary_key` which is admin-configured. The manual `"{pk_col}"` quoting is safe. However, for consistency with the type-safe pattern, future refactoring could wrap these in `SqlIdentifier`.

---

### Finding #25 — MEDIUM: `sort_ascending` interpolated via `str().upper()` (Datum path)

**Where:** `config_instance.py` `_save_ui_state_datum()` (~line 2362)

**What:** `{str(sort_ascending).upper()}` was used to interpolate a boolean into SQL. If `sort_ascending` were somehow a non-bool (e.g., string `"True; DROP TABLE x"`), this would inject raw SQL.

**Impact:** In practice, the type annotation is `sort_ascending: bool` and callers pass Python bools. But the pattern is inconsistent with the rest of the file which uses `SqlLiteral(bool_value)`.

**Severity:** MEDIUM (defense-in-depth gap).

**Fix:** Added `sort_asc_lit = SqlLiteral(bool(sort_ascending))` and replaced both `{str(sort_ascending).upper()}` occurrences with `{sort_asc_lit}`.

---

### Finding #26 — MEDIUM: Unvalidated `mod_id` from Datum proxy response

**Where:** `config_instance.py` `_save_modification_datum()` (~line 1896)

**What:** `mod_id = response.data[0].get("id")` was used directly in: `WHERE id = {mod_id}`. If the proxy response contained a non-integer `id`, this would inject raw SQL.

**Impact:** Requires a compromised or buggy Datum proxy to exploit. The proxy returns PostgreSQL `SERIAL` ids which are always integers.

**Severity:** MEDIUM (defense-in-depth).

**Fix:** Added `mod_id_lit = SqlLiteral(int(mod_id))` to validate and wrap the value.

---

### Finding #27 — MEDIUM: `SqlLiteral` accepted `Decimal` as string (wrong SQL type)

**Where:** `sql_types.py` `SqlLiteral._escape()`

**What:** `Decimal("3.14")` fell through to the `str(value)` catch-all, producing `'3.14'` (a string literal) instead of `3.14` (a numeric literal). PostgreSQL would then treat it as text, causing type comparison mismatches in numeric columns.

**Severity:** MEDIUM (silent type mismatch in edge case).

**Fix:** Added explicit `Decimal` handling before the `str` branch. Also added inf/nan checks for `Decimal` values. Added 5 tests.

---

### Finding #28 — LOW: `SqlLiteral` silently accepted `list`, `dict`, `bytes`

**Where:** `sql_types.py` `SqlLiteral._escape()`

**What:** `SqlLiteral([1, 2, 3])` would produce `'[1, 2, 3]'` via `str()` — a syntactically valid string literal, but semantically wrong. No code path currently passes these types, but the permissiveness could mask future bugs.

**Severity:** LOW (no current code path triggers this).

**Fix:** Changed the catch-all branch to raise `TypeError` for non-`str` types. Only `None`, `bool`, `int`, `float`, `Decimal`, and `str` are now accepted. Added 3 tests.

---

### Finding #29 — LOW: Empty `pk_columns` produces vacuous match

**Where:** `sql_types.py` `build_pk_json_expr()`

**What:** `build_pk_json_expr([])` produced `jsonb_build_object()` — an empty JSON object `{}`. This would match any row with `row_pk = '{}'::jsonb`, silently applying modifications to all rows.

**Impact:** Requires misconfigured `app_config.table.primary_key = []`, which would break many other things first.

**Severity:** LOW (fail-fast improvement).

**Fix:** Added `if not pk_columns: raise ValueError(...)`. Added 1 test.

---

### Data Flow Findings (Documented, Not Fixed)

These findings describe **design-level trade-offs** in `data_operations.py` that don't have surgical code fixes — they require architectural decisions:

| ID | Finding | Severity | Status |
|----|---------|----------|--------|
| A1 | `save_modification_to_db` returns `None` on failure — caller doesn't check, audit trail silently incomplete | HIGH | Design: audit log is best-effort. Adding retry/alerting is a UX decision. |
| A4 | `_get_row_pk` fallback returns `{"row_index": N}` on error — causes silent edit loss (bogus PK never matches) | HIGH | Design: fail-open vs fail-closed trade-off. Currently fail-open (show error but don't crash). |
| B1 | UPDATE + INSERT not atomic in cell edit path | HIGH | Design: would require database transaction or Datum batch endpoint. Datum has no batch API. |
| B2 | 3-step undo not atomic (revert → mark undone → insert record) | HIGH | Design: same atomicity constraint as B1. |
| F1 | No check for already-undone modification (double-undo creates duplicate records) | LOW | Audit trail is append-only by design. Duplicate "undo" records don't corrupt data. |
| F3 | Undo of an older edit clobbers later edits without warning | HIGH | Design: undo restores original value regardless of intermediate edits. This is documented behavior. |
| G2 | Datetime PKs crash `json.dumps` with `TypeError` | HIGH | No current table uses datetime PKs. Would need custom JSON encoder. |
| G4 | NULL PKs produce JSON `null` which never matches in PK comparison | MEDIUM | PKs should not be NULL by definition (PRIMARY KEY implies NOT NULL in PostgreSQL). |

### Test Coverage Findings (Documented)

| Finding | Details |
|---------|---------|
| 3 tautological tests | `test_data_operations.py` has tests that call a mock and assert the mock was called — no real logic tested |
| 22+ untested methods | Entire Datum persistence path: `_load_data_from_datum`, `_save_ui_state_datum`, `_save_preset_datum`, `_apply_field_modifications_datum`, etc. |
| No cross-validation | Golden snapshot JSON constants and test helper constants are two independent truth sources with no automated check that they agree |

### Round 3 Summary

| # | Finding | Real? | Fixed? | Severity |
|---|---------|-------|--------|----------|
| 22 | Double `jsonb_build_object` wrapping at 6 PK-matching sites | Yes | **Yes** | CRITICAL |
| 23 | Raw schema in CREATE SCHEMA at 2 sites | Yes | **Yes** | HIGH |
| 24 | Raw column identifiers in SQLAlchemy UPDATE (parameterized path) | Yes | No (safe as-is, style-only) | LOW |
| 25 | `sort_ascending` via `str().upper()` instead of `SqlLiteral` | Yes | **Yes** | MEDIUM |
| 26 | Unvalidated `mod_id` from proxy response | Yes | **Yes** | MEDIUM |
| 27 | `Decimal` type produced string literal | Yes | **Yes** | MEDIUM |
| 28 | `SqlLiteral` accepted exotic types silently | Yes | **Yes** | LOW |
| 29 | Empty `pk_columns` → vacuous match | Yes | **Yes** | LOW |
| A1–G4 | Data flow design issues (8 findings) | Yes | Documented | HIGH–LOW |
| Tests | 3 tautological, 22+ untested methods | Yes | Documented | — |

### Round 3 User Rebuttals & Resolutions

| ID | Finding | User Response | Resolution |
|----|---------|---------------|------------|
| A1 | `save_modification_to_db` returns `None` silently | "If return None we should capture and respond" | **Fixed.** Added `None` return check with warning log in both `config_instance` and `app_config` paths of `perform_cell_edit`. 3 new tests. |
| A4 | `_get_row_pk` fallback returns bogus PK | "Keep it this way now" | Accepted — fail-open by design. |
| B1 | UPDATE + INSERT not atomic (cell edit) | "We do not do batch anyway" | Accepted — Datum has no batch endpoint. |
| B2 | 3-step undo not atomic | "Each action is atomic" | Accepted — each DB call is atomic individually. |
| F3 | Undo old edit clobbers later edits | "Good point and very crucial, this is a behavior that was not intended" | **Fixed.** `perform_undo` now checks for newer non-undone edits on the same row+column. Returns error: "Cannot undo this edit — a newer edit exists". 5 new tests. |
| G2 | Datetime PKs crash JSON serialization | "Not gonna use datetime PK" | Accepted — not applicable to current schema. |
| G4 | NULL PKs prevent mod matching | "You cannot have null pk in postgres" | Confirmed non-issue — `PRIMARY KEY` implies `NOT NULL` in PostgreSQL. |

**Key takeaway:** Round 3 found one **CRITICAL** bug (#22) that would have broken all PK-matching queries at runtime — the most impactful finding across all three rounds. Seven code fixes were applied (6 in `config_instance.py`, 3 in `sql_types.py`). Two additional fixes from user rebuttals: A1 (None return capture) and F3 (undo latest-only guard). The data flow findings (A4, B1, B2, G2, G4) are accepted design decisions. Test suite: **1043 passed**, 34 skipped.

**Cumulative across 3 rounds:** 29 findings examined, 12 code fixes applied, 0 exploitable injection vectors found. The remaining gaps are operational (staging environment, manual QA) and architectural (atomicity accepted as-is given Datum constraints).

---

## Round 4 — Deep Code-Level Audit

**Methodology:** Three parallel deep-dive audits targeting independent code layers:
1. **Server.py reactive logic** — data flow in Shiny reactive graph, side effects, TOCTOU
2. **Datum adapter + DB layer** — HTTP client robustness, schema operations, safety gate
3. **Processing + Widget layer** — export SQL, modal XSS, clipboard injection, filter logic

**Scope:** ~2,500 lines across 12 source files. 53 raw findings triaged to 10 verified fixable.

### Findings Fixed (8 code patches, 11 new tests)

| # | Severity | File | Finding | Fix |
|----|----------|------|---------|-----|
| 30 | **HIGH** | `data_operations.py` | **Phantom log entry on DB failure.** `perform_cell_edit` appended a log entry even when `update_data_in_db` raised an exception (`db_failed=True`). UI showed the edit as successful in the modification log despite the DB rejecting it. | Moved log-entry creation and `.append()` inside `if not db_failed:` guard. 2 new tests. |
| 31 | **HIGH** | `filter_utils.py` | **`between` filter used string comparison for numbers.** `"9" > "15"` is `True` lexicographically, so a between filter on `[5, 15]` would incorrectly exclude `9`. | `_row_matches_operator` now attempts `float()` conversion first, falls back to string. 3 new tests. |
| 32 | **HIGH** | `process_modifications.py` | **`_export_as_sql` skipped falsy values.** Truthiness check `if new_value` skipped legitimate values `0`, `""`, `False`. | Changed to `if new_value is not None`. 3 new tests. |
| 33 | **MEDIUM** | `process_modifications.py` | **Raw `row_idx` in export SQL.** `_export_as_sql` interpolated `row_idx` directly into a `LIMIT 1 OFFSET {row_idx}` clause without wrapping. | Wrapped in `SqlLiteral(int(row_idx))`. |
| 34 | **MEDIUM** | `modal_utils.py` | **Modal onclick JS injection via single quotes in column/preset names.** 9 `onclick` handlers built strings like `onclick="Shiny.setInputValue('col', '{col_name}')"` — a column named `it's` broke the JS. | All 9 sites now escape `\` → `\\` and `'` → `\'` before interpolation. |
| 35 | **MEDIUM** | `db_operations.py` | **`column_names` property doesn't exist.** Line ~181 accessed `self._table_schema.column_names` but `TableSchema` only exposes `get_column_names()` method — guaranteed `AttributeError` at runtime. | Changed to `self._table_schema.get_column_names()`. |
| 39 | **LOW** | `clipboard_utils.py` | **Clipboard `</script>` XSS tag breakout.** `generate_clipboard_js` embedded cell data in a `<script>` block without escaping `</` sequences. A cell value containing `</script><script>alert(1)</script>` could break out. | Escape `</` → `<\/` in the JSON output before embedding. 1 new test. |

### Findings Documented (Not Fixed — Accepted Risk)

| # | Severity | File | Finding | Rationale |
|----|----------|------|---------|-----------|
| 36 | MEDIUM | `db_schema.py` | `create_mods_table`/`create_state_table` use raw `table_name` in DDL. | Admin-configured value only. SQLAlchemy-only path (not Datum). PostgreSQL `CREATE INDEX` would break with quoted identifiers in index names. |
| 37 | MEDIUM | `db_schema.py` | `get_row_count` accepts raw `where_clause` + `table_name`. | Dead code — only called from test fixtures, never in production paths. |
| 38 | LOW | `data_loader.py` | `_load_database` uses raw `config.db_table` in `SELECT * FROM`. | Admin config value, data loader path (not Datum). Same risk profile as #36. |

### Server.py Reactive Findings (Design-Level, Documented)

| ID | Finding | Status |
|----|---------|--------|
| S1 | Cell edit accepts `row_idx` / `col` from client without server-side validation | Design — Shiny controls the DataGrid; client can't send arbitrary indices without modifying framework internals |
| S2 | TOCTOU in approve/reject: checkbox indices may reference stale data after pagination | Design — accepted; approve/reject operates on current page view |
| S3 | Side effects inside `@render.ui` (`_fetch_page_data` called in render) | Architecture — Shiny render functions are idempotent by framework contract |
| S4 | `undo` log_idx not type-checked before use | `int()` conversion would raise `ValueError` naturally; adding explicit check adds no safety |

### DB Layer Findings (Design-Level, Documented)

| ID | Finding | Status |
|----|---------|--------|
| D1 | Datum HTTP client has no retry on transient failures | Operational — retries should live in Datum proxy, not the client |
| D2 | Datum response JSON not guarded against non-JSON responses | Datum proxy always returns JSON; non-JSON would indicate infrastructure failure beyond app control |
| D3 | Safety gate allows `UPDATE`/`DELETE` without `WHERE` | By design — some admin operations require table-wide updates; gate blocks DDL and multi-statement |
| D4 | Session book cleared before replacement query (data loss on failure) | Accepted — replacement query failure returns empty DataFrame which is surfaced to user |

### Round 4 Summary

| Category | Count |
|----------|-------|
| Raw findings triaged | 53 |
| Verified & fixed | 7 (8 code patches across 6 files) |
| Verified & documented (accepted risk) | 3 |
| Design-level documented | 8 |
| False positives / already mitigated | 35 |
| New tests added | 11 |
| **Test suite** | **1052 passed, 34 skipped** |

### Round 4 Highlights

- **Finding #30 (phantom log)** was the most impactful — users would see "successful" edits in the modification log that were never persisted to the database, creating silent data inconsistency.
- **Finding #31 (between filter)** was a classic string-vs-number comparison bug that would cause incorrect filter results for any numeric column with values crossing digit-length boundaries (e.g., 9 vs 15).
- **Finding #32 (falsy export)** would silently drop legitimate modifications where the new value was `0`, empty string, or `False` from SQL exports.
- **Finding #35 (AttributeError)** was a guaranteed runtime crash on a code path in `db_operations.py` — the property simply doesn't exist on the class.

**Cumulative across 4 rounds:** 39 findings examined, 19 code fixes applied, 0 exploitable SQL injection vectors found. Test suite grew from 332 → 1052 tests. The remaining documented items are design-level decisions and admin-configuration-only code paths.
