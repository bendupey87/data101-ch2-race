# Business Problem → Solution Race (Streamlit)

A lightweight classroom web game for Chapter 2: convert business problems into analytical solutions.
Students join, pick a prompt, submit three answers (problem, goal, model), and the app auto-scores with simple keyword rules.
A live leaderboard keeps score by round.

## Quick start (local)
```bash
pip install -r requirements.txt
streamlit run app.py
```

The first run creates `submissions.csv` next to the app. Data persists for the lifetime of the Streamlit Cloud instance (sufficient for in-class play).

## Instructor controls
- Start a new round (announces & lets you filter the leaderboard by round).
- Reset all data (requires admin code; default is `letmein`). On Streamlit Cloud, set a secret `ADMIN_CODE` to override.

## Deploy to Streamlit Community Cloud
1. Push this folder to a public GitHub repo.
2. Go to https://share.streamlit.io → "New app" → pick the repo and `app.py`.
3. In the app's Settings → Secrets, add:
   ```
   ADMIN_CODE = "your-secret-code"
   ```
4. Share the app URL or display a QR code in class.

## Customize prompts & scoring
- Edit `prompts.json` to add/remove scenarios and keywords.
- Each of the three fields is scored 0–3 based on matched keywords (case-insensitive), capped at 3 per field.

## Notes
- The app uses a simple CSV file with a file lock. This is fine for a classroom session.
- For long-term storage or cross-instance scaling, swap CSV for Google Sheets, Supabase, etc.