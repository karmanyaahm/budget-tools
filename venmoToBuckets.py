#!/usr/bin/env python3
"""
venmoToBuckets.py
Merge one or more Venmo CSV exports into buckets.csv

  ID, Date (YYYY‑MM‑DD), Memo, Amount

• Amount keeps the sign but no dollar symbol.
• Deduplicates by ID across all inputs.
• Prints each file’s ending balance.
• Prompts on unknown Type rows.
"""
import sys, os, csv, subprocess
from typing import List, Set

def get_our_name() -> str:
    """Return the git user.name, lowercased. Requires two chunks of >3 chars each."""
    try:
        name = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        name = ""
    chunks = name.split()
    if len(chunks) != 2 or any(len(c) <= 3 for c in chunks):
        sys.exit(f"Invalid git user.name {name!r}: need two chunks of >3 chars each")
    return name.lower()

OUR_NAME   = get_our_name()
OUTFILE    = "buckets.csv"

def confirm(msg: str) -> bool:
    return input(msg).strip().lower() in ("y", "yes")

def is_header(row: List[str]) -> bool:
    return "ID" in row and "Datetime" in row and "Ending Balance" in row

def clean_amt(raw: str) -> str:
    return raw.replace("$", "").replace(" ", "")

def process(path: str, writer: csv.writer, seen: Set[str]) -> None:
    with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
        rdr = csv.reader(fh)

        header = False
        id_i=dt_i=type_i=note_i=from_i=to_i=tot_i=end_i=None
        ending_bal = None

        for row in rdr:
            if not any(c.strip() for c in row):
                continue
            if not header:
                if is_header(row):
                    header = True
                    id_i, dt_i      = row.index("ID"), row.index("Datetime")
                    type_i, note_i  = row.index("Type"), row.index("Note")
                    from_i, to_i    = row.index("From"), row.index("To")
                    tot_i,  end_i   = row.index("Amount (total)"), row.index("Ending Balance")
                continue

            tx_id = row[id_i].strip()
            if tx_id == "":                        # balance line
                bal = row[end_i].strip()
                if bal:
                    ending_bal = clean_amt(bal)
                continue
            if not tx_id.isdigit() or tx_id in seen:
                continue

            date     = row[dt_i].split("T")[0]
            tx_type  = row[type_i].strip()
            note     = row[note_i].strip()
            frm, to  = row[from_i].strip(), row[to_i].strip()
            amount   = clean_amt(row[tot_i].strip())

            ttype = tx_type.lower()
            memo  = ""

            if "transfer" in ttype:
                memo = "transfer" + (f" {note}" if note else "")

            elif ttype == "payment":
                if frm.lower() == OUR_NAME or to.lower() == OUR_NAME:
                    memo = f"{frm} to {to}" + (f" {note}" if note else "")
                else:
                    continue

            elif ttype == "charge":
                # NEW FORMAT → "<From> requested from <To> …"
                if frm.lower() == OUR_NAME or to.lower() == OUR_NAME:
                    memo = f"{frm} requested from {to}" + (f" {note}" if note else "")
                else:
                    continue

            else:                                  # unknown type
                print(f"\nUnknown Type '{tx_type}' in {path} (ID {tx_id})")
                if not confirm("Include this transaction? (y/n): "):
                    continue
                custom = input("Enter memo text: ").strip()
                if not custom:
                    continue
                memo = custom

            writer.writerow([tx_id, date, memo, amount])
            seen.add(tx_id)

        print(f"'{path}': Ending balance = {ending_bal or 'N/A'}")

def main() -> None:
    print(f"Using name: {OUR_NAME}")
    if len(sys.argv) < 2:
        print("Usage: python ./venmoToBuckets.py file1.csv [file2.csv …]")
        sys.exit(1)

    if os.path.exists(OUTFILE) and not confirm(f"'{OUTFILE}' exists—overwrite? (y/n): "):
        print("Aborted."); sys.exit(0)

    seen: Set[str] = set()
    with open(OUTFILE, "w", newline="", encoding="utf-8") as out_fh:
        w = csv.writer(out_fh)
        w.writerow(["ID", "Date", "Memo", "Amount"])
        for in_path in sys.argv[1:]:
            if not in_path.lower().endswith(".csv"):
                print(f"Skipping '{in_path}' (not .csv)"); continue
            if not os.path.isfile(in_path):
                print(f"Skipping '{in_path}' (missing)");   continue
            process(in_path, w, seen)

    print(f"\nFinished — {len(seen)} unique transactions → '{OUTFILE}'")

if __name__ == "__main__":
    main()

