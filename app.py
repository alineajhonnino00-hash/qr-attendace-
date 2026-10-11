
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, send_file, jsonify, Response
)
import sqlite3
import secrets
import qrcode
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
DATABASE = "attendance.db"
PH_TIMEZONE = ZoneInfo("Asia/Manila")


def get_ph_time():
    return datetime.now(PH_TIMEZONE)


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_columns(conn, table):
    return {
        row["name"]
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def initialize_database():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE,
            full_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK(role IN ('admin', 'teacher', 'student')),
            qr_code TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT UNIQUE NOT NULL,
            subject_name TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES subjects(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            schedule_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            time_in TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(schedule_id) REFERENCES schedules(id)
        )
    """)

    # Safe additions: do not delete existing tables or records.
    if "qr_token" not in table_columns(conn, "subjects"):
        conn.execute("ALTER TABLE subjects ADD COLUMN qr_token TEXT")

    # Preserve older schedule-level QR tokens if they exist.
    if "qr_token" not in table_columns(conn, "schedules"):
        conn.execute("ALTER TABLE schedules ADD COLUMN qr_token TEXT")

    # Assign a permanent token only to subjects that do not have one.
    subjects_without_token = conn.execute("""
        SELECT id FROM subjects
        WHERE qr_token IS NULL OR qr_token = ''
    """).fetchall()

    for subject in subjects_without_token:
        conn.execute(
            "UPDATE subjects SET qr_token = ? WHERE id = ?",
            (secrets.token_urlsafe(24), subject["id"])
        )

    # Prevent duplicate attendance for the same student, schedule and date.
    # If an old database already contains duplicates, do not delete them.
    duplicate_groups = conn.execute("""
        SELECT student_id, schedule_id, attendance_date, COUNT(*) AS n
        FROM attendance
        GROUP BY student_id, schedule_id, attendance_date
        HAVING COUNT(*) > 1
    """).fetchall()

    if not duplicate_groups:
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_attendance_student_schedule_date
            ON attendance(student_id, schedule_id, attendance_date)
        """)

    conn.commit()
    conn.close()


def is_logged_in():
    return "user_id" in session


def login_required():
    return redirect(url_for("login"))


def allowed_staff():
    return session.get("role") in ("admin", "teacher")


def day_matches(schedule_day, current_day):
    """
    Supports individual days and grouped days:
    MW = Monday and Wednesday
    TTH = Tuesday and Thursday
    Friday remains separate.
    """
    value = (schedule_day or "").strip().upper()
    current_day = current_day.upper()

    day_aliases = {
        "MON": "MONDAY",
        "TUE": "TUESDAY",
        "TUES": "TUESDAY",
        "WED": "WEDNESDAY",
        "THU": "THURSDAY",
        "THUR": "THURSDAY",
        "FRI": "FRIDAY",
    }
    current_day = day_aliases.get(current_day, current_day)
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

