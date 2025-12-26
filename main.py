from flask import Flask, render_template, redirect, url_for, request, session
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

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        elo INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS friends (
        user TEXT,
        friend TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS friend_requests (
        sender TEXT,
        receiver TEXT
    )
    """)

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
            c.execute(
                "INSERT INTO users VALUES (?, ?, ?)",
                (u, generate_password_hash(p), 1000)
            )
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

    c.execute("SELECT friend FROM friends WHERE user=?", (session["user"],))
    friends = [f[0] for f in c.fetchall()]

    return render_template("profile.html",
                           username=session["user"],
                           elo=elo,
                           friends=friends)

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

    # 🔍 Пошук
    if request.method == "POST" and "search" in request.form:
        name = request.form["search_name"]

        c.execute("SELECT username FROM users WHERE username=?", (name,))
        if not c.fetchone():
            message = "Користувача не знайдено"
        elif name == user:
            message = "Це ти 🙂"
        else:
            search_result = name

    # ➕ Заявка
    if request.method == "POST" and "add_friend" in request.form:
        target = request.form["target"]
        c.execute("INSERT INTO friend_requests VALUES (?, ?)", (user, target))
        db.commit()
        message = "Заявку надіслано"

    # ✅ Прийняти
    if request.method == "POST" and "accept" in request.form:
        sender = request.form["sender"]

        c.execute("DELETE FROM friend_requests WHERE sender=? AND receiver=?",
                  (sender, user))
        c.execute("INSERT INTO friends VALUES (?, ?)", (user, sender))
        c.execute("INSERT INTO friends VALUES (?, ?)", (sender, user))
        db.commit()

    c.execute("SELECT sender FROM friend_requests WHERE receiver=?", (user,))
    requests = [r[0] for r in c.fetchall()]

    c.execute("SELECT friend FROM friends WHERE user=?", (user,))
    friends = [f[0] for f in c.fetchall()]

    return render_template("friends.html",
                           username=user,
                           friends=friends,
                           requests=requests,
                           search_result=search_result,
                           message=message)

# ================== GAME ==================
@app.route("/game")
def game():
    if "user" not in session:
        return redirect("/login")
    return render_template("game.html")

# ================== QUEUE ==================
@app.route("/queue")
def queue():
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    c = db.cursor()

    c.execute("SELECT elo FROM users WHERE username=?", (session["user"],))
    elo = c.fetchone()[0]

    c.execute("INSERT INTO queue VALUES (?, ?, ?)",
              (session["user"], elo, int(time.time())))
    db.commit()

    return redirect("/matchmaking")

# ================== MATCHMAKING ==================
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

# ================== LOBBY ==================
@app.route("/lobby/<p1>/<p2>")
def lobby(p1, p2):
    if session.get("user") not in [p1, p2]:
        return redirect("/")
    return render_template("lobby.html", p1=p1, p2=p2)

# ================== RESULT ==================
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
