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
    db.commit()
    db.close()

# ІНІЦІАЛІЗАЦІЯ БД ПРИ СТАРТІ (Render-safe)
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

    return render_template(
        "index.html",
        username=username,
        rank=user["elo"],  # передаємо як rank для нових шаблонів
        avatar=user["avatar"]
    )

@app.route("/profile/<username>")
def profile(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    db.close()

    if not user:
        return "Користувача не знайдено", 404

    return render_template(
        "profile.html",
        username=user["username"],
        rank=user["elo"],  # можна замінити на інше поле, якщо потрібно
        avatar=user["avatar"]
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
