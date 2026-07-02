"""
AI Interview Coach - Backend
-----------------------------
Flask app exposing two endpoints:
  POST /generate_question  -> returns a new interview question
  POST /evaluate_answer    -> returns structured feedback on the user's answer

Requires: ANTHROPIC_API_KEY environment variable
Install deps: pip install flask anthropic --break-system-packages
Run: python app.py
"""

import os
import json
import uuid
from flask import Flask, request, jsonify, session, render_template
from anthropic import Anthropic

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-change-me")

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

# In-memory session store: { session_id: {"role": str, "history": [...] } }
SESSIONS = {}


@app.route("/")
def index():
    return render_template("index.html")


def get_session(session_id):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"role": None, "history": []}
    return SESSIONS[session_id]


@app.route("/start_session", methods=["POST"])
def start_session():
    data = request.get_json(force=True)
    role = data.get("role", "Software Engineer")
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {"role": role, "history": []}
    return jsonify({"session_id": session_id, "role": role})


@app.route("/generate_question", methods=["POST"])
def generate_question():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    s = get_session(session_id)
    role = s["role"] or "Software Engineer"

    asked_so_far = [h["question"] for h in s["history"]]

    prompt = f"""You are an interview coach conducting a mock interview for the role: {role}.
Questions already asked: {asked_so_far if asked_so_far else "none"}.

Generate ONE new, relevant interview question (behavioral or technical, mix it up).
Return ONLY the question text, nothing else."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    question = resp.content[0].text.strip()
    s["history"].append({"question": question, "answer": None, "feedback": None})
    return jsonify({"question": question, "question_index": len(s["history"]) - 1})


@app.route("/evaluate_answer", methods=["POST"])
def evaluate_answer():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    question_index = data.get("question_index")
    answer = data.get("answer", "")

    s = get_session(session_id)
    role = s["role"] or "Software Engineer"
    question = s["history"][question_index]["question"]

    prompt = f"""You are an expert interview coach for the role: {role}.

Question asked: "{question}"
Candidate's answer: "{answer}"

Evaluate the answer and return STRICT JSON only (no markdown, no preamble) in this exact shape:
{{
  "clarity_score": <1-10>,
  "content_score": <1-10>,
  "confidence_score": <1-10>,
  "strengths": ["...", "..."],
  "improvements": ["...", "..."],
  "ideal_answer_tip": "one short tip on what a strong answer would include"
}}"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        feedback = json.loads(raw)
    except json.JSONDecodeError:
        feedback = {"error": "Could not parse feedback", "raw": raw}

    s["history"][question_index]["answer"] = answer
    s["history"][question_index]["feedback"] = feedback
    return jsonify(feedback)


@app.route("/summary", methods=["POST"])
def summary():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    s = get_session(session_id)

    scored = [h for h in s["history"] if h.get("feedback") and "clarity_score" in h["feedback"]]
    if not scored:
        return jsonify({"message": "No completed answers yet."})

    avg = lambda key: round(sum(h["feedback"][key] for h in scored) / len(scored), 1)

    return jsonify({
        "questions_answered": len(scored),
        "avg_clarity": avg("clarity_score"),
        "avg_content": avg("content_score"),
        "avg_confidence": avg("confidence_score"),
        "history": s["history"],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
