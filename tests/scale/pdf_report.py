"""
Builds the PDF test report from tests/scale/results/results.jsonl: a summary dashboard,
a categorized breakdown (full detail for failures and a representative sample of passes,
compact rows for the rest), and a flat appendix listing every test ID.

Usage:
    python -m tests.scale.pdf_report [--results PATH] [--out PATH]
"""
import argparse
import json
import statistics
import xml.sax.saxutils
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether,
)

RESULTS_PATH_DEFAULT = Path(__file__).resolve().parent / "results" / "results.jsonl"
OUT_PATH_DEFAULT = Path(__file__).resolve().parent / "results" / "AIvana_Voice_Test_Report.pdf"
CASES_DIR_DEFAULT = Path(__file__).resolve().parent / "results" / "cases"

# ReportLab's built-in fonts (Helvetica etc.) are Latin-only -- verified live, Telugu/Kannada/
# Gujarati/etc. content in a case PDF rendered as solid unreadable glyph boxes. This app's
# whole premise is multilingual voice input, so every language it actually produces has to be
# readable in the report, not just English. Nirmala UI (bundled with Windows) covers the
# Indic scripts (Devanagari, Bengali, Gujarati, Gurmukhi, Kannada, Malayalam, Oriya, Tamil,
# Telugu); Tahoma covers Arabic script (Urdu). Registration is best-effort: if a font file
# isn't present (e.g. running on non-Windows), that script's text falls back to boxes rather
# than crashing the whole report -- English-language cases (the majority) are unaffected
# either way since they never need these fonts.
_UNICODE_FONTS_AVAILABLE = {"indic": False, "arabic": False}
try:
    pdfmetrics.registerFont(TTFont("Nirmala", r"C:\Windows\Fonts\Nirmala.ttc", subfontIndex=0))
    _UNICODE_FONTS_AVAILABLE["indic"] = True
except Exception:
    pass
try:
    pdfmetrics.registerFont(TTFont("Tahoma", r"C:\Windows\Fonts\tahoma.ttf"))
    _UNICODE_FONTS_AVAILABLE["arabic"] = True
except Exception:
    pass

# (start, end) Unicode code point ranges -> which registered font covers them.
_SCRIPT_RANGES = [
    (0x0600, 0x06FF, "Tahoma"),    # Arabic (Urdu)
    (0x0750, 0x077F, "Tahoma"),    # Arabic Supplement
    (0x0900, 0x097F, "Nirmala"),   # Devanagari (Hindi, Marathi)
    (0x0980, 0x09FF, "Nirmala"),   # Bengali, Assamese
    (0x0A00, 0x0A7F, "Nirmala"),   # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF, "Nirmala"),   # Gujarati
    (0x0B00, 0x0B7F, "Nirmala"),   # Oriya (Odia)
    (0x0B80, 0x0BFF, "Nirmala"),   # Tamil
    (0x0C00, 0x0C7F, "Nirmala"),   # Telugu
    (0x0C80, 0x0CFF, "Nirmala"),   # Kannada
    (0x0D00, 0x0D7F, "Nirmala"),   # Malayalam
]


def _font_for_text(text: str) -> str:
    """First non-Latin script found in `text` determines the font for the whole string --
    fields in this report are effectively monolingual per-field even when the case overall
    is multilingual (the LLM answers a given field in one language), so this is simpler than
    per-run font-switching and matches what's actually been observed live."""
    for ch in text or "":
        cp = ord(ch)
        for lo, hi, font in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                return font if _UNICODE_FONTS_AVAILABLE[{"Nirmala": "indic", "Tahoma": "arabic"}[font]] else "Helvetica"
    return "Helvetica"


def _rx_text(value) -> str:
    """Prepares a prescription field value for a ReportLab Paragraph: XML-escapes it (raw
    '<'/'&' in clinical text -- e.g. "BP < 90", "T&C" -- would otherwise be parsed as
    malformed markup) and wraps it in a <font face="..."> run matched to its script so
    non-Latin content actually renders instead of showing as boxes."""
    text = str(value) if value is not None else ""
    escaped = xml.sax.saxutils.escape(text)
    font = _font_for_text(text)
    return f'<font face="{font}">{escaped}</font>' if escaped else "--"


