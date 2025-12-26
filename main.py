from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import time

app = Flask(__name__)
app.secret_key = "super-secret-key"
DB = "database.db"

# ================== DB ==================
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row  # щоб можна було звертатися як dict
    return db

def init_db():
    with get_db() as db:
        c = db.cursor()

        # Користувачі
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            elo INTEGER
        )
        """)

        # Друзі
        c.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user TEXT,
            friend TEXT
        )
        """)

        # Заявки у друзі
        c.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            sender TEXT,
            receiver TEXT
        )
        """)

        # Команди
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

        # Черга та матчі
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
                c.execute("INSERT INTO users (username, password, elo) VALUES (?, ?, ?)", 
                          (u, generate_password_hash(p), 1000))
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
        c.execute("SELECT elo FROM users WHERE username=?", (user,))
        row = c.fetchone()
        elo = row["elo"] if row else 1000
    return render_template("index.html", username=user, elo=elo)

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
            if team_name:
                c.execute("INSERT INTO teams (name, leader) VALUES (?, ?)", (team_name, user))
                team_id = c.lastrowid
                c.execute("INSERT INTO team_members (team_id, username) VALUES (?, ?)", (team_id, user))
                db.commit()
                return redirect("/profile")

        # ELO
        c.execute("SELECT elo FROM users WHERE username=?", (user,))
        elo = c.fetchone()["elo"]

        # Друзі
        c.execute("SELECT friend FROM friends WHERE user=?", (user,))
        friends = [f["friend"] for f in c.fetchall()]

        # Команди користувача
        c.execute("""
            SELECT t.id, t.name FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.username=?
        """, (user,))
        teams = c.fetchall()

    return render_template("profile.html", username=user, elo=elo, friends=friends, teams=teams)

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

# ================== TEAMS ==================
@app.route("/invite_friend", methods=["POST"])
def invite_friend():
    if "user" not in session:
        return redirect("/login")
    friend_name = request.form.get("friend_name")
    team_id = request.form.get("team_id")
    user = session["user"]
    with get_db() as db:
        c = db.cursor()
        # Перевірка чи друг
        c.execute("SELECT 1 FROM friends WHERE user=? AND friend=?", (user, friend_name))
        if not c.fetchone():
            return "Це не твій друг!"
        # Перевірка чи вже у команді
        c.execute("SELECT 1 FROM team_members WHERE team_id=? AND username=?", (team_id, friend_name))
        if not c.fetchone():
            c.execute("INSERT INTO team_members (team_id, username) VALUES (?, ?)", (team_id, friend_name))
            db.commit()
    return redirect("/profile")

@app.route("/team/<int:team_id>")
def team(team_id):
    if "user" not in session:
        return redirect("/login")
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT name, leader FROM teams WHERE id=?", (team_id,))
        team = c.fetchone()
        if not team:
            return "Команда не знайдена"
        c.execute("SELECT username FROM team_members WHERE team_id=?", (team_id,))
        members = [m["username"] for m in c.fetchall()]
    return render_template("team.html", team_name=team["name"], leader=team["leader"], members=members)

# ================== GAME / MATCHMAKING ==================
@app.route("/game")
def game():
    if "user" not in session:
        return redirect("/login")
    return render_template("game.html")

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
        c.execute("INSERT INTO queue VALUES (?, ?, ?)", (user, elo, int(time.time())))
        db.commit()
    return redirect("/matchmaking")

@app.route("/matchmaking")
def matchmaking():
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT username, elo FROM queue ORDER BY joined")
        players = c.fetchall()
        if len(players) >= 2:
            p1, p2 = players[0]["username"], players[1]["username"]
            c.execute("DELETE FROM queue WHERE username IN (?, ?)", (p1, p2))
            c.execute("INSERT INTO matches (p1, p2) VALUES (?, ?)", (p1, p2))
            db.commit()
            return redirect(f"/lobby/{p1}/{p2}")
    return "Очікування гравців..."

@app.route("/lobby/<p1>/<p2>")
def lobby(p1, p2):
    if "user" not in session or session["user"] not in [p1, p2]:
        return redirect("/")
    return render_template("lobby.html", p1=p1, p2=p2)

@app.route("/result/<winner>/<loser>")
def result(winner, loser):
    if "user" not in session:
        return redirect("/login")
    with get_db() as db:
        c = db.cursor()
        # Оновлення ELO
        c.execute("UPDATE users SET elo = elo + 25 WHERE username=?", (winner,))
        c.execute("UPDATE users SET elo = elo - 25 WHERE username=?", (loser,))
        # Оновлення конкретного матчу
        c.execute("""
            UPDATE matches SET winner=? 
            WHERE p1=? AND p2=? AND winner IS NULL
        """, (winner, winner, loser))
        db.commit()
    return redirect("/")

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
