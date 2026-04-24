name: Weekly Trello Sync

on:
  schedule:
    - cron: "0 4 * * 5"   # Every Friday at 04:00 UTC (06:00 CEST, buffer before 9am)
  workflow_dispatch:

permissions:
  contents: write

jobs:
  sync:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install requests playwright && python -m playwright install chromium --with-deps

      - name: Run sync script
        env:
          TRELLO_API_KEY:  ${{ secrets.TRELLO_API_KEY }}
          TRELLO_TOKEN:    ${{ secrets.TRELLO_TOKEN }}
          TRELLO_BOARD_ID: ${{ secrets.TRELLO_BOARD_ID }}
        run: python sync.py

      - name: Commit and push updated files
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data.json index.html snapshot.json snapshot_quarter.json
          git diff --cached --quiet || git commit -m "chore: weekly data sync $(date -u '+%Y-%m-%d')"
          git push

      - name: Take screenshot of dashboard
        run: python screenshot.py

      # Uncomment when ready to send to Slack
      # - name: Send screenshot to Slack
      #   env:
      #     SLACK_BOT_TOKEN:  ${{ secrets.SLACK_BOT_TOKEN }}
      #     SLACK_CHANNEL_ID: ${{ secrets.SLACK_CHANNEL_ID }}
      #   run: python slack_notify.py
