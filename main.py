from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import time

app = Flask(__name__)
app.secret_key = "super-secret-key"
DB = "database.db"

# ================== DATABASE ==================
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
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
        # ELO та аватар
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

        # Друзі користувача
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
        c.execute("""
            SELECT username, avatar FROM users
            WHERE username IN (SELECT friend FROM friends WHERE user=?)
        """, (user,))
        friends = c.fetchall()

        # Команди користувача
        c.execute("""
            SELECT t.id, t.name FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.username=?
        """, (user,))
        teams = c.fetchall()

    return render_template("profile.html", username=user, elo=elo, friends=friends, teams=teams, avatar=avatar)

# ================== FRIENDS ==================
@app.route("/friends", methods=["GET", "POST"])
def friends_page():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    message = None
    search_result = None

    with get_db() as db:
        c = db.cursor()

        if request.method == "POST":
            # Пошук користувача
            if "search" in request.form:
                name = request.form.get("search_name")
                c.execute("SELECT username FROM users WHERE username=?", (name,))
                if not c.fetchone():
                    message = "Користувача не знайдено"
                elif name == user:
                    message = "Це ти 🙂"
                else:
                    search_result = name

            # Надіслати заявку в друзі
            elif "add_friend" in request.form:
                target = request.form.get("target")
                c.execute("SELECT 1 FROM friends WHERE user=? AND friend=?", (user, target))
                if c.fetchone():
                    message = f"{target} вже у твоїх друзях"
                else:
                    c.execute("SELECT 1 FROM friend_requests WHERE sender=? AND receiver=?", (user, target))
                    if not c.fetchone():
                        c.execute("INSERT INTO friend_requests VALUES (?, ?)", (user, target))
                        db.commit()
                        message = "Заявку надіслано"
                    else:
                        message = "Заявка вже надіслана"

            # Прийняти заявку
            elif "accept" in request.form:
                sender = request.form.get("sender")
                c.execute("DELETE FROM friend_requests WHERE sender=? AND receiver=?", (sender, user))
                c.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (user, sender))
                c.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (sender, user))
                db.commit()
                message = f"Ви додали {sender} у друзі!"

        # Заявки на дружбу
        c.execute("SELECT sender FROM friend_requests WHERE receiver=?", (user,))
        requests = [r["sender"] for r in c.fetchall()]

        # Список друзів
        c.execute("SELECT friend FROM friends WHERE user=?", (user,))
        friends = [f["friend"] for f in c.fetchall()]

    return render_template("friends.html", username=user, friends=friends, requests=requests, search_result=search_result, message=message)

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
