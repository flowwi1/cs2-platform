from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import time
import os

app = Flask(__name__)
app.secret_key = "super-secret-key"
DB = "database.db"

# ================== DB ==================
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    if not os.path.exists(DB):
        with get_db() as db:
            c = db.cursor()
            # Таблиця користувачів
            c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT,
                elo INTEGER DEFAULT 1000,
                avatar TEXT DEFAULT '/static/default.png'
            )
            """)
            # Таблиця друзів
            c.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user TEXT,
                friend TEXT
            )
            """)
            # Таблиця заявок у друзі
            c.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                sender TEXT,
                receiver TEXT
            )
            """)
            # Таблиці команд
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
            # Таблиці черги та матчів
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
        u = request.form.get("username")
        p = request.form.get("password")
        if not u or not p:
            return render_template("login.html", message="Введіть логін і пароль")

        with get_db() as db:
            c = db.cursor()
            c.execute("SELECT password FROM users WHERE username=?", (u,))
            user = c.fetchone()

            if not user:
                # Створення нового користувача
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                          (u, generate_password_hash(p)))
                db.commit()
                session["user"] = u
                return redirect("/")
            elif check_password_hash(user["password"], p):
                session["user"] = u
                return redirect("/")
            else:
                return render_template("login.html", message="Неправильний пароль")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================== HOME ==================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")
    
    user = session["user"]
    
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT elo, avatar FROM users WHERE username=?", (user,))
        row = c.fetchone()
        elo = row["elo"] if row else 1000
        avatar = row["avatar"] if row else "/static/default.png"
        fc = 0

        # Команди користувача
        c.execute("""
            SELECT t.id, t.name FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.username=?
        """, (user,))
        teams = c.fetchall()

        # Друзі
        c.execute("SELECT friend FROM friends WHERE user=?", (user,))
        friends = [f["friend"] for f in c.fetchall()]

    return render_template("index.html", username=user, elo=elo, fc=fc, teams=teams, friends=friends, avatar=avatar)

# ================== PROFILE ==================
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]

    with get_db() as db:
        c = db.cursor()

        # Створення команди
        if request.method == "POST" and "create_team" in request.form:
            team_name = request.form.get("team_name")
            invited_friends = request.form.getlist("invite")
            if team_name:
                c.execute("INSERT INTO teams (name, leader) VALUES (?, ?)", (team_name, user))
                team_id = c.lastrowid
                c.execute("INSERT INTO team_members (team_id, username) VALUES (?, ?)", (team_id, user))
                for f in invited_friends:
                    c.execute("INSERT INTO team_members (team_id, username) VALUES (?, ?)", (team_id, f))
                db.commit()
                return redirect("/profile")

        # ELO та аватар
        c.execute("SELECT elo, avatar FROM users WHERE username=?", (user,))
        row = c.fetchone()
        elo = row["elo"]
        avatar = row["avatar"]

        # Друзі
        c.execute("SELECT username, avatar FROM users WHERE username IN (SELECT friend FROM friends WHERE user=?)", (user,))
        friends = c.fetchall()

        # Команди користувача
        c.execute("""
            SELECT t.id, t.name FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.username=?
        """, (user,))
        teams = c.fetchall()

    return render_template("profile.html", username=user, elo=elo, friends=friends, teams=teams, avatar=avatar)

# ================== інші маршрути ==================
# Тут можна додати /friends, /invite_friend, /team/<id> та /game маршрути аналогічно

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
