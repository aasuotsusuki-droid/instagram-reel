from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os
from werkzeug.security import check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DB = os.path.join(os.path.dirname(__file__), "database.db")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        is_open INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS contestants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        image TEXT DEFAULT '',
        FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        contestant_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, category_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE,
        FOREIGN KEY(contestant_id) REFERENCES contestants(id) ON DELETE CASCADE
    );
    """)
    admin = conn.execute("SELECT id FROM users WHERE is_admin=1 LIMIT 1").fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(username,email,password_hash,is_admin) VALUES(?,?,?,1)",
            ("admin", "admin@example.com", "admin123")
        )
    else:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE username=? AND email=? AND password_hash LIKE 'scrypt:%'",
            ("admin123", "admin", "admin@example.com")
        )
    count = conn.execute("SELECT COUNT(*) AS c FROM categories").fetchone()["c"]
    if count == 0:
        conn.execute("INSERT INTO categories(name,description) VALUES(?,?)",
                     ("Best Craftland Map", "Vote for your favorite Craftland creation."))
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.executemany(
            "INSERT INTO contestants(category_id,name,description,image) VALUES(?,?,?,?)",
            [
                (cid, "Shadow Arena", "Fast-paced gangster arena.", ""),
                (cid, "Neon District", "A neon city battle map.", ""),
                (cid, "Last Stand", "Survive until the final round.", "")
            ]
        )
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    conn=db()
    categories=conn.execute("SELECT * FROM categories ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", categories=categories)

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        username=request.form.get("username","").strip()
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        confirm=request.form.get("confirm","")
        if not username or not email or not password:
            flash("Please fill in every field.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            conn=db()
            try:
                conn.execute("INSERT INTO users(username,email,password_hash) VALUES(?,?,?)",
                             (username,email,password))
                conn.commit()
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Username or email is already registered.", "error")
            finally:
                conn.close()
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        identity=request.form.get("identity","").strip()
        password=request.form.get("password","")
        conn=db()
        user=conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (identity,identity.lower())
        ).fetchone()
        conn.close()
        valid_password = user and user["password_hash"] == password
        if user and not valid_password and user["password_hash"].startswith(("scrypt:", "pbkdf2:", "argon2:")):
            valid_password = check_password_hash(user["password_hash"], password)
            if valid_password:
                conn = db()
                conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password, user["id"]))
                conn.commit()
                conn.close()
        if valid_password:
            session.clear()
            session["user_id"]=user["id"]
            session["username"]=user["username"]
            session["is_admin"]=bool(user["is_admin"])
            return redirect(url_for("index"))
        flash("Invalid login details.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/vote/<int:category_id>", methods=["GET","POST"])
@login_required
def vote(category_id):
    conn=db()
    category=conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
    contestants=conn.execute("SELECT * FROM contestants WHERE category_id=?", (category_id,)).fetchall()
    existing=conn.execute(
        "SELECT contestant_id FROM votes WHERE user_id=? AND category_id=?",
        (session["user_id"],category_id)
    ).fetchone()
    if not category:
        conn.close()
        return "Category not found",404
    if request.method=="POST":
        if not category["is_open"]:
            flash("Voting is closed.", "error")
        elif existing:
            flash("You have already voted in this category.", "error")
        else:
            contestant_id=request.form.get("contestant_id", type=int)
            valid=conn.execute(
                "SELECT id FROM contestants WHERE id=? AND category_id=?",
                (contestant_id,category_id)
            ).fetchone()
            if not valid:
                flash("Invalid contestant.", "error")
            else:
                try:
                    conn.execute(
                        "INSERT INTO votes(user_id,category_id,contestant_id) VALUES(?,?,?)",
                        (session["user_id"],category_id,contestant_id)
                    )
                    conn.commit()
                    flash("Your vote has been recorded!", "success")
                except sqlite3.IntegrityError:
                    flash("You have already voted in this category.", "error")
                existing=conn.execute(
                    "SELECT contestant_id FROM votes WHERE user_id=? AND category_id=?",
                    (session["user_id"],category_id)
                ).fetchone()
    conn.close()
    return render_template("vote.html", category=category, contestants=contestants, existing=existing)

@app.route("/results/<int:category_id>")
def results(category_id):
    conn=db()
    category=conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
    rows=conn.execute("""
        SELECT c.*, COUNT(v.id) AS vote_count
        FROM contestants c
        LEFT JOIN votes v ON c.id=v.contestant_id
        WHERE c.category_id=?
        GROUP BY c.id ORDER BY vote_count DESC, c.id
    """,(category_id,)).fetchall()
    conn.close()
    if not category: return "Category not found",404
    return render_template("results.html", category=category, contestants=rows)

@app.route("/admin")
@admin_required
def admin():
    conn=db()
    categories=conn.execute("SELECT * FROM categories ORDER BY id DESC").fetchall()
    users=conn.execute("SELECT id,username,email,password_hash,is_admin,created_at FROM users ORDER BY id DESC").fetchall()
    stats=conn.execute("SELECT COUNT(*) AS c FROM votes").fetchone()["c"]
    conn.close()
    return render_template("admin.html", categories=categories, users=users, total_votes=stats)

@app.route("/admin/category", methods=["POST"])
@admin_required
def add_category():
    name=request.form.get("name","").strip()
    description=request.form.get("description","").strip()
    if name:
        conn=db(); conn.execute("INSERT INTO categories(name,description) VALUES(?,?)",(name,description)); conn.commit(); conn.close()
        flash("Category created.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/category/<int:category_id>/toggle", methods=["POST"])
@admin_required
def toggle_category(category_id):
    conn=db()
    conn.execute("UPDATE categories SET is_open=CASE is_open WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (category_id,))
    conn.commit(); conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/category/<int:category_id>/contestant", methods=["POST"])
@admin_required
def add_contestant(category_id):
    name=request.form.get("name","").strip()
    description=request.form.get("description","").strip()
    image=request.form.get("image","").strip()
    if name:
        conn=db(); conn.execute(
            "INSERT INTO contestants(category_id,name,description,image) VALUES(?,?,?,?)",
            (category_id,name,description,image)
        ); conn.commit(); conn.close()
        flash("Contestant added.", "success")
    return redirect(url_for("admin"))

init_db()

if __name__ == "__main__":
    app.run(debug=True)
