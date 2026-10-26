---
name: sap-encounter-reconciliation
description: Reconcile a PhilHealth KONSULTA SAP Masterlist (PDF) against Encounter List exports (CSV) by PhilHealth PIN, producing an Excel workbook with per-coverage-period matched/unmatched breakdowns. Use when the user wants to validate, compare, or cross-check a "SAP Masterlist" against an "Encounter list/export," mentions PhilHealth PIN reconciliation, or asks to check which encountered patients are missing from a SAP Masterlist.
---

# SAP Masterlist vs Encounter List Reconciliation

## What this does

Compares a PhilHealth KONSULTA **SAP Masterlist** ("Masterlist of Registered
Beneficiaries with First Patient Encounter," a PDF export) against one or more
**Encounter List** exports (CSV) from the clinical/EMR system, matched on
**PhilHealth Identification Number (PIN)**. Produces a single formatted `.xlsx`
workbook.

## When to use

Trigger this skill when the user wants to:
- validate or compare a SAP Masterlist against an Encounter list/export
- find which patients seen in encounters are missing from the SAP Masterlist (or vice versa)
- reconcile PhilHealth PIN records between these two sources
- do this for a folder of files rather than uploading them one at a time

## Inputs

Ask the user (if not already given) where the files live: a directory path
containing:
- one or more **SAP Masterlist PDFs** — each PDF's own header states its
  "Applicable Coverage: <Month> <Year>" (e.g. one PDF per month: June 2026,
  July 2026, August 2026, ...). All PDFs in the folder are picked up
  automatically — no need to name them a particular way.
- one or more **Encounter List CSVs** — raw exports from the clinical system.
  All CSVs in the folder are treated as encounter data and consolidated
  together, deduplicated by Encounter ID.

The script only looks directly inside the given folder (it does not recurse
into subfolders), and ignores any file that isn't a `.pdf` or `.csv`.

If the user says they'll upload files instead of pointing to a directory,
that's fine too — stage the uploads into a working folder first (e.g. via
`cp` into a scratch directory) and pass that folder to the script.

## How to run it

```bash
pip install pdfplumber openpyxl --break-system-packages   # only if either import fails
python3 scripts/build_report.py --input-dir /path/to/folder --output SAP_vs_Encounter_Comparison.xlsx
```

The script prints what it found (which PDFs, which CSVs, record counts) and a
one-line result per coverage period before exiting. Read that output — if it
reports 0 PDFs or 0 CSVs found, the folder path is probably wrong or the files
aren't directly inside it.

After it runs, deliver the output `.xlsx` to the user with SendUserFile.

## Matching logic (already built into the script — know this so you can explain results)

- **Match key**: PhilHealth PIN, present in both the Masterlist and the
  Encounter CSV's "PhilHealth Member PIN" column.
- **Cross-check scope, per coverage period**: an encounter counts toward a
  given month's masterlist only if its **Encounter Signed** date falls on or
  before the last calendar day of that month. Encounters still marked
  "Pending" (not yet signed) are excluded from every cross-check and reported
  separately.
- **One row per PIN**: when a PIN has multiple in-scope encounters, the
  Matched and Enc Only sheets collapse them to a single representative row —
  ordered by Encounter Signed date, preferring the earliest record whose
  Transaction No is not "Pending"; if every record for that PIN is still
  Pending, the earliest Pending record is used instead.
- **Name cross-check**: for PINs found in encounters but not in the
  Masterlist, the script also checks whether the patient's name appears
  anywhere in the Masterlist under a *different* PIN (possible transcription
  error) versus no match at all (likely genuinely unregistered), and labels
  each row accordingly.

## Output workbook structure

- `Summary` — headline numbers, a per-coverage-period cross-check table, and
  documented assumptions
- `All Encounters` — every encounter CSV combined, deduplicated by Encounter ID
- `SAP - <Month Year>` — one sheet per Masterlist PDF, full listing
- `Matched - <Month Year>` — PIN found in both, with SAP columns (SAP Number,
  Applicable Coverage, Member Type, dates) and Encounter columns (Encounter
  ID, Appointment Date, Create Date, Tranche, Transaction No, Encounter
  Signed, Status)
- `Enc Only - <Month Year>` — in-scope encounter PIN not found in that
  period's Masterlist, with a "Possible Cause" note
- `SAP Only - <Month Year>` — Masterlist registrant with no in-scope encounter yet
- `Blank-Invalid PIN` — encounter rows whose PIN field couldn't be parsed
  (blank, "Pending", or non-numeric)

## Notes for future changes

If the user asks to change any part of the matching rule (e.g. a different
date field for scoping, a different representative-record priority, adding
columns), edit `scripts/build_report.py` directly — the logic lives in
`extract_masterlist()`, `extract_encounters()`, `select_representative()`,
and `build_workbook()`. Re-run the same CLI command to regenerate the
workbook; there's no separate build step.
