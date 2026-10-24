# Data derivation — one-page plain-language guide

**Purpose.** This prototype turns the Dragon Passion case into deterministic synthetic data for 1 January–30 June 2026. It is a planning demonstrator, not company actuals or empirical validation. Seed 42 is fixed and no external API is called.

## 1. What comes from where

- **CASE-STATED** means a value is encoded as a case input in `config/case.json` or a case-marked config row.
- **DERIVED FROM CASE** means arithmetic from those inputs, such as ₹1,200 cr ÷ ₹60 = 200 million annual bottles.
- **MY ASSUMPTION** means a value or modeling choice invented to make the prototype work, including BOM coefficients, depot identities, last-year mix, capture rates, and exact planner notice.
- `VERIFIED_AGAINST_CASE_TEXT` is **N on every register row**. The original case text has not been supplied; case-marked rows must not be treated as independently verified.

## 2. Demand and losses

Annual bottles are `₹1,200 cr × 10,000,000 / ₹60 = 200,000,000`. Summer is 48%, or **96,000,000 latent bottles**; Jan–Feb is an assumed **26,000,000**. Flavor and channel shares apportion these totals with largest-remainder rounding.

Stock-outs censor **7,680,000 bottles = 8%** of summer latent demand, leaving **88,320,000 realised sales**. At ₹60 and 32% contribution, lost revenue is **₹46.08 cr** and lost contribution is **₹14.7456 cr**. The row-level loss distribution is still an assumption calibrated to the case total; it is not learned from physical production.

DP’s 4× uplift applies **only to DP QC**. The editable baseline ramp starts at 2.5× and rises linearly for 14 days. GT/MT propagation is a proxy, not GT outlet truth. Operational demand functions do not read `true_demand_bottles`; that column is reserved for synthetic back-tests.

## 3. Production, pulp and co-packing

Four summer months provide `25 m × 4 = 100 m` bottles of fixed in-house capacity. Actual summer production is **95 m = 95%**. Scheduled production is constrained by pulp and freed plant volume is reallocated, preserving the 95 m total.

The forward weekly planner uses opening pulp only. In-house production draws first; eligible co-packer output uses what remains, and closing pulp carries forward. No unconfirmed inbound, changeover matrix, line eligibility, or yield loss is invented. Co-packing therefore cannot create volume when pulp is unavailable.

## 4. Depot stock and conservation

Opening stock is three weeks of the preseason run rate: **9,254,237 bottles**. `config/last_year_mix.csv` allocates MPB/GC/PP/DP/DB as **50%/20%/30%/0%/0%**, with integer rounding by depot. No forward true demand is used.

Each day and depot then follows FIFO batches:

```text
opening + production receipts − sales − write-offs = closing
```

Across the full period this is **9,254,237 + 121,000,000 − 114,320,000 − 892,881.45 = 15,041,355.55 bottles**. Weekly snapshots expose trailing-current-demand cover and depot×flavor mismatch. Production-to-depot allocation is an assumption because no shipment manifest exists.

## 5. Aging, write-offs and shelf life

MT/QC reject stock below **60 days remaining**; bottled shelf life is 90 days. GT’s rule is unspecified and defaults to an editable zero-day/no-cutoff assumption in `config/channel_shelf_life.csv`.

At 30 June, FIFO batches breaching the cutoff produce **892,881.45 DP bottles** across nine depots’ MT/QC allocations. Their uncalibrated value is **₹5.3572887 cr**. The **₹6 cr case total is only a calibration target**: factor **1.11996951**, reported **₹6.0000000 cr**, disclosed gap **₹0.6427113 cr**. This is not independent verification of the case allocation.

## 6. Money and recommendations

Buffer optimisation compares 0–4 weeks using carry/storage + expected contribution loss + expected air premium, with a separate air-only strategy and break-even probability. The current recommendation is **+2 weeks**.

Avoided loss is **ASSUMPTION-BASED, NOT SIMULATED**: **₹6.325632 / ₹11.643392 / ₹16.432512 cr LOW/BASE/HIGH**. Root-cause shares and capture rates are assumptions; action savings are not added again. Every recommendation needs the required human approver, COO for peak trade-offs, and nothing executes automatically.

See `CHANGELOG.md` for before/after numbers and `README.md` for validation commands and limitations.