CATEGORY_LABELS = {
    "OPD": "OPD -- Single Outpatient Visits",
    "OBS": "IPD -- Short Observation Admissions (1-2 days)",
    "SHORT": "IPD -- Short Treatment Admissions (3-5 days)",
    "LONG": "IPD -- Long-Term Admissions (6-30+ days)",
    "EDGE": "Edge Cases & Error Injection",
}
CATEGORY_ORDER = ["OPD", "OBS", "SHORT", "LONG", "EDGE"]

MAX_ROWS_PER_TABLE = 45  # keeps each Table flowable a manageable page-breaking unit


def load_results(path: Path):
    results = []
    if not path.exists():
        return results
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="TinyMono", parent=styles["Normal"], fontSize=7, leading=9, fontName="Courier"))
    return styles


def _summary_table_data(results):
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = total - passed
    durations = [r.get("duration_sec", 0) for r in results if isinstance(r.get("duration_sec"), (int, float))]
    avg_dur = round(statistics.mean(durations), 2) if durations else 0
    total_tasks = sum(r.get("tasks_created_total", 0) or 0 for r in results)
    interaction_hits = sum(1 for r in results if r.get("interaction_warnings_triggered"))
    return [
        ["Total cases run", str(total)],
        ["Passed", f"{passed} ({(passed / total * 100):.1f}%)" if total else "0"],
        ["Failed", f"{failed} ({(failed / total * 100):.1f}%)" if total else "0"],
        ["Average case duration", f"{avg_dur} sec"],
        ["Total nurse tasks auto-created", str(total_tasks)],
        ["Cases where a drug-interaction warning fired", str(interaction_hits)],
    ]


def _category_counts(results):
    counts = Counter(r.get("category", "?") for r in results)
    pass_counts = Counter(r.get("category", "?") for r in results if r.get("status") == "pass")
    rows = [["Category", "Total", "Passed", "Failed", "Pass rate"]]
    for cat in CATEGORY_ORDER:
        t = counts.get(cat, 0)
        p = pass_counts.get(cat, 0)
        rate = f"{(p / t * 100):.1f}%" if t else "--"
        rows.append([CATEGORY_LABELS.get(cat, cat), str(t), str(p), str(t - p), rate])
    return rows


def _failure_reason_breakdown(results):
    reasons = Counter()
    for r in results:
        if r.get("status") != "pass":
            err = (r.get("error") or "unknown").split(":")[0]
            reasons[err] += 1
    return reasons.most_common(15)


