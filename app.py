
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
    # State for form persistence
    if "form_state" not in st.session_state:
        st.session_state["form_state"] = {
            "team": "",
            "prob_idx": None,
            "goal_choices": [],
            "model_idx": None,
            "feas_answers": [],
            "plan_idx": None,
            "minigame_done": False,
            "minigame_value": None,
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
            # Mini-game: Interactive side-scroller (HTML/JS)
            st.markdown("---")
            st.markdown("### 🎮 Mini-Game Challenge (required)")
            st.caption("Play and win the mini-game to submit your answers!")
            import streamlit.components.v1 as components
            minigame_html = '''
            <style>
            #gameCanvas { background: #f4f4f4; border: 2px solid #333; }
            </style>
            <canvas id="gameCanvas" width="400" height="100"></canvas>
            <div id="gameStatus"></div>
            <script>
            let canvas = document.getElementById('gameCanvas');
            let ctx = canvas.getContext('2d');
            let dino = { x: 30, y: 70, w: 20, h: 20, vy: 0, jumping: false };
            let obstacles = [];
            let score = 0;
            let gameOver = false;
            let started = false;
            function drawDino() {
                ctx.fillStyle = '#2c3e50';
                ctx.fillRect(dino.x, dino.y, dino.w, dino.h);
            }
            function drawObstacles() {
                ctx.fillStyle = '#e74c3c';
                obstacles.forEach(o => ctx.fillRect(o.x, o.y, o.w, o.h));
            }
            function updateObstacles() {
                obstacles.forEach(o => o.x -= 4);
                if (obstacles.length === 0 || obstacles[obstacles.length-1].x < 250) {
                    obstacles.push({ x: 400, y: 80, w: 15, h: 20 });
                }
                obstacles = obstacles.filter(o => o.x + o.w > 0);
            }
            function checkCollision() {
                for (let o of obstacles) {
                    if (dino.x < o.x + o.w && dino.x + dino.w > o.x && dino.y < o.y + o.h && dino.y + dino.h > o.y) {
                        return true;
                    }
                }
                return false;
            }
            function draw() {
                ctx.clearRect(0,0,400,100);
                drawDino();
                drawObstacles();
                ctx.fillStyle = '#333';
                ctx.font = '16px Arial';
                ctx.fillText('Score: ' + score, 320, 20);
            }
            function gameLoop() {
                if (!started || gameOver) return;
                dino.y += dino.vy;
                if (dino.jumping) dino.vy += 1;
                if (dino.y >= 70) { dino.y = 70; dino.vy = 0; dino.jumping = false; }
                updateObstacles();
                if (checkCollision()) {
                    gameOver = true;
                    document.getElementById('gameStatus').innerText = 'Game Over! Refresh to try again.';
                } else {
                    score++;
                    if (score >= 60) {
                        gameOver = true;
                        document.getElementById('gameStatus').innerText = 'You win! You may submit.';
                        window.parent.postMessage({ minigame_win: true }, '*');
                    }
                }
                draw();
                if (!gameOver) requestAnimationFrame(gameLoop);
            }
            canvas.onclick = function() {
                if (!started) { started = true; gameLoop(); return; }
                if (!dino.jumping) { dino.vy = -12; dino.jumping = true; }
            };
            draw();
            document.getElementById('gameStatus').innerText = 'Click the canvas to jump! Avoid red obstacles. Survive to 60 points.';
            </script>
            '''
            minigame_result = st.session_state.get("minigame_result", False)
            # Listen for win event
            components.html(minigame_html, height=160)
            # JS->Python communication workaround
            # User must click 'I won!' after winning
            if not minigame_result:
                minigame_result = st.checkbox("I won the mini-game! (Check after you see 'You win!')")
                st.session_state["minigame_result"] = minigame_result
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
            # Check mini-game
            if not st.session_state.get("minigame_result", False):
                st.warning("You must win the mini-game before submitting!")
            elif not team.strip():
                st.warning("Enter a team name.")
            elif prob_idx is None or model_idx is None or plan_idx is None:
                st.warning("Answer all required questions (1, 3, and 5).")
            else:
                # Score calculation
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
                total = s1 + s2 + s3 + s4 + s5
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
                }
                write_submission(row)
                # Per-question feedback
                feedback = []
                feedback.append(f"**Business problem:** {'✅ Correct' if s1 else '❌ Incorrect'}")
                feedback.append(f"**Business goals:** {'✅ Correct' if s2 else '❌ Incorrect'}")
                feedback.append(f"**Analytics solution/model:** {'✅ Correct' if s3 else '❌ Incorrect'}")
                feedback.append(f"**Feasibility:** {'✅ Correct' if s4 == len(feas_items)*block['feasibility_binary']['points_each'] else '❌ Incorrect'}")
                feedback.append(f"**Analytics plan:** {'✅ Correct' if s5 else '❌ Incorrect'}")
                st.success(f"Submitted! Score = {total}")
                st.markdown("### Your Results:")
                for f in feedback:
                    st.markdown(f)
                # Reset form state and mini-game
                st.session_state["form_state"] = {
                    "team": "",
                    "prob_idx": None,
                    "goal_choices": [],
                    "model_idx": None,
                    "feas_answers": [],
                    "plan_idx": None,
                }
                st.session_state["minigame_result"] = False

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
