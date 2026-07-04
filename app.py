"""
AI Interview Coach - Backend
-----------------------------
Requires: ANTHROPIC_API_KEY environment variable
Install: pip install flask anthropic gunicorn --break-system-packages
Run: python app.py

NOTE on persistence: candidate history is saved to candidate_history.json on
disk. This works fine during a live demo, but on free hosting tiers (like
Render's free plan) the disk resets on redeploy/restart, so history won't
survive across deploys. Fine for a one-week mini-project demo.
"""

import os
import re
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from anthropic import Anthropic

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-change-me")

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

SESSIONS = {}
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "candidate_history.json")

FILLER_WORDS = [
    "um", "umm", "uh", "uhh", "like", "you know", "actually", "basically",
    "so", "i mean", "kind of", "sort of", "right", "literally"
]

QUESTION_BANKS = {
    "Software Engineer": [
        "Tell me about a challenging bug you fixed and how you found it.",
        "How would you design a URL shortening service?",
        "Describe a time you disagreed with a teammate's technical approach.",
        "Explain the difference between processes and threads.",
    ],
    "Data Analyst": [
        "Walk me through how you'd investigate a sudden drop in a key metric.",
        "Tell me about a time your analysis changed a business decision.",
        "How do you handle messy or incomplete data?",
        "Explain a statistical concept to someone non-technical.",
    ],
    "HR / People Ops": [
        "Tell me about a time you handled a conflict between employees.",
        "How do you approach giving difficult feedback?",
        "Describe how you'd design an onboarding program.",
        "Tell me about a time you had to enforce a policy you disagreed with.",
    ],
    "Product Manager": [
        "Tell me about a product decision you made with incomplete data.",
        "How do you prioritize a roadmap with limited engineering resources?",
        "Describe a time a launch didn't go as planned.",
        "How would you improve a product you use every day?",
    ],
}

PERSONA_STYLES = {
    "Friendly HR": "Warm, encouraging, conversational tone. Focus more on behavioral/cultural-fit questions.",
    "Neutral Interviewer": "Professional, balanced, neutral tone. Mix of behavioral and role-specific questions.",
    "Tough Technical Lead": "Direct, probing, slightly skeptical tone. Push for specifics and technical depth. Ask sharper follow-up-style questions.",
}


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_history(all_history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(all_history, f, indent=2)
    except Exception:
        pass


def get_session(session_id):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "role": None, "difficulty": "Intermediate", "persona": "Neutral Interviewer",
            "resume": "", "candidate_name": "Anonymous", "history": []
        }
    return SESSIONS[session_id]


def count_filler_words(text):
    text_lower = text.lower()
    counts = {}
    total = 0
    for fw in FILLER_WORDS:
        pattern = r'\b' + re.escape(fw) + r'\b'
        matches = re.findall(pattern, text_lower)
        if matches:
            counts[fw] = len(matches)
            total += len(matches)
    return total, counts


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start_session", methods=["POST"])
def start_session():
    data = request.get_json(force=True)
    role = data.get("role", "Software Engineer")
    difficulty = data.get("difficulty", "Intermediate")
    persona = data.get("persona", "Neutral Interviewer")
    resume = data.get("resume", "")
    candidate_name = data.get("candidate_name", "Anonymous").strip() or "Anonymous"

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "role": role, "difficulty": difficulty, "persona": persona,
        "resume": resume, "candidate_name": candidate_name, "history": []
    }

    all_history = load_history()
    past_sessions = all_history.get(candidate_name, [])

    return jsonify({
        "session_id": session_id, "role": role,
        "past_sessions": past_sessions
    })


