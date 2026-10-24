#!/usr/bin/env python3
"""Build the downloadable PDF implementation audit with ReportLab."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "Pulp_Riot_Dragon_Passion_Audit.pdf"
PAGE_SIZE = landscape(A4)
NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#175CD3")
TEAL = colors.HexColor("#147D73")
INK = colors.HexColor("#263445")
MUTED = colors.HexColor("#5D6B7A")
PALE = colors.HexColor("#F3F6FA")
PALE_BLUE = colors.HexColor("#EAF1FB")
PALE_AMBER = colors.HexColor("#FFF5E6")
GRID = colors.HexColor("#D7E0E8")
WHITE = colors.white

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuMono", str(FONT_DIR / "DejaVuSansMono.ttf")))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="AuditTitle", fontName="DejaVu-Bold", fontSize=25, leading=31,
    textColor=NAVY, spaceAfter=8 * mm,
))
styles.add(ParagraphStyle(
    name="AuditSubtitle", fontName="DejaVu", fontSize=12, leading=17,
    textColor=MUTED, spaceAfter=7 * mm,
))
styles.add(ParagraphStyle(
    name="Eyebrow", fontName="DejaVu-Bold", fontSize=8, leading=11,
    textColor=BLUE, tracking=1.2, spaceAfter=5 * mm,
))
styles.add(ParagraphStyle(
    name="H1Audit", fontName="DejaVu-Bold", fontSize=17, leading=22,
    textColor=NAVY, spaceBefore=6 * mm, spaceAfter=3.5 * mm, keepWithNext=True,
))
styles.add(ParagraphStyle(
    name="H2Audit", fontName="DejaVu-Bold", fontSize=11.5, leading=15,
    textColor=BLUE, spaceBefore=4.5 * mm, spaceAfter=2.5 * mm, keepWithNext=True,
))
styles.add(ParagraphStyle(
    name="H3Audit", fontName="DejaVu-Bold", fontSize=9.5, leading=13,
    textColor=NAVY, spaceBefore=3 * mm, spaceAfter=1.5 * mm, keepWithNext=True,
))
styles.add(ParagraphStyle(
    name="BodyAudit", fontName="DejaVu", fontSize=8.8, leading=12.5,
    textColor=INK, spaceAfter=2.2 * mm, splitLongWords=True,
))
styles.add(ParagraphStyle(
    name="BodySmall", fontName="DejaVu", fontSize=7.6, leading=10.5,
    textColor=INK, spaceAfter=1.5 * mm, splitLongWords=True,
))
styles.add(ParagraphStyle(
    name="BulletAudit", fontName="DejaVu", fontSize=8.6, leading=12.1,
    textColor=INK, leftIndent=5 * mm, firstLineIndent=-3.5 * mm,
    bulletIndent=0, spaceAfter=1.4 * mm, splitLongWords=True,
))
styles.add(ParagraphStyle(
    name="TableHead", fontName="DejaVu-Bold", fontSize=6.9, leading=8.8,
    textColor=WHITE, splitLongWords=True,
))
styles.add(ParagraphStyle(
    name="TableCell", fontName="DejaVu", fontSize=6.7, leading=8.8,
    textColor=INK, splitLongWords=True,
))
styles.add(ParagraphStyle(
    name="TableCellSmall", fontName="DejaVu", fontSize=6.1, leading=7.8,
    textColor=INK, splitLongWords=True,
))
styles.add(ParagraphStyle(
    name="CodeAudit", fontName="DejaVuMono", fontSize=7.4, leading=10.2,
    textColor=NAVY, leftIndent=2 * mm, rightIndent=2 * mm,
))
styles.add(ParagraphStyle(
    name="Callout", fontName="DejaVu", fontSize=9, leading=13,
    textColor=NAVY, leftIndent=2 * mm, rightIndent=2 * mm,
))
styles.add(ParagraphStyle(
    name="Stat", fontName="DejaVu-Bold", fontSize=15, leading=19,
    textColor=BLUE, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="StatLabel", fontName="DejaVu", fontSize=7.2, leading=9.5,
    textColor=MUTED, alignment=TA_CENTER,
))

story: list = []


def p(text: str, style: str = "BodyAudit") -> None:
    story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))


def h1(text: str) -> None:
    story.append(Paragraph(escape(text), styles["H1Audit"]))


def h2(text: str) -> None:
    story.append(Paragraph(escape(text), styles["H2Audit"]))


def h3(text: str) -> None:
    story.append(Paragraph(escape(text), styles["H3Audit"]))


def bullet(text: str) -> None:
    story.append(Paragraph("• " + escape(text), styles["BulletAudit"]))


def code(text: str) -> None:
    block = Preformatted(text.strip("\n"), styles["CodeAudit"])
    table = Table([[block]], colWidths=[None])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 2.5 * mm)])


def callout(text: str, background=PALE_BLUE) -> None:
    para = Paragraph(escape(text), styles["Callout"])
    table = Table([[para]], colWidths=[None])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("LINEBEFORE", (0, 0), (0, -1), 3, BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([table, Spacer(1, 3 * mm)])


def add_table(headers: list[str], rows: list[list[object]], widths: list[float], small: bool = False) -> None:
    cell_style = styles["TableCellSmall" if small else "TableCell"]
    data = [[Paragraph(escape(str(value)), styles["TableHead"]) for value in headers]]
    for row in rows:
        data.append([Paragraph(escape(str(value)), cell_style) for value in row])
    total = sum(widths)
    available = PAGE_SIZE[0] - 28 * mm
    col_widths = [available * value / total for value in widths]
    table = LongTable(data, colWidths=col_widths, repeatRows=1, splitByRow=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for index in range(1, len(data)):
        if index % 2 == 0:
            commands.append(("BACKGROUND", (0, index), (-1, index), PALE))
    table.setStyle(TableStyle(commands))
    story.extend([table, Spacer(1, 3 * mm)])


def page_decor(canvas, doc) -> None:
    canvas.saveState()
    canvas.setTitle("Pulp Riot Dragon Passion — Full Implementation Audit")
    canvas.setAuthor("Arena.ai Agent Mode")
    width, height = PAGE_SIZE
    if doc.page > 1:
        canvas.setStrokeColor(GRID)
        canvas.setLineWidth(0.5)
        canvas.line(14 * mm, height - 12 * mm, width - 14 * mm, height - 12 * mm)
        canvas.setFont("DejaVu", 6.8)
        canvas.setFillColor(MUTED)
        canvas.drawString(14 * mm, height - 9 * mm, "PULP RIOT  /  DRAGON PASSION  /  IMPLEMENTATION AUDIT")
        canvas.drawRightString(width - 14 * mm, height - 9 * mm, "SOURCE: PROJECT CODE, CONFIG AND GENERATED DATA")
    canvas.setStrokeColor(GRID)
    canvas.line(14 * mm, 11 * mm, width - 14 * mm, 11 * mm)
    canvas.setFont("DejaVu", 6.8)
    canvas.setFillColor(MUTED)
    canvas.drawString(14 * mm, 7 * mm, "Audit snapshot: 24 October 2026  •  Synthetic prototype; not empirical validation")
    canvas.drawRightString(width - 14 * mm, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


# Cover
story.append(Spacer(1, 13 * mm))
story.append(Paragraph("IMPLEMENTATION AUDIT  /  OCTOBER 2026", styles["Eyebrow"]))
story.append(Paragraph("The Dragon Passion Problem<br/>at Pulp Riot Juice Co.", styles["AuditTitle"]))
story.append(Paragraph(
    "Full, code-verified review of the synthetic data, assumptions, hypotheses, decision rules, loss attribution, replay and sensitivity.",
    styles["AuditSubtitle"],
))
story.append(Table([[""]], colWidths=[62 * mm], rowHeights=[2.2 * mm], style=TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), BLUE),
])))
story.append(Spacer(1, 9 * mm))
stats = [
    [Paragraph("50 / 50", styles["Stat"]), Paragraph("16 / 16", styles["Stat"]), Paragraph("244", styles["Stat"]), Paragraph("73", styles["Stat"])],
    [Paragraph("reconciliation checks", styles["StatLabel"]), Paragraph("tests passed", styles["StatLabel"]), Paragraph("assumption rows", styles["StatLabel"]), Paragraph("sensitivity metrics", styles["StatLabel"])],
]
stat_table = Table(stats, colWidths=[48 * mm] * 4)
stat_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), PALE),
    ("BOX", (0, 0), (-1, -1), 0.5, GRID),
    ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, 0), 9),
    ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
]))
story.append(stat_table)
story.append(Spacer(1, 9 * mm))
callout(
    "Blunt overall finding: this is a deterministic, case-fitted prototype, not an empirically estimated or physically integrated supply-chain simulation. Its reconciliation is strong, but many causal allocations and counterfactual benefits are assumptions by construction.",
    PALE_AMBER,
)
p("Prepared from the actual repository code, configuration and generated CSVs. Regenerated datasets matched the included CSVs byte-for-byte. The requested 244-row assumptions register is supplied separately as assumptions_register.csv.", "BodyAudit")
story.append(PageBreak())

# Audit basis and contents
h1("Audit basis")
p("I inspected the generator, config, generated CSVs, analytical functions, UI controls, reconciliation code and tests. I also regenerated the data, reran reconciliation and tests, and added reproducible sensitivity runs.")
for item in [
    "Regenerated CSVs were byte-for-byte identical to the included files.",
    "Reconciliation result: 50 PASS / 0 FAIL.",
    "Automated tests: 16 passed.",
    "Sensitivity output: 73 result rows in sensitivity_results.csv.",
    "Assumptions register: 244 unique rows in assumptions_register.csv, with no blank required fields.",
    "README.md links the register and sensitivity artifacts.",
]:
    bullet(item)
callout(
    "Source caveat: the original case document is not in the repository. CASE-STATED means ‘marked as a case input in this repository’, usually in config/case.json or a config row with source=CASE. The classification could not be independently checked against the original McKinsey document.",
    PALE_AMBER,
)
h2("Contents")
add_table(
    ["Section", "Coverage"],
    [
        ["1", "Synthetic data: exact generation methods, date ranges, events and reconciliation"],
        ["2", "Assumptions register: coverage and decision-critical entries"],
        ["3", "Hypotheses: how each is tested and what would falsify it"],
        ["4", "Model parameters, decision rules and actual UI tunability"],
        ["5", "Loss attribution and scenario replay calculations"],
        ["6", "Limitations, top-five weak assumptions and three sensitivity tests"],
        ["End", "Things a judge could challenge, with suggested answers"],
    ],
    [1, 8],
)

# Section 1
h1("1) Synthetic data: how it was made")
h2("1.1 Common demand-generation method")
p("The generator uses one NumPy random generator with seed 42, covering 1 January–30 June 2026. The year and seed are assumptions, not case facts. Code: src/data_generator.py::SyntheticDataGenerator.__init__; config/assumptions.csv A001–A002.")
p("For each flavor × channel, daily latent-demand weights are:")
code("""
weight = monthly seasonality
       × weekend factor
       × lognormal noise
       × viral multiplier
