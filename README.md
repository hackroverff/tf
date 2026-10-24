# Pulp Riot Juice Co. — Dragon Passion Control Tower

A deterministic Python 3.11 + Streamlit planning prototype for **“The Dragon Passion Problem at Pulp Riot Juice Co.”** (TransfiNITTe 2026). Demand, Supply, Inventory, Distribution and Transportation share one data model.

**No external APIs. No automatic execution. Every recommendation requires the required human approver; peak-season trade-offs require COO.**

## 1. Quick start

```bash
cd /home/user/tf
python3.11 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python generate_data.py              # writes data/ and runs 63 checks
python -m pytest -q                  # 23 tests
streamlit run app.py
```

For a network/live-preview run:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

Generated CSVs are included. Regenerate after changing config. Kaleido provides real chart PNG downloads; openpyxl provides the active-scenario Excel workbook.

## 2. Application map

The top toggle switches **Last summer replay** and **Next summer plan** content. The sidebar groups ten pages:

| Group | Page | Main content |
|---|---|---|
| Overview | **Control Tower** | Four KPI cards, five area statuses, latent vs realised demand or forward plan, depot-cover heatmap |
| Overview | **What Went Wrong** | Loss waterfall, FIFO write-off calibration, LOW/BASE/HIGH avoided-loss chart and capture rates |
| Deep dives | **Demand** | Annotated launch/viral/notice/closure timeline, first Amber/Red, weekly reaction reforecast, launch and BOM scenarios |
| Deep dives | **Supply** | 1/2/3-week closures, 0–4-week buffer optimisation with air premium, air-only comparison, joint bottle+pulp capacity |
| Deep dives | **Causal Link Map** | Quantified Demand↔Supply edges and source flags |
| Decisions | **Recommendations** | Planner/S&OP Lead/COO roles, COO-gated peak approvals, action/time audit log, zero execution |
| Decisions | **Scenario Replay** | Date-limited actual-vs-model replay, or next-summer approval-ready checklist |
| Decisions | **Budget & Impact** | ₹2.5 cr cap gauge, build/run costs, benefit/cost and eight-month adoption roadmap |
| Evidence & system | **Assumptions & Sensitivity** | Initial-ramp lead chart, one-click controls, source lineage and verification status |
| Evidence & system | **Architecture & Data Quality** | Quality gates, active-scenario reconciliation, fallback simulator and scaling evidence |

Every page has a takeaway, four main KPI cards, one or two main charts, and bounded evidence tables in expanders. Key charts have **Download PNG** buttons. The sidebar’s **one-click Excel export** includes raw data, config, model tables, sensitivity, checks, current risks and approval log.

### Live scenario controls

- Initial DP QC ramp and 31 March planner notice (editable scenario inputs)
- Root-cause split and capture-rate multiplier
- Annual closure probability
- QC summer share; GT/MT resize proportionally

Changing ramp, notice or QC share regenerates deterministic data and reruns active-scenario reconciliation. The 4× peak remains restricted to **DP QC**. Capture rates cap at 100%. These are assumption scenarios, not fitted forecasts or executions.

## 3. Current headline results

### Reconciliation and physical balance

```text
96.00 m latent summer bottles
− 7.68 m stock-out-censored bottles (8%)
= 88.32 m realised summer sales
```

Economic impact is **₹14.7456 cr contribution + ₹3.20 cr air + ₹6.00 cr write-offs = ₹23.9456 cr**. Lost revenue of ₹46.08 cr is context and is not added again.

`python generate_data.py` currently reports **63 PASS / 0 FAIL**. New checks cover production→depot→sales conservation, opening mix, shelf-life rules and write-off calibration:

```text
9,254,237 opening
+ 121,000,000 production receipts
− 114,320,000 sales
− 892,881.45 write-off bottles
= 15,041,355.55 closing bottles
```

Maximum absolute daily balance error is zero; closing stock is non-negative. Opening DP stock is zero.

### Write-offs

The old eight-row MPB/GC allocation by depot weight × flavor share has been replaced by FIFO stock aging toward channel cutoffs. Current output is **18 DP MT/QC rows across nine depots**:

- Aged bottles allocated to MT/QC: **892,881.45**
- Uncalibrated value: **₹5.3572887 cr**
- Case calibration target / reported total: **₹6.0000000 cr**
- Calibration factor: **1.11996951**
- Disclosed calibration gap: **₹0.6427113 cr**

MT/QC reject below 60 days remaining. GT’s unspecified rule is an editable config toggle, defaulting to no cutoff. The ₹6 cr total is a calibration target, not independent validation of the allocation.

