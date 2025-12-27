from flask import Flask, render_template, redirect, request, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3, os

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
DB_PATH = os.path.join("/tmp", "database.db")
UPLOAD_FOLDER = os.path.join("static", "avatars")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# --- DATABASE INITIALIZATION ---
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
            status TEXT DEFAULT 'accepted'
        )
    """)
    db.commit()
    db.close()

init_db()

# --- HELPER FUNCTIONS ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_avatar(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT avatar FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    db.close()
    return user["avatar"] if user else ""

# --- ROUTES ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            return render_template("login.html", message="Введіть логін і пароль")

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
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
    cursor.execute("SELECT elo, avatar FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    db.close()
    return render_template("index.html", username=username, avatar=user["avatar"], rank=user["elo"])

@app.route("/profile/<username>", methods=["GET", "POST"])
def profile(username):
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        # Завантаження аватарки
        if 'avatar' not in request.files:
            flash("Файл не знайдено")
            return redirect(url_for('profile', username=username))
        file = request.files['avatar']
        if file.filename == '':
            flash("Файл не вибрано")
            return redirect(url_for('profile', username=username))
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{username}_{file.filename}")
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            # Оновлюємо БД
            db = get_db()
            cursor = db.cursor()
            cursor.execute("UPDATE users SET avatar=? WHERE username=?", (url_for('static', filename=f"avatars/{filename}"), username))
            db.commit()
            db.close()
            flash("Аватар оновлено!")
            return redirect(url_for('profile', username=username))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    db.close()
    if not user:
        return "Користувача не знайдено", 404
    return render_template("profile.html", username=user["username"], avatar=user["avatar"], rank=user["elo"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
