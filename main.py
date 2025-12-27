from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, time

app = Flask(__name__)
app.secret_key = "dev-secret-key"

DB_PATH = os.path.join("/tmp", "database.db")


# ===== DATABASE =====
def get_db():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        last_seen INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS friends (
        user TEXT,
        friend TEXT,
        PRIMARY KEY(user, friend)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS friend_requests (
        sender TEXT,
        receiver TEXT,
        PRIMARY KEY(sender, receiver)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS blocked (
        blocker TEXT,
        blocked TEXT,
        PRIMARY KEY(blocker, blocked)
    )
    """)

    db.commit()
    db.close()


init_db()


# ===== HELPERS =====
def update_last_seen(username):
    db = get_db()
    c = db.cursor()
    c.execute("UPDATE users SET last_seen=? WHERE username=?", (int(time.time()), username))
    db.commit()
    db.close()


def is_online(last_seen):
    if not last_seen:
        return False
    return int(time.time()) - last_seen < 60  # 1 хвилина


# ===== AUTH =====
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        c = db.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()

        if not user:
            c.execute(
                "INSERT INTO users (username, password, last_seen) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), int(time.time()))
            )
            db.commit()
            session["user"] = username
            db.close()
            return redirect("/friends")

        if check_password_hash(user["password"], password):
            session["user"] = username
            update_last_seen(username)
            db.close()
            return redirect("/friends")

        db.close()

    return render_template("login.html")


@app.before_request
def online_ping():
    if "user" in session:
        update_last_seen(session["user"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ===== FRIENDS =====
@app.route("/friends", methods=["GET", "POST"])
def friends():
    if "user" not in session:
        return redirect("/")

    me = session["user"]
    db = get_db()
    c = db.cursor()

    # друзі + онлайн
    c.execute("""
        SELECT u.username, u.last_seen
        FROM friends f
        JOIN users u ON u.username = f.friend
        WHERE f.user=?
    """, (me,))
    friends_list = [
        {"name": r["username"], "online": is_online(r["last_seen"])}
        for r in c.fetchall()
    ]

    # запити
    c.execute("SELECT sender FROM friend_requests WHERE receiver=?", (me,))
    requests = [r["sender"] for r in c.fetchall()]

    # пошук
    search = None
    add_friend = None

    if request.method == "POST":
        name = request.form["friend_name"]

        if name == me:
            search = "Це ти 🙂"
        else:
            c.execute("SELECT 1 FROM users WHERE username=?", (name,))
            if not c.fetchone():
                search = "Користувача не знайдено"
            else:
                c.execute("SELECT 1 FROM blocked WHERE blocker=? AND blocked=?", (name, me))
                if c.fetchone():
                    search = "Ви заблоковані цим користувачем"
                else:
                    c.execute("SELECT 1 FROM friends WHERE user=? AND friend=?", (me, name))
                    if c.fetchone():
                        search = "Ви вже друзі"
                    else:
                        c.execute("SELECT 1 FROM friend_requests WHERE sender=? AND receiver=?", (me, name))
                        if c.fetchone():
                            search = "Запит вже надіслано"
                        else:
                            search = f"Знайдено {name}"
                            add_friend = name

    db.close()
    return render_template("friends.html",
        friends=friends_list,
        requests=requests,
        search=search,
        add_friend=add_friend
    )


@app.route("/add_friend/<name>")
def add_friend(name):
    me = session["user"]
    db = get_db()
    c = db.cursor()
    c.execute("INSERT OR IGNORE INTO friend_requests VALUES (?, ?)", (me, name))
    db.commit()
    db.close()
    return redirect("/friends")


@app.route("/accept/<name>")
def accept(name):
    me = session["user"]
    db = get_db()
    c = db.cursor()

    c.execute("DELETE FROM friend_requests WHERE sender=? AND receiver=?", (name, me))
    c.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (me, name))
    c.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (name, me))

    db.commit()
    db.close()
    return redirect("/friends")


@app.route("/decline/<name>")
def decline(name):
    me = session["user"]
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM friend_requests WHERE sender=? AND receiver=?", (name, me))
    db.commit()
    db.close()
    return redirect("/friends")


@app.route("/remove_friend/<name>")
def remove_friend(name):
    me = session["user"]
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM friends WHERE user=? AND friend=?", (me, name))
    c.execute("DELETE FROM friends WHERE user=? AND friend=?", (name, me))
    db.commit()
    db.close()
    return redirect("/friends")


@app.route("/block/<name>")
def block(name):
    me = session["user"]
    db = get_db()
    c = db.cursor()

    c.execute("INSERT OR IGNORE INTO blocked VALUES (?, ?)", (me, name))
    c.execute("DELETE FROM friends WHERE user=? AND friend=?", (me, name))
    c.execute("DELETE FROM friends WHERE user=? AND friend=?", (name, me))
    c.execute("DELETE FROM friend_requests WHERE sender=? OR receiver=?", (name, me))

    db.commit()
    db.close()
    return redirect("/friends")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
