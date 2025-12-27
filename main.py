from flask import Flask, render_template, redirect, request, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
DB_PATH = os.path.join("/tmp", "database.db")
UPLOAD_FOLDER = os.path.join("static", "avatars")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
            avatar TEXT DEFAULT '/static/avatars/default.png'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user TEXT,
            friend TEXT,
            status TEXT,
            PRIMARY KEY(user, friend)
        )
    """)
    db.commit()
    db.close()

init_db()

# ===== HELPERS =====
def get_user_avatar(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT avatar FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    db.close()
    if user:
        return user["avatar"]
    return "/static/avatars/default.png"

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

    return render_template(
        "index.html",
        username=username,
        rank=user["elo"],
        avatar=user["avatar"]
    )


@app.route("/profile/<username>", methods=["GET", "POST"])
def profile(username):
    if "user" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        db.close()
        return "Користувача не знайдено", 404

    if request.method == "POST":
        if "avatar" in request.files:
            file = request.files["avatar"]
            if file.filename != "":
                filename = secure_filename(file.filename)
                path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(path)
                avatar_path = f"/{path.replace(os.sep, '/')}"
                cursor.execute("UPDATE users SET avatar=? WHERE username=?", (avatar_path, username))
                db.commit()
                flash("Аватар оновлено!")
    db.close()

    return render_template(
        "profile.html",
        username=user["username"],
        rank=user["elo"],
        avatar=user["avatar"]
    )


@app.route("/friends", methods=["GET", "POST"])
def friends():
    if "user" not in session:
        return redirect("/")

    username = session["user"]
    db = get_db()
    cursor = db.cursor()
    search_result = None
    add_friend = None

    if request.method == "POST":
        friend_name = request.form.get("friend_name")
        if friend_name == username:
            search_result = "Це ти сам"
        else:
            cursor.execute("SELECT * FROM users WHERE username=?", (friend_name,))
            user = cursor.fetchone()
            if user:
                search_result = f"Знайдено користувача {friend_name}"
                add_friend = friend_name
            else:
                search_result = "Користувача не знайдено"

    cursor.execute("SELECT friend FROM friends WHERE user=? AND status='accepted'", (username,))
    friends_list = [row["friend"] for row in cursor.fetchall()]
    db.close()

    return render_template(
        "friends.html",
        username=username,
        avatar=get_user_avatar(username),
        search_result=search_result,
        add_friend=add_friend,
        friends_list=friends_list
    )


@app.route("/add_friend/<friend_username>")
def add_friend(friend_username):
    if "user" not in session:
        return redirect("/")

    username = session["user"]
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM friends WHERE user=? AND friend=?", (username, friend_username))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO friends (user, friend, status) VALUES (?, ?, ?)", (username, friend_username, "accepted"))
        cursor.execute("INSERT INTO friends (user, friend, status) VALUES (?, ?, ?)", (friend_username, username, "accepted"))
        db.commit()
    db.close()
    return redirect("/friends")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