### Detection

- First Amber: **18 March 2026**
- First Red: **19 March 2026**
- Planner notice: **31 March 2026** (editable assumption)
- Headline **Amber reaction lead: 13 days**
- Separate **Red confirmation lead: 12 days**

Initial ramps of 1.0×/1.5×/2.0×/2.5×/3.0× produce Amber leads of **9/11/13/13/13 days**. Red does not trigger at 1.0–2.0× and is not interpolated.

Monthly WAPE (30%) and synthetic weekly reforecast WAPE (10.47695%) are confined to a footnote. They are not presented as a live forecast-improvement claim.

### Buffer and co-packer

The objective is now:

```text
annual carry/storage + expected contribution loss + expected air premium
```

Current comparison covers 0–4 weeks, conditional 1/2/3-week closures, and air-only:

- Recommendation: **+2 weeks**
- Expected annual objective: **₹1.6759198 cr**
- Net expected benefit vs zero buffer: **₹4.1904665 cr**
- Recoverable working capital: **₹6.4458453 cr**, outside the selected program budget
- Break-even annual closure probability: **17.1409%**
- Air-only expected premium: **₹4.7235412 cr**
- Buffer-vs-air recommendation margin: **₹3.0476214 cr**

Air-only assumes every shortage kilogram can be flown in time and causes no residual stock-out. The buffer objective conservatively retains both contribution loss and air premium for residual shortage; these are scenario conventions, not a probabilistic operating simulation.

The joint 4× weekly plan uses only **208,345 co-packer bottles**. **3,241,347 bottles** of would-be co-packer output are blocked by pulp and **45,436,336 bottles** of scenario demand are unmet. Opening pulp only is credited; in-house draws first and balances carry forward.

### Avoided loss

**LOW ₹6.325632 cr / BASE ₹11.643392 cr / HIGH ₹16.432512 cr**, with effective capture **26.4167% / 48.6243% / 68.6243%**.

This is **ASSUMPTION-BASED, NOT SIMULATED**: case-total allocation × assumed capture rates. It is not a confidence interval or guaranteed saving. Action and transfer benefits are not added again.

## 4. Configuration and source lineage

Operational config includes:

- `case.json`, `assumptions.csv`
- `flavors.csv`, `channels.csv`, `depots.csv`, `pulps.csv`, `bom.csv`, `suppliers.csv`, `routes.csv`
- `last_year_mix.csv` and `channel_shelf_life.csv`
- seasonality, allocation/supply options, loss attribution, budget and roadmap tables

Labels are **CASE-STATED**, **DERIVED FROM CASE**, and **MY ASSUMPTION**. Rows combining invented economics with case fields are not labelled pure case facts. `VERIFIED_AGAINST_CASE_TEXT=Y/N` is present in config and registers; all current values are **N** until the original case text is supplied.

`assumptions_register.csv` currently contains **251 unique rows = 62 CASE-STATED + 10 DERIVED FROM CASE + 179 MY ASSUMPTION**. Rebuild it with:

```bash
python build_assumptions_register.py
```

Formerly documentary IDs A036, A055–A057, A059–A065 and A067–A069 now drive code. Removed legacy stock-noise/multiplier IDs A020–A024 are listed in `CHANGELOG.md`. The ₹2.5 cr cap remains an explicit hardcoded project constraint in `src/budget.py`; ₹ crore unit conversion is a numerical convention, not a forecast input.

### Add a flavor, depot or channel

1. Add its config row and keep shares/weights summing to one.
2. Add flavor BOM and `last_year_mix.csv` rows; add channel shelf-life rows for a new channel.
3. Add pulp/supplier/route rows only if new entities are needed.
4. Regenerate and rerun tests.

`tests/test_config_scaling.py` proves config-only flavor/depot/channel scaling while preserving the exact 96 m summer total. Case-specific DP/PP events remain explicit logic rather than generic claims about arbitrary new products.

## 5. Generated data

