import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from filelock import FileLock, Timeout

DATA_FILE = Path("submissions.csv")
LOCK_FILE = Path("submissions.csv.lock")
PROMPTS_FILE = Path("prompts.json")

st.set_page_config(page_title="Business Problem → Solution Race", layout="wide")

@st.cache_data
def load_prompts():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def init_storage():
    if not DATA_FILE.exists():
        df = pd.DataFrame(columns=[
            "ts_iso","round","team","prompt",
            "problem","goal","model",
            "score_problem","score_goal","score_model","total_score"
        ])
        df.to_csv(DATA_FILE, index=False)

def read_submissions() -> pd.DataFrame:
    if not DATA_FILE.exists():
        init_storage()
    return pd.read_csv(DATA_FILE)

def write_submission(row: dict):
    # Ensure file exists
    init_storage()
    # Use a file lock to avoid concurrent write collisions
    lock = FileLock(str(LOCK_FILE))
    try:
        with lock.acquire(timeout=5):
            df = pd.read_csv(DATA_FILE)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df.to_csv(DATA_FILE, index=False)
    except Timeout:
        st.error("Server is busy. Please try submitting again.")

def score_text(text: str, keywords: list[str]) -> int:
    if not text: return 0
    t = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in t)
    # Cap to 3 points per field to keep it simple
    return min(hits, 3)

def score_submission(prompt_name: str, problem: str, goal: str, model: str) -> tuple[int,int,int,int]:
    rules = load_prompts()[prompt_name]
    sp = score_text(problem, rules["problem_keywords"])
    sg = score_text(goal, rules["goal_keywords"])
    sm = score_text(model, rules["model_keywords"])
    return sp, sg, sm, sp + sg + sm

def main():
    st.title("🏁 Business Problem → Solution Race")
    st.caption("Chapter 2: Converting business problems into analytical solutions — live, in-class game")

    prompts = load_prompts()
    col_left, col_right = st.columns([2,1], gap="large")

    with col_left:
        st.subheader("Submit your team's answers")
        with st.form("submit_form", clear_on_submit=True):
            team = st.text_input("Team name", placeholder="e.g., Data Warriors", max_chars=50)
            prompt_name = st.selectbox("Problem prompt", options=list(prompts.keys()))
            round_num = st.number_input("Round #", min_value=1, max_value=20, value=1, step=1)

            st.markdown("**1) State the business problem (plain English):**")
            problem = st.text_area("Business problem", placeholder="What's happening? Who's affected? Why it matters?", height=100)

            st.markdown("**2) Define the business goal(s):**")
            goal = st.text_area("Business goal", placeholder="What should improve? How will we know?", height=100)

            st.markdown("**3) Suggest the analytics solution type/model:**")
            model = st.text_area("Analytics solution", placeholder="Type of model + how the business would use it", height=100)

            submitted = st.form_submit_button("Submit answers 🚀")

        if submitted:
            if not team.strip():
                st.warning("Enter a team name.")
            else:
                sp, sg, sm, total = score_submission(prompt_name, problem, goal, model)
                row = {
                    "ts_iso": datetime.now(timezone.utc).isoformat(),
                    "round": int(round_num),
                    "team": team.strip(),
                    "prompt": prompt_name,
                    "problem": problem.strip(),
                    "goal": goal.strip(),
                    "model": model.strip(),
                    "score_problem": sp,
                    "score_goal": sg,
                    "score_model": sm,
                    "total_score": total,
                }
                write_submission(row)
                st.success(f"Submitted! Auto-score = {total} (Problem {sp} • Goal {sg} • Model {sm})")

    with col_right:
        st.subheader("📊 Live Leaderboard")
        df = read_submissions()
        if df.empty:
            st.info("No submissions yet. Be the first!")
        else:
            # Latest round filter
            latest_round = int(df["round"].max())
            show_round = st.number_input("Leaderboard round", min_value=1, max_value=latest_round, value=latest_round, step=1)
            view = df[df["round"] == show_round].copy()

            # Keep the best (highest score, then earliest timestamp) per team
            view["ts_iso"] = pd.to_datetime(view["ts_iso"])
            view.sort_values(["team","total_score","ts_iso"], ascending=[True, False, True], inplace=True)
            best = view.groupby("team", as_index=False).first()

            # Rank
            best.sort_values(["total_score","ts_iso"], ascending=[False, True], inplace=True)
            best.insert(0, "rank", range(1, len(best)+1))
            best = best[["rank","team","prompt","total_score","score_problem","score_goal","score_model","ts_iso"]]
            best.rename(columns={"ts_iso":"submitted_utc"}, inplace=True)
            st.dataframe(best, use_container_width=True, hide_index=True)

            with st.expander("All submissions (this round)"):
                st.dataframe(view.sort_values("ts_iso"), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🧑‍🏫 Instructor Controls")
    with st.form("instructor"):
        colA, colB, colC = st.columns([2,1,1])
        with colA:
            action = st.selectbox("Action", ["(choose one)", "Start new round", "Reset all data"])
        with colB:
            new_round = st.number_input("Next round #", min_value=1, max_value=100, value=1, step=1)
        with colC:
            code = st.text_input("Admin code", type="password", placeholder="enter the code")
        go = st.form_submit_button("Apply")

    admin_code = os.getenv("ADMIN_CODE", "letmein")
    if go:
        if code != admin_code:
            st.error("Wrong admin code.")
        else:
            if action == "Start new round":
                st.success(f"Announce: Round {int(new_round)} is live!")
            elif action == "Reset all data":
                try:
                    lock = FileLock(str(LOCK_FILE))
                    with lock.acquire(timeout=5):
                        if DATA_FILE.exists():
                            DATA_FILE.unlink()
                        init_storage()
                    st.success("All submissions cleared.")
                except Timeout:
                    st.error("Could not acquire file lock to reset. Try again.")
            else:
                st.info("Choose an action first.")

if __name__ == "__main__":
    init_storage()
    main()