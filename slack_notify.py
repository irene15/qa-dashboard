import os, json, requests

webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
if not webhook:
    print("No webhook URL, skipping")
    exit(0)

with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

kpi     = data.get("kpi", {})
weekly  = data.get("weekly", {}).get("kpi", {})
quarter = data.get("quarterly", {})
q_label = quarter.get("label", "Quarter")
q_kpi   = quarter.get("kpi", {})

msg = (
    f"📊 *QA Dashboard — {data.get('last_updated', '')}*\n"
    f"\n"
    f"*ALL TIME*\n"
    f"  Returned tickets: {kpi.get('returned_cards', 0)} ({kpi.get('pct_returned', 0)}%)\n"
    f"  Avg returns: {kpi.get('avg_return_count', 0)}\n"
    f"  Failed QG: {kpi.get('failed_qg_count', 0)}\n"
    f"\n"
    f"*THIS WEEK*\n"
    f"  New returns: {weekly.get('returned_cards', 0)} tickets\n"
    f"  New failed QG: {weekly.get('failed_qg_count', 0)} tickets\n"
    f"\n"
    f"*{q_label}*\n"
    f"  New returns: {q_kpi.get('returned_cards', 0)} tickets\n"
    f"  New failed QG: {q_kpi.get('failed_qg_count', 0)} tickets"
)

r = requests.post(webhook, json={"text": msg})
print("Slack response:", r.status_code)
