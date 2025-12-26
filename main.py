from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import time

app = Flask(__name__)
app.secret_key = "super-secret-key"
DB = "database.db"

# ================== DB ==================
def get_db():
    return sqlite3.connect(DB)

def init_db():
    db = get_db()
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
    db.commit()
    db.close()

init_db()

# ================== AUTH ==================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        db = get_db()
        c = db.cursor()
        c.execute("SELECT password FROM users WHERE username=?", (u,))
        user = c.fetchone()

        if not user:
            # реєстрація нового користувача
            c.execute("INSERT INTO users VALUES (?, ?, ?)", (u, generate_password_hash(p), 1000))
            db.commit()
            session["user"] = u
            return redirect("/")
        if check_password_hash(user[0], p):
            session["user"] = u
            return redirect("/")

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
    db = get_db()
    c = db.cursor()
    c.execute("SELECT elo FROM users WHERE username=?", (session["user"],))
    elo = c.fetchone()[0]
    return render_template("index.html", username=session["user"], elo=elo)

# ================== PROFILE ==================
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect("/login")
    db = get_db()
    c = db.cursor()

    c.execute("SELECT elo FROM users WHERE username=?", (session["user"],))
    elo = c.fetchone()[0]

    # Друзі
    c.execute("SELECT friend FROM friends WHERE user=?", (session["user"],))
    friends = [f[0] for f in c.fetchall()]

    # Команди
    c.execute("""
        SELECT t.id, t.name FROM teams t
        JOIN team_members tm ON t.id = tm.team_id
        WHERE tm.username=?
    """, (session["user"],))
    teams = c.fetchall()

    return render_template("profile.html", username=session["user"], elo=elo, friends=friends, teams=teams)

# ================== FRIENDS ==================
@app.route("/friends", methods=["GET", "POST"])
def friends_page():
    if "user" not in session:
        return redirect("/login")
    db = get_db()
    c = db.cursor()
    user = session["user"]
    message = None
    search_result = None

    # Пошук користувача
    if request.method == "POST" and "search" in request.form:
        name = request.form["search_name"]
        c.execute("SELECT username FROM users WHERE username=?", (name,))
        if not c.fetchone():
            message = "Користувача не знайдено"
        elif name == user:
            message = "Це ти 🙂"
        else:
            search_result = name

    # Надіслати заявку в друзі
    if request.method == "POST" and "add_friend" in request.form:
        target = request.form["target"]

        # Перевірка, чи користувач вже у друзях
        c.execute("SELECT 1 FROM friends WHERE user=? AND friend=?", (user, target))
        if c.fetchone():
            message = f"{target} вже у твоїх друзях"
        else:
            # Перевірка, чи заявка вже є
            c.execute("SELECT 1 FROM friend_requests WHERE sender=? AND receiver=?", (user, target))
            if not c.fetchone():
                c.execute("INSERT INTO friend_requests VALUES (?, ?)", (user, target))
                db.commit()
                message = "Заявку надіслано"
            else:
                message = "Заявка вже надіслана"

    # Прийняти заявку
    if request.method == "POST" and "accept" in request.form:
        sender = request.form["sender"]
        # видалити заявку
        c.execute("DELETE FROM friend_requests WHERE sender=? AND receiver=?", (sender, user))
        # додати у друзі обох
        c.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (user, sender))
        c.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (sender, user))
        db.commit()
        message = f"Ви додали {sender} у друзі!"

    # Заявки на дружбу
    c.execute("SELECT sender FROM friend_requests WHERE receiver=?", (user,))
    requests = [r[0] for r in c.fetchall()]

    # Список друзів
    c.execute("SELECT friend FROM friends WHERE user=?", (user,))
    friends = [f[0] for f in c.fetchall()]

    return render_template("friends.html", username=user, friends=friends, requests=requests, search_result=search_result, message=message)

# ================== TEAMS ==================
@app.route("/create_team", methods=["POST"])
def create_team():
    if "user" not in session:
        return redirect("/login")
    team_name = request.form["team_name"]
    user = session["user"]
    db = get_db()
    c = db.cursor()
    c.execute("INSERT INTO teams (name, leader) VALUES (?, ?)", (team_name, user))
    team_id = c.lastrowid
    c.execute("INSERT INTO team_members (team_id, username) VALUES (?, ?)", (team_id, user))
    db.commit()
    return redirect("/profile")

@app.route("/invite_friend", methods=["POST"])
def invite_friend():
    if "user" not in session:
        return redirect("/login")
    friend_name = request.form["friend_name"]
    team_id = request.form["team_id"]
    user = session["user"]
    db = get_db()
    c = db.cursor()

    # Перевірка, чи друг у списку друзів
    c.execute("SELECT 1 FROM friends WHERE user=? AND friend=?", (user, friend_name))
    if not c.fetchone():
        return "Це не твій друг!"

    # Перевірка, чи вже в команді
    c.execute("SELECT 1 FROM team_members WHERE team_id=? AND username=?", (team_id, friend_name))
    if not c.fetchone():
        c.execute("INSERT INTO team_members (team_id, username) VALUES (?, ?)", (team_id, friend_name))
        db.commit()
    return redirect("/profile")

@app.route("/team/<int:team_id>")
def team(team_id):
    if "user" not in session:
        return redirect("/login")
    db = get_db()
    c = db.cursor()
    c.execute("SELECT name, leader FROM teams WHERE id=?", (team_id,))
    team = c.fetchone()
    c.execute("SELECT username FROM team_members WHERE team_id=?", (team_id,))
    members = [m[0] for m in c.fetchall()]
    return render_template("team.html", team_name=team[0], leader=team[1], members=members)

# ================== GAME / MATCHMAKING / LOBBY ==================
@app.route("/game")
def game():
    if "user" not in session:
        return redirect("/login")
    return render_template("game.html")

@app.route("/queue")
def queue():
    if "user" not in session:
        return redirect("/login")
    db = get_db()
    c = db.cursor()
    c.execute("SELECT elo FROM users WHERE username=?", (session["user"],))
    elo = c.fetchone()[0]
    c.execute("INSERT INTO queue VALUES (?, ?, ?)", (session["user"], elo, int(time.time())))
    db.commit()
    return redirect("/matchmaking")

@app.route("/matchmaking")
def matchmaking():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT username, elo FROM queue ORDER BY joined")
    players = c.fetchall()
    if len(players) >= 2:
        p1, p2 = players[0][0], players[1][0]
        c.execute("DELETE FROM queue WHERE username IN (?, ?)", (p1, p2))
        c.execute("INSERT INTO matches (p1, p2) VALUES (?, ?)", (p1, p2))
        db.commit()
        return redirect(f"/lobby/{p1}/{p2}")
    return "Очікування гравців..."

@app.route("/lobby/<p1>/<p2>")
def lobby(p1, p2):
    if session.get("user") not in [p1, p2]:
        return redirect("/")
    return render_template("lobby.html", p1=p1, p2=p2)

@app.route("/result/<winner>/<loser>")
def result(winner, loser):
    db = get_db()
    c = db.cursor()
    c.execute("UPDATE users SET elo = elo + 25 WHERE username=?", (winner,))
    c.execute("UPDATE users SET elo = elo - 25 WHERE username=?", (loser,))
    c.execute("UPDATE matches SET winner=? WHERE winner IS NULL", (winner,))
    db.commit()
    return redirect("/")

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