""")
for item in [
    "Monthly multipliers: Jan 0.95, Feb 1.05, Mar 0.90, Apr 1.00, May 1.10, Jun 1.00.",
    "Saturday/Sunday uplift: +6%; there is no other day-of-week pattern.",
    "Daily noise: numpy.random.lognormal(mean=0, sigma=0.08). A004 calls this coefficient of variation, but the code uses it as log-space standard deviation.",
    "There is no trend term, region-specific seasonality or channel-specific calendar pattern.",
    "DP pre-launch weights are zero.",
    "Integer bottles are assigned using capped largest-remainder apportionment, preserving requested totals exactly.",
]:
    bullet(item)
p("Code: src/data_generator.py::SyntheticDataGenerator._daily_weights and _build_demand_and_sales; src/utils.py::apportion; config/monthly_seasonality.csv. Apportionment means noise changes the shape of demand, not the prescribed flavor × channel totals.")

h2("1.2 Dataset-by-dataset construction")
add_table(
    ["Dataset", "Date range and granularity", "Exact construction and case anchors", "Code"],
    [
        ["Sales — daily_sales.csv", "24,435 rows = 181 days × 5 flavors × 3 channels × 9 depots. Daily, 1 Jan–30 Jun 2026.", "Jan–Feb latent demand fixed at 26 m; Mar–Jun at 96 m. Summer flavor shares 38/20/16/14/12%; channel shares 55/25/20%, applied independently to every flavor. Existing-flavor preseason shares are renormalized over 88%. Daily date × depot allocations are jointly apportioned.", "SyntheticDataGenerator._build_demand_and_sales; config/flavors.csv, channels.csv, depots.csv; A003"],
        ["Losses and realised sales — daily_sales.csv", "Same grain and dates.", "Event-risk-weighted latent demand is scaled to exactly 7.68 m = 8% of 96 m. sales = true_demand − lost_sales; stockout_flag = lost_sales > 0. Losses are not calculated from production, finished-goods inventory or depot stock.", "SyntheticDataGenerator._allocate_case_losses and _build_demand_and_sales"],
        ["GT distributor orders — daily_sales.csv", "Daily GT rows.", "round(latent_GT_demand × (1 + Normal(0, 0.15))), floored at zero and realised sales. Proxy generated from synthetic ground truth, not independent distributor data.", "SyntheticDataGenerator._build_demand_and_sales; A025"],
        ["QC feed — qc_sell_through.csv", "8,145 rows = 181 days × 5 flavors × 9 depots. Daily QC, 1 Jan–30 Jun.", "Exact copy of QC realised sales and stock-out flags; no extra noise or missingness. Marketing date = event date; planner consolidated availability = month-end.", "SyntheticDataGenerator._build_qc_feed"],
        ["Monthly forecast — monthly_forecast.csv", "270 rows = 6 months × 5 flavors × 9 depots. Monthly, Jan–Jun.", "Current actual monthly sales × alternating ±30%, forcing WAPE to 30%. Despite MONTHLY_LAST_YEAR_MIX, there is no last-year dataset or forecast model.", "SyntheticDataGenerator._build_monthly_forecast; A062–A063"],
        ["Depot stock — depot_stock_weekly.csv", "1,215 rows = 27 snapshots × 5 flavors × 9 depots. 1 Jan–29 Jun: 1 Jan plus Mondays. Available one day later.", "Stock = round(forward 21-day true demand × event/depot factor × lognormal(0, 0.10)); not actual last-year mix. Channels aggregated. Near 30 Jun, missing future days are padded with earlier dates.", "SyntheticDataGenerator._build_depot_stock; A019–A024"],
        ["Write-offs — depot_writeoffs.csv", "8 rows, all 30 Jun: MPB and GC in four OVERSTOCK-profile depots.", "Fixed ₹6.00 cr allocated using depot demand_weight × flavor summer_share, rounded with final-row adjustment. Not calculated from expiry, stock age or shelf life.", "SyntheticDataGenerator._build_writeoffs; A068"],
        ["Production — production_daily.csv", "905 rows = 181 days × 5 flavors. Daily, 1 Jan–30 Jun.", "Jan–Feb production equals latent demand by flavor. Each summer month targets 25 m × 95% = 23.75 m, giving 95 m. April DP weight ×1.20; May–Jun PP ×0.50 and DP ×1.50, then normalized.", "SyntheticDataGenerator._build_scheduled_production; A015–A018, A057, A069"],
        ["Capacity — plant_copacker_capacity.csv", "18 rows = 6 months × 3 assets. Monthly, Jan–Jun.", "Two plants each get 12.5 m monthly capacity and 50% of actual output. Summer capacity 100 m, production 95 m, utilisation 95%. Co-packer 2.5 m/month, 14-day notice, 25% premium, but generated actual output is zero.", "SyntheticDataGenerator._build_capacity; A058"],
        ["Pulp inventory — pulp_inventory_daily.csv", "1,448 rows = 181 days × 8 pulps. Daily, 1 Jan–30 Jun.", "Consumption = actual bottles × BOM kg/bottle. Non-passion pulps replenish daily and never constrain production. Passion starts at 21 days of early-summer baseline and declines to 14 at closure. Closing = opening + inbound − consumption.", "SyntheticDataGenerator._constrain_and_build_pulp; config/bom.csv and pulps.csv; A014, A026"],
        ["Pulp inbound — pulp_inbound.csv", "1,425 shipment rows. Arrivals 1 Jan–30 Jun; bookings from 13 Nov 2025.", "Regular receipts smoothed into daily arrivals. Booking = arrival − lead time. Cost = quantity × assumed normal cost × mode multiplier. No supplier capacity.", "SyntheticDataGenerator._constrain_and_build_pulp; A056"],
        ["Supplier/routes — supplier_routes.csv", "8 static rows, one primary supplier per pulp; no dates.", "Join of suppliers and routes. Passion: one source, one road, 3-day transit, 60% closure probability. ₹180/kg is synthetic even though the supplier row is marked CASE. Imported dragonfruit uses 49-day midpoint assumption.", "SyntheticDataGenerator.generate; config/suppliers.csv and routes.csv"],
        ["Viral/events — viral_profile.csv and event_calendar.csv", "Viral: 15 daily rows, 17–31 Mar. Events: 8 rows, 3 Mar–30 May.", "Explicit story-calendar tables generated from the same config and assumptions used elsewhere.", "SyntheticDataGenerator._build_viral_profile and _build_events"],
    ],
    [1.15, 1.35, 3.75, 1.55],
    small=True,
)

h2("1.3 Exact story-event injection")
add_table(
    ["Event", "Implementation", "Source status and code"],
    [
        ["DP launch", "DP demand is zero before 3 Mar 2026, then becomes available.", "Date case-marked in case.json and flavors.csv; _build_demand_and_sales"],
        ["Viral ramp", "Starts 17 Mar. DP QC starts at assumed 2.5×, rises linearly to 4.0× on 31 Mar, then remains 4×.", "Endpoint/duration case-marked; 2.5 and linear path are MY ASSUMPTION, A042; _daily_weights and _build_viral_profile"],
        ["Cross-channel propagation", "DP GT/MT receive 1 + (QC multiplier − 1) × 0.35; peak non-QC multiplier is 2.05×. Other flavors receive none.", "A006, MY ASSUMPTION; _daily_weights"],
        ["Meaning of 4×", "Applies to DP QC daily weights only, not total QC/DP/company demand. Season totals are re-apportioned, so the event redistributes volume over time rather than increasing prescribed summer volume.", "_daily_weights and _build_demand_and_sales"],
        ["Planner notice", "31 Mar, the same date the viral profile reaches 4×.", "A007, MY ASSUMPTION; _build_events"],
        ["Highway closure", "10–30 May inclusive = 21 days. No passion road arrivals 10 May–2 Jun; receipts resume 3 Jun after transit lag.", "Dates/duration case-marked; _constrain_and_build_pulp and _build_events"],
        ["Emergency air", "Booked 17 May, arrives 20 May after assumed 3-day lag. Lot = ₹3.2 cr / (₹180/kg × 5) = 35,555.56 kg. Total ₹3.20 cr; normal ₹0.64 cr; premium ₹2.56 cr.", "Cost/multiple case-marked; dates, ₹180/kg and interpretation are assumptions A012–A013/A036; _constrain_and_build_pulp"],
        ["Depot imbalance", "From 31 Mar DP factor 0.55. From 10 May onward DP/PP factor 0.10. May–Jun MPB/GC: 2.20× in OVERSTOCK and 0.45× in SHORT depots.", "A021–A024, MY ASSUMPTION; _build_depot_stock"],
        ["Rival launch", "28 Apr, exactly 42 days after viral start.", "Case says six weeks; exact date synthetic, A067; _build_events"],
    ],
    [1.2, 4.2, 2.3],
)
h3("Synthetic production allocation during the closure")
p("When passionfruit is insufficient, the generator gives pulp to DP first, then PP, and reallocates freed bottle volume 60% to MPB and 40% to GC, keeping total output equal to schedule. This hardcoded story rule is separate from the three human allocation options shown in the app. Code: SyntheticDataGenerator._constrain_and_build_pulp; A018.")

h2("1.4 Reconciliation results")
p("I ran python generate_data.py --output /tmp/tf-audit-data. The regenerated CSVs matched the included CSVs byte-for-byte. Code: generate_data.py::main; src/reconciliation.py::reconcile.")
add_table(
    ["Check", "Actual", "Expected", "Difference / result"],
    [
        ["VOL_01 — annual bottles from ₹1,200 cr / ₹60", "200,000,000", "200,000,000", "0 — PASS"],
        ["VOL_02 — summer latent demand", "96,000,000", "96,000,000", "0 — PASS"],
        ["VOL_03 — Jan–Feb demand", "26,000,000", "26,000,000", "0 — PASS; expected value is assumption A003"],
        ["Flavor volumes", "MPB 36.48 m; GC 19.20 m; PP 15.36 m; DB 13.44 m; DP 11.52 m", "Same", "All exact — PASS"],
        ["Channel volumes", "GT 52.80 m; MT 24.00 m; QC 19.20 m", "Same", "All exact — PASS"],
        ["CAP_01 — Mar–Jun capacity", "100,000,000", "100,000,000", "0 — PASS"],
        ["CAP_02 — Mar–Jun production", "95,000,000", "95,000,000", "0 — PASS"],
        ["CAP_03 — utilisation", "95.00%", "95.00%", "0 — PASS"],
        ["LOSS_01 — censored bottles", "7,680,000", "7,680,000", "0 — PASS"],
        ["LOSS_04 — realised summer sales", "88,320,000", "88,320,000", "0 — PASS"],
        ["LOSS_05 — lost share", "8.00%", "8.00%", "0 — PASS"],
        ["LOSS_02 — lost revenue", "₹46.08 cr", "₹46.08 cr", "0 — PASS"],
        ["LOSS_03 — lost contribution", "₹14.7456 cr", "₹14.7456 cr", "0 — PASS"],
        ["FEED_03 — monthly forecast WAPE", "30.00%", "30.00%", "0 — PASS"],
        ["PULP_02 — passion cover at closure", "14.00 days", "14.00 days", "0 — PASS"],
        ["EVENT_06 — closure duration", "21 days", "21 days", "0 — PASS"],
        ["PULP_03 — road arrivals during closure", "0", "0", "0 — PASS"],
        ["AIR_01 / AIR_02", "₹3.20 cr / 5×", "₹3.20 cr / 5×", "0 — PASS"],
        ["WRITE_01 — write-offs/discounts", "₹6.00 cr", "₹6.00 cr", "0 — PASS"],
    ],
    [3.2, 2.1, 1.7, 1.8],
)
callout("Overall: 50 PASS / 0 FAIL. Full output: data/reconciliation_checks.csv.")
h3("Checks that do not match")
p("There are no failed checks. PULP_01 needs clarification: minimum closing pulp is 0.0543056 kg while the displayed expected value is 0. This is a non-negativity check, not an equality check; reconcile() deliberately overrides its status to PASS when minimum stock is ≥0.")
h3("What reconciliation does not prove")
for item in [
    "The 96 m, 7.68 m, ₹3.2 cr and ₹6 cr totals are largely imposed by construction.",
    "Many expected values come from the same config used to generate the data; these are self-consistency checks, not external validation.",
    "summer_revenue_share = 48% is not read or reconciled, although 48% × 200 m = 96 m happens to hold numerically.",
    "There is no production → finished-goods inventory → depot → shipment → sales conservation check.",
    "Entity-count checks compare generated entities with config entities, not independently with the original case document.",
]:
    bullet(item)

# Section 2
h1("2) Assumptions register")
h2("Delivered register")
p("The requested exhaustive table is assumptions_register.csv with columns: ID | Assumption | Value used | Source | Why it was needed | Where in code | Impact if wrong.")
add_table(
    ["Source", "Rows"],
    [["CASE-STATED, as encoded in the repository", "62"], ["DERIVED FROM CASE", "10"], ["MY ASSUMPTION", "172"], ["Total", "244"]],
    [6, 1],
)
p("Coverage includes the original 154 scalar/row-level assumptions, 48 case.json inputs, 15 additional case-marked table inputs/constraints, 9 derived values and 18 material implicit modeling choices. Rebuild with python build_assumptions_register.py. Impact ratings are audit judgment, not measured elasticities.")

h2("Decision-critical entries")
p("This is the readable high-impact subset. The CSV contains every individual BOM, depot, supplier, route, budget, roadmap, seasonality and option row.")
add_table(
    ["ID", "Assumption", "Value used", "Source", "Why needed", "Where in code", "Impact"],
    [
        ["A003", "Jan–Feb baseline", "26 m bottles: (200 m − 96 m) / 8 × 2", "MY ASSUMPTION", "No preseason volume; even spread across eight non-summer months", "_build_demand_and_sales", "High"],
        ["DEPOT_D01–D09", "Depot identities, regions and weights", "D01–D09 weights 14/8/16/9/15/12/10/11/5%", "MY ASSUMPTION", "Case gives counts, not demand split", "config/depots.csv; demand/stock/write-off builders", "High"],
        ["DEPOT_D01–D09 aggregate", "Region split", "North 22%, West 25%, South 37%, East 16%", "MY ASSUMPTION", "Depot allocation and regional transfers", "config/depots.csv; _build_demand_and_sales", "High"],
        ["MODEL_DP_QC_SHARE", "DP's QC share", "20% of DP = 2.304 m bottles; 2.4% of total summer", "MY ASSUMPTION", "Total QC mix does not specify DP channel mix", "_build_demand_and_sales", "High"],
        ["MODEL_VIRAL_APPLICATION", "Application of 4×", "DP QC daily weights, 2.5× → 4× over 14 days, totals renormalized", "MY ASSUMPTION", "Response path and normalization unspecified", "_daily_weights and _build_demand_and_sales", "High"],
        ["A006", "Historical GT/MT viral spillover", "35% of uplift above baseline", "MY ASSUMPTION", "Only QC 4× is given", "_daily_weights", "High"],
        ["A034", "Forward GT/MT scenario spillover", "50% of uplift above baseline", "MY ASSUMPTION", "Weekly reforecast and scenarios", "weekly_rolling_reforecast; build_demand_scenarios", "High"],
        ["BOM_001–BOM_011", "Pulp-per-bottle conversion", "MPB .105 mango/.035 peach/.010 basil; GC .145 guava/.005 chilli; PP .150 passion; DB .090 domestic/.060 imported dragon; DP .054 domestic/.036 imported dragon/.060 passion kg/bottle", "MY ASSUMPTION", "No BOM coefficients supplied", "config/bom.csv; pulp and allocation functions", "High"],
        ["BOM_009–BOM_011", "DP passion/dragon split", "0.06 kg passion + 0.09 kg dragon per bottle; dragon 0.054 domestic / 0.036 imported", "MY ASSUMPTION", "DP pulp exposure; 40/60 passion/dragon by mass; dragon 60/40 domestic/imported", "config/bom.csv; _constrain_and_build_pulp", "High"],
        ["MODEL_UNIFORM_PRICE_MARGIN", "Uniform economics", "₹60 and 32% applied to every flavor/channel", "MY ASSUMPTION", "Case gives averages, not a margin matrix", "build_loss_attribution; passionfruit_requirement_profile; shortage_allocation_options", "High"],
        ["DERIVED_COPACKER_CAPACITY", "Co-packer 10% base", "10% × 25 m = 2.5 m bottles/month", "DERIVED FROM CASE", "Maximum additional capacity", "_build_capacity; constrained_weekly_planner", "High"],
        ["MODEL_COPACKER_FLAVOR_FLEXIBILITY", "Co-packer flexibility", "Implicitly fully flexible; aggregate bottles, no flavor/BOM/changeover restriction", "MY ASSUMPTION", "No line-eligibility data", "constrained_weekly_planner", "High"],
        ["MODEL_CAPACITY_PULP_SEPARATION", "Capacity and pulp feasibility", "Calculated separately; co-packer volume can appear without simultaneous pulp balance", "MY ASSUMPTION", "No joint production optimizer", "src/analysis.py::build_analysis", "High"],
        ["CASE_PASSION_CLOSURE_PROBABILITY", "Annual closure likelihood", "60%", "CASE-STATED", "Expected-loss weighting", "closure_loss_scenarios via build_analysis", "High"],
        ["A031–A033", "Closure-length weights", "1 week 25%, 2 weeks 35%, 3 weeks 40%, conditional on closure", "MY ASSUMPTION", "No closure-length distribution", "build_analysis → closure_loss_scenarios", "High"],
        ["CASE_BOTTLED_SHELF_LIFE_DAYS / DERIVED_MT_QC_PREBUILD", "Shelf-life rule", "Bottled 90 days; MT/QC require 60 remaining; derived prebuild cap 30 days", "DERIVED FROM CASE", "Prevent excessive finished-goods prebuild", "constrained_weekly_planner", "High"],
        ["—", "GT shelf-life rule", "Not modeled", "—", "No GT rule or expiry-lot implementation", "No corresponding function", "High"],
        ["A025 / MODEL_GT_ORDER_GENERATION", "GT demand proxy", "Orders centered on latent GT demand with 15% Normal noise", "MY ASSUMPTION", "GT outlet data unavailable", "_build_demand_and_sales", "High"],
        ["MODEL_CENSORING_CORRECTION", "Stock-out correction", "In-stock sales unchanged; GT orders if above sales/baseline; otherwise recursive 14-day corrected mean or sales lower bound", "MY ASSUMPTION", "Latent demand unobserved in stock-outs", "estimate_censored_demand; prepare_qc_signal", "High"],
        ["MODEL_LOSS_ALLOCATION", "Synthetic stock-out allocation", "Risk-weighted rows scaled to exactly 7.68 m, independently of production/depot inventory", "MY ASSUMPTION", "Case total known; row-level losses unknown", "_allocate_case_losses", "High"],
        ["A014", "Passion cover before viral ramp", "21 days of early-summer baseline requirement", "MY ASSUMPTION", "Only closure cover is given", "_constrain_and_build_pulp", "High"],
        ["A029 + A030", "Buffer carrying and storage", "18% + 8% = 26% annually of pulp principal", "MY ASSUMPTION", "No financing or cold-storage rate", "build_analysis → calculate_buffer_option", "High"],
        ["MODEL_BUFFER_OBJECTIVE", "Buffer objective", "Carry/storage + expected contribution loss; air premium excluded", "MY ASSUMPTION", "Defines optimiser choice", "calculate_buffer_option; optimise_buffer", "High"],
        ["SUPPLIER_SUP_PASSION", "Normal passion cost", "₹180/kg; row also contains case-marked lead/source fields", "MY ASSUMPTION", "Air-lot size and buffer economics", "config/suppliers.csv; _constrain_and_build_pulp", "High"],
        ["A036", "Meaning of 5× air cost", "5× total normal delivered pulp cost for emergency lot", "MY ASSUMPTION", "Infer air kilograms from ₹3.2 cr", "Hardcoded in _constrain_and_build_pulp; A036 documentary", "High"],
        ["A021–A024", "Depot stock factors", "2.20 / 0.45 / 0.55 / 0.10 by event and profile", "MY ASSUMPTION", "Create simultaneous overstocks and shortages", "_build_depot_stock", "High"],
        ["A068", "Write-off allocation", "depot_weight × flavor_share, only MPB/GC in overstock depots", "MY ASSUMPTION", "Case total known; causal distribution unknown", "_build_writeoffs; documentary value, hardcoded logic", "High"],
        ["A035", "Transfer sales recovery", "70% of transferred deficit bottles become realised sales", "MY ASSUMPTION", "Convert transfers into expected contribution", "suggest_depot_transfers", "High"],
        ["A043–A045", "Channel delisting weights", "GT 1, MT 2, QC 3", "MY ASSUMPTION", "Relative trade-off score without outlet data", "shortage_allocation_options", "Med"],
        ["ALLOC_PROTECT_DP / PROTECT_PP / BALANCED", "DP share of available passion", "70% / 30% / 55%", "MY ASSUMPTION", "Three explicit COO choices", "config/allocation_options.csv; shortage_allocation_options", "High"],
        ["ATTRIBUTION_*", "Lost-contribution shares", "Late 35%, route 35%, launch 15%, stale depot mix 15%", "MY ASSUMPTION", "No measured causal split", "config/loss_attribution.csv; build_loss_attribution", "High"],
        ["ATTRIBUTION_*", "Air/write-off assignment", "100% air to route; 100% write-offs to stale depot mix", "MY ASSUMPTION", "Root-cause waterfall", "build_loss_attribution", "High"],
        ["ATTRIBUTION_*", "LOW/BASE/HIGH capture", "Late 25/45/65%; route 30/55/75%; launch 40/65/85%; stale 20/40/60%", "MY ASSUMPTION", "Convert impact into counterfactual avoided loss", "build_loss_attribution", "High"],
        ["SUPPLY_OPTION_*", "Intervention efficacy", "Second supplier 65% loss reduction; co-packer 5%; air trigger 35% loss and 20% air-cost reduction", "MY ASSUMPTION", "No intervention performance data", "supply_option_economics; build_scenario_replay", "High"],
        ["BUDGET_*", "Selected budget lines", "Build .35; vendor IT .20; cloud .12; training .12; S&OP .10; Excel .08; second supplier .45; air trigger .15; contingency .20 = ₹1.77 cr", "MY ASSUMPTION", "No vendor quotations", "config/budget.csv; build_budget", "High"],
        ["CASE_BUDGET_CAP", "First-year cap", "₹2.50 cr, hardcoded", "CASE-STATED project constraint", "Required package constraint", "build_budget; budget_reconciliation", "High"],
        ["A037/A038", "Scenario uncertainty", "±20% fresh / ±40% degraded", "MY ASSUMPTION", "Not estimated from live forecasts", "build_analysis; feed_fallback_assessment", "Med"],
        ["A039", "Minimum active alert history", "5 nonzero observations", "MY ASSUMPTION", "Prevent launch-day tiny-denominator alerts", "detect_demand_anomalies", "Med"],
        ["A040/A041/A060", "Reforecast/scenario windows", "4-week reforecast; 28-day scenario history; 8-week horizon", "MY ASSUMPTION", "Planning-window choices", "weekly_rolling_reforecast; build_demand_scenarios; A060 documentary", "Med"],
        ["MODEL_APPROVAL_CHAIN", "Approval and escalation", "Planner → S&OP → COO for peak trade-offs", "MY ASSUMPTION", "Proposed governance design", "build_risk_register; apply_decision", "Med"],
    ],
    [1.05, 1.35, 2.8, 1.05, 2.0, 2.15, 0.55],
    small=True,
)
callout("Approval caveat: apply_decision() checks only that actor text is nonempty. It does not authenticate the user, verify their role or require sequential Planner → S&OP → COO approvals.", PALE_AMBER)

# Section 3
h1("3) Hypotheses the model tests")
add_table(
    ["Hypothesis", "How the model tests it and observed result", "What would prove it wrong / audit verdict"],
    [
        ["QC leads GT demand", "weekly_rolling_reforecast() uses current-week QC uplift versus a prior four-week baseline to modify next-week GT/MT. The generator applies QC and GT/MT effects on the same dates, with no estimated lag. Weekly WAPE is 10.48% against corrected synthetic demand, not GT outlet truth.", "Real GT data showing no lead, negative lag or no improvement over a non-QC baseline. Not proven; lead is assumed, not estimated."],
        ["Sensing would catch the spike before planners", "detect_demand_anomalies() compares daily QC with shifted rolling baselines. Base: Amber 18 Mar, Red 19 Mar, versus assumed notice 31 Mar. Headline 12 days uses Red in preference to earlier Amber.", "No alert before the real notice or different ramp/feed latency. Sensitivity shows Red disappears under less front-loaded ramps. Illustrative, not independently validated."],
        ["Frozen-pulp buffer beats air freight", "optimise_buffer() searches 0–8 weeks. Base optimum +1 week, only ₹0.0946 cr net expected benefit. Expected air premium is displayed but excluded from the objective.", "Carry/working capital exceeding avoided total cost, lower closure probability or cheaper/reliable air. Adding displayed air premium changes optimum to +2 weeks. Full buffer-versus-air comparison is not implemented."],
        ["Co-packer fixes demand spike but not pulp shortage", "constrained_weekly_planner() adds up to 0.575 m/week after notice. In 8-week VIRAL_4X, unmet falls from 13.773 m to 10.323 m but is not eliminated. Pulp is separate.", "Flavor ineligibility/changeovers could worsen capacity results; joint model could alter them. Helps capacity but does not fully fix 4×; ‘cannot create pulp’ is structurally true but not jointly simulated."],
        ["Last-year depot mix caused ₹6 cr write-offs", "Stock is labeled last-year mix and all ₹6 cr assigned to stale mix. But stock uses forward true demand × factors, and write-offs are allocated by assumption.", "Actual ledger showing other depots/flavors/causes, or current-mix simulation not reducing write-offs. Not tested causally; conclusion built in."],
        ["Launch handoff made DP unready", "launch_readiness_gate() requires every BOM pulp to cover lead + 7 days using forward scheduled requirements. Imported dragonfruit 49 + 7 = 56 days; result BLOCKED; notice/lead gap 35 days.", "Actual lead ≤14 days, sufficient 56-day cover or approved alternate supplier. Depends on 49-day midpoint and synthetic inventory."],
        ["Viral demand eroded passion cover", "build_causal_links() compares old-baseline and current-demand cover at closure: 2.00 → 1.719 weeks. VIRAL_4X increases weekly passion requirement 31.02%.", "Actual pulp demand not increasing, alternate BOM or replenishment maintaining cover. Mechanically demonstrated using assumed BOM/spillovers."],
        ["Stock-outs censor demand and correction helps", "Exactly 7.68 m losses imposed. censoring_validation() reports 34.93% lower absolute error than raw sales on stocked-out rows.", "Real-data back-test where proxy does not beat sales or is biased. Estimated lost demand is 9.965 m versus true 7.680 m, a 29.75% overestimate; helps does not mean recovers truth."],
        ["Protecting DP improves contribution/kg with PP/rival trade-off", "DP uses 0.06 kg/bottle, PP 0.15. shortage_allocation_options() ranks contribution and channel-weighted risk but chooses no winner.", "Different actual margins/BOM or channel/rival evidence. Rival shelf-space loss is not quantified."],
        ["Proposed workflow can capture modeled benefits", "App demonstrates recommendation, approval and audit-log mechanics. Avoided loss then applies assumed capture rates.", "Planner non-adoption, missed SLAs, approval delays or lower measured pilot capture. Software mechanics tested; organisational capture not tested."],
    ],
    [1.65, 3.8, 2.8],
)

# Section 4
h1("4) Model parameters and decision rules")
h2("UI tunability")
p("Only six detector inputs are real analytical UI controls: baseline window, Amber multiplier and consecutive days, Red multiplier and consecutive days, and minimum active history. Code: app.py::main.")
p("The Architecture page’s QC/depot checkboxes call only feed_fallback_assessment() for a demonstration; they do not rebuild the analytical context. Code: src/pages/budget_architecture.py::render_architecture. Everything below otherwise requires config/code changes, and several documentary config values are not read at all.")

h2("Demand, sensing and launch rules")
add_table(
    ["Rule", "Value and reason", "UI-tunable?"],
    [
        ["Detector baseline", "Trailing 14-day mean, shifted one day. EWMA and z-score are diagnostics, not triggers. Case-encoded threshold; shift is implementation choice. detect_demand_anomalies()", "Yes"],
        ["Minimum history", "5 prior nonzero observations, preventing pre-launch zeros from creating false spikes. A039.", "Yes"],
        ["Amber", "Signal/baseline >1.5× for 2 consecutive days. Case-encoded.", "Yes"],
        ["Red", "Signal/baseline >2.0× for 3 consecutive days. Case-encoded.", "Yes"],
        ["First actionable lead", "Red preferred over Amber rather than earliest. Base lead is 12 days although Amber was 13 days before notice. build_causal_links(); build_scenario_replay()", "No"],
        ["Stock-out correction window", "Recursive trailing 14 corrected observations. GT proxy must exceed sales and baseline; otherwise rolling baseline or sales lower bound. estimate_censored_demand()", "No"],
        ["Weekly reforecast", "4-week rolling baseline; QC uplift clipped to at least 1; GT/MT receive 50% of uplift above 1. weekly_rolling_reforecast()", "No"],
        ["Forward scenarios", "28-day history, 8-week horizon; BASE/2×/4× apply to DP QC, with 50% non-QC spillover. build_demand_scenarios()", "No"],
        ["Scenario uncertainty", "±20% fresh, ±40% when QC or depot data is missing. A037–A038.", "No"],
        ["Launch gate", "Every BOM pulp: opening kg / forward scheduled daily requirement ≥ supplier lead + 7 days; all must pass for READY. Imported dragonfruit 49 + 7 = 56 days. launch_readiness_gate()", "No"],
        ["Launch notice comparison", "14-day notice versus 49-day imported lead gives 35-day gap; informational, not an additional gate by itself.", "No"],
    ],
    [1.6, 5.7, 0.75],
)

h2("Supply, capacity, buffer and allocation rules")
add_table(
    ["Rule", "Value and reason", "UI-tunable?"],
    [
        ["Exposure fragility", "closure probability × route factor × source factor; factor 1 for single, 0.5 otherwise. RED if cover < lead or fragility ≥0.50; AMBER if cover < lead + 1 week or fragility ≥0.20. build_exposure_map()", "No"],
        ["Closure scenarios", "60% annual probability × conditional 25/35/40% for 1/2/3 weeks. Shortage = requirement − stock − buffer, floored at zero. closure_loss_scenarios()", "No"],
        ["Air scenario cost", "Shortage kg × ₹180 × 5 total; premium uses ×4. Next-summer scenario does not reconcile to actual ₹3.2 cr lot.", "No"],
        ["Buffer search", "Integer 0–8 weeks, ≤180 days. Principal = buffer kg × ₹180. Annual cost = principal × 26%. A046/A029/A030.", "No"],
        ["Buffer objective", "Minimise annual carry/storage + expected contribution loss. Expected air premium excluded. Working capital outside selected budget. calculate_buffer_option(); optimise_buffer()", "No"],
        ["Weekly in-house capacity", "25 m × 7 / 30.4375 = 5.749 m bottles/week. Historical run rate 95%, leaving 5% headroom. constrained_weekly_planner()", "No"],
        ["Co-packer", "10% × 25 m = 2.5 m/month = 0.575 m/week. Eligible after 14 days. Premium = 25% × ₹40.80 = ₹10.20/bottle on used volume.", "No"],
        ["Shelf-life rule", "MT/QC prebuild displayed as 90 − 60 = 30 days; structural buffer directed to 180-day frozen pulp. Returned rule/text, not dynamic lot-expiry constraint.", "No"],
        ["Synthetic historical allocation", "DP receives pulp first, PP second; freed volume 60% MPB / 40% GC so total output stays at schedule. _constrain_and_build_pulp()", "No"],
        ["Human shortage options", "DP pulp share 70% / 30% / 55% for Protect DP / Protect PP / Balanced. Within each flavor, all channels receive same service fraction. shortage_allocation_options()", "No"],
        ["Allocation scoring", "Contribution ₹19.20/bottle; unmet risk weights GT 1, MT 2, QC 3. Contribution rank descending, risk rank ascending. No automatic winner.", "No"],
        ["Supply-option economics", "Configured assumed reductions. Buffer uses calculated economics; benefits not added to top-down replay savings. supply_option_economics()", "No"],
    ],
    [1.6, 5.7, 0.75],
)

h2("Inventory, control-tower, replay and governance rules")
add_table(
    ["Rule", "Value and reason", "UI-tunable?"],
    [
        ["Current depot cover", "Latest snapshot per flavor/depot; trailing 28-day corrected demand; target 21 days. inventory_cover_snapshot()", "No"],
        ["Inventory status", "SHORT <14 days; OVERSTOCK >35 days; otherwise WATCH; zero demand gets NO_CURRENT_DEMAND. A052–A053.", "No"],
        ["Stale depot sheet", "as_of − snapshot_available_date > 7 days. Stale rows cannot originate transfers. A054.", "No"],
        ["Transfers", "Greedy largest-surplus origin to lowest-cover destination; origin retains 21-day cover. Same region 2 days, cross-region 4 days.", "No"],
        ["Transfer acceptance", "Quantity × ₹1.50 cost; recovered contribution = quantity × 70% × ₹19.20. Only positive-net suggestions; all require human approval. suggest_depot_transfers()", "No"],
        ["Control-tower demand", "Latest DP alert status at page as-of date. Missing alerts produce unavailable/degraded messaging. control_tower_tiles()", "No"],
        ["Inventory tile severity", "RED if both SHORT and OVERSTOCK; AMBER if only one or stock unavailable; otherwise GREEN.", "No"],
        ["Distribution tile severity", "AMBER when transfers exist or cover unavailable; otherwise GREEN.", "No"],
        ["Transportation tile severity", "RED during 10–30 May; otherwise AMBER, even outside closure.", "No"],
        ["Risk severity", "R001 RED if alert exists; R002 RED when launch blocked; R003/R004 fixed RED; R005/R006 fixed AMBER. build_risk_register()", "No"],
        ["Replay actions", "Manual route input 3 May, allocation deadline 9 May, model air 10 May, actual air 17 May. Assumptions, not learned triggers.", "Timeline date only"],
        ["Replay air cost", "₹3.20 cr × (1 − 20%) = ₹2.56 cr. Not added again to avoided loss.", "No"],
        ["Replay buffer line", "Actual cover + selected buffer weeks; static stress-test, not re-simulated inventory.", "No"],
        ["Loss-impact LOW/HIGH cards", "Base impact ±25% of allocated contribution component only; air and write-offs fixed. A047.", "No"],
        ["Avoided-loss LOW/BASE/HIGH", "Uses cause-level capture rates, not the ±25% impact columns. build_loss_attribution()", "No"],
        ["Budget selection", "Sum selected config rows; must be ≤₹2.50 cr. Buffer principal and unselected co-packer excluded. build_budget()", "No"],
        ["Payback", "12 × selected cost / expected next-summer benefit; simple, undiscounted. budget_impact()", "No"],
        ["Approval workflow", "PROPOSED → APPROVED/REJECTED, or MODIFY → PROPOSED_MODIFIED. MODIFY requires replacement text; actor merely nonempty. Execution remains zero. apply_decision()", "Yes, action buttons"],
    ],
    [1.6, 5.7, 0.75],
)

# Section 5
h1("5) Loss attribution and replay")
h2("5.1 Base calculations")
code("""
Lost bottles       = 96.00 m × 8% = 7.68 m
Lost revenue       = 7.68 m × ₹60 / 1 crore = ₹46.08 cr
Lost contribution  = ₹46.08 cr × 32% = ₹14.7456 cr

