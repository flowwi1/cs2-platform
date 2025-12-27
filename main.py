from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)

# ===== CONFIG =====
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
DB_PATH = os.path.join("/tmp", "database.db")

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
            avatar TEXT DEFAULT 'https://via.placeholder.com/80'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            friend TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    """)
    db.commit()
    db.close()

init_db()

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
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            db.commit()
            session["user"] = username
            db.close()
            return redirect("/home")

        if check_password_hash(user["password"], password):
            session["user"] = username
            db.close()
            return redirect("/home")

        db.close()
        return render_template("login.html", message="Невірний пароль")

    return render_template("login.html")

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

    return render_template("index.html",
                           username=username,
                           avatar=user["avatar"],
                           rank=user["elo"])

@app.route("/profile/<username>")
def profile(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    db.close()

    if not user:
        return "Користувача не знайдено", 404

    return render_template("profile.html",
                           username=user["username"],
                           avatar=user["avatar"],
                           rank=user["elo"])

@app.route("/friends", methods=["GET"])
def friends():
    if "user" not in session:
        return redirect("/")
    username = session["user"]

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT friend FROM friends
        WHERE (user=? OR friend=?) AND status='accepted'
    """, (username, username))
    friends_list = cursor.fetchall()
    friends_names = []
    for f in friends_list:
        if f["friend"] != username:
            friends_names.append(f["friend"])
        else:
            # Якщо рядок має користувача у колонці friend
            cursor.execute("SELECT user FROM friends WHERE friend=? AND status='accepted'", (username,))
            temp = cursor.fetchone()
            if temp:
                friends_names.append(temp["user"])
    db.close()

    return render_template("friends.html",
                           username=username,
                           avatar=get_user_avatar(username),
                           friends=friends_names)

@app.route("/search_friend", methods=["POST"])
def search_friend():
    if "user" not in session:
        return redirect("/")
    username = session["user"]
    friend_name = request.form.get("friend_name")

    if friend_name == username:
        return render_template("friends.html",
                               username=username,
                               avatar=get_user_avatar(username),
                               friends=get_user_friends(username),
                               search_result="Це ти",
                               add_friend=None)

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username FROM users WHERE username = ?", (friend_name,))
    user = cursor.fetchone()

    if not user:
        db.close()
        return render_template("friends.html",
                               username=username,
                               avatar=get_user_avatar(username),
                               friends=get_user_friends(username),
                               search_result="Користувача не знайдено",
                               add_friend=None)
    else:
        db.close()
        return render_template("friends.html",
                               username=username,
                               avatar=get_user_avatar(username),
                               friends=get_user_friends(username),
                               search_result="Користувача знайдено",
                               add_friend=friend_name)

@app.route("/add_friend/<friend>")
def add_friend(friend):
    if "user" not in session:
        return redirect("/")
    username = session["user"]

    db = get_db()
    cursor = db.cursor()
    # Перевірка, чи запит вже є
    cursor.execute("""
        SELECT * FROM friends WHERE
        (user=? AND friend=?) OR (user=? AND friend=?)
    """, (username, friend, friend, username))
    existing = cursor.fetchone()
    if existing is None:
        cursor.execute("INSERT INTO friends (user, friend, status) VALUES (?, ?, ?)", (username, friend, 'accepted'))
        db.commit()
    db.close()
    return redirect("/friends")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ===== HELPERS =====
def get_user_avatar(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT avatar FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    db.close()
    return user["avatar"] if user else ""

def get_user_friends(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT friend FROM friends
        WHERE (user=? OR friend=?) AND status='accepted'
    """, (username, username))
    friends_list = cursor.fetchall()
    friends_names = []
    for f in friends_list:
        if f["friend"] != username:
            friends_names.append(f["friend"])
        else:
            cursor.execute("SELECT user FROM friends WHERE friend=? AND status='accepted'", (username,))
            temp = cursor.fetchone()
            if temp:
                friends_names.append(temp["user"])
    db.close()
    return friends_names

if __name__ == "__main__":
    app.run(debug=True)
