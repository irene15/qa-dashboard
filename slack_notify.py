import os, json, requests

webhook    = os.environ.get("SLACK_WEBHOOK_URL", "")
token      = os.environ.get("SLACK_BOT_TOKEN", "")
channel    = os.environ.get("SLACK_CHANNEL_ID", "")

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

# Send text via webhook
if webhook:
    requests.post(webhook, json={"text": msg})
    print("Text message sent")

# Send screenshot via bot token
if token and channel and os.path.exists("dashboard.png"):
    with open("dashboard.png", "rb") as f:
        content = f.read()

    r1 = requests.get(
        "https://slack.com/api/files.getUploadURLExternal",
        headers={"Authorization": f"Bearer {token}"},
        params={"filename": "dashboard.png", "length": len(content)}
    )
    data1 = r1.json()
    print("getUploadURL:", data1.get("ok"), data1.get("error", ""))

    if data1.get("ok"):
        r2 = requests.post(
            data1["upload_url"],
            data=content,
            headers={"Content-Type": "image/png"}
        )
        print("Upload status:", r2.status_code)

        r3 = requests.post(
            "https://slack.com/api/files.completeUploadExternal",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "files": [{"id": data1["file_id"]}],
                "channel_id": channel,
            }
        )
        print("completeUpload:", r3.json().get("ok"), r3.json().get("error", ""))
else:
    print("No screenshot or missing token/channel — skipping image upload")
