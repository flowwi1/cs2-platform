from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import time

app = Flask(__name__)

# ===== CONFIG =====
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
DB_PATH = os.path.join("/tmp", "database.db")  # пізніше можна замінити на Render Persistent Disk

UPLOAD_FOLDER = os.path.join("static", "avatars")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ===== DATABASE =====
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            elo INTEGER DEFAULT 1000,
            avatar TEXT DEFAULT '/static/avatars/default.png',
            last_seen INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user TEXT NOT NULL,
            friend TEXT NOT NULL,
            PRIMARY KEY(user, friend)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            sender TEXT,
            receiver TEXT,
            PRIMARY KEY(sender, receiver)
        )
    """)
    cursor.execute("""
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
    return int(time.time()) - last_seen < 60  # 1 хвилина онлайн

@app.before_request
def ping():
    if "user" in session:
        update_last_seen(session["user"])

# ===== ROUTES =====
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            return render_template("login.html", message="Введіть логін і пароль")

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user is None:
            cursor.execute(
                "INSERT INTO users (username, password, last_seen) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), int(time.time()))
            )
            db.commit()
            session["user"] = username
            db.close()
            return redirect("/home")

        if check_password_hash(user["password"], password):
            session["user"] = username
            update_last_seen(username)
            db.close()
            return redirect("/home")

        db.close()
        return render_template("login.html", message="Невірний пароль")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ===== HOME =====
@app.route("/home")
def home():
    if "user" not in session:
        return redirect("/")
    username = session["user"]
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT elo, avatar FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    db.close()
    return render_template("index.html", username=username, rank=user["elo"], avatar=user["avatar"])

# ===== PROFILE =====
@app.route("/profile/<username>", methods=["GET", "POST"])
def profile(username):
    if "user" not in session:
        return redirect("/")
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        db.close()
        return "Користувача не знайдено", 404

    if request.method == "POST" and "avatar" in request.files:
        file = request.files["avatar"]
        if file.filename != "":
            filename = secure_filename(f"{username}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            avatar_url = f"/static/avatars/{filename}"
            cursor.execute("UPDATE users SET avatar = ? WHERE username = ?", (avatar_url, username))
            db.commit()
            return redirect(f"/profile/{username}")

    db.close()
    return render_template("profile.html", username=user["username"], rank=user["elo"], avatar=user["avatar"])

# ===== FRIENDS =====
@app.route("/friends", methods=["GET", "POST"])
def friends():
    if "user" not in session:
        return redirect("/")
    me = session["user"]
    search_result = None
    add_friend = None
    db = get_db()
    cursor = db.cursor()

    # список друзів
    cursor.execute("SELECT friend FROM friends WHERE user=?", (me,))
    friends_list = []
    for r in cursor.fetchall():
        cursor.execute("SELECT last_seen FROM users WHERE username=?", (r["friend"],))
        last_seen = cursor.fetchone()["last_seen"]
        friends_list.append({"name": r["friend"], "online": is_online(last_seen)})

    # запити
    cursor.execute("SELECT sender FROM friend_requests WHERE receiver=?", (me,))
    requests = [r["sender"] for r in cursor.fetchall()]

    # пошук
    if request.method == "POST":
        friend_name = request.form.get("friend_name")
        if friend_name == me:
            search_result = "Це ти 😎"
        else:
            cursor.execute("SELECT * FROM users WHERE username=?", (friend_name,))
            user = cursor.fetchone()
            if not user:
                search_result = "Користувача не знайдено"
            else:
                cursor.execute("SELECT * FROM blocked WHERE blocker=? AND blocked=?", (friend_name, me))
                if cursor.fetchone():
                    search_result = "Вас заблоковано цим користувачем"
                else:
                    cursor.execute("SELECT * FROM friends WHERE user=? AND friend=?", (me, friend_name))
                    if cursor.fetchone():
                        search_result = "Ви вже друзі"
                    else:
                        cursor.execute("SELECT * FROM friend_requests WHERE sender=? AND receiver=?", (me, friend_name))
                        if cursor.fetchone():
                            search_result = "Запит вже надіслано"
                        else:
                            search_result = f"Знайдено користувача {friend_name}"
                            add_friend = friend_name

    db.close()
    return render_template("friends.html", username=me, friends_list=friends_list,
                           requests=requests, search_result=search_result, add_friend=add_friend)

@app.route("/add_friend/<friend_name>")
def add_friend_route(friend_name):
    if "user" not in session:
        return redirect("/")
    me = session["user"]
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO friend_requests VALUES (?, ?)", (me, friend_name))
    db.commit()
    db.close()
    return redirect("/friends")

@app.route("/accept/<friend_name>")
def accept(friend_name):
    if "user" not in session:
        return redirect("/")
    me = session["user"]
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM friend_requests WHERE sender=? AND receiver=?", (friend_name, me))
    cursor.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (me, friend_name))
    cursor.execute("INSERT OR IGNORE INTO friends VALUES (?, ?)", (friend_name, me))
    db.commit()
    db.close()
    return redirect("/friends")

@app.route("/decline/<friend_name>")
def decline(friend_name):
    if "user" not in session:
        return redirect("/")
    me = session["user"]
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM friend_requests WHERE sender=? AND receiver=?", (friend_name, me))
    db.commit()
    db.close()
    return redirect("/friends")

@app.route("/remove_friend/<friend_name>")
def remove_friend(friend_name):
    if "user" not in session:
        return redirect("/")
    me = session["user"]
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM friends WHERE user=? AND friend=?", (me, friend_name))
    cursor.execute("DELETE FROM friends WHERE user=? AND friend=?", (friend_name, me))
    db.commit()
    db.close()
    return redirect("/friends")

@app.route("/block/<friend_name>")
def block(friend_name):
    if "user" not in session:
        return redirect("/")
    me = session["user"]
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO blocked VALUES (?, ?)", (me, friend_name))
    cursor.execute("DELETE FROM friends WHERE user=? AND friend=?", (me, friend_name))
    cursor.execute("DELETE FROM friends WHERE user=? AND friend=?", (friend_name, me))
    cursor.execute("DELETE FROM friend_requests WHERE sender=? OR receiver=?", (friend_name, me))
    db.commit()
    db.close()
    return redirect("/friends")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
