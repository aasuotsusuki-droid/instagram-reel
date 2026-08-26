# FF Vote

A Free Fire-inspired community voting website built with Flask + SQLite.

## Run on Windows

1. Install Python 3.10+.
2. Open a terminal in this folder.
3. Create a virtual environment:
   `python -m venv venv`
4. Activate it:
   `venv\Scripts\activate`
5. Install dependencies:
   `pip install -r requirements.txt`
6. Start:
   `python app.py`
7. Open `http://127.0.0.1:5000`

## Default development admin

Username: `admin`
Email: `admin@example.com`
Password: `admin123`

Change/remove these defaults before using the site publicly.

## Data

All persistent data is stored in `database.db`:
users, plain-text passwords, categories, contestants and votes.

Do not upload `database.db` to a public repository.
