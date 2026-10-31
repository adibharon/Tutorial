# Student Quiz Website

A 10-question multiple-choice quiz with a teacher-set title and validity window, LaTeX import, group/class capture, one submission per student ID, and CSV records export. The validity dates are inclusive and evaluated in Malaysia time.

## Run locally

1. Open a terminal in this folder.
2. Run `python server.py`.
3. Open the teacher page at `http://127.0.0.1:8765/guru`.
4. Students use `http://127.0.0.1:8765/`.
5. Records are at `http://127.0.0.1:8765/rekod`.
6. Press `Ctrl+C` in the terminal to stop the local server.

## Deploy to PythonAnywhere

The hosted version uses `wsgi.py`; the local version continues to use `server.py`.

1. Create a PythonAnywhere account and add a Python web app using the **Manual configuration** option.
2. Upload `wsgi.py`, `requirements.txt`, `admin.html`, `admin.js`, `index.html`, `app.js`, `responses.html`, `responses.js`, and `style.css` into a folder such as `/home/YOUR_USERNAME/student_form_website`. `README.md` is optional; `server.py` is only for running locally. Do not upload log files or `__pycache__`.

   `respons.db` contains both the saved quiz (title, dates, questions, and answer key) and student submissions. Upload it only if you want to transfer both to PythonAnywhere. If you leave it out, the hosted quiz database starts empty, so you will need to enter and save the quiz again. Do not upload it if you do not want existing student names and IDs copied to the host.
3. In a PythonAnywhere Bash console, create a virtual environment and install the dependency (adjust the Python version to the one selected for the web app):

   ```bash
   mkvirtualenv --python=/usr/bin/python3.13 quiz-env
   pip install -r ~/student_form_website/requirements.txt
   ```

   Set that virtual environment in the Web tab. If your account uses a different Python version, use its matching executable instead of `python3.13`.
4. Open the WSGI configuration file linked from the Web tab. Add this configuration, replacing `YOUR_USERNAME` and choosing a strong teacher password:

   ```python
   import os
   import sys

   project = "/home/YOUR_USERNAME/student_form_website"
   if project not in sys.path:
       sys.path.insert(0, project)

   os.environ["TEACHER_USERNAME"] = "teacher"
   os.environ["TEACHER_PASSWORD"] = "REPLACE_WITH_A_LONG_UNIQUE_PASSWORD"

   from wsgi import app as application
   ```

   Keep the WSGI configuration private. It contains the teacher password. Do not put the password in a public repository or share it with students.
5. Click **Reload** in the Web tab. Your public site address will be `https://YOUR_USERNAME.pythonanywhere.com`.

Hosted links:

- Student quiz: `https://YOUR_USERNAME.pythonanywhere.com/`
- Teacher question import: `https://YOUR_USERNAME.pythonanywhere.com/guru`
- Student records: `https://YOUR_USERNAME.pythonanywhere.com/rekod`

The teacher pages and their data APIs require the username and password configured in the WSGI file. Students can access the quiz and submit once per student ID. The hosted application creates `respons.db` in the project folder when it starts; keep a separate backup of records. PythonAnywhere free accounts have limited resources and expire monthly unless renewed, so verify its current limits before relying on it for a live class.

## Notes

- PythonAnywhere hosting and the current local server are separate. Changes to local `respons.db` do not automatically sync to the hosted database.
- Student names, IDs, answers, and scores are personal information. Follow your institution's rules for storing them online and restrict access to the teacher links.
- `wsgi.py` uses Flask; `requirements.txt` lists the hosting dependency.
