"""Local ten-question LaTeX quiz with teacher import and SQLite submissions."""
from __future__ import annotations
import json
import sqlite3
from datetime import date, datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "respons.db"
LETTERS = ("A", "B", "C", "D")


def init_database() -> None:
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS quiz_questions (
                question_number INTEGER PRIMARY KEY,
                question_text TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_answer TEXT NOT NULL CHECK(correct_answer IN ('A','B','C','D')),
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE TABLE IF NOT EXISTS quiz_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO quiz_settings(setting_key, setting_value) VALUES ('title', 'Student quiz')")
        db.execute("INSERT OR IGNORE INTO quiz_settings(setting_key, setting_value) VALUES ('valid_from', '')")
        db.execute("INSERT OR IGNORE INTO quiz_settings(setting_key, setting_value) VALUES ('valid_until', '')")
        db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                student_group TEXT NOT NULL DEFAULT '',
                answers_json TEXT NOT NULL,
                score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                submitted_at TEXT NOT NULL
            )
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(submissions)")}
        if "student_group" not in columns:
            db.execute("ALTER TABLE submissions ADD COLUMN student_group TEXT NOT NULL DEFAULT ''")
        has_duplicate_ids = db.execute("""
            SELECT 1 FROM submissions GROUP BY student_id HAVING COUNT(*) > 1 LIMIT 1
        """).fetchone()
        if not has_duplicate_ids:
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_student_submission ON submissions(student_id)")
        # Preserve responses from the original one-question form if present.
        db.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                answer TEXT NOT NULL CHECK(answer IN ('A','B','C','D')),
                submitted_at TEXT NOT NULL,
                question_id INTEGER NOT NULL DEFAULT 1,
                is_correct INTEGER NOT NULL DEFAULT 0
            )
        """)


class FormHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/guru":
            self.path = "/admin.html"
            return super().do_GET()
        if path == "/rekod":
            self.path = "/responses.html"
            return super().do_GET()
        if path in {"/api/question", "/api/guru/questions", "/api/guru/submissions"}:
            if path == "/api/guru/submissions":
                with sqlite3.connect(DATABASE) as db:
                    db.row_factory = sqlite3.Row
                    rows = db.execute("SELECT response_id, student_name, student_id, student_group, answers_json, score, total_questions, submitted_at FROM submissions ORDER BY response_id DESC").fetchall()
                records = [{"response_id": row["response_id"], "nama": row["student_name"], "id": row["student_id"], "group": row["student_group"],
                    "answers": json.loads(row["answers_json"]), "score": row["score"],
                    "total": row["total_questions"], "submitted_at": row["submitted_at"]} for row in rows]
                self._json(200, {"records": records})
                return
            with sqlite3.connect(DATABASE) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("SELECT * FROM quiz_questions ORDER BY question_number").fetchall()
                settings = {r["setting_key"]: r["setting_value"] for r in db.execute("SELECT setting_key, setting_value FROM quiz_settings")}
            title = settings.get("title", "Student quiz")
            valid_from = settings.get("valid_from", "")
            valid_until = settings.get("valid_until", "")
            today = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
            is_open = bool(valid_from and valid_until and valid_from <= today <= valid_until)
            if path == "/api/guru/questions":
                questions = [{"number": r["question_number"], "question_text": r["question_text"],
                    "options": json.loads(r["options_json"]), "correct_answer": r["correct_answer"]} for r in rows]
            else:
                questions = [{"number": r["question_number"], "question_text": r["question_text"],
                    "options": json.loads(r["options_json"])} for r in rows]
            self._json(200, {"available": bool(questions), "title": title, "valid_from": valid_from,
                "valid_until": valid_until, "today": today, "is_open": is_open, "questions": questions})
            return
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/respons", "/api/guru/questions"}:
            self.send_error(404)
            return
        try:
            data = self._read_payload()
            if path == "/api/guru/questions":
                self._save_questions(data)
            else:
                self._save_submission(data)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(400, {"ok": False, "mesej": str(exc) or "Invalid information."})
        except LookupError as exc:
            self._json(409, {"ok": False, "mesej": str(exc)})
        except sqlite3.IntegrityError:
            self._json(409, {"ok": False, "mesej": "This student ID has already submitted."})
        except Exception:
            self._json(500, {"ok": False, "mesej": "An error occurred. Please try again."})

    def do_DELETE(self) -> None:
        if urlparse(self.path).path != "/api/guru/submissions":
            self.send_error(404)
            return
        with sqlite3.connect(DATABASE) as db:
            result = db.execute("DELETE FROM submissions")
            deleted = result.rowcount
        self._json(200, {"ok": True, "mesej": f"Deleted {deleted} student submission(s). Students can submit again."})

    def _read_payload(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 100_000:
            raise ValueError("The request is empty or too large.")
        return json.loads(self.rfile.read(size).decode("utf-8"))

    def _save_questions(self, data: dict) -> None:
        valid_from = str(data.get("valid_from", "")).strip()
        valid_until = str(data.get("valid_until", "")).strip()
        try:
            start_date = date.fromisoformat(valid_from)
            end_date = date.fromisoformat(valid_until)
        except ValueError:
            raise ValueError("Choose both form validity dates.")
        if start_date > end_date:
            raise ValueError("The valid-until date must be on or after the valid-from date.")
        title = str(data.get("title", "")).strip()
        if not title or len(title) > 150:
            raise ValueError("Enter a quiz title (up to 150 characters).")
        questions = data.get("questions")
        if not isinstance(questions, list) or len(questions) != 10:
            raise ValueError("The import must contain exactly 10 questions.")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for expected, q in enumerate(questions, start=1):
            text = str(q.get("question_text", "")).strip()
            options = q.get("options", {})
            correct = str(q.get("correct_answer", "")).upper()
            if int(q.get("number", expected)) != expected:
                raise ValueError("Question numbers must run consecutively from 1 to 10.")
            if not text or len(text) > 8000:
                raise ValueError(f"Question {expected} is empty or too long.")
            if any(not str(options.get(letter, "")).strip() or len(str(options.get(letter, ""))) > 2000 for letter in LETTERS):
                raise ValueError(f"Complete choices A through D for question {expected}.")
            if correct not in LETTERS:
                raise ValueError(f"The answer key for question {expected} is invalid.")
            rows.append((expected, text, json.dumps({k: str(options[k]).strip() for k in LETTERS}, ensure_ascii=False), correct, now))
        with sqlite3.connect(DATABASE) as db:
            db.execute("DELETE FROM quiz_questions")
            db.executemany("INSERT INTO quiz_questions VALUES (?, ?, ?, ?, ?)", rows)
            db.executemany("INSERT OR REPLACE INTO quiz_settings(setting_key, setting_value) VALUES (?, ?)",
                [("title", title), ("valid_from", valid_from), ("valid_until", valid_until)])
        self._json(200, {"ok": True, "title": title, "mesej": "Validity dates, quiz title, and all 10 questions were saved."})

    def _save_submission(self, data: dict) -> None:
        name = str(data.get("nama", "")).strip()
        student_id = str(data.get("id", "")).strip()
        student_group = str(data.get("group", "")).strip()
        answers = data.get("answers")
        if not name or len(name) > 120:
            raise ValueError("Enter your name (up to 120 characters).")
        if not student_id or len(student_id) > 40:
            raise ValueError("Enter your student ID (up to 40 characters).")
        if not student_group or len(student_group) > 80:
            raise ValueError("Enter your group or class (up to 80 characters).")
        if not isinstance(answers, dict):
            raise ValueError("Please answer all 10 questions.")
        with sqlite3.connect(DATABASE) as db:
            window = dict(db.execute("SELECT setting_key, setting_value FROM quiz_settings WHERE setting_key IN ('valid_from', 'valid_until')").fetchall())
            today = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
            if not window.get("valid_from") or not window.get("valid_until"):
                raise LookupError("The lecturer has not set the form validity dates yet.")
            if not window["valid_from"] <= today <= window["valid_until"]:
                raise LookupError(f"This quiz accepts responses from {window['valid_from']} through {window['valid_until']} (Malaysia time).")
            key_rows = db.execute("SELECT question_number, correct_answer FROM quiz_questions ORDER BY question_number").fetchall()
            if len(key_rows) != 10:
                raise LookupError("The teacher has not set up the 10 questions yet.")
            if db.execute("SELECT 1 FROM submissions WHERE student_id = ? LIMIT 1", (student_id,)).fetchone():
                raise LookupError("This student ID has already submitted. Each ID may submit only once.")
            keys = {str(number): answer for number, answer in key_rows}
            if any(answers.get(str(i)) not in LETTERS for i in range(1, 11)):
                raise ValueError("Please answer all 10 questions.")
            score = sum(answers[str(i)] == keys[str(i)] for i in range(1, 11))
            db.execute("INSERT INTO submissions(student_name, student_id, student_group, answers_json, score, total_questions, submitted_at) VALUES (?, ?, ?, ?, ?, 10, ?)",
                (name, student_id, student_group, json.dumps(answers), score, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        self._json(201, {"ok": True, "mesej": f"Answers recorded. Your score: {score}/10."})

    def _json(self, status: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    init_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), FormHandler)
    print("Student form: http://127.0.0.1:8765")
    print("Teacher question import: http://127.0.0.1:8765/guru")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()

