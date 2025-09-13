import json
from pathlib import Path
from datetime import datetime, timezone
import os

import streamlit as st
import pandas as pd
from filelock import FileLock, Timeout

DATA_FILE = Path("submissions_v3.csv")
LOCK_FILE = Path("submissions_v3.csv.lock")
PROMPTS_FILE = Path("prompts_rounds.json")

st.set_page_config(page_title="Business Problem → Solution Race (3 Rounds, Auto-Scenario)", layout="wide")

@st.cache_data
def load_config():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Map rounds for quick lookup
    round_map = {item["round"]: item for item in cfg["rounds"]}
    return cfg, round_map

def init_storage():
    if not DATA_FILE.exists():
        df = pd.DataFrame(columns=[
            "ts_iso","round","team","scenario_key","scenario_title","score",
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
    st.title("🏁 Business Problem → Solution Race — Explicit Scoring (3 Rounds)")
    st.caption("Round determines the scenario. Each round auto-loads a different scenario and description.")

    cfg, round_map = load_config()
    left, right = st.columns([2,1], gap="large")
    # Form state for persistence
    if "form_state" not in st.session_state:
        st.session_state["form_state"] = {
            "team": "",
            "prob_idx": None,
            "goal_choices": [],
            "model_idx": None,
            "feas_answers": [],
            "plan_idx": None,
        }
    form_state = st.session_state["form_state"]
    with left:
        st.subheader("Submit your team's answers")
        round_num = st.number_input("Round #", 1, 3, value=1, step=1)
        meta = round_map.get(int(round_num))
        if not meta:
            st.warning("Round must be 1, 2, or 3.")
            st.stop()
        st.markdown(f"### Scenario: {meta['title']}")
        st.caption(meta["description"])
        scenario_key = meta["scenario_key"]
        block = cfg["scenarios"][scenario_key]
        with st.form("submit_form", clear_on_submit=False):
            # Team name
            team = st.text_input("Team name", value=form_state["team"], placeholder="e.g., Data Warriors", max_chars=50)
            # Problem
            st.markdown(f"**1) Business problem** _(Points: {block['problem_single']['points']})_")
            prob_idx = st.radio(block["problem_single"]["question"],
                                options=list(range(len(block["problem_single"]["options"]))),
                                format_func=lambda i: block["problem_single"]["options"][i],
                                index=form_state["prob_idx"])
            # Goals (multi)
            st.markdown(f"**2) Business goals (select all that apply)** _(Points: {block['goals_multi']['points_each']} each)_")
            goal_labels = block["goals_multi"]["options"]
            goal_choices = st.multiselect(block["goals_multi"]["question"],
                                          options=list(range(len(goal_labels))),
                                          format_func=lambda i: goal_labels[i],
                                          default=form_state["goal_choices"])
            # Model
            st.markdown(f"**3) Analytics solution/model** _(Points: {block['model_single']['points']})_")
            model_idx = st.radio(block["model_single"]["question"],
                                 options=list(range(len(block["model_single"]["options"]))),
                                 format_func=lambda i: block["model_single"]["options"][i],
                                 index=form_state["model_idx"])
            # Feasibility (binary)
            st.markdown(f"**4) Feasibility** _(Points: {block['feasibility_binary']['points_each']} each)_")
            feas_items = block["feasibility_binary"]["question_items"]
            feas_answers = []
            for i, item in enumerate(feas_items):
                ans = st.radio(item["text"], options=["Yes","No"], horizontal=True,
                               index=form_state["feas_answers"][i] if len(form_state["feas_answers"]) > i else 0,
                               key=f"feas_{i}")
                feas_answers.append(ans)
            # Plan
            st.markdown(f"**5) Analytics plan** _(Points: {block['plan_single']['points']})_")
            plan_idx = st.radio(block["plan_single"]["question"],
                                 options=list(range(len(block["plan_single"]["options"]))),
                                 format_func=lambda i: block["plan_single"]["options"][i],
                                 index=form_state["plan_idx"])
            # Mini-game: Click the moving target
            st.markdown("---")
            st.markdown("### 🎮 Mini-Game Challenge (required)")
            st.caption("Click the moving target as many times as you can in 15 seconds! 15+ clicks = bonus points.")
            import streamlit.components.v1 as components
            minigame_html = '''
<style>
#targetGameBox { position: relative; width: 400px; height: 120px; background: #f4f4f4; border: 2px solid #333; margin-bottom: 8px; }
#target { position: absolute; width: 32px; height: 32px; background: #3498db; border-radius: 50%; cursor: pointer; display: none; }
#gameInfo { font-size: 16px; margin-bottom: 4px; }
</style>
<div id="gameInfo">Clicks: <span id="clickCount">0</span> | Time left: <span id="timeLeft">15</span>s</div>
<div id="targetGameBox">
  <div id="target"></div>
</div>
<div id="gameResult"></div>
<input type="hidden" id="minigame_score_hidden" value="0" />
<script>
var box = document.getElementById('targetGameBox');
var target = document.getElementById('target');
var clickCount = 0;
var timeLeft = 15;
var timer = null;
var gameActive = false;
var timerStarted = false;
function randomPos() {
    var x = Math.floor(Math.random() * (box.offsetWidth - target.offsetWidth));
    var y = Math.floor(Math.random() * (box.offsetHeight - target.offsetHeight));
    target.style.left = x + 'px';
    target.style.top = y + 'px';
}
function startGame() {
    clickCount = 0;
    timeLeft = 15;
    gameActive = true;
    timerStarted = false;
    document.getElementById('clickCount').innerText = clickCount;
    document.getElementById('timeLeft').innerText = timeLeft;
    target.style.display = 'block';
    randomPos();
    document.getElementById('minigame_score_hidden').value = 0;
}
target.onclick = function(e) {
    if (!gameActive) return;
    clickCount++;
    document.getElementById('clickCount').innerText = clickCount;
    randomPos();
    if (!timerStarted) {
        timerStarted = true;
        timer = setInterval(function() {
            timeLeft--;
            document.getElementById('timeLeft').innerText = timeLeft;
            if (timeLeft <= 0) endGame();
        }, 1000);
    }
};
function endGame() {
    gameActive = false;
    target.style.display = 'none';
    if (timer) clearInterval(timer);
    var msg = 'Game over! You clicked ' + clickCount + ' times.';
    if (clickCount >= 15) {
        msg += ' Bonus unlocked!';
    }
    document.getElementById('gameResult').innerText = msg;
    document.getElementById('minigame_score_hidden').value = clickCount;
}
// Start game on load
setTimeout(startGame, 500);
</script>
'''
            components.html(minigame_html, height=200)
            # Read mini-game score from hidden input using JS injection
            minigame_score_int = st.session_state.get("minigame_score", 0)
            minigame_score_js = """
<script>
window.addEventListener('DOMContentLoaded', function() {
    setInterval(function() {
        var val = document.getElementById('minigame_score_hidden').value;
        if (window.parent) {
            window.parent.postMessage({minigame_score: val}, '*');
        }
    }, 500);
});
</script>
"""
            st.markdown(minigame_score_js, unsafe_allow_html=True)
            # Use Streamlit's session state to update score
            import streamlit as st
            if "minigame_score" not in st.session_state:
                st.session_state["minigame_score"] = 0
            # Use JS to update session state via postMessage (Streamlit can't do this natively, so user must click submit after game ends)
            submitted = st.form_submit_button("Submit answers 🧮")
            # Save state
            form_state["team"] = team
            form_state["prob_idx"] = prob_idx
            form_state["goal_choices"] = goal_choices
            form_state["model_idx"] = model_idx
            form_state["feas_answers"] = [0 if ans=="Yes" else 1 for ans in feas_answers]
            form_state["plan_idx"] = plan_idx
        # Submission logic
        if submitted:
            # Try to get score from JS hidden input
            import streamlit.components.v1 as components
            minigame_score = st.experimental_get_query_params().get("minigame_score_hidden", ["0"])[0]
            try:
                minigame_score_int = int(minigame_score)
            except:
                minigame_score_int = 0
            if minigame_score_int < 1:
                st.warning("You must play the mini-game before submitting!")
            elif not team.strip():
                st.warning("Enter a team name.")
            elif prob_idx is None or model_idx is None or plan_idx is None:
                st.warning("Answer all required questions (1, 3, and 5).")
            else:
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
                s4 = score_binary(["Yes" if i==0 else "No" for i in form_state["feas_answers"]],
                                  feas_items,
                                  block["feasibility_binary"]["points_each"])
                s5 = score_section_single(plan_idx,
                                          block["plan_single"]["answer_index"],
                                          block["plan_single"]["points"])
                # Mini-game bonus
                bonus = 10 if minigame_score_int >= 15 else 0
                total = s1 + s2 + s3 + s4 + s5 + bonus
                row = {
                    "ts_iso": datetime.now(timezone.utc).isoformat(),
                    "round": int(round_num),
                    "team": team.strip(),
                    "scenario_key": scenario_key,
                    "scenario_title": meta["title"],
                    "score": int(total),
                    "detail_problem": s1,
                    "detail_goals": s2,
                    "detail_model": s3,
                    "detail_feas": s4,
                    "detail_plan": s5,
                    "minigame_score": minigame_score_int,
                    "minigame_bonus": bonus,
                }
                write_submission(row)
                st.success(f"Submitted! Score = {total} (Mini-game clicks: {minigame_score_int}, Bonus: {bonus})")
                st.markdown("### Your Results:")
                # 1) Business problem
                correct_idx = block["problem_single"]["answer_index"]
                if s1:
                    st.markdown(f"<span style='color:green'><b>Business problem: Correct!</b></span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color:red'><b>Business problem: Incorrect.</b></span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='background-color:#ffe6e6'><b>Correct answer:</b> {block['problem_single']['options'][correct_idx]}</span>", unsafe_allow_html=True)
                # 2) Business goals
                correct_goals = set(block["goals_multi"]["answer_indices"])
                chosen_goals = set(goal_choices)
                if s2 == len(correct_goals)*block["goals_multi"]["points_each"]:
                    st.markdown(f"<span style='color:green'><b>Business goals: Correct!</b></span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color:red'><b>Business goals: Incorrect.</b></span>", unsafe_allow_html=True)
                    correct_labels = [block['goals_multi']['options'][i] for i in correct_goals]
                    st.markdown(f"<span style='background-color:#ffe6e6'><b>Correct answers:</b> {', '.join(correct_labels)}</span>", unsafe_allow_html=True)
                # 3) Analytics solution/model
                correct_idx = block["model_single"]["answer_index"]
                if s3:
                    st.markdown(f"<span style='color:green'><b>Analytics solution/model: Correct!</b></span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color:red'><b>Analytics solution/model: Incorrect.</b></span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='background-color:#ffe6e6'><b>Correct answer:</b> {block['model_single']['options'][correct_idx]}</span>", unsafe_allow_html=True)
                # 4) Feasibility
                feas_correct = len(feas_items)*block['feasibility_binary']['points_each']
                if s4 == feas_correct:
                    st.markdown(f"<span style='color:green'><b>Feasibility: Correct!</b></span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color:red'><b>Feasibility: Incorrect.</b></span>", unsafe_allow_html=True)
                    correct_labels = [f"{item['text']} — {item['answer']}" for item in feas_items]
                    st.markdown(f"<span style='background-color:#ffe6e6'><b>Correct answers:</b> {'; '.join(correct_labels)}</span>", unsafe_allow_html=True)
                # 5) Analytics plan
                correct_idx = block["plan_single"]["answer_index"]
                if s5:
                    st.markdown(f"<span style='color:green'><b>Analytics plan: Correct!</b></span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color:red'><b>Analytics plan: Incorrect.</b></span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='background-color:#ffe6e6'><b>Correct answer:</b> {block['plan_single']['options'][correct_idx]}</span>", unsafe_allow_html=True)
                # Reset form state and mini-game
                st.session_state["form_state"] = {
                    "team": "",
                    "prob_idx": None,
                    "goal_choices": [],
                    "model_idx": None,
                    "feas_answers": [],
                    "plan_idx": None,
                }
                st.session_state["minigame_score"] = 0

    with right:
        st.subheader("📊 Live Leaderboard")
        df = read_submissions()
        if df.empty:
            st.info("No submissions yet. Be the first!")
        else:
            latest_round = int(min(3, max(df["round"].max(), 1)))
            show_round = st.number_input("Leaderboard round", 1, 3, value=latest_round, step=1)
            view = df[df["round"] == show_round].copy()
            view["ts_iso"] = pd.to_datetime(view["ts_iso"])
            # best per team
            view.sort_values(["team","score","ts_iso"], ascending=[True, False, True], inplace=True)
            best = view.groupby("team", as_index=False).first()
            best.sort_values(["score","ts_iso"], ascending=[False, True], inplace=True)
            best.insert(0, "rank", range(1, len(best)+1))
            best.rename(columns={"ts_iso":"submitted_utc"}, inplace=True)
            st.dataframe(best[["rank","team","scenario_title","score","submitted_utc"]],
                         use_container_width=True, hide_index=True)

            with st.expander("All submissions (this round)"):
                st.dataframe(view.sort_values("ts_iso"),
                             use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🧑‍🏫 Instructor Controls")
    st.write("Rounds are fixed: 1=Fraud, 2=Churn, 3=Late Deliveries. Change the round above to play the next scenario.")
    with st.form("instructor"):
        action = st.selectbox("Action", ["(choose one)", "Reset all data"])
        code = st.text_input("Admin code", type="password", placeholder="enter the code")
        go = st.form_submit_button("Apply")

    admin_code = os.getenv("ADMIN_CODE", "letmein")

    if go:
        if code != admin_code:
            st.error("Wrong admin code.")
        else:
            if action == "Reset all data":
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
