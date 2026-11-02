#!/usr/bin/env python3
"""
Fill missing IAM dataset fields using OpenAI (Responses API).

- Preserves existing values, fills ONLY the blanks.
- Works with CSV or Excel (.xlsx).
- Adds coherent, synthetic values (NOT real people): names, emails, titles, dates, etc.
- Enforces simple business rules: unique IDs, date ordering, valid enums.
- Writes the completed file back with the same columns.

Usage:
  pip install --upgrade openai pandas python-dateutil
  export OPENAI_API_KEY=sk-********************************
  python iam_synth_fill.py \
    --in "Roles Entitlement Dummy Test Data file (2nd Draft).xlsx.xlsx" \
    --out "roles_filled.xlsx" \
    --model gpt-4o-mini \
    --batch-size 25 \
    --temperature 0.9

Columns expected (case-sensitive; extra columns are preserved):
  IdentityID, EmployeeID, FirstName, LastName, Email, ManagerID, Department,
  Application, Entitlement, Role, Role_permission, Role Description, AccessLevel_Proposed,
  StartDate, EndDate, Status, LastLoginDate, ProvisioningStatus, SourceSystem, Location,
  JobTitle, AccessLevel, EmployeeType, Role_Description
"""
import os
import json
import argparse
import hashlib
from datetime import datetime, timedelta
from dateutil.parser import parse as dtparse
import pandas as pd
from typing import List, Dict, Any
from openai import OpenAI

REQUIRED_COLS = [
    "IdentityID","EmployeeID","FirstName","LastName","Email","ManagerID","Department",
    "Application","Entitlement","Role","Role_permission","Role Description","AccessLevel_Proposed",
    "StartDate","EndDate","Status","LastLoginDate","ProvisioningStatus","SourceSystem","Location",
    "JobTitle","AccessLevel","EmployeeType","Role_Description"
]

ENUMS = {
    "Department": ["Finance","HR","IT","Security","Sales","Marketing","Operations","Legal","Procurement","Engineering","Support"],
    "Application": ["SAP","Workday","Salesforce","ServiceNow","Okta","Jira","Confluence","GitHub","Snowflake","Oracle ERP","Tableau"],
    "AccessLevel": ["read","write","modify","admin","approve","execute","delete"],
    "AccessLevel_Proposed": ["read","write","modify","admin","approve","execute","delete"],
    "Status": ["Active","Inactive","Suspended","Terminated","Provisioning"],
    "ProvisioningStatus": ["Provisioned","Deprovisioned","Pending","Failed","In-Progress"],
    "EmployeeType": ["Full-Time","Part-Time","Contractor","Intern","Temporary"],
    "SourceSystem": ["Okta","SailPoint","Saviynt","HRIS","CSV Import","Manual Entry"],
    "Location": ["US-VA","US-MD","US-DC","US-NY","US-TX","IN-DL","IN-MH","UK-LON","DE-BER","SG-SIN"]
}

DATE_FIELDS = ["StartDate","EndDate","LastLoginDate"]
OUT_DT_FMT = "%Y-%m-%d"

def detect_input_type(path: str) -> str:
    low = path.lower()
    if low.endswith(".csv"): return "csv"
    if low.endswith(".xlsx") or low.endswith(".xls"): return "excel"
    raise SystemExit("Input must be .csv or .xlsx")

def read_frame(path: str) -> pd.DataFrame:
    t = detect_input_type(path)
    if t == "csv":
        return pd.read_csv(path, dtype=str).fillna("")
    return pd.read_excel(path, dtype=str).fillna("")

def write_frame(df: pd.DataFrame, path: str) -> None:
    if path.lower().endswith(".csv"):
        df.to_csv(path, index=False)
    else:
        df.to_excel(path, index=False)

