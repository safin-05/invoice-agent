import os
import json
import pypdf
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-haiku-4-5-20251001"

# ── Mock database ─────────────────────────────────────────────────────────────

PO_DATABASE = {
    "PO-1001": {"vendor": "Acme Supplies", "approved_amount": 50000, "currency": "INR"},
    "PO-1002": {"vendor": "Bright Logistics", "approved_amount": 30000, "currency": "INR"},
    "PO-1003": {"vendor": "TechSoft Solutions", "approved_amount": 75000, "currency": "INR"},
}

# ── Tool implementations ──────────────────────────────────────────────────────
# These are plain Python functions. Claude never calls them directly —
# it tells us WHICH tool to call and WITH WHAT arguments. We execute them
# and send the result back. Claude decides what to do next.

def extract_invoice_data(pdf_text: str) -> dict:
    """Pull structured fields out of raw invoice text using regex."""
    import re

    data = {}

    patterns = {
        "invoice_number": r"Invoice Number[:\s]+([A-Z0-9-]+)",
        "po_number":      r"PO Number[:\s]+([A-Z0-9-]+)",
        "due_date":       r"Due Date[:\s]+([\d]+ \w+ \d{4})",
        # TOTAL DUE line looks like: "TOTAL DUE: Rs. 50,000.00"
        "total_due":      r"TOTAL DUE[:\s]+Rs\.?\s*([\d,]+\.?\d*)",
    }

    for field, pattern in patterns.items():
        m = re.search(pattern, pdf_text, re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if field == "total_due":
                value = float(value.replace(",", ""))
            data[field] = value

    return data if data else {"error": "Could not parse any invoice fields from text"}


def lookup_po(po_number: str) -> dict:
    """Check the mock PO database. Returns approved details or not-found."""
    record = PO_DATABASE.get(po_number.strip())
    if record:
        return {"found": True, "po_number": po_number, **record}
    return {"found": False, "po_number": po_number,
            "message": f"No approved PO found for {po_number}"}


def flag_exception(reason: str) -> dict:
    """Record a discrepancy that needs human review."""
    # In production this would write to a DB or send an alert.
    print(f"\n  *** EXCEPTION FLAGGED ***\n  Reason: {reason}\n")
    return {"flagged": True, "reason": reason, "status": "Queued for human review"}


# ── Tool dispatcher ───────────────────────────────────────────────────────────
# Maps the string names Claude uses in its response to the actual functions.

TOOL_FNS = {
    "extract_invoice_data": extract_invoice_data,
    "lookup_po":            lookup_po,
    "flag_exception":       flag_exception,
}

def dispatch(name: str, inputs: dict):
    fn = TOOL_FNS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    return fn(**inputs)


# ── Tool schemas ──────────────────────────────────────────────────────────────
# This is what we send to the API. Claude reads the descriptions to decide
# which tool to call and what arguments to pass — it does NOT see our code.

TOOL_SCHEMAS = [
    {
        "name": "extract_invoice_data",
        "description": (
            "Parse an invoice's raw text and return structured fields: "
            "invoice_number, po_number, total_due (float, INR), and due_date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pdf_text": {
                    "type": "string",
                    "description": "The complete raw text extracted from the invoice PDF.",
                }
            },
            "required": ["pdf_text"],
        },
    },
    {
        "name": "lookup_po",
        "description": (
            "Look up a Purchase Order number in the database. "
            "Returns the vendor name, approved amount, and currency if found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "po_number": {
                    "type": "string",
                    "description": "The PO number from the invoice, e.g. 'PO-1001'.",
                }
            },
            "required": ["po_number"],
        },
    },
    {
        "name": "flag_exception",
        "description": (
            "Flag this invoice for human review. Call this whenever: "
            "the PO is missing, the invoice total doesn't match the approved PO amount, "
            "or any other discrepancy is found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "A clear explanation of the problem, including relevant amounts or IDs.",
                }
            },
            "required": ["reason"],
        },
    },
]


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_agent(pdf_path: str) -> dict:
    """
    Run the invoice agent and return a result dict:
      flagged       – True if flag_exception was called at least once
      flag_reasons  – list of reason strings passed to flag_exception
      final_summary – Claude's closing text
      iterations    – number of API round-trips
    """
    # 1. Read the PDF into plain text
    reader = pypdf.PdfReader(pdf_path)
    pdf_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )
    print(f"[PDF] Read {len(pdf_text)} chars from '{pdf_path}'\n")

    flagged      = False
    flag_reasons = []
    final_summary = ""

    # 2. Seed the conversation with the invoice text and a task description.
    #    'messages' is the growing history we keep appending to each turn.
    messages = [
        {
            "role": "user",
            "content": (
                "You are an invoice-processing agent. Given the invoice text below:\n"
                "1. Extract its structured data.\n"
                "2. Verify the PO number against our database.\n"
                "3. Flag any exceptions (missing PO, amount mismatch, etc.).\n"
                "4. Return a concise final summary of your findings.\n\n"
                f"INVOICE TEXT:\n{pdf_text}"
            ),
        }
    ]

    # 3. Loop until Claude stops requesting tools.
    #    Each iteration = one API call. Claude may call multiple tools per turn.
    iteration = 0
    while True:
        iteration += 1
        print(f"{'-'*50}")
        print(f"Iteration {iteration}: sending {len(messages)} messages to Claude")

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        print(f"Stop reason: {response.stop_reason}")

        # Always append Claude's response to history so it has full context.
        messages.append({"role": "assistant", "content": response.content})

        # stop_reason == "end_turn"  → Claude is done, no more tool calls.
        if response.stop_reason == "end_turn":
            final_summary = next(
                (b.text for b in response.content if hasattr(b, "text")), "(no text)"
            )
            print(f"\n{'='*50}")
            print("FINAL AGENT SUMMARY")
            print('='*50)
            print(final_summary)
            break

        # stop_reason == "tool_use" → Claude wants us to run one or more tools.
        # Collect every tool call in this response, run them all, then send
        # ALL results back in a single "user" turn. This is required by the API.
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"\n  > Tool call : {block.name}")
                print(f"    Arguments : {json.dumps(block.input, indent=14)}")

                # Track flag_exception calls before dispatching so run_tests.py
                # can inspect results without parsing stdout.
                if block.name == "flag_exception":
                    flagged = True
                    flag_reasons.append(block.input.get("reason", ""))

                result = dispatch(block.name, block.input)

                print(f"    Result    : {json.dumps(result, indent=14)}")

                # Each result must reference the tool_use_id from Claude's request.
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

        # Feed results back; the loop continues with Claude's next response.
        messages.append({"role": "user", "content": tool_results})

    return {
        "flagged":       flagged,
        "flag_reasons":  flag_reasons,
        "final_summary": final_summary,
        "iterations":    iteration,
    }


if __name__ == "__main__":
    import sys
    default = os.path.join(os.path.dirname(__file__), "mock_invoice.pdf")
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else default
    run_agent(pdf_path)