Economic impact_i = ₹14.7456 cr × lost_contribution_share_i
                  + ₹3.20 cr     × air_freight_share_i
                  + ₹6.00 cr     × writeoff_share_i
""")
p("Lost revenue is allocated for context using the same 35/35/15/15 shares but is not added again to economic impact. Code: src/links.py::build_loss_attribution.")

h2("5.2 Exact root-cause allocation")
add_table(
    ["Root cause", "Revenue context", "Contribution", "Air", "Write-offs", "Economic impact", "Capture L/B/H", "Avoided LOW", "Avoided BASE", "Avoided HIGH"],
    [
        ["Late demand sensing", "₹16.128 cr", "₹5.16096 cr", "0", "0", "₹5.16096 cr", "25/45/65%", "₹1.290240 cr", "₹2.322432 cr", "₹3.354624 cr"],
        ["Single source/route", "₹16.128 cr", "₹5.16096 cr", "₹3.20 cr", "0", "₹8.36096 cr", "30/55/75%", "₹2.508288 cr", "₹4.598528 cr", "₹6.270720 cr"],
        ["Launch handoff", "₹6.912 cr", "₹2.21184 cr", "0", "0", "₹2.21184 cr", "40/65/85%", "₹0.884736 cr", "₹1.437696 cr", "₹1.880064 cr"],
        ["Stale depot mix", "₹6.912 cr", "₹2.21184 cr", "0", "₹6.00 cr", "₹8.21184 cr", "20/40/60%", "₹1.642368 cr", "₹3.284736 cr", "₹4.927104 cr"],
        ["Total", "₹46.08 cr", "₹14.7456 cr", "₹3.20 cr", "₹6.00 cr", "₹23.9456 cr", "—", "₹6.325632 cr", "₹11.643392 cr", "₹16.432512 cr"],
    ],
    [1.5, 1.05, 1.05, 0.7, 0.75, 1.05, 0.85, 1.0, 1.0, 1.0],
    small=True,
)
h3("Case inputs versus judgment")
p("Case-marked inputs: 96 m summer bottles, 8% loss share, ₹60/bottle, 32% contribution margin, ₹3.20 cr emergency air and ₹6.00 cr write-offs/discounts.")
p("Judgment/model choices: 35/35/15/15 contribution split; 100% of air to route fragility; 100% of write-offs to stale depot mix; every capture rate; adding full ₹3.20 cr air rather than only the ₹2.56 cr premium; treating contribution, air and write-offs as additive and independent; and the resulting ₹23.9456 cr combined-impact convention.")
p("The attribution shares are not estimated from the generator’s A008–A011 event-level stock-out weights. They are a separate top-down allocation.")

h2("5.3 Avoided-loss range in scenario replay")
code("""
Avoided_loss_scenario_i = base_economic_impact_i × capture_rate_scenario_i

