# Changelog

## 2026-10-24 — Data/logic correction and ten-page dashboard rebuild

### Validation gates by requested section

| Gate | Generator reconciliation | Pytest | Additional evidence |
|---|---:|---:|---|
| Pre-change baseline | 50 PASS / 0 FAIL | 16 passed | Baseline metrics saved before edits |
| A — data and conservation | **63 PASS / 0 FAIL** | **17 passed** | Zero depot balance error; config-change output test added |
| B — logic and approvals | **63 PASS / 0 FAIL** | **21 passed** | Air break-even, pulp feasibility, COO and sensitivity tests added |
| C — UI and exports | **63 PASS / 0 FAIL** | **23 passed** | All 10 pages + both toggle modes passed runtime smoke tests; PNG and workbook tests added |
| D — documentation | **63 PASS / 0 FAIL** | **23 passed** | 251-row register rebuilt; six focused validators and 20 page-mode runs passed; final workbook 5,702,869 bytes / 75 sheets |

### Exact before/after numbers

| Measure | Before | After | Why it changed |
|---|---:|---:|---|
| Write-off allocation | **8 rows**, MPB/GC in overstock-profile depots; depot weight × flavor share | **18 rows**, DP MT/QC across **9 depots**; FIFO batch aging and channel cutoffs | Allocation is now driven by remaining shelf life, not a hardcoded stale-mix split |
| Reported write-offs/discounts | **₹6.0000000 cr** | **₹6.0000000 cr** | ₹6 cr retained only as case calibration target |
| Uncalibrated write-off value | Not separately reported | **₹5.3572887 cr** | 892,881.45 aged DP bottles × ₹60 before calibration |
| Calibration gap | Not separately reported | **+₹0.6427113 cr**, factor **1.11996951** | Gap is disclosed rather than hidden |
| Buffer recommendation | **+1 week** | **+2 weeks** | Expected air premium entered the objective; search is explicitly 0–4 weeks |
| Buffer expected annual objective | **₹1.0482322505 cr** | **₹1.6759197659 cr** | New optimum includes carry/storage + expected contribution loss + expected air premium |
| Net expected benefit vs zero buffer | **₹0.0946128260 cr** | **₹4.1904665248 cr** | Avoided expected air premium is included consistently |
| Break-even closure probability | **53.9128%** in the earlier no-air-premium sensitivity | **17.1409077%** | Recomputed from the corrected objective at the selected option |
| Air-only comparison | Not in recommendation | **₹4.7235412142 cr** expected premium; buffer advantage **₹3.0476214483 cr** | Separate strategy assumes all shortage can be air-freighted in time |
| Headline detection lead | **12 days**, based on first Red | **13 days**, based on first Amber | Amber is the first actionable reaction signal |
| Red confirmation lead | Conflated with headline | **12 days** | Reported separately from Amber |
| First Amber / Red | **18 / 19 March 2026** | **18 / 19 March 2026** | Dates unchanged; interpretation corrected |
| Avoided loss LOW / BASE / HIGH | **₹6.325632 / ₹11.643392 / ₹16.432512 cr** | **₹6.325632 / ₹11.643392 / ₹16.432512 cr** | Default arithmetic unchanged; label is now exactly **ASSUMPTION-BASED, NOT SIMULATED** |
| Effective LOW / BASE / HIGH capture | Not shown with headline | **26.4167% / 48.6243% / 68.6243%** | Capture is always visible with the range |
| 4× unmet scenario demand | **10.323105 m** with independent bottle capacity | **45.436336 m** with joint bottle+pulp feasibility | Co-packer can no longer consume unavailable pulp |
| 4× co-packer output | Bottle-capacity-only estimate | **208,345 bottles**; **3,241,347 bottles** blocked by pulp | Opening stock only, in-house first, closing pulp carried forward |
| Generator checks | **50** | **63** | Added volume, shelf-life, calibration and six conservation checks; two obsolete definitions corrected |
| Tests | **16** | **23** | Added config-change, air objective/break-even, pulp feasibility, COO, sensitivity, PNG and Excel tests |
| App pages | **8** | **10** | Added What Went Wrong and Assumptions & Sensitivity; grouped navigation and replay/plan toggle |
| Assumptions register | **244 rows = 62 / 10 / 172** | **251 rows = 62 / 10 / 179** | New mix/shelf/config/model assumptions and corrected live references; categories are CASE / DERIVED / ASSUMPTION respectively |

### A — data and configuration

