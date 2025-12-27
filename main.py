from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import time
import uuid

# ================= APP =================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# ================= PATHS =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = "/data/database.db"   # 🔒 Render persistent disk

# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    c = db.cursor()

    # -------- USERS --------
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            elo INTEGER DEFAULT 1000,
            avatar TEXT DEFAULT '/static/avatars/default.png',
            last_seen INTEGER
        )
    """)

    # -------- FRIENDS --------
    c.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user TEXT,
            friend TEXT,
            PRIMARY KEY (user, friend)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            sender TEXT,
            receiver TEXT,
            PRIMARY KEY (sender, receiver)
        )
    """)

    # -------- LOBBY --------
    c.execute("""
        CREATE TABLE IF NOT EXISTS lobbies (
            id TEXT PRIMARY KEY,
            leader TEXT,
            status TEXT DEFAULT 'waiting',
            created_at INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS lobby_members (
            lobby_id TEXT,
            username TEXT,
            ready INTEGER DEFAULT 0,
            PRIMARY KEY (lobby_id, username)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS lobby_invites (
            lobby_id TEXT,
            sender TEXT,
            receiver TEXT,
            created_at INTEGER,
            PRIMARY KEY (lobby_id, receiver)
        )
    """)

    db.commit()
    db.close()

init_db()

# ================= HELPERS =================
def update_last_seen(username):
    db = get_db()
    db.execute(
        "UPDATE users SET last_seen=? WHERE username=?",
        (int(time.time()), username)
    )
    db.commit()
    db.close()

@app.before_request
def before_request():
    if "user" in session:
        update_last_seen(session["user"])

# ================= AUTH =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (u,))
        user = cur.fetchone()

        if not user:
            cur.execute("""
                INSERT INTO users (username, password, elo, avatar, last_seen)
                VALUES (?, ?, 1000, '/static/avatars/default.png', ?)
            """, (u, generate_password_hash(p), int(time.time())))
            db.commit()
            session["user"] = u
            return redirect("/home")

        if check_password_hash(user["password"], p):
            session["user"] = u
            return redirect("/home")

        return render_template("login.html", message="Невірний пароль")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= HOME =================
@app.route("/home")
def home():
    if "user" not in session:
        return redirect("/")

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()
    db.close()

    return render_template(
        "index.html",
        username=user["username"],
        elo=user["elo"],
        avatar=user["avatar"]
    )

# ================= LOBBY =================

@app.route("/lobby/create")
def lobby_create():
    if "user" not in session:
        return redirect("/")

    lobby_id = str(uuid.uuid4())[:8]
    db = get_db()

    db.execute("""
        INSERT INTO lobbies (id, leader, status, created_at)
        VALUES (?, ?, 'waiting', ?)
    """, (lobby_id, session["user"], int(time.time())))

    db.execute("""
        INSERT INTO lobby_members (lobby_id, username, ready)
        VALUES (?, ?, 0)
    """, (lobby_id, session["user"]))

    db.commit()
    db.close()

    return redirect(f"/lobby/{lobby_id}")

@app.route("/lobby/<lobby_id>")
def lobby_view(lobby_id):
    if "user" not in session:
        return redirect("/")

    db = get_db()

    lobby = db.execute(
        "SELECT * FROM lobbies WHERE id=?",
        (lobby_id,)
    ).fetchone()

    if not lobby:
        db.close()
        return redirect("/home")

    members = db.execute("""
        SELECT username, ready
        FROM lobby_members
        WHERE lobby_id=?
    """, (lobby_id,)).fetchall()

    friends = db.execute("""
        SELECT friend FROM friends WHERE user=?
    """, (session["user"],)).fetchall()

    db.close()

    return render_template(
        "lobby.html",
        lobby=lobby,
        members=members,
        friends=[f["friend"] for f in friends],
        me=session["user"]
    )

@app.route("/lobby/ready/<lobby_id>")
def lobby_ready(lobby_id):
    if "user" not in session:
        return redirect("/")

    db = get_db()
    db.execute("""
        UPDATE lobby_members
        SET ready = CASE ready WHEN 1 THEN 0 ELSE 1 END
        WHERE lobby_id=? AND username=?
    """, (lobby_id, session["user"]))
    db.commit()
    db.close()

    return redirect(f"/lobby/{lobby_id}")

@app.route("/lobby/start/<lobby_id>")
def lobby_start(lobby_id):
    if "user" not in session:
        return redirect("/")

    db = get_db()

    lobby = db.execute(
        "SELECT * FROM lobbies WHERE id=?",
        (lobby_id,)
    ).fetchone()

    if lobby["leader"] != session["user"]:
        db.close()
        return "ONLY LEADER", 403

    not_ready = db.execute("""
        SELECT 1 FROM lobby_members
        WHERE lobby_id=? AND ready=0
    """, (lobby_id,)).fetchone()

    if not_ready:
        db.close()
        return "NOT ALL READY", 400

    db.execute(
        "UPDATE lobbies SET status='started' WHERE id=?",
        (lobby_id,)
    )
    db.commit()
    db.close()

    return "MATCH STARTED 🔥"

# ================= INVITES =================

@app.route("/lobby/invite/<lobby_id>/<friend>")
def lobby_invite(lobby_id, friend):
    if "user" not in session:
        return redirect("/")

    db = get_db()

    is_friend = db.execute("""
        SELECT 1 FROM friends
        WHERE user=? AND friend=?
    """, (session["user"], friend)).fetchone()

    if not is_friend:
        db.close()
        return "NOT YOUR FRIEND", 403

    db.execute("""
        INSERT OR IGNORE INTO lobby_invites
        (lobby_id, sender, receiver, created_at)
        VALUES (?, ?, ?, ?)
    """, (lobby_id, session["user"], friend, int(time.time())))

    db.commit()
    db.close()

    return redirect(f"/lobby/{lobby_id}")

@app.route("/lobby/invites")
def lobby_invites():
    if "user" not in session:
        return redirect("/")

    db = get_db()
    invites = db.execute("""
        SELECT lobby_id, sender
        FROM lobby_invites
        WHERE receiver=?
    """, (session["user"],)).fetchall()
    db.close()

    return render_template("lobby_invites.html", invites=invites)

@app.route("/lobby/accept/<lobby_id>")
def lobby_accept(lobby_id):
    if "user" not in session:
        return redirect("/")

    db = get_db()

    db.execute("""
        DELETE FROM lobby_invites
        WHERE lobby_id=? AND receiver=?
    """, (lobby_id, session["user"]))

    db.execute("""
        INSERT OR IGNORE INTO lobby_members
        (lobby_id, username, ready)
        VALUES (?, ?, 0)
    """, (lobby_id, session["user"]))

    db.commit()
    db.close()

    return redirect(f"/lobby/{lobby_id}")

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
