
import json
from pathlib import Path
from datetime import datetime, timezone

import streamlit as st
import pandas as pd
from filelock import FileLock, Timeout

DATA_FILE = Path("submissions_v2.csv")
LOCK_FILE = Path("submissions_v2.csv.lock")
PROMPTS_FILE = Path("prompts_explicit.json")

st.set_page_config(page_title="Business Problem → Solution Race (Explicit Scoring)", layout="wide")

@st.cache_data
def load_prompts():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def init_storage():
    if not DATA_FILE.exists():
        df = pd.DataFrame(columns=[
            "ts_iso","round","team","scenario","score",
            "detail_problem","detail_goals","detail_model","detail_feas","detail_plan"
        ])
        df.to_csv(DATA_FILE, index=False)

def read_submissions():
    if not DATA_FILE.exists():
        init_storage()
    return pd.read_csv(DATA_FILE)

def write_submission(row: dict):
    init_storage()
    lock = FileLock(str(LOCK_FILE))
    try:
        with lock.acquire(timeout=5):
            df = pd.read_csv(DATA_FILE)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df.to_csv(DATA_FILE, index=False)
    except Timeout:
        st.error("Server is busy. Please try submitting again.")

def score_section_single(selected_idx, answer_idx, points):
    return points if selected_idx == answer_idx else 0

def score_section_multi(selected_indices, answer_indices, points_each, penalize_extras=True):
    correct = set(answer_indices)
    chosen = set(selected_indices)
    hits = len(correct.intersection(chosen))
    extras = len(chosen - correct) if penalize_extras else 0
    raw = hits * points_each - (extras if penalize_extras else 0)
    return max(raw, 0)

def score_binary(answers, key_items, points_each):
    total = 0
    for given, item in zip(answers, key_items):
        total += points_each if given == item["answer"] else 0
    return total

def main():
    st.title("🏁 Business Problem → Solution Race — Explicit Scoring")
    st.caption("Chapter 2: Converting business problems into analytical solutions — no fuzzy matching, only right/wrong choices.")

    prompts = load_prompts()

    left, right = st.columns([2,1], gap="large")

    with left:
        st.subheader("Submit your team's answers")
        with st.form("submit_form", clear_on_submit=True):
            team = st.text_input("Team name", placeholder="e.g., Data Warriors", max_chars=50)
            scenario = st.selectbox("Scenario", options=list(prompts.keys()))
            round_num = st.number_input("Round #", 1, 50, value=1, step=1)

            block = prompts[scenario]

            # Problem
            st.markdown("**1) Business problem**")
            prob_idx = st.radio(block["problem_single"]["question"],
                                options=list(range(len(block["problem_single"]["options"]))),
                                format_func=lambda i: block["problem_single"]["options"][i],
                                index=None)

            # Goals (multi)
            st.markdown("**2) Business goals (select all that apply)**")
            goal_labels = block["goals_multi"]["options"]
            goal_choices = st.multiselect(block["goals_multi"]["question"], options=list(range(len(goal_labels))),
                                          format_func=lambda i: goal_labels[i])

            # Model
            st.markdown("**3) Analytics solution/model**")
            model_idx = st.radio(block["model_single"]["question"],
                                 options=list(range(len(block["model_single"]["options"]))),
                                 format_func=lambda i: block["model_single"]["options"][i],
                                 index=None)

            # Feasibility (binary)
            st.markdown("**4) Feasibility**")
            feas_items = block["feasibility_binary"]["question_items"]
            feas_answers = []
            for item in feas_items:
                ans = st.radio(item["text"], options=["Yes","No"], horizontal=True, index=0)
                feas_answers.append(ans)

            # Plan
            st.markdown("**5) Analytics plan**")
            plan_idx = st.radio(block["plan_single"]["question"],
                                 options=list(range(len(block["plan_single"]["options"]))),
                                 format_func=lambda i: block["plan_single"]["options"][i],
                                 index=None)

            submitted = st.form_submit_button("Submit answers 🧮")

        if submitted:
            if not team.strip():
                st.warning("Enter a team name.")
            elif prob_idx is None or model_idx is None or plan_idx is None:
                st.warning("Answer all required questions (1, 3, and 5).")
            else:
                # Score
                s1 = score_section_single(prob_idx,
                                          block["problem_single"]["answer_index"],
                                          block["problem_single"]["points"])
                s2 = score_section_multi(goal_choices,
                                         block["goals_multi"]["answer_indices"],
                                         block["goals_multi"]["points_each"],
                                         penalize_extras=block["goals_multi"].get("penalize_extras", True))
                s3 = score_section_single(model_idx,
                                          block["model_single"]["answer_index"],
                                          block["model_single"]["points"])
                s4 = score_binary(feas_answers,
                                  feas_items,
                                  block["feasibility_binary"]["points_each"])
                s5 = score_section_single(plan_idx,
                                          block["plan_single"]["answer_index"],
                                          block["plan_single"]["points"])
                total = s1 + s2 + s3 + s4 + s5

                detail = f"Problem={s1}, Goals={s2}, Model={s3}, Feasibility={s4}, Plan={s5}"
                row = {
                    "ts_iso": datetime.now(timezone.utc).isoformat(),
                    "round": int(round_num),
                    "team": team.strip(),
                    "scenario": scenario,
                    "score": int(total),
                    "detail_problem": s1,
                    "detail_goals": s2,
                    "detail_model": s3,
                    "detail_feas": s4,
                    "detail_plan": s5,
                }
                write_submission(row)
                st.success(f"Submitted! Score = {total} ({detail})")

    with right:
        st.subheader("📊 Live Leaderboard")
        df = read_submissions()
        if df.empty:
            st.info("No submissions yet. Be the first!")
        else:
            latest_round = int(df["round"].max())
            show_round = st.number_input("Leaderboard round", 1, latest_round, value=latest_round, step=1)
            view = df[df["round"] == show_round].copy()
            view["ts_iso"] = pd.to_datetime(view["ts_iso"])
            # best per team
            view.sort_values(["team","score","ts_iso"], ascending=[True, False, True], inplace=True)
            best = view.groupby("team", as_index=False).first()
            best.sort_values(["score","ts_iso"], ascending=[False, True], inplace=True)
            best.insert(0, "rank", range(1, len(best)+1))
            best.rename(columns={"ts_iso":"submitted_utc"}, inplace=True)
            st.dataframe(best[["rank","team","scenario","score","submitted_utc"]],
                         use_container_width=True, hide_index=True)

            with st.expander("All submissions (this round)"):
                st.dataframe(view.sort_values("ts_iso"),
                             use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🧑‍🏫 Instructor Controls")
    with st.form("instructor"):
        colA, colB = st.columns([2,1])
        with colA:
            action = st.selectbox("Action", ["(choose one)", "Start new round", "Reset all data"])
        with colB:
            code = st.text_input("Admin code", type="password", placeholder="enter the code")
        go = st.form_submit_button("Apply")

    admin_code = "letmein"
    if go:
        if code != admin_code:
            st.error("Wrong admin code.")
        else:
            if action == "Start new round":
                st.success("Announce the next round and change the round number above to filter the board.")
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