@app.route("/generate_question", methods=["POST"])
def generate_question():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    s = get_session(session_id)
    role = s["role"] or "Software Engineer"
    difficulty = s["difficulty"]
    persona = s["persona"]
    resume = s["resume"]

    asked_so_far = [h["question"] for h in s["history"]]
    bank_samples = QUESTION_BANKS.get(role, [])
    persona_style = PERSONA_STYLES.get(persona, PERSONA_STYLES["Neutral Interviewer"])

    resume_note = f"\nCandidate's resume/background:\n{resume}\nTailor the question to their actual background where relevant." if resume.strip() else ""

    prompt = f"""You are conducting a mock interview for the role: {role}.
Difficulty level: {difficulty}.
Interviewer persona/style: {persona} — {persona_style}
Reference-style questions real interviewers ask for this role (for inspiration only, don't repeat verbatim): {bank_samples}
Questions already asked in this session: {asked_so_far if asked_so_far else "none"}.
{resume_note}

Generate ONE new, relevant interview question appropriate for the difficulty level and persona.
Return ONLY the question text, nothing else."""

    resp = client.messages.create(model=MODEL, max_tokens=200, messages=[{"role": "user", "content": prompt}])
    question = resp.content[0].text.strip()
    s["history"].append({"question": question, "answer": None, "feedback": None, "nonverbal": None, "answer_time_seconds": None})
    return jsonify({"question": question, "question_index": len(s["history"]) - 1})


