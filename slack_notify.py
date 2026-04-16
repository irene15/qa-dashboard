import os, requests

token   = os.environ.get("SLACK_BOT_TOKEN", "")
channel = os.environ.get("SLACK_CHANNEL_ID", "")

if not token or not channel:
    print("Missing SLACK_BOT_TOKEN or SLACK_CHANNEL_ID")
    exit(0)

if not os.path.exists("dashboard.png"):
    print("No screenshot found")
    exit(0)

with open("dashboard.png", "rb") as f:
    content = f.read()

r1 = requests.get(
    "https://slack.com/api/files.getUploadURLExternal",
    headers={"Authorization": f"Bearer {token}"},
    params={"filename": "dashboard.png", "length": len(content)}
)
data1 = r1.json()
print("getUploadURL:", data1.get("ok"), data1.get("error", ""))

if not data1.get("ok"):
    exit(1)

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
        "initial_comment": "📊 QA Dashboard — This week"
    }
)
print("completeUpload:", r3.json().get("ok"), r3.json().get("error", ""))
