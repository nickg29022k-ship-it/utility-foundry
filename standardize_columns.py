#!/usr/bin/env python3
"""
standardize_columns.py

Normalize messy IAM-style CSV headers so these 6 fields ALWAYS come first:
  1) Role_Description
  2) Application
  3) Department
  4) AccessLevel
  5) Entitlement
  6) Role

Features
- Fuzzy-ish header mapping (prefixes + synonyms + token overlap).
- Auto-detects common encodings (UTF-8/UTF-8-SIG/Windows-1252/Latin-1) unless you override.
- Auto-sniffs delimiters (comma, tab, semicolon, pipe) unless you override.
- Concatenates multiple mapped columns into a single canonical field using a join separator (default " | ").
- Streams rows to avoid high memory usage.

Usage
    python standardize_columns.py input.csv -o output.csv
    # optional flags
    --encoding auto|utf-8|utf-8-sig|cp1252|latin-1
    --delimiter auto|,|\t|;||
    --join-sep " | "

"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple, Iterable, Optional

# ===== Canonical order =====
CANONICAL_ORDER = [
    "Role_Description",
    "Application",
    "Department",
    "AccessLevel",
    "Entitlement",
    "Role",
]

# ===== Synonyms & prefixes for fuzzy-ish matching =====
SYNONYMS: Dict[str, List[str]] = {
    "Role_Description": [
        "role_description", "roledescription", "role desc", "role-desc",
        "desc", "description", "job_description", "role_summary", "summary"
    ],
    "Application": [
        "application", "app", "app_name", "appname", "system", "product"
    ],
    "Department": [
        "department", "dept", "org", "organization", "business_unit", "bu", "team"
    ],
    "AccessLevel": [
        "accesslevel", "access_level", "access", "level", "clearance",
        "permission_level", "privilege", "scope", "tier"
    ],
    "Entitlement": [
        # treat any column starting with "entitlement" as a match
        "entitlement", "entitlements", "entitlement_type", "entitlement_value",
        "entitlement_name", "entitlement_anything", "entitle", "perm", "permission"
    ],
    "Role": [
        "role", "title", "job_role", "job", "position", "functional_role"
    ],
}

PRIORITY_PREFIXES: Dict[str, List[str]] = {
    "Entitlement": ["entitlement"],
    "AccessLevel": ["accesslevel", "access_level", "access", "permissionlevel", "clearance"],
    "Department": ["department", "dept", "org", "organization"],
    "Application": ["application", "app", "system"],
    "Role_Description": ["role_description", "roledescription", "description", "desc"],
    "Role": ["role", "job_role", "title", "position"],
}

_word_re = re.compile(r"[a-z0-9]+")

def norm(s: str) -> str:
    s = s.strip().lower().replace("-", "_").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s

def tokenize(s: str) -> List[str]:
    return _word_re.findall(norm(s))

def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))

@dataclass
class StandardizedRecord:
    Role_Description: str = ""
    Application: str = ""
    Department: str = ""
    AccessLevel: str = ""
    Entitlement: str = ""
    Role: str = ""

    @classmethod
    def headers(cls) -> List[str]:
        return CANONICAL_ORDER[:]

def best_target_for_column(col_name: str) -> Optional[str]:
    n = norm(col_name)
    toks = tokenize(col_name)

    # 1) Priority prefix match
    for target, prefixes in PRIORITY_PREFIXES.items():
        for p in prefixes:
            if n.startswith(p):
                return target

    # 2) Exact token match against synonyms
    for target, syns in SYNONYMS.items():
        for syn in syns:
            if n == norm(syn):
                return target

    # 3) Token-based (Jaccard) similarity against synonyms
    best_tgt, best_score = None, 0.0
    for target, syns in SYNONYMS.items():
        for syn in syns:
            score = jaccard(toks, tokenize(syn))
            if score > best_score:
                best_score = score
                best_tgt = target

    # Threshold to avoid silly mappings
    return best_tgt if (best_score >= 0.34) else None

def build_header_map(headers: List[str]) -> Dict[str, Optional[str]]:
    header_map: Dict[str, Optional[str]] = {}
    for h in headers:
        tgt = best_target_for_column(h)
        header_map[h] = tgt if tgt in CANONICAL_ORDER else None
    return header_map

def standardize_row(row: Dict[str, str], header_map: Dict[str, Optional[str]], join_sep: str) -> Dict[str, str]:
    # Aggregate values for canonical fields
    agg: Dict[str, List[str]] = {k: [] for k in CANONICAL_ORDER}
    passthrough: Dict[str, str] = {}

    for src_col, value in row.items():
        value = value if value is not None else ""
        target = header_map.get(src_col)
        if target in CANONICAL_ORDER:
            if value != "":
                agg[target].append(value)
        else:
            # untouched column stays as-is
            passthrough[src_col] = value

    # Build output row with the first 6 in required order
    out: Dict[str, str] = {}
    for k in CANONICAL_ORDER:
        out[k] = join_sep.join(v for v in agg[k] if v).strip()

    # Then append remaining columns in their original order (but skip those that mapped)
    for src_col, value in row.items():
        if header_map.get(src_col) in CANONICAL_ORDER:
            continue
        out[src_col] = passthrough.get(src_col, value or "")

    return out

# ===== Robust file handling (encodings & delimiter) =====
COMMON_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

def guess_encoding(path: str) -> str:
    # Light-weight: try decoding a small chunk with common encodings
    try:
        with open(path, "rb") as f:
            sample = f.read(8192)
        for enc in COMMON_ENCODINGS:
            try:
                sample.decode(enc)
                return enc
            except UnicodeDecodeError:
                continue
    except Exception:
        pass
    return "utf-8"  # default

def sniff_dialect(path: str, encoding: str) -> Tuple[str, Optional[csv.Dialect]]:
    # Try csv.Sniffer on a small text sample; otherwise fallback to common delimiters
    try:
        with open(path, "r", encoding=encoding, errors="replace") as f:
            sample = f.read(4096)
        # Quick check for TSV/pipe/semicolon
        for delim in ["\t", "|", ";", ","]:
            if delim in sample and sample.count(delim) > 1:
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[delim])
                    return delim, dialect
                except Exception:
                    return delim, None
        # Last resort: sniffer without hints
        dialect = csv.Sniffer().sniff(sample)
        return getattr(dialect, "delimiter", ","), dialect
    except Exception:
        # Fallback to comma
        return ",", None

def standardize_file(in_path: str, out_path: str, encoding_opt: str, delimiter_opt: str, join_sep: str) -> None:
    # Resolve encoding
    encoding = guess_encoding(in_path) if encoding_opt == "auto" else encoding_opt

    # Resolve delimiter
    if delimiter_opt == "auto":
        delim, dialect = sniff_dialect(in_path, encoding)
    else:
        delim, dialect = delimiter_opt, None

    # Read & write streaming
    with open(in_path, "r", encoding=encoding, errors="replace", newline="") as f_in, \
         open(out_path, "w", encoding="utf-8", newline="") as f_out:

        reader = csv.DictReader(f_in, dialect=dialect) if dialect else csv.DictReader(f_in, delimiter=delim)
        rows_iter = iter(reader)

        try:
            first_row = next(rows_iter)
        except StopIteration:
            # Empty file -> write only canonical headers
            writer = csv.DictWriter(f_out, fieldnames=StandardizedRecord.headers())
            writer.writeheader()
            return

        headers = reader.fieldnames or list(first_row.keys())
        header_map = build_header_map(headers)

        remaining_headers = [h for h in headers if (header_map.get(h) not in CANONICAL_ORDER)]
        out_headers = StandardizedRecord.headers() + remaining_headers

        writer = csv.DictWriter(f_out, fieldnames=out_headers)
        writer.writeheader()

        # write first row
        out_first = standardize_row(first_row, header_map, join_sep)
        writer.writerow(out_first)

        # write remaining rows
        for row in rows_iter:
            writer.writerow(standardize_row(row, header_map, join_sep))

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Standardize IAM data columns and ordering.")
    p.add_argument("input", help="Input CSV path")
    p.add_argument("-o", "--output", help="Output CSV path", default="standardized_output.csv")
    p.add_argument("--encoding", default="auto",
                   choices=["auto", "utf-8", "utf-8-sig", "cp1252", "latin-1"],
                   help="Input file encoding (default: auto)")
    p.add_argument("--delimiter", default="auto",
                   help="Input delimiter: auto, ',', '\\t', ';', or '|' (default: auto)")
    p.add_argument("--join-sep", default=" | ",
                   help="Separator used when multiple columns map to the same canonical field (default: ' | ')")
    return p.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    if not os.path.exists(args.input):
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        sys.exit(2)
    try:
        standardize_file(
            in_path=args.input,
            out_path=args.output,
            encoding_opt=args.encoding,
            delimiter_opt=args.delimiter,
            join_sep=args.join_sep,
        )
        print(f"Wrote standardized file to {args.output}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