| Dataset | Purpose |
|---|---|
| `daily_sales.csv` | Date × flavor × channel × depot; latent demand, sales, losses and GT proxy orders |
| `depot_flow_daily.csv` | Opening, production receipts, sales, write-offs, closing, FIFO age and conservation |
| `depot_stock_weekly.csv` | Weekly stock, trailing current-demand cover and mismatch |
| `depot_writeoffs.csv` / `writeoff_reconciliation.csv` | FIFO/channel write-offs and raw-vs-calibrated reconciliation |
| `production_daily.csv` / `plant_copacker_capacity.csv` | Scheduled vs actual production and fixed asset capacity |
| `pulp_inventory_daily.csv` / `pulp_inbound.csv` | Pulp balances, inbound, air cost and cover |
| `qc_sell_through.csv` / `monthly_forecast.csv` | QC latency and monthly forecast diagnostics |
| `supplier_routes.csv` | Supplier/route exposure with component source fields |
| `viral_profile.csv` / `event_calendar.csv` | Editable scenario events and source/verification labels |
| `assumptions.csv` / `assumptions.xlsx` | Compiled MY ASSUMPTION register with verification field |

`true_demand_bottles` is synthetic ground truth and is not an operational feature. See **`data_derivation.md`** for the plain-language one-page derivation.

## 6. Budget and approvals

Selected first-year package: **₹1.77 cr**, leaving **₹0.73 cr** below the cap: ₹1.00 cr build and ₹0.77 cr run + contingency. Co-packer retainer and buffer principal are excluded; hidden selected working capital is ₹0. Base simple payback is **1.82 months**, undiscounted and assumption-based.

Adoption is designed for **15 spreadsheet planners**, **vendor-run IT**, and **no internal data/AI team**: Excel import/export, one weekly depot workbook, one alert owner, planner challenge rights, read-only parallel run, training, outage drills, rollback and vendor hypercare.

Approvals enforce **Planner / S&OP Lead / COO** roles. The required approver must match, and peak-season approvals require COO. Logs contain approver, action and timestamp. `execution_status` remains exactly `NOT_EXECUTED_HUMAN_DECISION_ONLY`; role selection is not authenticated identity and no ERP transaction occurs.

## 7. Validation

```bash
python generate_data.py
python -m pytest -q
python validate_demand.py
python validate_supply.py
python validate_links.py
python validate_recommendations.py
python validate_replay.py
python validate_control_budget.py
```

Current core results:

- **63/63** generator reconciliation checks
- **23/23** pytest tests
- **14/14** application data-quality checks
- All **10 pages** and both top-toggle modes passed Streamlit runtime smoke tests without exceptions
- Final default workbook validated from bytes: **5,702,869 bytes / 75 sheets**, including ramp sensitivity, scenario settings and conservation
- Key PNGs validated by PNG signature; fixed seed and no external APIs preserved

## 8. Honest limitations

1. **Case verification is pending.** Original case text is absent; every case-marked register row remains N.
2. **Synthetic mechanics are not empirical validation.** No live forecast accuracy, causal uplift or realised saving is claimed.
3. **Stock-out loss allocation remains calibrated.** The 7.68 m distribution is not derived from physical production, although resulting realised sales are conserved through depot flow.
4. **Write-off calibration is not independent evidence.** Raw FIFO value is ₹5.3572887 cr and the ₹6 cr target adds a disclosed ₹0.6427113 cr gap; fractional bottles are expected channel allocations, not transaction records.
5. **Forward capacity is deliberately narrow.** No unconfirmed inbound, line-eligibility, changeover or yield matrix is invented.
6. **Buffer economics are scenario conventions.** Air-only assumes perfect timely coverage; the residual buffer objective conservatively includes both loss and air premium.
7. **Avoided loss is assumption-based, not simulated.** Root-cause shares and capture rates lack historical intervention identification.
8. **Replay remains a static buffer stress-test**, not a second physical simulation. Weather/landslide input is manual.
9. **Operational detail is missing.** GT has no outlet feed; transfers lack truck/lane capacity; role names are not authenticated; nothing integrates with or executes in ERP.

## Repository map and historical artifacts

```text
app.py                         Ten-page Streamlit shell, scenario pipeline and Excel export
generate_data.py               Generator + 63-check reconciliation CLI
data_derivation.md             Plain-language one-page derivation
CHANGELOG.md                   Exact before/after numbers and unresolved items
build_assumptions_register.py  Reproducible 251-row register builder
config/                        Case, entity, scenario and source/verification config
data/                          Generated CSVs, checks and assumptions workbook
src/                           Analytics, sensitivity, figures, UI and page renderers
tests/                         23 detector/supply/workflow/scaling/config/UI tests
validate_*.py                  Focused module sanity scripts
```

`Pulp_Riot_Dragon_Passion_Audit.pdf`, `build_audit_pdf.py`, `audit_sensitivity.py` and `sensitivity_results.csv` are **pre-change audit artifacts**. The PDF’s 50-check/244-row figures and the 73-row sensitivity file describe the earlier baseline, not current outputs.
