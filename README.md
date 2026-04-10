# Engineering & QA Dashboard

Static HTML dashboard fed by a Python script that pulls data from Trello.

## Files

| File | Purpose |
|------|---------|
| `sync.py` | Fetches Trello data → writes `data.json` |
| `index.html` | Dashboard — open in browser |
| `data.json` | Auto-generated, do not edit manually |
| `.github/workflows/weekly_sync.yml` | Runs sync every Sunday 06:00 UTC |

## Setup

### 1. Trello credentials
Get your API key and token from https://trello.com/power-ups/admin

### 2. Find your Board ID
Open your Trello board in browser → the URL looks like:
`https://trello.com/b/BOARD_ID/board-name`

### 3. Check custom field names
In `sync.py`, update these two constants to match exactly what you named them in Trello:
```python
RETURN_COUNT_FIELD_NAME = "Returns count"
QUALITY_GATE_FIELD_NAME = "Quality Gate"
```

### 4. Test locally
```bash
pip install requests
export TRELLO_API_KEY=your_key
export TRELLO_TOKEN=your_token
export TRELLO_BOARD_ID=your_board_id
python sync.py
# then open index.html in browser
```

### 5. GitHub Pages setup
1. Push this repo to GitHub
2. Go to Settings → Pages → Source: `main` branch, `/ (root)`
3. Add three Secrets (Settings → Secrets → Actions):
   - `TRELLO_API_KEY`
   - `TRELLO_TOKEN`
   - `TRELLO_BOARD_ID`
4. The workflow runs every Sunday automatically.
   You can also trigger it manually: Actions → Weekly Trello Sync → Run workflow