def build_case_pdf(result: dict, out_path: Path):
    """One PDF per test case, written the moment that case finishes -- e.g. OPD-00001.pdf --
    so results are inspectable case-by-case during a long run, not only in the combined
    report generated at the end."""
    styles = _styles()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    story = []
    status = result.get("status", "?")
    status_color = colors.HexColor("#15803d") if status == "pass" else colors.HexColor("#b91c1c")

    story.append(Paragraph(f"Test Case {result.get('test_id', '?')}", styles["Title"]))
    status_style = ParagraphStyle(name="Status", parent=styles["Heading2"], textColor=status_color)
    story.append(Paragraph(status.upper(), status_style))
    story.append(Spacer(1, 0.4 * cm))

    meta_rows = [
        ["Category", CATEGORY_LABELS.get(result.get("category", ""), result.get("category", ""))],
        ["Specialty", result.get("specialty", "")],
        ["Language", result.get("language", "")],
        ["Patient", f"{result.get('age', '')} yr {result.get('age_band', '')} {result.get('gender', '')}"],
        ["Admission length", f"{result.get('admission_days', 0)} day(s)"],
        ["Medication complexity", result.get("med_complexity", "")],
        ["Interacting pair prescribed", " + ".join(result.get("interacting_pair") or []) or "None"],
        ["Edge case type", result.get("edge_type") or "None"],
        ["Duration", f"{result.get('duration_sec', '')} sec"],
        ["Started", result.get("started_at", "")],
        ["Finished", result.get("finished_at", "")],
    ]
    meta_tbl = Table(meta_rows, colWidths=[5 * cm, 10 * cm])
    meta_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Outcome", styles["Heading2"]))
    outcome_rows = [
        ["Nurse tasks auto-created", str(result.get("tasks_created_total", 0))],
        ["Drug-interaction warning fired", "Yes" if result.get("interaction_warnings_triggered") else "No"],
        ["JS errors observed", str(len(result.get("js_errors") or []))],
    ]
    outcome_tbl = Table(outcome_rows, colWidths=[7 * cm, 8 * cm])
    outcome_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(outcome_tbl)
    story.append(Spacer(1, 0.5 * cm))

    prescriptions = result.get("prescriptions") or []
    for rx in prescriptions:
        label = "Prescription" if len(prescriptions) == 1 else f"Prescription -- Visit {rx.get('visit')} (Day {rx.get('day')})"
        story.append(Paragraph(label, styles["Heading2"]))
        field_rows = [
            ["Chief Complaint", rx.get("chiefComplaint")],
            ["History of Present Illness", rx.get("hpi")],
            ["Primary Diagnosis", rx.get("primaryDiagnosis")],
            ["Differential Diagnosis", rx.get("differentialDiagnosis")],
            ["Advice", rx.get("advice")],
        ]
        field_tbl = Table(
            [[Paragraph(f"<b>{k}</b>", styles["Small"]), Paragraph(_rx_text(v), styles["Small"])] for k, v in field_rows],
            colWidths=[4.5 * cm, 10.5 * cm],
        )
        field_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(field_tbl)
        story.append(Spacer(1, 0.25 * cm))

        meds = rx.get("medications") or []
        story.append(Paragraph("Medications", styles["Heading3"]))
        if meds:
            # Plain strings in a Table cell don't wrap -- ReportLab only wraps flowables, so a
            # long generic name (e.g. "Trimethoprim-sulfamethoxazole") overflowed straight
            # into the Dose column instead of wrapping within its own. Wrapping every cell in
            # a Paragraph makes the column widths actually get respected.
            # Table's TEXTCOLOR command can't reach text already colored inside a Paragraph,
            # so the header's white-on-dark-navy has to be set via inline <font> here instead.
            header = [Paragraph(f'<font color="white"><b>{h}</b></font>', styles["Small"])
                      for h in ("Drug", "Dose", "Frequency", "Route", "Duration")]
            med_rows = [header] + [
                [
                    Paragraph(_rx_text(m.get("drugName")), styles["Small"]),
                    Paragraph(_rx_text(m.get("dose")), styles["Small"]),
                    Paragraph(_rx_text(m.get("frequency")), styles["Small"]),
                    Paragraph(_rx_text(m.get("route")), styles["Small"]),
                    Paragraph(_rx_text(m.get("duration")), styles["Small"]),
                ]
                for m in meds if isinstance(m, dict)
            ]
            med_tbl = Table(med_rows, colWidths=[4 * cm, 2.3 * cm, 3.2 * cm, 2 * cm, 3 * cm])
            med_tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(med_tbl)
        else:
            story.append(Paragraph("None prescribed.", styles["Small"]))
        story.append(Spacer(1, 0.2 * cm))

        labs = rx.get("labTests") or []
        story.append(Paragraph("Lab Tests", styles["Heading3"]))
        story.append(Paragraph(_rx_text(", ".join(str(l) for l in labs)) if labs else "None ordered.", styles["Small"]))
        story.append(Spacer(1, 0.4 * cm))

    if not prescriptions and result.get("status") == "pass":
        story.append(Paragraph(
            "No prescription was captured for this case (e.g. an edge-case scenario with no "
            "extraction step, such as an empty-speech or single-word-speech guard test).",
            styles["Small"],
        ))
        story.append(Spacer(1, 0.4 * cm))

    if result.get("error"):
        story.append(Paragraph("Error", styles["Heading2"]))
        story.append(Paragraph(str(result["error"])[:800], styles["Small"]))
        story.append(Spacer(1, 0.3 * cm))

    if result.get("notes"):
        story.append(Paragraph("Notes", styles["Heading2"]))
        for n in result["notes"]:
            story.append(Paragraph(f"&bull; {n}"[:500], styles["Small"]))
        story.append(Spacer(1, 0.3 * cm))

    if result.get("js_errors"):
        story.append(Paragraph("JS Errors", styles["Heading2"]))
        for e in result["js_errors"][:10]:
            story.append(Paragraph(str(e)[:300], styles["TinyMono"]))

    doc.build(story)
    return out_path


