"""
Batch test runner for the invoice agent.

Runs each invoice in test_invoices/ through the agent, suppresses the verbose
per-iteration output, then prints a summary table.

Expected outcomes are defined here alongside each test case — if you add new
invoices, add a matching entry to TEST_CASES.
"""
import io
import os
import sys

# Suppress agent's iteration-by-iteration stdout during batch runs.
# We redirect before importing so the module-level client init stays quiet too.
import agent   # noqa: E402  (imported after path setup below)


# ── Test definitions ──────────────────────────────────────────────────────────
# Each entry: (filename, expected_flagged, short label for the expected column)

TEST_CASES = [
    ("invoice_match.pdf",           False, "APPROVED"),
    ("invoice_over.pdf",            True,  "EXCEPTION – amount over PO"),
    ("invoice_vendor_mismatch.pdf", True,  "EXCEPTION – vendor mismatch"),
    ("invoice_no_po.pdf",           True,  "EXCEPTION – no PO number"),
]

INVOICE_DIR = os.path.join(os.path.dirname(__file__), "test_invoices")


# ── Helpers ───────────────────────────────────────────────────────────────────

def short_reason(reasons: list[str], max_len: int = 60) -> str:
    """Collapse flag reasons into one line, truncated for the table."""
    if not reasons:
        return ""
    combined = " | ".join(reasons)
    return combined if len(combined) <= max_len else combined[:max_len - 3] + "..."


def actual_label(result: dict) -> str:
    """Human-readable actual outcome from the agent result dict."""
    if not result["flagged"]:
        return "APPROVED"
    reason = short_reason(result["flag_reasons"])
    return f"EXCEPTION – {reason}" if reason else "EXCEPTION"


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    rows = []

    for filename, expected_flagged, expected_label in TEST_CASES:
        pdf_path = os.path.join(INVOICE_DIR, filename)
        print(f"\nRunning: {filename} ...", flush=True)

        # Redirect stdout to silence the agent's verbose iteration output.
        _saved = sys.stdout
        sys.stdout = io.StringIO()
        try:
            result = agent.run_agent(pdf_path)
        finally:
            sys.stdout = _saved

        actual    = actual_label(result)
        passed    = result["flagged"] == expected_flagged
        rows.append((filename, expected_label, actual, "PASS" if passed else "FAIL",
                     result["iterations"]))

    # ── Print summary table ───────────────────────────────────────────────────
    col_file     = max(len(r[0]) for r in rows)
    col_expected = max(len(r[1]) for r in rows)
    col_actual   = max(len(r[2]) for r in rows)
    col_result   = 4   # PASS / FAIL

    def divider():
        print(
            "+-" + "-" * col_file     + "-+-"
            + "-" * col_expected + "-+-"
            + "-" * col_actual   + "-+-"
            + "-" * col_result   + "-+-"
            + "-------+"
        )

    def row_line(f, e, a, r, iters):
        print(
            f"| {f:<{col_file}} | {e:<{col_expected}} | {a:<{col_actual}} "
            f"| {r:<{col_result}} | {iters:>5} |"
        )

    print("\n")
    divider()
    row_line("filename", "expected", "actual", "result", "iters")
    divider()
    for filename, expected_label, actual, verdict, iters in rows:
        row_line(filename, expected_label, actual, verdict, iters)
    divider()

    passed = sum(1 for *_, v, __ in rows if v == "PASS")
    total  = len(rows)
    print(f"\n{passed}/{total} tests passed.")


if __name__ == "__main__":
    run_all()
