"""PythonAnywhere WSGI entry point for the student quiz."""
from __future__ import annotations

import hmac
import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("QUIZ_DATABASE", ROOT / "respons.db"))
LETTERS = ("A", "B", "C", "D")
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100_000


def connect_db():
    db = sqlite3.connect(DATABASE, timeout=15)
    db.row_factory = sqlite3.Row
    return db


def init_database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS quiz_questions (
            question_number INTEGER PRIMARY KEY, question_text TEXT NOT NULL,
            options_json TEXT NOT NULL, correct_answer TEXT NOT NULL CHECK(correct_answer IN ('A','B','C','D')),
            updated_at TEXT NOT NULL)""")
        db.execute("CREATE TABLE IF NOT EXISTS quiz_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO quiz_settings(setting_key, setting_value) VALUES ('title', 'Student quiz')")
        db.execute("INSERT OR IGNORE INTO quiz_settings(setting_key, setting_value) VALUES ('valid_from', '')")
        db.execute("INSERT OR IGNORE INTO quiz_settings(setting_key, setting_value) VALUES ('valid_until', '')")
        db.execute("""CREATE TABLE IF NOT EXISTS submissions (
            response_id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT NOT NULL,
            student_id TEXT NOT NULL, student_group TEXT NOT NULL DEFAULT '', answers_json TEXT NOT NULL,
            score INTEGER NOT NULL, total_questions INTEGER NOT NULL, submitted_at TEXT NOT NULL)""")
        cols = {row[1] for row in db.execute("PRAGMA table_info(submissions)")}
        if "student_group" not in cols:
            db.execute("ALTER TABLE submissions ADD COLUMN student_group TEXT NOT NULL DEFAULT ''")
        duplicate = db.execute("SELECT 1 FROM submissions GROUP BY student_id HAVING COUNT(*) > 1 LIMIT 1").fetchone()
        if not duplicate:
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_student_submission ON submissions(student_id)")
        db.execute("""CREATE TABLE IF NOT EXISTS responses (
            response_id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT NOT NULL,
            student_id TEXT NOT NULL, answer TEXT NOT NULL CHECK(answer IN ('A','B','C','D')),
            submitted_at TEXT NOT NULL, question_id INTEGER NOT NULL DEFAULT 1,
            is_correct INTEGER NOT NULL DEFAULT 0)""")


def teacher_only(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        username = os.environ.get("TEACHER_USERNAME", "")
        password = os.environ.get("TEACHER_PASSWORD", "")
        auth = request.authorization
        valid = (username and password and auth and
                 hmac.compare_digest(auth.username or "", username) and
                 hmac.compare_digest(auth.password or "", password))
        if not valid:
            return Response("Teacher login required", 401,
                            {"WWW-Authenticate": 'Basic realm="Teacher area", charset="UTF-8"',
                             "Cache-Control": "no-store"})
        return fn(*args, **kwargs)
    return wrapped


@app.get("/")
def student_page():
    return send_from_directory(ROOT, "index.html")


@app.get("/guru")
@teacher_only
def teacher_page():
    return send_from_directory(ROOT, "admin.html")


@app.get("/rekod")
@teacher_only
def records_page():
    return send_from_directory(ROOT, "responses.html")


@app.get("/api/question")
def get_quiz():
    with connect_db() as db:
        rows = db.execute("SELECT * FROM quiz_questions ORDER BY question_number").fetchall()
        settings = {r["setting_key"]: r["setting_value"] for r in db.execute("SELECT setting_key, setting_value FROM quiz_settings")}
    questions = [{"number": r["question_number"], "question_text": r["question_text"],
                  "options": json.loads(r["options_json"])} for r in rows]
    today = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
    valid_from, valid_until = settings.get("valid_from", ""), settings.get("valid_until", "")
    is_open = bool(valid_from and valid_until and valid_from <= today <= valid_until)
    return jsonify(available=bool(questions), title=settings.get("title", "Student quiz"), valid_from=valid_from,
                   valid_until=valid_until, today=today, is_open=is_open, questions=questions)


@app.get("/api/guru/questions")
@teacher_only
def get_teacher_questions():
    with connect_db() as db:
        rows = db.execute("SELECT * FROM quiz_questions ORDER BY question_number").fetchall()
        settings = {r["setting_key"]: r["setting_value"] for r in db.execute("SELECT setting_key, setting_value FROM quiz_settings")}
    questions = [{"number": r["question_number"], "question_text": r["question_text"],
                  "options": json.loads(r["options_json"]), "correct_answer": r["correct_answer"]} for r in rows]
    return jsonify(available=bool(questions), title=settings.get("title", "Student quiz"),
                   valid_from=settings.get("valid_from", ""), valid_until=settings.get("valid_until", ""), questions=questions)


@app.get("/api/guru/submissions")
@teacher_only
def get_submissions():
    with connect_db() as db:
        rows = db.execute("SELECT response_id, student_name, student_id, student_group, answers_json, score, total_questions, submitted_at FROM submissions ORDER BY response_id DESC").fetchall()
    records = [{"response_id": r["response_id"], "nama": r["student_name"], "id": r["student_id"],
                "group": r["student_group"], "answers": json.loads(r["answers_json"]),
                "score": r["score"], "total": r["total_questions"], "submitted_at": r["submitted_at"]} for r in rows]
    return jsonify(records=records)


@app.delete("/api/guru/submissions")
@teacher_only
def clear_submissions():
    with connect_db() as db:
        deleted = db.execute("DELETE FROM submissions").rowcount
    return jsonify(ok=True, mesej=f"Deleted {deleted} student submission(s). Students can submit again.")


@app.post("/api/guru/questions")
@teacher_only
def save_questions():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, mesej="Request must contain valid JSON."), 400
    valid_from, valid_until = str(data.get("valid_from", "")).strip(), str(data.get("valid_until", "")).strip()
    try:
        start_date, end_date = date.fromisoformat(valid_from), date.fromisoformat(valid_until)
    except ValueError:
        return jsonify(ok=False, mesej="Choose both form validity dates."), 400
    if start_date > end_date:
        return jsonify(ok=False, mesej="The valid-until date must be on or after the valid-from date."), 400
    title = str(data.get("title", "")).strip()
    if not title or len(title) > 150:
        return jsonify(ok=False, mesej="Enter a quiz title (up to 150 characters)."), 400
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) != 10:
        return jsonify(ok=False, mesej="The import must contain exactly 10 questions."), 400
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    try:
        for expected, q in enumerate(questions, 1):
            text = str(q.get("question_text", "")).strip()
            opts = q.get("options", {})
            correct = str(q.get("correct_answer", "")).upper()
            if int(q.get("number", expected)) != expected:
                raise ValueError("Question numbers must run consecutively from 1 to 10.")
            if not text or len(text) > 8000:
                raise ValueError(f"Question {expected} is empty or too long.")
            if not isinstance(opts, dict) or any(not str(opts.get(k, "")).strip() or len(str(opts.get(k, ""))) > 2000 for k in LETTERS):
                raise ValueError(f"Complete choices A through D for question {expected}.")
            if correct not in LETTERS:
                raise ValueError(f"The answer key for question {expected} is invalid.")
            rows.append((expected, text, json.dumps({k: str(opts[k]).strip() for k in LETTERS}, ensure_ascii=False), correct, now))
        with connect_db() as db:
            db.execute("DELETE FROM quiz_questions")
            db.executemany("INSERT INTO quiz_questions VALUES (?, ?, ?, ?, ?)", rows)
            db.executemany("INSERT OR REPLACE INTO quiz_settings(setting_key, setting_value) VALUES (?, ?)",
                           [("title", title), ("valid_from", valid_from), ("valid_until", valid_until)])
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(ok=False, mesej=str(exc)), 400
    return jsonify(ok=True, title=title, mesej="Validity dates, quiz title, and all 10 questions were saved.")


@app.post("/api/respons")
def save_submission():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, mesej="Request must contain valid JSON."), 400
    name = str(data.get("nama", "")).strip()
    student_id = str(data.get("id", "")).strip()
    group = str(data.get("group", "")).strip()
    answers = data.get("answers")
    if not name or len(name) > 120:
        return jsonify(ok=False, mesej="Enter your name (up to 120 characters)."), 400
    if not student_id or len(student_id) > 40:
        return jsonify(ok=False, mesej="Enter your student ID (up to 40 characters)."), 400
    if not group or len(group) > 80:
        return jsonify(ok=False, mesej="Enter your group or class (up to 80 characters)."), 400
    if not isinstance(answers, dict) or any(answers.get(str(i)) not in LETTERS for i in range(1, 11)):
        return jsonify(ok=False, mesej="Please answer all 10 questions."), 400
    try:
        with connect_db() as db:
            window = dict(db.execute("SELECT setting_key, setting_value FROM quiz_settings WHERE setting_key IN ('valid_from', 'valid_until')").fetchall())
            today = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
            if not window.get("valid_from") or not window.get("valid_until"):
                return jsonify(ok=False, mesej="The lecturer has not set the form validity dates yet."), 409
            if not window["valid_from"] <= today <= window["valid_until"]:
                return jsonify(ok=False, mesej=f"This quiz accepts responses from {window['valid_from']} through {window['valid_until']} (Malaysia time)."), 409
            key_rows = db.execute("SELECT question_number, correct_answer FROM quiz_questions ORDER BY question_number").fetchall()
            if len(key_rows) != 10:
                return jsonify(ok=False, mesej="The teacher has not set up the 10 questions yet."), 409
            keys = {str(r["question_number"]): r["correct_answer"] for r in key_rows}
            score = sum(answers[str(i)] == keys[str(i)] for i in range(1, 11))
            db.execute("INSERT INTO submissions(student_name, student_id, student_group, answers_json, score, total_questions, submitted_at) VALUES (?, ?, ?, ?, ?, 10, ?)",
                       (name, student_id, group, json.dumps(answers), score, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    except sqlite3.IntegrityError:
        return jsonify(ok=False, mesej="This student ID has already submitted. Each ID may submit only once."), 409
    return jsonify(ok=True, mesej=f"Answers recorded. Your score: {score}/10."), 201


@app.get("/<path:filename>")
def static_file(filename):
    return send_from_directory(ROOT, filename)


@app.errorhandler(413)
def too_large(_error):
    return jsonify(ok=False, mesej="The request is too large."), 413


init_database()
