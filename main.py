from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os

app = Flask(__name__)

# ===== CONFIG =====
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
DB_PATH = os.path.join("/tmp", "database.db")

# Папка для аватарок
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
            avatar TEXT DEFAULT '/static/avatars/default.png'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user TEXT NOT NULL,
            friend TEXT NOT NULL,
            PRIMARY KEY(user, friend)
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
    return render_template("index.html", username=username, rank=user["elo"], avatar=user["avatar"])

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

    # Завантаження аватарки
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

@app.route("/friends", methods=["GET", "POST"])
def friends():
    if "user" not in session:
        return redirect("/")
    username = session["user"]
    search_result = None
    add_friend = None
    db = get_db()
    cursor = db.cursor()

    # Список друзів користувача
    cursor.execute("SELECT friend FROM friends WHERE user = ?", (username,))
    friends_list = [row['friend'] for row in cursor.fetchall()]

    # Пошук друзів
    if request.method == "POST":
        friend_name = request.form.get("friend_name")
        if friend_name == username:
            search_result = "Це ти 😎"
        else:
            cursor.execute("SELECT * FROM users WHERE username = ?", (friend_name,))
            friend = cursor.fetchone()
            if friend:
                # Перевірка чи вже є у друзях
                cursor.execute("SELECT * FROM friends WHERE user=? AND friend=?", (username, friend_name))
                exists = cursor.fetchone()
                if exists:
                    search_result = f"{friend_name} вже у друзях"
                else:
                    search_result = f"Знайдено користувача {friend_name}"
                    add_friend = friend_name
            else:
                search_result = "Користувача не знайдено"

    db.close()
    return render_template("friends.html", username=username, friends_list=friends_list,
                           search_result=search_result, add_friend=add_friend)

@app.route("/add_friend/<friend_name>")
def add_friend(friend_name):
    if "user" not in session:
        return redirect("/")
    username = session["user"]
    db = get_db()
    cursor = db.cursor()

    # Додаємо тільки якщо ще не є друзями
    cursor.execute("SELECT * FROM friends WHERE user=? AND friend=?", (username, friend_name))
    exists = cursor.fetchone()
    if not exists:
        cursor.execute("INSERT INTO friends (user, friend) VALUES (?, ?)", (username, friend_name))
        cursor.execute("INSERT INTO friends (user, friend) VALUES (?, ?)", (friend_name, username))
        db.commit()
    db.close()
    return redirect("/friends")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
