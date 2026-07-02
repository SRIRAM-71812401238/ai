# AI Interview Coach — Demo Setup

## 1. Install dependencies
```bash
pip install -r requirements.txt --break-system-packages
```

## 2. Set your API key
Get a key from https://console.anthropic.com and set it:
```bash
export ANTHROPIC_API_KEY="your-key-here"      # Mac/Linux
set ANTHROPIC_API_KEY=your-key-here           # Windows (cmd)
```

## 3. Run the app
```bash
python app.py
```
Open http://127.0.0.1:5000 in **Google Chrome** (needed for the mic/speech feature).

## How it works
1. Pick a role → backend creates a session.
2. Backend asks Claude to generate a question for that role.
3. You answer by typing or clicking the mic button (uses your browser's built-in speech-to-text — no extra setup needed).
4. Backend sends your question+answer to Claude, which returns scores (clarity, content, confidence) plus strengths/improvements.
5. Repeat for a few questions, then click "Finish" to see your average scores.

## Extending it further (if you have extra time)
- Persist sessions in SQLite instead of memory so results survive a restart.
- Add resume upload so questions are tailored to the candidate's background.
- Add a timer per question to simulate real interview pressure.
- Track score trends across multiple practice sessions (needs login/user accounts).
- Add text-to-speech (browser `SpeechSynthesis` API) so the AI "asks" the question out loud.

## Demo day tips
- Pre-test your mic + Chrome permissions before presenting.
- Have a backup: a short screen recording of a full run, in case live API/network fails.
- Keep your role list small (2–3 roles) — depth beats breadth for a 1-week demo.