def hash_row_key(row: Dict[str,str]) -> str:
    key = json.dumps(row, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def normalize_dates(df: pd.DataFrame) -> pd.DataFrame:
    for c in DATE_FIELDS:
        if c in df.columns:
            def norm(v: str) -> str:
                v = (v or "").strip()
                if not v: return ""
                try: return dtparse(v, dayfirst=False).date().strftime(OUT_DT_FMT)
                except Exception: return ""
            df[c] = df[c].map(norm)
    return df

def coerce_business_rules(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure unique IdentityID / EmployeeID across blanks/dupes
    seen_ids = set()
    def uniq(base: str, prefix: str) -> str:
        if base and base not in seen_ids:
            seen_ids.add(base); return base
        i = 1
        while True:
            cand = f"{prefix}{i:06d}"
            if cand not in seen_ids:
                seen_ids.add(cand)
                return cand
            i += 1

    # Pre-mark existing IDs
    for col, pref in [("IdentityID","ID"), ("EmployeeID","EMP")]:
        if col in df.columns:
            for v in df[col].fillna("").tolist():
                vv = (v or "").strip()
                if vv: seen_ids.add(vv)

    # Fill blanks/dupes
    for col, pref in [("IdentityID","ID"), ("EmployeeID","EMP")]:
        if col not in df.columns: continue
        new_vals, seen_local = [], set()
        col_vals = df[col].fillna("").tolist()
        for v in col_vals:
            vv = (v or "").strip()
            if not vv or vv in seen_local or col_vals.count(vv) > 1:
                new_vals.append(uniq(vv, pref))
            else:
                new_vals.append(vv)
            seen_local.add(new_vals[-1])
        df[col] = new_vals

    # Email -> use FirstName/LastName if blank
    if {"Email","FirstName","LastName"}.issubset(df.columns):
        def make_email(fn, ln, domain="example.com"):
            fn = (fn or "").strip().lower()
            ln = (ln or "").strip().lower()
            core = ".".join([p for p in [fn, ln] if p]) or "user"
            return f"{core}@{domain}"
        df["Email"] = [
            (e if (e or "").strip() else make_email(fn, ln))
            for e, fn, ln in zip(df["Email"], df["FirstName"], df["LastName"])
        ]

    # Dates sanity: StartDate ≤ EndDate, and LastLoginDate between StartDate..today if missing
    today = datetime.utcnow().date()
    for i, row in df.iterrows():
        sd = row.get("StartDate", ""); ed = row.get("EndDate", ""); ll = row.get("LastLoginDate", "")
        try: sd_d = dtparse(sd).date() if sd else None
        except: sd_d = None
        try: ed_d = dtparse(ed).date() if ed else None
        except: ed_d = None
        try: ll_d = dtparse(ll).date() if ll else None
        except: ll_d = None

        if sd_d and ed_d and ed_d < sd_d:
            ed_d = sd_d + timedelta(days=90)
        if sd_d and not ll_d:
            midpoint = sd_d + (today - sd_d) // 2
            ll_d = midpoint
        if sd_d: df.at[i,"StartDate"] = sd_d.strftime(OUT_DT_FMT)
        if ed_d: df.at[i,"EndDate"] = ed_d.strftime(OUT_DT_FMT)
        if ll_d: df.at[i,"LastLoginDate"] = ll_d.strftime(OUT_DT_FMT)

    # Enums: coerce blanks/invalids to allowed values deterministically
    for col, choices in ENUMS.items():
        if col in df.columns:
            new_vals = []
            for v in df[col]:
                v = (v or "").strip()
                if v in choices and v:
                    new_vals.append(v)
                else:
                    idx = int(hash_row_key({"v": v, "col": col})[:4], 16) % len(choices)
                    new_vals.append(choices[idx])
            df[col] = new_vals

    return df

def model_fill_batch(client: OpenAI, model: str, batch_rows: List[Dict[str, Any]], temperature: float = 0.9) -> Dict[str, Dict[str, str]]:
    """
    Ask the model to fill ONLY missing fields for each item.
    Returns: { row_index: {MissingCol: value, ...}, ... }
    """
    contract = (
        "Return STRICT JSON ONLY. A JSON object whose keys are the provided 'row_index' values, "
        "and whose values are JSON objects containing ONLY the missing columns for that row.\n"
        "Rules:\n"
        "- Do not include keys for fields that are already non-empty.\n"
        "- Generate synthetic but coherent enterprise IAM data.\n"
        "- For dates use YYYY-MM-DD.\n"
        "- Email should align with FirstName/LastName if possible.\n"
        "- AccessLevel/AccessLevel_Proposed must be one of: {access_levels}.\n"
        "- Department, Application, Status, ProvisioningStatus, EmployeeType, SourceSystem, Location must come from given enums.\n"
        "- Role_Description: 1–2 sentences summarizing effective access using Role, Role_permission, Entitlement, Department, Application.\n"
    ).format(access_levels=",".join(ENUMS["AccessLevel"]))

    payload = {
        "required_columns": REQUIRED_COLS,
        "enums": ENUMS,
        "rows": batch_rows
    }

    resp = client.responses.create(
        model=model,
        temperature=temperature,
        instructions=(
            "You are an IAM data synthesizer. Preserve existing non-empty fields. "
            "Only fill blanks, keeping values plausible and consistent. Avoid PII. No markdown."
        ),
        input=contract + "\nPayload:\n" + json.dumps(payload, ensure_ascii=False),
    )
    text = (getattr(resp, "output_text", None) or "").strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise RuntimeError(f"Model did not return JSON: {text[:200]}...")
    data = json.loads(text[s:e+1])

    fixed: Dict[str, Dict[str, str]] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            fixed[k] = {kk: ("" if vkk is None else str(vkk)) for kk, vkk in v.items()}
    return fixed

def batch_iterable(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="Input CSV/XLSX path")
    ap.add_argument("--out", dest="out_path", required=True, help="Output CSV/XLSX path")
    ap.add_argument("--model", default="gpt-4o-mini", help="OpenAI model (default: gpt-4o-mini)")
    ap.add_argument("--batch-size", type=int, default=25, help="Rows per request")
    ap.add_argument("--temperature", type=float, default=0.9, help="Creativity for synthetic data")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in your environment.")

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    df = read_frame(args.in_path)

    # Ensure required columns exist (create empty if missing)
    for c in REQUIRED_COLS:
        if c not in df.columns:
            df[c] = ""

    df = normalize_dates(df)

    # Build a list of rows with missing fields
    pending: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        missing = [c for c in REQUIRED_COLS if not str(row.get(c, "")).strip()]
        if missing:
            row_payload = {
                "row_index": idx,
                "present": {c: str(row.get(c,"")) for c in REQUIRED_COLS if str(row.get(c,"")).strip()},
                "missing": missing
            }
            pending.append(row_payload)

    # Batch call the model
    updates: Dict[int, Dict[str, str]] = {}
    for batch in batch_iterable(pending, args.batch_size):
        result = model_fill_batch(client, args.model, batch, temperature=args.temperature)
        for k, v in result.items():
            try:
                updates[int(k)] = v
            except ValueError:
                pass

    # Apply updates
    for idx, patch in updates.items():
        for col, val in patch.items():
            df.at[idx, col] = val

    # Coerce rules post-fill (unique IDs, enums, dates)
    df = normalize_dates(df)
    df = coerce_business_rules(df)

    write_frame(df, args.out_path)
    print(f"✅ Wrote: {args.out_path}")

if __name__ == "__main__":
    main()