def write_case_pdfs_for_new_results(results, cases_dir: Path = CASES_DIR_DEFAULT, seen: set = None):
    """Writes one PDF per result whose test_id isn't already in `seen`, returns the updated
    seen set -- lets a caller (e.g. a tailing watcher) keep calling this cheaply as new lines
    arrive without re-writing PDFs for cases already done."""
    seen = set(seen) if seen else set()
    for r in results:
        test_id = r.get("test_id")
        if not test_id or test_id in seen:
            continue
        build_case_pdf(r, cases_dir / f"{test_id}.pdf")
        seen.add(test_id)
    return seen


def build_pdf(results, out_path: Path, bugs_found=None, ux_changes=None, methodology_notes=None):
    styles = _styles()
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    story = []

    # ---- Cover / Summary ----
    story.append(Paragraph("AIvana OS -- Voice-Input Test Report", styles["Title"]))
    story.append(Paragraph(f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "Every case in this report was driven through a real headless browser with a mocked "
        "microphone/SpeechRecognition firing recognized-speech events at the actual application "
        "UI (opd.html / ipd.html) -- never a raw transcript posted directly to the API. Results "
        "are differentiated by test ID (e.g. OPD-00001, LONG-00042).", styles["Normal"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    summary_tbl = Table(_summary_table_data(results), colWidths=[9 * cm, 6 * cm])
    summary_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Results by Category", styles["Heading2"]))
    cat_tbl = Table(_category_counts(results), colWidths=[8 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.4 * cm])
    cat_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(cat_tbl)
    story.append(Spacer(1, 0.5 * cm))

    reasons = _failure_reason_breakdown(results)
    if reasons:
        story.append(Paragraph("Top Failure Reasons", styles["Heading2"]))
        reason_rows = [["Reason", "Count"]] + [[r, str(c)] for r, c in reasons]
        reason_tbl = Table(reason_rows, colWidths=[12 * cm, 2 * cm])
        reason_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(reason_tbl)
        story.append(Spacer(1, 0.5 * cm))

    if bugs_found:
        story.append(Paragraph("Bugs Found &amp; Fixed", styles["Heading2"]))
        for b in bugs_found:
            story.append(Paragraph(f"&bull; {b}", styles["Small"]))
        story.append(Spacer(1, 0.4 * cm))

    if ux_changes:
        story.append(Paragraph("UX Improvements Trialed", styles["Heading2"]))
        for u in ux_changes:
            story.append(Paragraph(f"&bull; {u}", styles["Small"]))
        story.append(Spacer(1, 0.4 * cm))

    if methodology_notes:
        story.append(Paragraph("Methodology Notes", styles["Heading2"]))
        for m in methodology_notes:
            story.append(Paragraph(f"&bull; {m}", styles["Small"]))

    story.append(PageBreak())

    # ---- Categorized breakdown ----
    by_category = defaultdict(list)
    for r in results:
        by_category[r.get("category", "?")].append(r)

    for cat in CATEGORY_ORDER:
        cat_results = by_category.get(cat, [])
        if not cat_results:
            continue
        story.append(Paragraph(CATEGORY_LABELS.get(cat, cat), styles["Heading1"]))
        failures = [r for r in cat_results if r.get("status") != "pass"]
        passes = [r for r in cat_results if r.get("status") == "pass"]
        story.append(Paragraph(
            f"{len(cat_results)} cases -- {len(passes)} passed, {len(failures)} failed.", styles["Normal"],
        ))
        story.append(Spacer(1, 0.3 * cm))

        if failures:
            story.append(Paragraph("Failures (full detail)", styles["Heading3"]))
            for r in failures[:200]:  # full narrative capped to keep the PDF sane; rest covered in the appendix
                block = [
                    Paragraph(f"<b>{r['test_id']}</b> -- {r.get('specialty', '')} / {r.get('language', '')}", styles["Small"]),
                    Paragraph(f"Error: {r.get('error', 'unknown')}", styles["Small"]),
                ]
                if r.get("notes"):
                    block.append(Paragraph("Notes: " + "; ".join(r["notes"])[:400], styles["Small"]))
                story.append(KeepTogether(block))
                story.append(Spacer(1, 0.15 * cm))
            story.append(Spacer(1, 0.3 * cm))

        sample = passes[:20]
        if sample:
            story.append(Paragraph("Representative passing cases", styles["Heading3"]))
            rows = [["Test ID", "Specialty", "Language", "Days", "Tasks", "Interaction?"]]
            for r in sample:
                rows.append([
                    r["test_id"], r.get("specialty", ""), r.get("language", ""),
                    str(r.get("admission_days", 0)), str(r.get("tasks_created_total", 0)),
                    "Yes" if r.get("interaction_warnings_triggered") else "No",
                ])
            t = Table(rows, colWidths=[2.5 * cm, 3.8 * cm, 2.8 * cm, 1.5 * cm, 1.5 * cm, 2.5 * cm])
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.3 * cm))

        story.append(Paragraph("All cases in this category (compact)", styles["Heading3"]))
        rows = [["Test ID", "Status", "Specialty", "Days", "Tasks", "Duration (s)"]]
        for r in cat_results:
            rows.append([
                r["test_id"], r.get("status", ""), r.get("specialty", "")[:20],
                str(r.get("admission_days", 0)), str(r.get("tasks_created_total", 0)),
                str(r.get("duration_sec", "")),
            ])
        for start in range(1, len(rows), MAX_ROWS_PER_TABLE):
            chunk = [rows[0]] + rows[start:start + MAX_ROWS_PER_TABLE]
            t = Table(chunk, colWidths=[2.5 * cm, 1.8 * cm, 4 * cm, 1.5 * cm, 1.5 * cm, 2.5 * cm], repeatRows=1)
            style = [
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ]
            for i, row in enumerate(chunk[1:], start=1):
                if row[1] != "pass":
                    style.append(("TEXTCOLOR", (1, i), (1, i), colors.red))
            t.setStyle(TableStyle(style))
            story.append(t)
        story.append(PageBreak())

    # ---- Appendix: flat table of every test ID ----
    story.append(Paragraph("Appendix: Full Test ID Index", styles["Heading1"]))
    story.append(Paragraph("Every case in this run, in test-ID order, for quick scanning.", styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))
    sorted_results = sorted(results, key=lambda r: r.get("test_id", ""))
    rows = [["Test ID", "Category", "Status", "Duration (s)"]]
    for r in sorted_results:
        rows.append([r.get("test_id", ""), r.get("category", ""), r.get("status", ""), str(r.get("duration_sec", ""))])
    for start in range(1, len(rows), MAX_ROWS_PER_TABLE * 2):
        chunk = [rows[0]] + rows[start:start + MAX_ROWS_PER_TABLE * 2]
        t = Table(chunk, colWidths=[3.5 * cm, 2.5 * cm, 2.5 * cm, 3 * cm], repeatRows=1)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ]
        for i, row in enumerate(chunk[1:], start=1):
            if row[2] != "pass":
                style.append(("TEXTCOLOR", (2, i), (2, i), colors.red))
        t.setStyle(TableStyle(style))
        story.append(t)

    doc.build(story)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=RESULTS_PATH_DEFAULT)
    parser.add_argument("--out", type=Path, default=OUT_PATH_DEFAULT)
    args = parser.parse_args()

    results = load_results(args.results)
    if not results:
        print(f"No results found at {args.results}")
        return
    out_path = build_pdf(results, args.out)
    print(f"Wrote {out_path} ({len(results)} cases)")


if __name__ == "__main__":
    main()
