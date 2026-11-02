#!/usr/bin/env python3
import os, json, csv, argparse, time, hashlib
import pandas as pd
from typing import Dict, Any, List
from openai import OpenAI

# ---- Config ----
MODEL = "gpt-4o"  # or "gpt-4o-mini"
SYSTEM = (
    "You are an experienced IAM analyst. Given Entitlement, Role, Role_Permission, "
    "Department, and Application, write a concise 1–2 sentence role description that "
    "reflects the effective access within the department and application. No markdown, no PII."
)

# Capitalized headers in your CSV:
IN_FIELDS = ["Entitlement", "Role", "Role_permission", "Department", "Application"]
OUT_COL = "Role_Description"

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def stable_id(bundle: Dict[str, str]) -> str:
    return hashlib.sha1(json.dumps(bundle, sort_keys=True).encode("utf-8")).hexdigest()[:16]

def call_openai_batch(model: str, batch_items: List[Dict[str, str]]) -> Dict[str, str]:
    """
    batch_items: [{'id': 'abc123', 'Entitlement': ..., 'Role': ..., ...}, ...]
    Returns {id: description}
    """
    contract = (
        "Return STRICT JSON ONLY mapping each 'id' to a 1–2 sentence description.\n"
        "- Keys: exactly the provided 'id' values.\n"
        "- Values: plain text. No markdown. No extra keys.\n"
    )
    payload = {
        "items": batch_items,
        "fields": IN_FIELDS,
        "instructions": "Write concise enterprise IAM role descriptions."
    }
    resp = client.responses.create(
        model=model,
        instructions=SYSTEM,
        input=contract + "Payload:\n" + json.dumps(payload, ensure_ascii=False),
    )
    text = (getattr(resp, "output_text", None) or "").strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise RuntimeError(f"Model did not return JSON: {text[:200]}...")
    return json.loads(text[s:e+1])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-per-call", type=int, default=40)
    ap.add_argument("--cache", dest="cache_path", default=None)
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in your environment.")

    df = pd.read_csv(args.in_path, dtype=str).fillna("")
    missing = [c for c in IN_FIELDS if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required column(s): {missing}")

    if OUT_COL not in df.columns:
        df[OUT_COL] = ""

    # Build unique combos → ID
    combos: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        bundle = {k: row.get(k, "").strip() for k in IN_FIELDS}
        sid = stable_id(bundle)
        if sid not in combos:
            combos[sid] = {"id": sid, **bundle}

    # Load cache (optional)
    cache: Dict[str, str] = {}
    if args.cache_path and os.path.exists(args.cache_path):
        with open(args.cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)

    # Prepare pending
    pending = [v for k, v in combos.items() if k not in cache]

    # Batch-generate
    for i in range(0, len(pending), args.max_per_call):
        batch = pending[i:i+args.max_per_call]
        mapping = call_openai_batch(args.model, batch)
        cache.update({k: " ".join(v.split()) for k, v in mapping.items()})
        if args.cache_path:
            with open(args.cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

    # Fill the dataframe
    def describe_row(row) -> str:
        bundle = {k: row.get(k, "").strip() for k in IN_FIELDS}
        sid = stable_id(bundle)
        return cache.get(sid, "")

    df[OUT_COL] = df.apply(describe_row, axis=1)
    df.to_csv(args.out_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"✅ Wrote: {args.out_path}")

if __name__ == "__main__":
    main()
