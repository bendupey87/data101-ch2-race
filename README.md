
# Business Problem → Solution Race (v3: 3 Rounds, Auto-Scenario)

- Round determines the scenario (no scenario dropdown).
- Each round shows a scenario *title* and *description*.
- Explicit, rule-based scoring (no fuzzy matching).

## Files
- `app_v3.py` — Streamlit app with round→scenario mapping
- `prompts_rounds.json` — round metadata + scenarios + answer keys
- `requirements.txt`

## Run
```bash
pip install -r requirements.txt
streamlit run app_v3.py
```

## Deploy
On Streamlit Cloud, set **Main file path** to `app_v3.py`. (Optional: add `runtime.txt` with `3.11`.)

## Customize
- Change the three rounds or descriptions in `prompts_rounds.json` under `"rounds"`
- Edit scenario answer keys in `"scenarios"`
