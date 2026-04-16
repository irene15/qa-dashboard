import os
import json
import requests
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────────────────────────
TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY", "YOUR_API_KEY")
TRELLO_TOKEN   = os.environ.get("TRELLO_TOKEN",   "YOUR_TOKEN")
BOARD_ID       = os.environ.get("TRELLO_BOARD_ID","YOUR_BOARD_ID")

RETURN_COUNT_FIELD_NAME  = "return_count"
QUALITY_GATE_FIELD_NAME  = "quality_gate"

OUTPUT_FILE          = "data.json"
SNAPSHOT_FILE        = "snapshot.json"
SNAPSHOT_QUARTER_FILE = "snapshot_quarter.json"
TEMPLATE_FILE        = "index.html"
# ────────────────────────────────────────────────────────────────────────────

BASE = "https://api.trello.com/1"
AUTH = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}


def get_current_quarter(dt):
    return (dt.month - 1) // 3 + 1


def get_quarter_label(dt):
    return f"Q{get_current_quarter(dt)} {dt.year}"


def get(path, **params):
    r = requests.get(f"{BASE}{path}", params={**AUTH, **params})
    r.raise_for_status()
    return r.json()


def fetch_custom_field_defs(board_id):
    fields = get(f"/boards/{board_id}/customFields")
    field_map = {f["id"]: f["name"] for f in fields}
    option_map = {}
    for f in fields:
        for opt in f.get("options", []):
            option_map[opt["id"]] = opt["value"].get("text", "").strip().lower()
    return field_map, option_map


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


def parse_custom_fields(card_cf_items, field_defs, option_map):
    result = {"return_count": 0, "quality_gate": "yes"}
    for item in card_cf_items:
        field_name = field_defs.get(item.get("idCustomField"), "")
        if field_name == RETURN_COUNT_FIELD_NAME:
            val = item.get("value") or {}
            try:
                result["return_count"] = int(val.get("number", 0))
            except (ValueError, TypeError):
                result["return_count"] = 0
        elif field_name == QUALITY_GATE_FIELD_NAME:
            id_value = item.get("idValue")
            if id_value:
                text = option_map.get(id_value, "")
            else:
                val = item.get("value") or {}
                text = val.get("text", "").strip().lower()
            result["quality_gate"] = text if text in ("yes", "no") else "yes"
    return result


