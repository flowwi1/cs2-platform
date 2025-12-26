from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DB = "database.db"

# ---------- DATABASE ----------
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        c = db.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            elo INTEGER DEFAULT 1000,
            avatar TEXT DEFAULT 'https://i.imgur.com/8Km9tLL.png'
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user TEXT,
            friend TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            leader TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER,
            username TEXT
        )
        """)

        db.commit()

init_db()

# ---------- AUTH ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        with get_db() as db:
            c = db.cursor()
            c.execute("SELECT password FROM users WHERE username=?", (u,))
            user = c.fetchone()

            if not user:
                c.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (u, generate_password_hash(p))
                )
                db.commit()
                session["user"] = u
                return redirect("/")
            elif check_password_hash(user["password"], p):
                session["user"] = u
                return redirect("/")
            else:
                return render_template("login.html", error="Невірний пароль")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- HOME ----------
@app.route("/")
def index():
    if "user" not in session:
        return redirect("/login")

    user = session["user"]

    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT elo, avatar FROM users WHERE username=?", (user,))
        u = c.fetchone()

    return render_template(
        "index.html",
        username=user,
        elo=u["elo"],
        avatar=u["avatar"]
    )

# ---------- PROFILE ----------
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect("/login")

    user = session["user"]

    with get_db() as db:
        c = db.cursor()

        c.execute("SELECT elo, avatar FROM users WHERE username=?", (user,))
        u = c.fetchone()

        c.execute("SELECT friend FROM friends WHERE user=?", (user,))
        friends = [f["friend"] for f in c.fetchall()]

        c.execute("""
        SELECT t.name FROM teams t
        JOIN team_members tm ON t.id = tm.team_id
        WHERE tm.username=?
        """, (user,))
        teams = c.fetchall()

    return render_template(
        "profile.html",
        username=user,
        elo=u["elo"],
        avatar=u["avatar"],
        friends=friends,
        teams=teams
    )

# ---------- RUN (RENDER) ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