@app.route("/evaluate_answer", methods=["POST"])
def evaluate_answer():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    question_index = data.get("question_index")
    answer = data.get("answer", "")
    nonverbal = data.get("nonverbal", {})
    answer_time_seconds = data.get("answer_time_seconds")

    s = get_session(session_id)
    role = s["role"] or "Software Engineer"
    persona = s["persona"]
    question = s["history"][question_index]["question"]

    nonverbal_note = ""
    if nonverbal:
        expr = nonverbal.get("dominant_expression", "unknown")
        eye = nonverbal.get("eye_contact_percent")
        voice = nonverbal.get("voice_energy_percent")
        nonverbal_note = f"""
Non-verbal signals captured during the answer (approximate, webcam/mic based):
- Dominant facial expression: {expr}
- Estimated eye contact: {eye}%
- Voice energy level: {voice}%
Give 1-2 concrete, actionable body-language/vocal delivery tips based on these numbers. If they look healthy, say so briefly."""

    time_note = f"\nThe candidate took {answer_time_seconds} seconds to answer." if answer_time_seconds is not None else ""

    prompt = f"""You are an expert interview coach with a {persona} style for the role: {role}.

Question asked: "{question}"
Candidate's answer: "{answer}"
{nonverbal_note}
{time_note}

Evaluate the answer and return STRICT JSON only (no markdown, no preamble) in this exact shape:
{{
  "clarity_score": <1-10>,
  "content_score": <1-10>,
  "confidence_score": <1-10>,
  "strengths": ["...", "..."],
  "improvements": ["...", "..."],
  "ideal_answer_tip": "one short tip on what a strong answer would include",
  "nonverbal_feedback": ["1-2 short tips based on the nonverbal signals; empty array if none provided"],
  "star_analysis": {{
    "applicable": true or false,
    "detected": true or false,
    "missing_parts": ["Situation", "Task", "Action", "Result"] (only the ones missing, empty if all present or not applicable)
  }}
}}
Set star_analysis.applicable to false if this is a technical/factual question rather than a behavioral one."""

    resp = client.messages.create(model=MODEL, max_tokens=600, messages=[{"role": "user", "content": prompt}])
    raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()

    try:
        feedback = json.loads(raw)
    except json.JSONDecodeError:
        feedback = {"error": "Could not parse feedback", "raw": raw}

    filler_total, filler_breakdown = count_filler_words(answer)
    time_flag = None
    if answer_time_seconds is not None:
        if answer_time_seconds < 10:
            time_flag = "This answer was very quick — make sure you're fully addressing the question."
        elif answer_time_seconds > 150:
            time_flag = "This answer ran long — try to be more concise and get to the point faster."

    feedback["filler_word_count"] = filler_total
    feedback["filler_word_breakdown"] = filler_breakdown
    feedback["answer_time_seconds"] = answer_time_seconds
    feedback["time_flag"] = time_flag

    s["history"][question_index].update({
        "answer": answer, "feedback": feedback, "nonverbal": nonverbal,
        "answer_time_seconds": answer_time_seconds
    })
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

    nv_entries = [h["nonverbal"] for h in scored if h.get("nonverbal")]
    avg_eye = avg_voice = None
    expr_counts = {}
    if nv_entries:
        eye_vals = [n["eye_contact_percent"] for n in nv_entries if n.get("eye_contact_percent") is not None]
        voice_vals = [n["voice_energy_percent"] for n in nv_entries if n.get("voice_energy_percent") is not None]
        if eye_vals: avg_eye = round(sum(eye_vals) / len(eye_vals), 1)
        if voice_vals: avg_voice = round(sum(voice_vals) / len(voice_vals), 1)
        for n in nv_entries:
            e = n.get("dominant_expression")
            if e: expr_counts[e] = expr_counts.get(e, 0) + 1
    dominant_expression_overall = max(expr_counts, key=expr_counts.get) if expr_counts else None

    total_filler = sum(h["feedback"].get("filler_word_count", 0) for h in scored)
    star_applicable = [h["feedback"]["star_analysis"] for h in scored if h["feedback"].get("star_analysis", {}).get("applicable")]
    star_full_count = sum(1 for sa in star_applicable if sa.get("detected"))

    overall_tips = []
    if avg_eye is not None:
        if avg_eye < 50:
            overall_tips.append("Your eye contact was low across the session — practice looking at the camera lens, not the screen.")
        elif avg_eye >= 75:
            overall_tips.append("Good consistent eye contact throughout — keep it up.")
    if avg_voice is not None:
        if avg_voice < 40:
            overall_tips.append("Your voice energy was low overall — project more and vary your pitch.")
        elif avg_voice > 85:
            overall_tips.append("Your voice energy was quite tense/high throughout — slow down and breathe between points.")
    if dominant_expression_overall in ("neutral", "sad", "fearful", "angry"):
        overall_tips.append(f"Your most common expression was '{dominant_expression_overall}' — relax your face and smile naturally where appropriate.")
    if total_filler > len(scored) * 3:
        overall_tips.append(f"You used {total_filler} filler words (um, like, etc.) across your answers — pause silently instead of filling gaps with filler words.")
    if star_applicable and star_full_count < len(star_applicable):
        overall_tips.append(f"Only {star_full_count}/{len(star_applicable)} behavioral answers fully followed the STAR structure (Situation, Task, Action, Result) — try structuring your stories that way.")

    result = {
        "candidate_name": s["candidate_name"],
        "role": s["role"],
        "questions_answered": len(scored),
        "avg_clarity": avg("clarity_score"),
        "avg_content": avg("content_score"),
        "avg_confidence": avg("confidence_score"),
        "avg_eye_contact_percent": avg_eye,
        "avg_voice_energy_percent": avg_voice,
        "dominant_expression_overall": dominant_expression_overall,
        "total_filler_words": total_filler,
        "star_score": f"{star_full_count}/{len(star_applicable)}" if star_applicable else "n/a",
        "overall_nonverbal_tips": overall_tips,
        "history": s["history"],
    }

    # Save to persistent candidate history for progress tracking
    all_history = load_history()
    candidate_list = all_history.get(s["candidate_name"], [])
    candidate_list.append({
        "timestamp": datetime.utcnow().isoformat(),
        "role": s["role"],
        "avg_clarity": result["avg_clarity"],
        "avg_content": result["avg_content"],
        "avg_confidence": result["avg_confidence"],
        "questions_answered": result["questions_answered"],
    })
    all_history[s["candidate_name"]] = candidate_list
    save_history(all_history)

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
