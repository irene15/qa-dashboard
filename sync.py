import os
import json
import requests
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────────────────────────
TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY", "YOUR_API_KEY")
TRELLO_TOKEN   = os.environ.get("TRELLO_TOKEN",   "YOUR_TOKEN")
BOARD_ID       = os.environ.get("TRELLO_BOARD_ID","YOUR_BOARD_ID")

# Names of your custom fields in Trello (case-sensitive)
RETURN_COUNT_FIELD_NAME  = "Returns count"
QUALITY_GATE_FIELD_NAME  = "Quality Gate"

OUTPUT_FILE   = "data.json"
SNAPSHOT_FILE = "snapshot.json"
TEMPLATE_FILE = "index.html"
# ────────────────────────────────────────────────────────────────────────────

BASE = "https://api.trello.com/1"
AUTH = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}


def get(path, **params):
    r = requests.get(f"{BASE}{path}", params={**AUTH, **params})
    r.raise_for_status()
    return r.json()


def fetch_custom_field_defs(board_id):
    fields = get(f"/boards/{board_id}/customFields")
    return {f["id"]: f["name"] for f in fields}


def fetch_lists(board_id):
    lists = get(f"/boards/{board_id}/lists")
    return {l["id"]: l["name"] for l in lists}


def fetch_cards(board_id):
    return get(
        f"/boards/{board_id}/cards",
        customFieldItems="true",
        members="true",
        fields="id,name,idList,dateLastActivity,due,url"
    )


def parse_custom_fields(card_cf_items, field_defs):
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


def load_snapshot():
    """Load previous snapshot. Returns {} if file does not exist yet."""
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(all_tickets):
    snap = {
        t["card_id"]: {
            "return_count": t["return_count"],
            "quality_gate": t["quality_gate"],
        }
        for t in all_tickets
    }
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)


def build_kpi(tickets, total_cards, count_field="return_count"):
    n = len(tickets)
    avg = round(sum(t[count_field] for t in tickets) / n, 1) if n else 0
    pct = round(n / total_cards * 100, 1) if total_cards else 0
    return {
        "total_cards":      total_cards,
        "returned_cards":   n,
        "pct_returned":     pct,
        "avg_return_count": avg,
        "failed_qg_count":  len([t for t in tickets if t["quality_gate_failed"]]),
    }


def main():
    print("Fetching board data from Trello...")

    field_defs   = fetch_custom_field_defs(BOARD_ID)
    list_map     = fetch_lists(BOARD_ID)
    cards        = fetch_cards(BOARD_ID)
    snapshot     = load_snapshot()
    is_first_run = len(snapshot) == 0

    all_tickets = []
    for card in cards:
        cf           = parse_custom_fields(card.get("customFieldItems", []), field_defs)
        assignees    = [m["fullName"] for m in card.get("members", [])]
        all_tickets.append({
            "card_id":             card["id"],
            "ticket_name":         card["name"],
            "return_count":        cf["return_count"],
            "current_status":      list_map.get(card["idList"], "Unknown"),
            "assignee":            ", ".join(assignees) if assignees else "—",
            "created_date":        card["dateLastActivity"][:10],
            "quality_gate":        cf["quality_gate"],
            "quality_gate_failed": cf["quality_gate"] == "No",
            "card_url":            card["url"],
        })

    # ── Tab 1: all-time ─────────────────────────────────────────────────────
    tab1 = sorted(
        [t for t in all_tickets if t["return_count"] > 0],
        key=lambda t: t["return_count"], reverse=True
    )
    tab1_failed_qg = sorted(
        [t for t in tab1 if t["quality_gate_failed"]],
        key=lambda t: t["created_date"], reverse=True
    )

    # ── Tab 2: weekly diff ───────────────────────────────────────────────────
    weekly_tickets   = []
    weekly_failed_qg = []

    if not is_first_run:
        for t in all_tickets:
            prev    = snapshot.get(t["card_id"], {})
            new_rc  = t["return_count"] - prev.get("return_count", 0)
            qg_new_fail = t["quality_gate"] == "No" and prev.get("quality_gate") != "No"

            if new_rc > 0:
                weekly_tickets.append({**t, "new_returns": new_rc})

            if qg_new_fail:
                weekly_failed_qg.append(t)

        weekly_tickets.sort(key=lambda t: t["new_returns"], reverse=True)
        weekly_failed_qg.sort(key=lambda t: t["created_date"], reverse=True)

    total_cards = len(cards)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%b %d, %Y"),
        "is_first_run": is_first_run,
        "kpi":          build_kpi(tab1, total_cards),
        "tickets":      tab1,
        "failed_qg":    tab1_failed_qg,
        "weekly": {
            "kpi":       build_kpi(weekly_tickets, total_cards, count_field="new_returns"),
            "tickets":   weekly_tickets,
            "failed_qg": weekly_failed_qg,
        },
    }

    # Save snapshot for next run
    save_snapshot(all_tickets)

    # Write data.json
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Inject into index.html
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

    print(f"Done.")
    print(f"  Tab 1 — returned tickets : {len(tab1)}")
    print(f"  Tab 1 — failed QG        : {len(tab1_failed_qg)}")
    print(f"  Tab 2 — new returns this week : {len(weekly_tickets)} {'(first run — snapshot saved, Tab 2 empty)' if is_first_run else ''}")
    print(f"  Tab 2 — new failed QG    : {len(weekly_failed_qg)}")


if __name__ == "__main__":
    main()
