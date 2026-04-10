import os
import json
import requests
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────────────────────────
TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY", "YOUR_API_KEY")
TRELLO_TOKEN   = os.environ.get("TRELLO_TOKEN",   "YOUR_TOKEN")
BOARD_ID       = os.environ.get("TRELLO_BOARD_ID","YOUR_BOARD_ID")

# Names of your custom fields in Trello (case-sensitive)
RETURN_COUNT_FIELD_NAME  = "return_count"
QUALITY_GATE_FIELD_NAME  = "quality_gate"

OUTPUT_FILE   = "data.json"
TEMPLATE_FILE = "index.html"
# ────────────────────────────────────────────────────────────────────────────

BASE = "https://api.trello.com/1"
AUTH = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}


def get(path, **params):
    r = requests.get(f"{BASE}{path}", params={**AUTH, **params})
    r.raise_for_status()
    return r.json()


def fetch_custom_field_defs(board_id):
    """Returns {field_id: field_name} mapping."""
    fields = get(f"/boards/{board_id}/customFields")
    return {f["id"]: f["name"] for f in fields}


def fetch_lists(board_id):
    """Returns {list_id: list_name} mapping."""
    lists = get(f"/boards/{board_id}/lists")
    return {l["id"]: l["name"] for l in lists}


def fetch_cards(board_id):
    """Returns all open cards with their custom field values."""
    return get(
        f"/boards/{board_id}/cards",
        customFieldItems="true",
        members="true",
        fields="id,name,idList,dateLastActivity,due,url"
    )


def parse_custom_fields(card_cf_items, field_defs):
    """Extracts return_count and quality_gate from a card's customFieldItems."""
    result = {"return_count": 0, "quality_gate": None}

    for item in card_cf_items:
        field_name = field_defs.get(item.get("idCustomField"), "")

        if field_name == RETURN_COUNT_FIELD_NAME:
            val = item.get("value") or {}
            try:
                result["return_count"] = int(val.get("number", 0))
            except (ValueError, TypeError):
                result["return_count"] = 0

        elif field_name == QUALITY_GATE_FIELD_NAME:
            val = item.get("value") or {}
            text = val.get("text", "").strip().lower()
            if text in ("yes", "no"):
                result["quality_gate"] = text.capitalize()
            else:
                result["quality_gate"] = None

    return result


def main():
    print("Fetching board data from Trello…")

    field_defs = fetch_custom_field_defs(BOARD_ID)
    list_map   = fetch_lists(BOARD_ID)
    cards      = fetch_cards(BOARD_ID)

    tickets = []

    for card in cards:
        cf = parse_custom_fields(card.get("customFieldItems", []), field_defs)

        return_count = cf["return_count"]
        quality_gate = cf["quality_gate"]

        # Only include tickets that have been returned at least once
        if return_count < 1:
            continue

        assignees = [m["fullName"] for m in card.get("members", [])]

        tickets.append({
            "card_id":              card["id"],
            "ticket_name":          card["name"],
            "return_count":         return_count,
            "current_status":       list_map.get(card["idList"], "Unknown"),
            "assignee":             ", ".join(assignees) if assignees else "—",
            "created_date":         card["dateLastActivity"][:10],
            "quality_gate":         quality_gate,
            "quality_gate_failed":  quality_gate == "No",
            "card_url":             card["url"],
        })

    # Sort descending by return_count
    tickets.sort(key=lambda t: t["return_count"], reverse=True)

    # ── KPI calculations ────────────────────────────────────────────────────
    total_cards       = len(cards)
    returned_cards    = len(tickets)
    failed_qg_cards   = [t for t in tickets if t["quality_gate_failed"]]
    avg_return        = (
        round(sum(t["return_count"] for t in tickets) / returned_cards, 1)
        if returned_cards else 0
    )
    pct_returned = (
        round(returned_cards / total_cards * 100, 1)
        if total_cards else 0
    )

    # Returns per assignee
    assignee_map = {}
    for t in tickets:
        for name in t["assignee"].split(", "):
            name = name.strip()
            if name and name != "—":
                assignee_map[name] = assignee_map.get(name, 0) + t["return_count"]

    returns_per_assignee = [
        {"assignee": k, "returns": v}
        for k, v in sorted(assignee_map.items(), key=lambda x: -x[1])
    ]

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%b %d, %Y"),
        "kpi": {
            "total_cards":       total_cards,
            "returned_cards":    returned_cards,
            "pct_returned":      pct_returned,
            "avg_return_count":  avg_return,
            "failed_qg_count":   len(failed_qg_cards),
        },
        "tickets":               tickets,
        "failed_qg":             sorted(failed_qg_cards, key=lambda t: t["created_date"], reverse=True),
        "returns_per_assignee":  returns_per_assignee,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Inject data into index.html so it works when opened locally via file://
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            html = f.read()

        inline = f"<script>\nvar __DASHBOARD_DATA__ = {json.dumps(output, ensure_ascii=False)};\n</script>"
        marker = "<!-- __INJECTED_DATA__ -->"

        if marker in html:
            html = html.split(marker)[0] + marker + "\n" + inline + html.split(marker)[1]
        else:
            html = html.replace("</body>", f"{marker}\n{inline}\n</body>")

        with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Data injected into {TEMPLATE_FILE}")

    print(f"Done. {returned_cards} tickets written to {OUTPUT_FILE}")
    print(f"  Failed QG : {len(failed_qg_cards)}")
    print(f"  Avg returns: {avg_return}")


if __name__ == "__main__":
    main()
