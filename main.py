from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key")
DB = "database.db"

# ================== DATABASE ==================
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        c = db.cursor()
        # Users table
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            elo INTEGER DEFAULT 1000,
            avatar TEXT DEFAULT '/static/default.png'
        )
        """)
        # Friends table
        c.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user TEXT,
            friend TEXT
        )
        """)
        # Friend requests table
        c.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            sender TEXT,
            receiver TEXT
        )
        """)
        # Teams
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
        # Queue & matches
        c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            username TEXT,
            elo INTEGER,
            joined INTEGER
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            p1 TEXT,
            p2 TEXT,
            winner TEXT
        )
        """)
        db.commit()

init_db()

# ================== AUTH ==================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            return render_template("login.html", message="Введіть логін і пароль")

        with get_db() as db:
            c = db.cursor()
            c.execute("SELECT password FROM users WHERE username=?", (username,))
            user = c.fetchone()

            if not user:
                # Register new user
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                          (username, generate_password_hash(password)))
                db.commit()
                session["user"] = username
                return redirect("/game")
            elif check_password_hash(user["password"], password):
                session["user"] = username
                return redirect("/game")
            else:
                return render_template("login.html", message="Неправильний пароль")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================== GAME ==================
@app.route("/game")
def game():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT elo, avatar FROM users WHERE username=?", (user,))
        row = c.fetchone()
        elo = row["elo"] if row else 1000
        avatar = row["avatar"] if row else "/static/default.png"
    return render_template("game.html", username=user, elo=elo, avatar=avatar)

# ================== QUEUE ==================
@app.route("/queue")
def queue():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT elo FROM users WHERE username=?", (user,))
        row = c.fetchone()
        elo = row["elo"] if row else 1000
        c.execute("INSERT OR REPLACE INTO queue (username, elo, joined) VALUES (?, ?, ?)",
                  (user, elo, int(time.time())))
        db.commit()
    return "Ти доданий у чергу! (після тестів можна редирект на /matchmaking)"

# ================== HOME ==================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    return redirect("/game")

# ================== RUN ==================
if __name__ == "__main__":
    # Для Render порт читаємо з ENV
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