- Added `config/last_year_mix.csv`: MPB/GC/PP/DP/DB = 50%/20%/30%/0%/0%. Opening stock is **9,254,237 bottles**, three weeks of preseason run rate, not forward true demand.
- Added `depot_flow_daily.csv`: opening + production receipts − sales − write-offs = closing, with FIFO batch age and depot×flavor mismatch. Full-period closing is **15,041,355.55 bottles**.
- Added `writeoff_reconciliation.csv` and `config/channel_shelf_life.csv`. MT/QC use the explicit 60-day rule; GT remains an editable no-cutoff assumption.
- Added production/receipt/sales/closing conservation checks. Production receipts tie to **121,000,000 bottles**; depot sales issues tie to **114,320,000 bottles**.
- Made co-packer output jointly pulp-feasible and forwarded capacity, frozen/bottled shelf-life and exposure config into analytics.
- Made A036, A055–A057, A059–A065 and A067–A069 live. Added a config-change output test for the editable initial ramp.
- Removed obsolete **A020–A024** (old stock noise and event/depot stock multipliers). They no longer determine physical stock and are not presented as live knobs.
- Normalized source labels, separated supplier/route component lineage, and added `VERIFIED_AGAINST_CASE_TEXT`. All current values are **N** pending original case text.
- Corrected two obsolete checks rather than hiding failures: aging write-offs need not be confined to overstock-profile depots, and exported assumptions now use `MY ASSUMPTION`.

### B — logic and decision governance

- Included expected air premium in buffer objective and net benefit; added 0–4 week, 1/2/3-week closure and air-only comparisons with break-even probability.
- Added ramp sensitivity: initial 1.0×/1.5×/2.0×/2.5×/3.0× gives Amber leads **9/11/13/13/13 days**. Red is absent at 1.0–2.0× and appears at 2.5×/3.0×.
- Replaced headline forecast-improvement framing with reaction lag. Synthetic WAPE values remain only in a footnote.
- Added one-click root-cause, capture, closure-probability and QC-share controls through a shared scenario/export pipeline.
- Enforced Planner / S&OP Lead / COO roles. Required approver must match; COO is mandatory for peak-season approvals. Logs contain approver, action and timestamp; nothing executes.

### C — dashboard and exports

- Rebuilt a light, wide consulting dashboard with deep teal/navy accents, status-only traffic colors, takeaway headlines, four main KPI cards per page, consistent tables and grouped navigation.
- Added annotated Plotly timelines, loss waterfall, depot-cover heatmap, ramp-lead chart, buffer/closure comparisons and budget gauge.
- Added replay/plan top toggle with different KPI/chart content and a next-summer action checklist.
- Moved raw tables and assumptions into bounded expanders; removed main-view debug clutter.
- Added real PNG downloads via Kaleido and active-scenario Excel export. The C-gate workbook was **5,702,303 bytes / 75 sheets**; after D's final lineage-label cleanup it is **5,702,869 bytes / 75 sheets** (+566 bytes), including ramp, scenario and conservation tables.

### D — documentation

- Added plain-language `data_derivation.md`.
- Updated `README.md`, source/verification guidance and current limitations.
- Rebuilt `assumptions_register.csv` to **251 unique rows** with a reproducible builder and no stale documentary/unused-key findings.
- Historical audit PDF and 73-row sensitivity artifact are explicitly labelled pre-change; their old 50-check/244-row figures are not presented as current.

### Unresolved items and reasons

1. **Original case verification:** source text is still required. No case-marked row is marked Y.
2. **Empirical accuracy and realised savings:** only synthetic data are available. Back-tests prove mechanics, not live accuracy or causal benefit.
3. **Physical derivation of the 7.68 m stock-out loss distribution:** case total is known, but row-level loss history is not; allocation remains calibrated even though resulting sales are conserved.
4. **Independent write-off validation:** FIFO raw value is ₹5.3572887 cr, so the ₹6 cr target requires the disclosed +₹0.6427113 cr calibration. Fractional bottles are expected MT/QC allocations, not scanned units.
5. **Richer co-packer operations:** no confirmed future inbound, line eligibility, changeover or yield data are supplied; the model deliberately credits opening pulp only.
6. **Emergency-air effectiveness:** air-only assumes timely full coverage; buffer residual cost conservatively includes contribution loss and air premium. These are explicit scenario conventions.
7. **Avoided-loss causality:** root-cause shares and capture rates are assumptions without intervention history; ranges are not simulations or statistical intervals.
8. **Replay and external events:** buffer visualization remains a static stress-test; weather/landslide input is manual and no prediction is claimed.
9. **Execution and operational feasibility:** role names are not authenticated identities; transfers lack truck/lane capacity; no ERP, purchase, production, launch or transfer execution exists.
