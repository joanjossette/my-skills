#!/usr/bin/env python3
"""
SAP Masterlist vs Encounter List reconciliation.

Scans a directory for:
  - one or more SAP Masterlist PDFs ("Masterlist of Registered Beneficiaries
    with First Patient Encounter" — PhilHealth KONSULTA export). Each PDF's
    header states its own "Applicable Coverage: <Month> <Year>".
  - one or more Encounter List CSV exports (any *.csv in the directory).

Produces a single .xlsx workbook:
  - Summary                         : headline numbers + per-period cross-check table
  - All Encounters                  : every encounter CSV combined, deduplicated by Encounter ID
  - SAP - <Month Year>              : full masterlist listing, one sheet per uploaded PDF
  - Matched - <Month Year>          : PIN found in both, one row per PIN (see selection rule below)
  - Enc Only - <Month Year>         : PIN in encounters (in scope) but not in that period's masterlist
  - SAP Only - <Month Year>         : masterlist registrant with no in-scope encounter yet
  - Blank-Invalid PIN               : encounter rows whose PIN could not be parsed

Matching key: PhilHealth Identification Number (PIN).

Cross-check scope for a given coverage period: encounters whose "Encounter Signed"
date is on or before the last calendar day of that period's month. Encounters still
marked "Pending" (not yet signed) are excluded from every cross-check and counted
separately in the Summary.

Representative-record selection: a single PIN can have multiple in-scope encounter
records. When that happens, Matched and Enc Only show ONE row, chosen by:
  1) order that PIN's records chronologically by Encounter Signed date,
  2) prefer the earliest record whose PhilHealth Transaction No is not "Pending",
  3) if every record for that PIN is still Pending, fall back to the earliest one.

Usage:
    python3 build_report.py --input-dir /path/to/folder [--output report.xlsx]

The input folder should contain the SAP Masterlist PDF(s) and Encounter CSV(s)
directly (subfolders are not scanned). Nothing else in the folder is required —
any other file types present are ignored.
"""

import argparse
import calendar
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Missing dependency: pdfplumber. Install with: pip install pdfplumber --break-system-packages", file=sys.stderr)
    raise

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Missing dependency: openpyxl. Install with: pip install openpyxl --break-system-packages", file=sys.stderr)
    raise

MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_name) if m}
PIN_RE = re.compile(r'^\d{9,12}$')

# ----------------------------------------------------------------------------
# SAP Masterlist PDF extraction
# ----------------------------------------------------------------------------

def extract_masterlist(path):
    with pdfplumber.open(path) as pdf:
        page0_text = pdf.pages[0].extract_text() or ""
        rows = []
        for page in pdf.pages:
            for t in page.extract_tables():
                for r in t:
                    rows.append(r)

    cov_m = re.search(r'Applicable Coverage:\s*([A-Za-z]+)\s+(\d{4})', page0_text)
    sap_m = re.search(r'SAP Number\s*:\s*(\S+)', page0_text)
    acc_m = re.search(r'Accreditation Number:\s*(\S+)', page0_text)
    hci_m = re.search(r'Health Care Institution \(HCI\) Name:\s*(.+?)\s{2,}', page0_text)

    if not cov_m:
        raise ValueError(f"Could not find 'Applicable Coverage: <Month> <Year>' header in {path}")

    month_name, year = cov_m.group(1).upper(), int(cov_m.group(2))
    if month_name not in MONTHS:
        raise ValueError(f"Unrecognized month '{month_name}' in {path}")
    month_num = MONTHS[month_name]
    last_day = calendar.monthrange(year, month_num)[1]
    coverage_end = datetime(year, month_num, last_day, 23, 59, 59)
    coverage_label = f"{month_name.title()} {year}"

    sap_number = sap_m.group(1) if sap_m else ""
    accreditation = acc_m.group(1) if acc_m else ""
    hci_name = hci_m.group(1).strip() if hci_m else ""

    records = {}
    for row in rows:
        if len(row) < 6 or not row[0] or not row[0].strip().isdigit():
            continue
        no, pin, name, mtype, dor, doe = row[:6]
        pin = pin.strip()
        if not PIN_RE.match(pin):
            continue
        records[pin] = {
            "no": no, "pin": pin, "name": name.replace("\n", " ").strip(),
            "member_type": mtype.replace("\n", " ").strip(),
            "date_reg": dor.strip(), "date_encounter": doe.strip(),
            "sap_number": sap_number, "coverage": coverage_label,
            "accreditation": accreditation, "hci_name": hci_name,
        }

    return {
        "coverage_label": coverage_label,
        "coverage_end": coverage_end,
        "sap_number": sap_number,
        "accreditation": accreditation,
        "hci_name": hci_name,
        "records": records,
        "source_file": Path(path).name,
    }


