import subprocess, time, os
from playwright.sync_api import sync_playwright

# Start local server
server = subprocess.Popen(
    ["python", "-m", "http.server", "8000"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)
time.sleep(2)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto("http://localhost:8000/index.html", wait_until="networkidle")
        time.sleep(1)
        page.screenshot(path="dashboard.png", full_page=False)
        browser.close()
    print("Screenshot saved: dashboard.png")
finally:
    server.terminate()
