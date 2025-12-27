from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
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
            sender TEXT,
            receiver TEXT,
            accepted INTEGER DEFAULT 0
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

@app.route("/profile/<username>")
def profile(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    db.close()
    if not user:
        return "Користувача не знайдено", 404
    return render_template("profile.html", username=user["username"], rank=user["elo"], avatar=user["avatar"])

@app.route("/friends")
def friends():
    if "user" not in session:
        return redirect("/")
    username = session["user"]
    db = get_db()
    cursor = db.cursor()
    # Прийняті друзі
    cursor.execute("""
        SELECT * FROM friends WHERE (sender = ? OR receiver = ?) AND accepted = 1
    """, (username, username))
    friends_list = cursor.fetchall()
    # Запити в очікуванні
    cursor.execute("SELECT * FROM friends WHERE receiver = ? AND accepted = 0", (username,))
    requests_list = cursor.fetchall()
    db.close()
    return render_template("friends.html", username=username, friends=friends_list, requests=requests_list)

@app.route("/search_friend", methods=["POST"])
def search_friend():
    if "user" not in session:
        return redirect("/")
    friend_name = request.form.get("friend_name")
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (friend_name,))
    user = cursor.fetchone()
    db.close()
    if user:
        return render_template("base.html", username=session["user"], search_result="Користувача знайдено", add_friend=friend_name)
    else:
        return render_template("base.html", username=session["user"], search_result="Користувача не знайдено")

@app.route("/add_friend/<friend_name>")
def add_friend(friend_name):
    if "user" not in session:
        return redirect("/")
    sender = session["user"]
    db = get_db()
    cursor = db.cursor()
    # Перевіряємо, чи не існує запит
    cursor.execute("SELECT * FROM friends WHERE sender=? AND receiver=?", (sender, friend_name))
    exists = cursor.fetchone()
    if not exists:
        cursor.execute("INSERT INTO friends (sender, receiver) VALUES (?, ?)", (sender, friend_name))
        db.commit()
    db.close()
    return redirect("/friends")

@app.route("/accept_friend/<int:request_id>")
def accept_friend(request_id):
    if "user" not in session:
        return redirect("/")
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE friends SET accepted = 1 WHERE id = ?", (request_id,))
    db.commit()
    db.close()
    return redirect("/friends")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