def load_snapshot(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(path, all_tickets, quarter_label=None, week_label=None):
    snap = {
        t["card_id"]: {
            "return_count": t["return_count"],
            "quality_gate": t["quality_gate"],
        }
        for t in all_tickets
    }
    if quarter_label:
        snap["__quarter__"] = quarter_label
    if week_label:
        snap["__week__"] = week_label
    with open(path, "w", encoding="utf-8") as f:
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


def calc_diff(all_tickets, snapshot, new_returns_field="new_returns"):
    tickets   = []
    failed_qg = []
    for t in all_tickets:
        prev        = snapshot.get(t["card_id"], {})
        new_rc      = t["return_count"] - prev.get("return_count", 0)
        qg_new_fail = t["quality_gate"] == "no" and prev.get("quality_gate") != "no"
        if new_rc > 0:
            tickets.append({**t, new_returns_field: new_rc})
        if qg_new_fail:
            failed_qg.append(t)
    tickets.sort(key=lambda t: t[new_returns_field], reverse=True)
    failed_qg.sort(key=lambda t: t["created_date"], reverse=True)
    return tickets, failed_qg


def get_week_label(dt):
    # Week runs Friday to Friday
    # Find the most recent Friday (or today if Friday)
    days_since_friday = (dt.weekday() - 4) % 7
    last_friday = dt - __import__('datetime').timedelta(days=days_since_friday)
    return last_friday.strftime("%Y-W%V-fri")


def main():
    print("Fetching board data from Trello...")

    now                    = datetime.now(timezone.utc)
    current_quarter_label  = get_quarter_label(now)
    current_week_label     = get_week_label(now)

    field_defs, option_map = fetch_custom_field_defs(BOARD_ID)
    list_map               = fetch_lists(BOARD_ID)
    cards                  = fetch_cards(BOARD_ID)

    snapshot         = load_snapshot(SNAPSHOT_FILE)
    snap_quarter     = load_snapshot(SNAPSHOT_QUARTER_FILE)

    # Weekly: check if snapshot belongs to current calendar week (Mon–Sun)
    snap_week_label  = snapshot.get("__week__")
    is_new_week      = snap_week_label != current_week_label
    is_first_run     = len(snapshot) == 0

    # Check if quarter snapshot belongs to current quarter
    snap_quarter_label = snap_quarter.get("__quarter__")
    is_new_quarter     = snap_quarter_label != current_quarter_label

    all_tickets = []
    for card in cards:
        cf        = parse_custom_fields(card.get("customFieldItems", []), field_defs, option_map)
        assignees = [m["fullName"] for m in card.get("members", [])]
        all_tickets.append({
            "card_id":             card["id"],
            "ticket_name":         card["name"],
            "return_count":        cf["return_count"],
            "current_status":      list_map.get(card["idList"], "Unknown"),
            "assignee":            ", ".join(assignees) if assignees else "—",
            "created_date":        card["dateLastActivity"][:10],
            "quality_gate":        cf["quality_gate"],
            "quality_gate_failed": cf["quality_gate"] == "no",
            "card_url":            card["url"],
        })

    # ── Tab 1: all-time ──────────────────────────────────────────────────────
    tab1 = sorted(
        [t for t in all_tickets if t["return_count"] > 0],
        key=lambda t: t["return_count"], reverse=True
    )
    tab1_failed_qg = sorted(
        [t for t in tab1 if t["quality_gate_failed"]],
        key=lambda t: t["created_date"], reverse=True
    )

    # ── Tab 2: weekly diff ───────────────────────────────────────────────────
    # If new week — save fresh snapshot, show empty
    if is_first_run or is_new_week:
        weekly_tickets, weekly_failed_qg = [], []
        if is_new_week and not is_first_run:
            print(f"  New week detected ({current_week_label}) — weekly snapshot will reset")
    else:
        weekly_tickets, weekly_failed_qg = calc_diff(all_tickets, snapshot)

    # ── Tab 3: quarterly diff ────────────────────────────────────────────────
    # If new quarter — save fresh snapshot, show empty
    if is_new_quarter:
        save_snapshot(SNAPSHOT_QUARTER_FILE, all_tickets, quarter_label=current_quarter_label)
        quarter_tickets, quarter_failed_qg = [], []
        print(f"  New quarter detected ({current_quarter_label}) — quarter snapshot saved")
    else:
        quarter_tickets, quarter_failed_qg = calc_diff(all_tickets, snap_quarter)

    # Week starts on Friday
    from datetime import timedelta
    days_since_friday = (now.weekday() - 4) % 7
    week_start    = (now - timedelta(days=days_since_friday)).replace(hour=0, minute=0, second=0, microsecond=0)
    quarter       = get_current_quarter(now)
    quarter_month = (quarter - 1) * 3 + 1
    quarter_start = now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)

    # Count active cards per period based on dateLastActivity
    def is_active_since(ticket, since_dt):
        try:
            activity = datetime.fromisoformat(ticket["created_date"]).replace(tzinfo=timezone.utc)
        except Exception:
            return False
        return activity >= since_dt

    # Use raw dateLastActivity from cards for accurate comparison
    card_activity = {c["id"]: c.get("dateLastActivity", "") for c in cards}

    def count_active(since_dt):
        count = 0
        for card in cards:
            raw = card.get("dateLastActivity", "")
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if dt >= since_dt:
                        count += 1
                except Exception:
                    pass
        return count

    active_this_week    = count_active(week_start)
    active_this_quarter = count_active(quarter_start)

    total_cards = len(cards)

    output = {
        "last_updated":   now.strftime("%b %d, %Y"),
        "is_first_run":   is_first_run,
        "kpi":            build_kpi(tab1, total_cards),
        "tickets":        tab1,
        "failed_qg":      tab1_failed_qg,
        "weekly": {
            "kpi":        build_kpi(weekly_tickets, active_this_week, count_field="new_returns"),
            "tickets":    weekly_tickets,
            "failed_qg":  weekly_failed_qg,
        },
        "quarterly": {
            "label":      current_quarter_label,
            "is_new":     is_new_quarter,
            "kpi":        build_kpi(quarter_tickets, active_this_quarter, count_field="new_returns"),
            "tickets":    quarter_tickets,
            "failed_qg":  quarter_failed_qg,
        },
    }

    # Save weekly snapshot (always update — tracks current state)
    save_snapshot(SNAPSHOT_FILE, all_tickets, week_label=current_week_label)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

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
    print(f"  Tab 1 — returned tickets        : {len(tab1)}")
    print(f"  Tab 1 — failed QG               : {len(tab1_failed_qg)}")
    print(f"  Tab 2 — new returns this week   : {len(weekly_tickets)} {'(first run)' if is_first_run else ''}")
    print(f"  Tab 3 — new returns {current_quarter_label:<8}   : {len(quarter_tickets)} {'(new quarter)' if is_new_quarter else ''}")
    print(f"  Tab 3 — new failed QG           : {len(quarter_failed_qg)}")


if __name__ == "__main__":
    main()