LOW  total = ₹6.325632 cr
BASE total = ₹11.643392 cr
HIGH total = ₹16.432512 cr
""")
p("These ranges come from capture-rate choices, not statistical confidence intervals. The separate ±25% contribution sensitivity is used for risk-card LOW/HIGH economic-impact values; it is not used in avoided-loss totals. Code: src/links.py::build_loss_attribution; src/replay.py::build_scenario_replay.")

h2("5.4 What replay does and does not simulate")
p("Replay includes Amber/Red dates and notice; conditional co-packer notice on 19 Mar and eligibility on 2 Apr; manual route input 3 May; allocation deadline 9 May; counterfactual air booking 10 May, seven days early; a static buffer-cover line; and human-readable action/owner/approver tables.")
p("Replay does not rerun production, inventory, depot allocation or sales under each recommendation. Avoided loss is entirely the top-down attribution calculation above.")
code("Counterfactual air cost = ₹3.20 cr × 80% = ₹2.56 cr")
p("That ₹2.56 cr is a 20% lower total scenario cost. It happens to equal the actual lot’s separately calculated ₹2.56 cr premium, but those are different concepts. Code: src/replay.py::build_scenario_replay; src/data_generator.py::SyntheticDataGenerator._constrain_and_build_pulp.")

# Section 6
h1("6) Limitations and sensitivity")
h2("6.1 Five weakest assumptions, ranked by headline influence")
p("This ranking is audit judgment, not a fitted elasticity ranking.")
add_table(
    ["Rank", "Weak assumption", "Why it is weak / what it changes"],
    [
        ["1", "Root-cause shares and intervention capture rates", "No measured causal attribution or adoption evidence. Directly determines ₹6.33/₹11.64/₹16.43 cr avoided loss and 1.82-month payback."],
        ["2", "Front-loaded viral path and planner-notice date", "A042 starts at 2.5× and A007 fixes notice at 31 Mar. Together they manufacture the precise Red-on-19-Mar / 12-day-lead story."],
        ["3", "Closure/buffer economics", "Conditional closure weights, ₹180/kg, BOM coefficients and 26% annual carry are assumptions. +1 week has only ₹0.095 cr net benefit and excludes air premium from its objective."],
        ["4", "Flavor-independent channel mix, viral spillover and GT proxy", "DP QC assumed 20% of DP; GT/MT propagation assumed; GT orders generated from latent truth. Affects alert timing, pulp uplift, reforecast accuracy and censoring correction."],
        ["5", "Depot stock factors and stale-mix write-off allocation", "2.20/0.45/0.55/0.10 factors create the inventory story, while 100% of ₹6 cr is assigned to stale mix without ledger or expiry model."],
    ],
    [0.5, 2.5, 5.0],
)

h2("6.2 Sensitivity 1: viral-ramp shape")
p("Only A042, the initial DP QC multiplier, was varied, using the actual generator and detector. Planner notice remains fixed at assumed 31 Mar. Code: audit_sensitivity.py::sensing_sensitivity; results: sensitivity_results.csv.")
add_table(
    ["Initial multiplier", "First Amber", "First Red", "Headline lead: Red if available else Amber", "Amber lead"],
    [
        ["1.0×", "22 Mar", "Not triggered", "9 days", "9 days"],
        ["1.5×", "20 Mar", "Not triggered", "11 days", "11 days"],
        ["2.0×", "18 Mar", "Not triggered", "13 days", "13 days"],
        ["2.5× — base", "18 Mar", "19 Mar", "12 days", "13 days"],
        ["3.0×", "18 Mar", "19 Mar", "12 days", "13 days"],
    ],
    [1.0, 1.0, 1.2, 2.2, 0.9],
)
h3("Does the conclusion hold?")
for item in [
    "Some Amber warning precedes assumed planner notice in every tested path.",
    "The specific Red alert and 12-day headline do not hold at initial multipliers of 1.0–2.0.",
    "Lead values are not monotonic because the headline prefers Red over earlier Amber.",
    "All leads remain measured against assumed 31 Mar notice. An earlier real notice could eliminate them.",
]:
    bullet(item)
callout("Early sensing is plausible in the synthetic design, but the precise 12-day claim is not robust or independently evidenced.", PALE_AMBER)

h2("6.3 Sensitivity 2: closure probability")
p("Annual closure probability was varied while every other input remained unchanged. Code: audit_sensitivity.py::closure_sensitivity; src/supply.py::optimise_buffer.")
add_table(
    ["Annual closure probability", "Zero-buffer expected loss", "Optimal buffer", "Net expected benefit of optimum"],
    [
        ["15%", "₹0.286 cr", "0 weeks", "₹0"],
        ["30%", "₹0.571 cr", "0 weeks", "₹0"],
        ["45%", "₹0.857 cr", "0 weeks", "₹0"],
        ["60% — base", "₹1.143 cr", "1 week", "₹0.0946 cr"],
        ["90%", "₹1.714 cr", "1 week", "₹0.561 cr"],
    ],
    [1.4, 1.6, 1.0, 1.8],
)
p("The one-week option’s carry break-even probability is approximately 53.91%.")
h3("Does the conclusion hold?")
for item in [
    "No. At or below 45% in the tested grid, the optimum is no additional buffer.",
    "At the case-encoded 60%, the one-week decision has a very small margin.",
    "Adding the already-displayed expected air premium to the objective changes the optimum from 1 week to 2 weeks, with combined cost ₹1.676 cr.",
]:
    bullet(item)
callout("The buffer conclusion is sensitive both to probability and to the objective definition.", PALE_AMBER)

h2("6.4 Sensitivity 3: lost-contribution attribution split")
p("Only the four contribution shares were changed, leaving air/write-off assignments and capture rates intact. Code: audit_sensitivity.py::attribution_sensitivity; src/links.py::build_loss_attribution; src/budget.py::budget_impact.")
add_table(
    ["Contribution split: late/route/launch/stale", "Avoided LOW", "Avoided BASE", "Avoided HIGH", "Base payback"],
    [
        ["35/35/15/15 — base", "₹6.326 cr", "₹11.643 cr", "₹16.433 cr", "1.824 months"],
        ["Equal 25/25/25/25", "₹6.399 cr", "₹11.717 cr", "₹16.506 cr", "1.813 months"],
        ["Route-heavy 15/55/15/15", "₹6.473 cr", "₹11.938 cr", "₹16.727 cr", "1.779 months"],
        ["Sensing-heavy 55/15/15/15", "₹6.178 cr", "₹11.348 cr", "₹16.138 cr", "1.872 months"],
        ["Extreme 0/0/0/100 to stale mix", "₹5.109 cr", "₹10.058 cr", "₹14.847 cr", "2.112 months"],
    ],
    [2.4, 1.0, 1.0, 1.0, 1.0],
)
h3("Does the conclusion hold?")
for item in [
    "Positive modeled benefit survives these split variations.",
    "The precise ₹11.64 cr benefit and 1.82-month payback do change.",
    "Robustness is limited: fixed air/write-off totals and positive assumed capture rates remain. If adoption/capture is zero, avoided benefit is zero regardless of split.",
]:
    bullet(item)
callout("The arithmetic is stable across alternative splits, but the business case remains wholly dependent on unvalidated capture assumptions.", PALE_AMBER)

h2("6.5 Other material simplifications and gaps")
limitations = [
    "No integrated physical flow. Sales losses, production cuts, pulp stock and depot stock are separately constructed. No end-to-end finished-goods or transportation conservation model. Code: SyntheticDataGenerator.generate; src/reconciliation.py::reconcile.",
    "‘Last-year mix’ is mostly a label. Monthly forecasts use current actual sales × ±30%; depot stock uses forward true demand × factors. No last-year data exists.",
    "No real GT outlet validation. The 10.48% weekly WAPE and 34.93% censoring improvement are synthetic and should not be compared directly with monthly 30% WAPE as like-for-like accuracy improvements.",
    "No shelf-life lot simulation. The 30-day MT/QC prebuild rule is displayed, not enforced through expiry lots or channel receipt/rejection transactions. GT rejection rules are absent.",
    "No joint pulp/capacity/co-packer optimisation. Co-packer flexibility, supplier capacity, changeovers, line eligibility and BOM feasibility are not simultaneously modeled.",
    "Pulp constraints affect only part of the story. Passionfruit can constrain DP/PP production, but other pulps never constrain output. The blocked DP launch gate does not physically stop generated DP production.",
    "No full-year simulation. Only Jan–Jun is generated. The 200 m annual volume is an arithmetic anchor, not a simulated annual total.",
    "No realistic transport execution. No trucks, lane capacities, shipment consolidation, vehicle costs, alternate physical routes or transfer shelf-life checks.",
    "No weather/landslide prediction. The 3 May route warning is manual scenario text.",
    "No measured adoption or causal intervention effect. Supplier qualification, air-trigger, co-packer and planner-workflow benefits are assumed.",
    "Approval governance is a prototype. No authentication, role permission enforcement, immutable audit store or ERP integration.",
    "Config is not uniformly live. Fourteen scalar rows are documentary rather than read by Python: A036, A055, A056, A057, A059–A065, A067–A069. Changing their CSV values does not change the hardcoded implementation.",
    "Several case keys are not read: summer_revenue_share, plant_count, region_count, gt_distributor_count, all three shelf-life keys, dragonfruit_domestic_share, and imported-lead minimum/maximum. Related behavior is hardcoded or duplicated elsewhere.",
    "Some function calls use defaults rather than forwarding config. Capacity, shelf-life and some exposure calculations are not guaranteed to respond consistently to config edits.",
    "Source labels are not perfectly consistent. SUP_PASSION is marked CASE while containing synthetic ₹180/kg cost, and channel rows marked CASE coexist with separate FEED_GT/FEED_MT assumptions. The new register separates these where possible and identifies mixed rows.",
]
for index, item in enumerate(limitations, 1):
    bullet(f"{index}. {item}")

# Judge challenges
h1("Things a judge could challenge")
add_table(
    ["Challenge", "How you should answer"],
    [
        ["You engineered the data to tell the story.", "Yes, it is a deterministic case-fitted prototype. Totals are reconciled by construction. We separate case inputs, derived values and 172 modeling assumptions, and do not claim empirical causality."],
        ["Do 50 passing checks prove the model is right?", "No. They prove reproducibility and internal numerical consistency. Several checks are self-referential, and there is no independent case-document validation or end-to-end physical conservation test."],
        ["Is the 12-day sensing lead manufactured?", "It is conditional on assumed 2.5× initial response and 31 Mar notice. Lower front-loading removes Red in our sensitivity. Present it as an illustrative detector result, not a measured historical lead."],
        ["Is ₹11.64 cr a guaranteed saving?", "No. It is a top-down counterfactual using judgmental attribution and capture rates. It is not a confidence interval or booked benefit; it requires a measured pilot."],
        ["Why is one week the optimal buffer?", "Only under 60% closure probability, 26% carry rate and contribution-loss-only objective. Below roughly 54%, zero weeks wins; including expected air premium changes the answer to two weeks."],
        ["Does co-packing solve the spike?", "Not in the 4× scenario. It reduces capacity-only unmet volume but leaves 10.32 m unmet over eight weeks, and cannot create pulp. Flavor flexibility remains unvalidated."],
        ["Did stale depot allocation really cause ₹6 cr?", "The prototype does not prove that. It allocates the case total to stale mix by assumption. Actual write-off, expiry and depot ledgers are needed to test causality."],
        ["What GT visibility do you actually have?", "No outlet-level GT truth. Distributor orders, depot secondary sales and QC are proxies. GT orders here are synthetic and must be replaced and validated with real data."],
        ["Is everything config-driven?", "Entity expansion is tested, but not every parameter is live. The audit register identifies documentary rows, unused case keys and hardcoded rules so we do not overclaim configurability."],
        ["Is the approval system production-ready?", "It is a decision-log prototype only. It records human decisions and executes nothing, but still needs authentication, role enforcement, secure persistence and operational integrations."],
    ],
    [2.1, 5.9],
)

h2("Audit artifacts")
add_table(
    ["File", "Purpose"],
    [
        ["Pulp_Riot_Dragon_Passion_Audit.pdf", "This formatted report"],
        ["assumptions_register.csv", "Exhaustive 244-row assumptions register"],
        ["sensitivity_results.csv", "73 long-form sensitivity metric rows"],
        ["build_assumptions_register.py", "Rebuilds the register from actual config and Python function references"],
        ["audit_sensitivity.py", "Reproduces the viral-ramp, closure, attribution and buffer-objective checks"],
        ["data/reconciliation_checks.csv", "Full 50-check reconciliation output"],
    ],
    [2.2, 5.8],
)
p("End of report.", "BodySmall")


def main() -> int:
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=PAGE_SIZE,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=17 * mm, bottomMargin=15 * mm,
        title="Pulp Riot Dragon Passion — Full Implementation Audit",
        author="Arena.ai Agent Mode",
        subject="Code-verified audit of synthetic data, assumptions, model rules, attribution and sensitivity",
    )
    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    reader = PdfReader(str(OUTPUT))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required = [
        "1) Synthetic data: how it was made",
        "2) Assumptions register",
        "3) Hypotheses the model tests",
        "4) Model parameters and decision rules",
        "5) Loss attribution and replay",
        "6) Limitations and sensitivity",
        "Things a judge could challenge",
        "₹46.08 cr",
        "244",
    ]
    missing = [value for value in required if value not in text]
    if missing:
        raise RuntimeError(f"PDF text validation failed; missing: {missing}")
    if len(reader.pages) < 10:
        raise RuntimeError(f"Unexpectedly short PDF: {len(reader.pages)} pages")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, {len(reader.pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