# ----------------------------------------------------------------------------
# Encounter CSV extraction
# ----------------------------------------------------------------------------

FIELDS = ["Encounter ID", "Create Date", "Appointment Date", "PhilHealth Tranche",
          "PhilHealth Transaction No", "PhilHealth Transmittal ID", "PhilHealth Case No",
          "PhilHealth Member PIN", "PhilHealth Member Type", "Patient Name", "Patient MRN",
          "Cancelled", "Status", "Encounter Signed", "Reason for Visit"]


def parse_create_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_signed_date(s):
    s = (s or "").strip()
    if not s or s.lower() == "pending":
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def extract_encounters(csv_paths):
    header = None
    raw_rows = []
    for fp in csv_paths:
        with open(fp, encoding="utf-8-sig", newline='') as f:
            rows = list(csv.reader(f))
        if not rows:
            continue
        if header is None:
            header = rows[0]
        for row in rows[1:]:
            raw_rows.append((Path(fp).name, row))

    if header is None:
        return []

    idx = {name: i for i, name in enumerate(header)}
    missing = [f for f in FIELDS if f not in idx]
    if missing:
        print(f"Warning: encounter CSV missing expected column(s): {missing}", file=sys.stderr)

    def get(row, field):
        i = idx.get(field)
        if i is None or i >= len(row):
            return ""
        return row[i].strip()

    by_encounter_id = {}
    order = []
    dup_count = 0
    for src, row in raw_rows:
        eid = get(row, "Encounter ID")
        if not eid:
            continue
        if eid in by_encounter_id:
            dup_count += 1
            continue
        rec = {f: get(row, f) for f in FIELDS}
        rec["source_file"] = src
        rec["create_dt"] = parse_create_date(rec["Create Date"])
        rec["signed_dt"] = parse_signed_date(rec["Encounter Signed"])
        rec["pin_valid"] = bool(PIN_RE.match(rec["PhilHealth Member PIN"]))
        by_encounter_id[eid] = rec
        order.append(eid)

    if dup_count:
        print(f"Note: {dup_count} duplicate Encounter ID row(s) dropped (kept first occurrence).")

    return [by_encounter_id[eid] for eid in order]


def select_representative(elist):
    """Pick one record per PIN when multiple in-scope encounters exist:
    order by Encounter Signed date, prefer the earliest non-'Pending' Transaction No,
    fall back to the earliest record if every one is still Pending."""
    if not elist:
        return None
    ordered = sorted(elist, key=lambda e: (e["signed_dt"] or datetime.min))
    non_pending = [e for e in ordered if (e.get("PhilHealth Transaction No") or "").strip() != "Pending"]
    return non_pending[0] if non_pending else ordered[0]


def norm_name(s):
    s = s.upper()
    s = re.sub(r'[^A-Z\s]', ' ', s)
    return set(t for t in s.split() if len(t) > 2)


# ----------------------------------------------------------------------------
# Workbook building
# ----------------------------------------------------------------------------

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=14, color="1F4E78")
SECTION_FONT = Font(name=FONT, size=11, bold=True, color="1F4E78")
SUB_FONT = Font(name=FONT, size=10, italic=True, color="555555")
NORMAL = Font(name=FONT, size=10)
RED_FILL = PatternFill("solid", fgColor="FCE4E4")
GREEN_FILL = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 28


