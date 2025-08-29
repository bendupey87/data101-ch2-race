
# Business Problem → Solution Race (Explicit Scoring)

This v2 version removes fuzzy keyword scoring. Students answer using radios/multiselects with a fixed answer key. Scores are deterministic.

## Files
- `app_v2.py` — Streamlit app
- `prompts_explicit.json` — scenarios, options, and answer keys
- `requirements.txt` — minimal deps

## Run locally
```bash
pip install -r requirements.txt
streamlit run app_v2.py
```

## Deploy
- Push these three files to your repo (or a subfolder and point Streamlit to `app_v2.py`).
- Optional: create `runtime.txt` with `3.11` to pin Python.

## Scoring
- Problem (single choice): 2 points
- Goals (multi-select): up to 3 points total (1 each, optional penalty for extra wrong picks)
- Model (single choice): 2 points
- Feasibility (2 binary): 2 points
- Plan (single choice): 1 point
**Total = 10 points**