def autofit(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def write_data_row(ws, values, fill=None):
    ws.append(values)
    r = ws.max_row
    for c in range(1, len(values) + 1):
        cell = ws.cell(row=r, column=c)
        cell.font = NORMAL
        cell.border = BORDER
        if fill:
            cell.fill = fill
    return r


def safe_sheet_name(name):
    for ch in ['\\', '/', '*', '[', ']', ':', '?']:
        name = name.replace(ch, '-')
    return name[:31]


def build_workbook(masterlists, encounters, output_path):
    wb = openpyxl.Workbook()

    # ---- All Encounters ----
    ws_enc = wb.active
    ws_enc.title = "All Encounters"
    enc_headers = ["Encounter ID", "PIN", "Patient Name", "Create Date", "Appointment Date",
                   "PhilHealth Tranche", "PhilHealth Transaction No", "PhilHealth Case No",
                   "Encounter Signed", "Member Type", "Cancelled", "Status", "Source File"]
    ws_enc.append(enc_headers)
    style_header(ws_enc, 1, len(enc_headers))
    sorted_enc = sorted(encounters, key=lambda e: e["create_dt"] or datetime.min)
    for e in sorted_enc:
        write_data_row(ws_enc, [
            e["Encounter ID"], e["PhilHealth Member PIN"], e["Patient Name"], e["Create Date"],
            e["Appointment Date"], e["PhilHealth Tranche"], e["PhilHealth Transaction No"],
            e["PhilHealth Case No"], e["Encounter Signed"], e["PhilHealth Member Type"],
            e["Cancelled"], e["Status"], e["source_file"]
        ])
    ws_enc.freeze_panes = "A2"
    autofit(ws_enc, [26, 16, 26, 17, 18, 10, 20, 18, 14, 12, 10, 12, 32])
    ws_enc.sheet_view.showGridLines = False
    note = ws_enc.cell(row=1, column=15, value=f"{len(encounters)} unique Encounter IDs (deduplicated across all encounter files)")
    note.font = SUB_FONT

    summary_blocks = []

    for ml in masterlists:
        label = ml["coverage_label"]
        cov_end = ml["coverage_end"]
        records = ml["records"]
        sheet_tag = safe_sheet_name(label)

        # ---- Full SAP masterlist sheet ----
        ws_sap = wb.create_sheet(safe_sheet_name(f"SAP - {sheet_tag}"))
        ws_sap["A1"] = (f"SAP Masterlist — Coverage: {label}  |  SAP Number: {ml['sap_number']}  |  "
                         f"Accreditation: {ml['accreditation']}  |  HCI: {ml['hci_name']}")
        ws_sap["A1"].font = SUB_FONT
        ws_sap.merge_cells("A1:F1")
        hdr_row = 2
        sap_headers = ["No.", "PIN", "Name", "Member Type", "Date Registered", "Date of 1st Encounter"]
        for c, h in enumerate(sap_headers, start=1):
            ws_sap.cell(row=hdr_row, column=c, value=h)
        style_header(ws_sap, hdr_row, len(sap_headers))
        for pin, rec in sorted(records.items(), key=lambda kv: int(kv[1]["no"])):
            write_data_row(ws_sap, [rec["no"], pin, rec["name"], rec["member_type"], rec["date_reg"], rec["date_encounter"]])
        ws_sap.freeze_panes = f"A{hdr_row + 1}"
        autofit(ws_sap, [8, 16, 30, 14, 16, 20])
        ws_sap.sheet_view.showGridLines = False

        # ---- Scope: encounters signed on or before this period's cutoff ----
        in_scope = [e for e in encounters if e["signed_dt"] is not None and e["signed_dt"] <= cov_end]
        unsigned_excluded = [e for e in encounters if e["signed_dt"] is None]

        by_pin = {}
        for e in in_scope:
            by_pin.setdefault(e["PhilHealth Member PIN"], []).append(e)

        enc_pins_valid = {p for p in by_pin if PIN_RE.match(p)}
        sap_pins = set(records.keys())
        matched_pins = sorted(enc_pins_valid & sap_pins)
        enc_only_pins = enc_pins_valid - sap_pins
        sap_only_pins = sorted(sap_pins - enc_pins_valid, key=lambda p: int(records[p]["no"]))

        sap_name_idx = {}
        for pin, rec in records.items():
            for tok in norm_name(rec["name"]):
                sap_name_idx.setdefault(tok, []).append(pin)
        truly_missing, likely_typo = [], []
        for pin in enc_only_pins:
            e0 = by_pin[pin][0]
            toks = norm_name(e0["Patient Name"])
            cands = set()
            for t in toks:
                cands.update(sap_name_idx.get(t, []))
            good = [c for c in cands if len(toks & norm_name(records[c]["name"])) >= 2]
            (likely_typo if good else truly_missing).append(pin)

        # ---- Matched sheet ----
        ws_m = wb.create_sheet(safe_sheet_name(f"Matched - {sheet_tag}"))
        m_headers = ["PIN", "SAP Name", "SAP Number", "Applicable Coverage", "SAP Member Type",
                     "SAP Date Registered", "SAP Date of 1st Encounter", "# Encounters in scope",
                     "Encounter ID", "Encounter Patient Name", "Appointment Date", "Create Date",
                     "PhilHealth Tranche", "PhilHealth Transaction No", "Encounter Signed", "Status"]
        ws_m.append(m_headers)
        style_header(ws_m, 1, len(m_headers))
        for pin in matched_pins:
            rec = records[pin]
            elist = by_pin[pin]
            e = select_representative(elist)
            write_data_row(ws_m, [
                pin, rec["name"], rec["sap_number"], rec["coverage"], rec["member_type"],
                rec["date_reg"], rec["date_encounter"], len(elist),
                e["Encounter ID"], e["Patient Name"], e["Appointment Date"], e["Create Date"],
                e["PhilHealth Tranche"], e["PhilHealth Transaction No"], e["Encounter Signed"], e["Status"]
            ], fill=GREEN_FILL)
        ws_m.freeze_panes = "A2"
        autofit(ws_m, [16, 26, 18, 16, 14, 16, 20, 14, 26, 26, 18, 17, 10, 20, 16, 14])
        ws_m.sheet_view.showGridLines = False

        # ---- Encounter-only sheet ----
        ws_eo = wb.create_sheet(safe_sheet_name(f"Enc Only - {sheet_tag}"))
        eo_headers = ["PIN (as entered)", "Patient Name", "# Encounters in scope", "Appointment Date",
                      "Encounter Signed", "Status", "Encounter ID", "Possible Cause"]
        ws_eo.append(eo_headers)
        style_header(ws_eo, 1, len(eo_headers))
        for pin in sorted(enc_only_pins, key=lambda p: by_pin[p][0]["Patient Name"]):
            elist = by_pin[pin]
            e = select_representative(elist)
            cause = ("No matching name in SAP Masterlist — likely not yet registered/submitted"
                      if pin in truly_missing else
                      "Possible PIN entry error — name found under a different PIN in SAP")
            write_data_row(ws_eo, [pin, e["Patient Name"], len(elist), e["Appointment Date"],
                                    e["Encounter Signed"], e["Status"], e["Encounter ID"], cause], fill=RED_FILL)
        ws_eo.freeze_panes = "A2"
        autofit(ws_eo, [20, 28, 16, 18, 16, 14, 26, 46])
        ws_eo.sheet_view.showGridLines = False

        # ---- SAP-only sheet ----
        ws_so = wb.create_sheet(safe_sheet_name(f"SAP Only - {sheet_tag}"))
        so_headers = ["No.", "PIN", "SAP Name", "Member Type", "Date Registered", "Date of 1st Encounter"]
        ws_so.append(so_headers)
        style_header(ws_so, 1, len(so_headers))
        for pin in sap_only_pins:
            rec = records[pin]
            write_data_row(ws_so, [rec["no"], pin, rec["name"], rec["member_type"], rec["date_reg"], rec["date_encounter"]])
        ws_so.freeze_panes = "A2"
        autofit(ws_so, [8, 16, 30, 14, 16, 20])
        ws_so.sheet_view.showGridLines = False

        summary_blocks.append({
            "label": label, "cov_end": cov_end.strftime("%m/%d/%Y"), "sap_number": ml["sap_number"],
            "sap_total": len(records), "enc_pins_in_scope": len(enc_pins_valid),
            "matched": len(matched_pins), "enc_only": len(enc_only_pins),
            "enc_only_no_name": len(truly_missing), "enc_only_typo": len(likely_typo),
            "sap_only": len(sap_only_pins), "unsigned_excluded": len(unsigned_excluded),
        })

    # ---- Blank/Invalid PIN sheet ----
    invalid = [e for e in encounters if not e["pin_valid"]]
    ws_bad = wb.create_sheet("Blank-Invalid PIN")
    bad_headers = ["Encounter ID", "Patient Name", "PIN value", "Status", "Create Date"]
    ws_bad.append(bad_headers)
    style_header(ws_bad, 1, len(bad_headers))
    for e in invalid:
        write_data_row(ws_bad, [e["Encounter ID"], e["Patient Name"], e["PhilHealth Member PIN"] or "(blank)",
                                 e["Status"], e["Create Date"]])
    autofit(ws_bad, [26, 26, 14, 14, 18])
    ws_bad.sheet_view.showGridLines = False

    # ---- Summary sheet (inserted first) ----
    ws_sum = wb.create_sheet("Summary", 0)
    ws_sum["B2"] = "SAP Masterlist vs Encounter List — Reconciliation Summary"
    ws_sum["B2"].font = TITLE_FONT
    hci = masterlists[0]["hci_name"] if masterlists else ""
    acc = masterlists[0]["accreditation"] if masterlists else ""
    ws_sum["B3"] = f"HCI: {hci}  |  Accreditation No.: {acc}"
    ws_sum["B3"].font = SUB_FONT
    ws_sum["B4"] = ("Matching key: PhilHealth Identification Number (PIN)  |  Cross-check scope: encounters "
                     "with Encounter Signed date on or before the last day of each coverage month")
    ws_sum["B4"].font = SUB_FONT

    r = 6
    ws_sum.cell(row=r, column=2, value="Consolidated Encounters").font = SECTION_FONT
    r += 1
    ws_sum.cell(row=r, column=2, value="Total unique Encounter IDs (all files, deduplicated)").font = NORMAL
    ws_sum.cell(row=r, column=3, value=len(encounters)).font = NORMAL
    r += 1
    ws_sum.cell(row=r, column=2, value="Encounters with blank/invalid PhilHealth PIN").font = NORMAL
    ws_sum.cell(row=r, column=3, value=len(invalid)).font = NORMAL
    r += 1
    ws_sum.cell(row=r, column=2, value="Encounters not yet signed (Encounter Signed = Pending) — excluded from all cross-checks").font = NORMAL
    ws_sum.cell(row=r, column=3, value=sum(1 for e in encounters if e["signed_dt"] is None)).font = NORMAL
    r += 2

    sap_hdr = ["Coverage Period", "SAP Registrants", "Cutoff Date", "Signed Encounters ≤ Cutoff (unique PIN)",
               "Matched", "Encounter-Only (not in SAP)", "  → no name match", "  → possible PIN typo",
               "SAP-Only (no encounter yet)"]
    ws_sum.cell(row=r, column=2, value="Per-Coverage-Period Cross-Check").font = SECTION_FONT
    r += 1
    for c, h in enumerate(sap_hdr, start=2):
        ws_sum.cell(row=r, column=c, value=h)
    for c in range(2, 2 + len(sap_hdr)):
        cell = ws_sum.cell(row=r, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = BORDER
    ws_sum.row_dimensions[r].height = 30
    r += 1
    for b in summary_blocks:
        vals = [b["label"], b["sap_total"], b["cov_end"], b["enc_pins_in_scope"], b["matched"],
                b["enc_only"], b["enc_only_no_name"], b["enc_only_typo"], b["sap_only"]]
        for c, v in enumerate(vals, start=2):
            cell = ws_sum.cell(row=r, column=c, value=v)
            cell.font = NORMAL
            cell.border = BORDER
        r += 1

    if summary_blocks:
        r += 1
        ws_sum.cell(row=r, column=2, value="Headline finding").font = Font(name=FONT, size=11, bold=True, color="C00000")
        r += 1
        b0 = summary_blocks[0]
        rate = (b0['matched'] / b0['enc_pins_in_scope']) if b0['enc_pins_in_scope'] else 0
        finding = (f"For {b0['label']} (cutoff {b0['cov_end']}), {b0['matched']} of {b0['enc_pins_in_scope']} unique "
                   f"patients with a signed encounter on or before the coverage cutoff were found in the SAP "
                   f"Masterlist by PIN ({rate:.1%} match rate). {b0['enc_only']} did not match by PIN "
                   f"({b0['enc_only_no_name']} with zero name overlap either). Separately, {b0['sap_only']} of "
                   f"{b0['sap_total']} SAP registrants have no in-scope encounter yet.")
        c = ws_sum.cell(row=r, column=2, value=finding)
        c.font = NORMAL
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws_sum.merge_cells(start_row=r, start_column=2, end_row=r, end_column=10)
        ws_sum.row_dimensions[r].height = 75
        r += 2

    ws_sum.cell(row=r, column=2, value="Notes / Assumptions").font = SECTION_FONT
    r += 1
    notes = [
        "\"Submitted\" for cross-check purposes is the encounter's Encounter Signed date. Encounters still "
        "marked Pending (not yet signed) are excluded from every cross-check tab and counted separately.",
        "When a PIN has more than one in-scope encounter, Matched and Enc Only show a single representative "
        "record: sorted by Encounter Signed date, preferring the earliest record whose Transaction No is not "
        "\"Pending\"; if every record for that PIN is still Pending, the earliest Pending record is shown "
        "instead. The '# Encounters in scope' column on the Matched tab shows how many records existed for "
        "that PIN.",
        "Every SAP Masterlist PDF found in the input folder gets its own 'SAP - <Month Year>' sheet plus "
        "matching 'Matched / Enc Only / SAP Only' sheets for that coverage period.",
        "All Encounters sheet is the single consolidated, deduplicated (by Encounter ID) source used for "
        "every cross-check tab.",
    ]
    for n in notes:
        ws_sum.cell(row=r, column=2, value="• " + n).font = NORMAL
        ws_sum.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
        ws_sum.merge_cells(start_row=r, start_column=2, end_row=r, end_column=10)
        ws_sum.row_dimensions[r].height = 40
        r += 1

    autofit(ws_sum, [3, 34, 16, 14, 20, 12, 20, 14, 16, 22])
    ws_sum.sheet_view.showGridLines = False

    wb.save(output_path)
    return summary_blocks


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def discover_files(input_dir):
    input_dir = Path(input_dir)
    pdfs = sorted(input_dir.glob("*.pdf"))
    csvs = sorted(input_dir.glob("*.csv"))
    return pdfs, csvs


def main():
    ap = argparse.ArgumentParser(description="Reconcile SAP Masterlist PDF(s) against Encounter List CSV(s).")
    ap.add_argument("--input-dir", required=True, help="Folder containing the SAP Masterlist PDF(s) and Encounter CSV(s)")
    ap.add_argument("--output", default="SAP_vs_Encounter_Comparison.xlsx", help="Output .xlsx path")
    args = ap.parse_args()

    pdfs, csvs = discover_files(args.input_dir)
    if not pdfs:
        print(f"No SAP Masterlist PDF(s) found in {args.input_dir}", file=sys.stderr)
        sys.exit(1)
    if not csvs:
        print(f"No Encounter List CSV(s) found in {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(pdfs)} masterlist PDF(s): {[p.name for p in pdfs]}")
    print(f"Found {len(csvs)} encounter CSV(s): {[c.name for c in csvs]}")

    masterlists = []
    seen_periods = {}
    for p in pdfs:
        ml = extract_masterlist(str(p))
        if ml["coverage_label"] in seen_periods:
            print(f"Warning: multiple PDFs claim coverage '{ml['coverage_label']}' "
                  f"({seen_periods[ml['coverage_label']]} and {p.name}) — keeping the later one processed.", file=sys.stderr)
        seen_periods[ml["coverage_label"]] = p.name
        masterlists.append(ml)
        print(f"  {ml['coverage_label']}: {len(ml['records'])} registrants, SAP# {ml['sap_number']}")
    masterlists.sort(key=lambda m: m["coverage_end"])

    encounters = extract_encounters([str(c) for c in csvs])
    print(f"Consolidated {len(encounters)} unique encounters (by Encounter ID).")

    summary_blocks = build_workbook(masterlists, encounters, args.output)
    print(f"\nSaved: {args.output}")
    for b in summary_blocks:
        print(f"  {b['label']}: matched={b['matched']} enc_only={b['enc_only']} sap_only={b['sap_only']}")


if __name__ == "__main__":
    main()
