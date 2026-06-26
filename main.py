"""
=============================================================
  RepetitorBot - O'quv Markazi Boshqaruv Tizimi
  Aiogram 3.x | SQLite | FSM | OOP | Async
  Production-Ready | by 10-yillik Python/Aiogram Developer
=============================================================
"""

import asyncio
import logging
import sqlite3
import hashlib
import random
import string
from datetime import datetime, timedelta
from os import getenv
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    BotCommand, BotCommandScopeDefault
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# ─── LOGGING SOZLAMASI ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("RepetitorBot")

# ─── SOZLAMALAR ───────────────────────────────────────────────────────────────
BOT_TOKEN = getenv("BOT_TOKEN", "")        # <-- O'z tokeningizni qo'ying
_admin_ids_raw = getenv("ADMIN_IDS", "")   # <-- Vergul bilan ajratilgan Admin ID lari: "123456,789012"
ADMIN_IDS: List[int] = [int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()]
DB_PATH = getenv("DB_PATH", "repetitor.db")

SUBJECTS = [
    "Matematika", "Fizika", "Kimyo", "Biologiya", "Tarix",
    "Ingliz tili", "Rus tili", "O'zbek tili va adabiyoti",
    "Geografiya", "Informatika", "Iqtisodiyot", "Musiqa",
    "Chizmachilik", "Buxgalteriya", "Dasturlash"
]

STARS = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

# ─── FSM HOLATLARI ────────────────────────────────────────────────────────────
class RegistrationSG(StatesGroup):
    role = State()
    first_name = State()
    last_name = State()
    phone = State()
    # Repetitor qo'shimcha
    subjects = State()
    experience = State()
    university = State()
    certificates = State()
    price = State()
    format_type = State()
    work_hours = State()
    location = State()

class BookingSG(StatesGroup):
    select_subject = State()
    select_tutor = State()
    select_date = State()
    select_time = State()
    confirm = State()

class ReviewSG(StatesGroup):
    rating = State()
    comment = State()

class HomeworkSG(StatesGroup):
    select_student = State()
    title = State()
    description = State()
    deadline = State()

class TestSG(StatesGroup):
    title = State()
    subject = State()
    add_question = State()
    question_text = State()
    option_a = State()
    option_b = State()
    option_c = State()
    option_d = State()
    correct = State()

class PaymentSG(StatesGroup):
    select_student = State()
    amount = State()
    description = State()

class AttendanceSG(StatesGroup):
    select_student = State()
    status = State()
    note = State()

class PromoSG(StatesGroup):
    code = State()
    discount = State()
    expiry = State()

class RescheduleOfferSG(StatesGroup):
    booking_id = State()
    new_date = State()
    new_time = State()

# ─── DATABASE MANAGER ─────────────────────────────────────────────────────────
class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.executescript("""
        -- Foydalanuvchilar
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student','tutor','parent','admin')),
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            username TEXT,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            bonus_lessons INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(referred_by) REFERENCES users(id)
        );

        -- Repetitor profillari
        CREATE TABLE IF NOT EXISTS tutor_profiles (
            id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL,
            subjects TEXT NOT NULL,
            experience INTEGER DEFAULT 0,
            university TEXT,
            certificates TEXT,
            price_per_hour REAL DEFAULT 0,
            format_type TEXT DEFAULT 'offline',
            work_hours TEXT,
            location TEXT,
            rating REAL DEFAULT 0,
            total_reviews INTEGER DEFAULT 0,
            total_students INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0,
            bio TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        -- Bronlar
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            tutor_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            lesson_date TEXT NOT NULL,
            lesson_time TEXT NOT NULL,
            duration_minutes INTEGER DEFAULT 60,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending','confirmed','cancelled','completed','rescheduled')),
            student_confirmed INTEGER DEFAULT 0,
            tutor_confirmed INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(tutor_id) REFERENCES users(id)
        );

        -- Davomat
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY,
            booking_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            tutor_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('present','absent','late','excused')),
            note TEXT,
            marked_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(booking_id) REFERENCES bookings(id),
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(tutor_id) REFERENCES users(id)
        );

        -- Uyga vazifalar
        CREATE TABLE IF NOT EXISTS homeworks (
            id INTEGER PRIMARY KEY,
            tutor_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            subject TEXT,
            deadline TEXT,
            file_id TEXT,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending','submitted','checked','overdue')),
            student_answer TEXT,
            tutor_feedback TEXT,
            grade INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(tutor_id) REFERENCES users(id),
            FOREIGN KEY(student_id) REFERENCES users(id)
        );

        -- Testlar
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY,
            tutor_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            subject TEXT,
            is_active INTEGER DEFAULT 1,
            time_limit_minutes INTEGER DEFAULT 30,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(tutor_id) REFERENCES users(id)
        );

        -- Test savollari
        CREATE TABLE IF NOT EXISTS test_questions (
            id INTEGER PRIMARY KEY,
            test_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL CHECK(correct_option IN ('A','B','C','D')),
            FOREIGN KEY(test_id) REFERENCES tests(id)
        );

        -- Test natijalari
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY,
            test_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            score INTEGER DEFAULT 0,
            total_questions INTEGER DEFAULT 0,
            percentage REAL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(test_id) REFERENCES tests(id),
            FOREIGN KEY(student_id) REFERENCES users(id)
        );

        -- To'lovlar
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            tutor_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending','paid','overdue','cancelled')),
            due_date TEXT,
            paid_at TEXT,
            promo_code TEXT,
            discount_amount REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(tutor_id) REFERENCES users(id)
        );

        -- Sharhlar / Reytinglar
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY,
            tutor_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            booking_id INTEGER,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(tutor_id) REFERENCES users(id),
            FOREIGN KEY(student_id) REFERENCES users(id)
        );

        -- Promo kodlar
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            discount_percent REAL NOT NULL,
            usage_limit INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            expiry_date TEXT,
            created_by INTEGER,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        -- Ota-ona bog'lanishi
        CREATE TABLE IF NOT EXISTS parent_links (
            id INTEGER PRIMARY KEY,
            parent_telegram_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(student_id) REFERENCES users(id)
        );

        -- Eslatmalar
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            booking_id INTEGER,
            reminder_type TEXT,
            remind_at TEXT NOT NULL,
            is_sent INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(booking_id) REFERENCES bookings(id)
        );

        -- Xabarlar tarixi (admin uchun)
        CREATE TABLE IF NOT EXISTS message_logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            message_text TEXT,
            timestamp TEXT DEFAULT (datetime('now','localtime'))
        );
        """)
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")

    # ── FOYDALANUVCHI METODLARI ──────────────────────────────────────────────
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_user(self, telegram_id: int, role: str, first_name: str,
                    last_name: str, phone: str, username: str = None,
                    referred_by_code: str = None) -> int:
        conn = self._get_conn()
        referral_code = self._gen_referral()
        referred_by = None
        if referred_by_code:
            ref = conn.execute("SELECT id FROM users WHERE referral_code=?", (referred_by_code,)).fetchone()
            if ref:
                referred_by = ref["id"]
        cursor = conn.execute(
            "INSERT INTO users (telegram_id,role,first_name,last_name,phone,username,referral_code,referred_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (telegram_id, role, first_name, last_name, phone, username, referral_code, referred_by)
        )
        conn.commit()
        uid = cursor.lastrowid
        conn.close()
        return uid

    def _gen_referral(self) -> str:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    # ── REPETITOR METODLARI ──────────────────────────────────────────────────
    def create_tutor_profile(self, user_id: int, subjects: str, experience: int,
                              university: str, certificates: str, price: float,
                              format_type: str, work_hours: str, location: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO tutor_profiles "
            "(user_id,subjects,experience,university,certificates,price_per_hour,format_type,work_hours,location) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, subjects, experience, university, certificates, price, format_type, work_hours, location)
        )
        conn.commit()
        conn.close()

    def get_tutor_profile(self, user_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT tp.*, u.first_name, u.last_name, u.phone, u.username, u.telegram_id "
            "FROM tutor_profiles tp JOIN users u ON tp.user_id=u.id WHERE tp.user_id=?", (user_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_tutors_by_subject(self, subject: str) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT tp.*, u.first_name, u.last_name, u.telegram_id "
            "FROM tutor_profiles tp JOIN users u ON tp.user_id=u.id "
            "WHERE tp.subjects LIKE ? AND u.is_active=1 "
            "ORDER BY tp.rating DESC",
            (f"%{subject}%",)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_tutors(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT tp.*, u.first_name, u.last_name, u.telegram_id "
            "FROM tutor_profiles tp JOIN users u ON tp.user_id=u.id "
            "WHERE u.is_active=1 ORDER BY tp.rating DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_tutor_rating(self, tutor_user_id: int):
        conn = self._get_conn()
        result = conn.execute(
            "SELECT AVG(rating) as avg_r, COUNT(*) as cnt FROM reviews WHERE tutor_id=?",
            (tutor_user_id,)
        ).fetchone()
        if result:
            conn.execute(
                "UPDATE tutor_profiles SET rating=?, total_reviews=? WHERE user_id=?",
                (round(result["avg_r"] or 0, 1), result["cnt"], tutor_user_id)
            )
            conn.commit()
        conn.close()

    # ── BRON METODLARI ───────────────────────────────────────────────────────
    def create_booking(self, student_id: int, tutor_id: int, subject: str,
                       lesson_date: str, lesson_time: str, duration: int = 60) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO bookings (student_id,tutor_id,subject,lesson_date,lesson_time,duration_minutes) "
            "VALUES (?,?,?,?,?,?)",
            (student_id, tutor_id, subject, lesson_date, lesson_time, duration)
        )
        conn.commit()
        bid = cursor.lastrowid
        conn.close()
        return bid

    def get_booking(self, booking_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_booking_status(self, booking_id: int, status: str):
        conn = self._get_conn()
        conn.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
        conn.commit()
        conn.close()

    def get_student_bookings(self, student_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT b.*, u.first_name as tutor_fn, u.last_name as tutor_ln "
            "FROM bookings b JOIN users u ON b.tutor_id=u.id "
            "WHERE b.student_id=? ORDER BY b.lesson_date DESC, b.lesson_time DESC",
            (student_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_tutor_bookings(self, tutor_id: int, status: str = None) -> List[Dict]:
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                "SELECT b.*, u.first_name as student_fn, u.last_name as student_ln, u.telegram_id as student_tg "
                "FROM bookings b JOIN users u ON b.student_id=u.id "
                "WHERE b.tutor_id=? AND b.status=? ORDER BY b.lesson_date, b.lesson_time",
                (tutor_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT b.*, u.first_name as student_fn, u.last_name as student_ln, u.telegram_id as student_tg "
                "FROM bookings b JOIN users u ON b.student_id=u.id "
                "WHERE b.tutor_id=? ORDER BY b.lesson_date DESC, b.lesson_time DESC",
                (tutor_id,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def check_time_conflict(self, tutor_id: int, lesson_date: str, lesson_time: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM bookings WHERE tutor_id=? AND lesson_date=? AND lesson_time=? "
            "AND status IN ('pending','confirmed')",
            (tutor_id, lesson_date, lesson_time)
        ).fetchone()
        conn.close()
        return row is not None

    # ── DAVOMAT METODLARI ────────────────────────────────────────────────────
    def mark_attendance(self, booking_id: int, student_id: int, tutor_id: int,
                        status: str, note: str = None) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO attendance (booking_id,student_id,tutor_id,status,note) VALUES (?,?,?,?,?)",
            (booking_id, student_id, tutor_id, status, note)
        )
        conn.commit()
        aid = cursor.lastrowid
        conn.close()
        return aid

    def get_student_attendance(self, student_id: int, tutor_id: int = None) -> List[Dict]:
        conn = self._get_conn()
        if tutor_id:
            rows = conn.execute(
                "SELECT a.*, b.lesson_date, b.lesson_time, b.subject FROM attendance a "
                "JOIN bookings b ON a.booking_id=b.id "
                "WHERE a.student_id=? AND a.tutor_id=? ORDER BY b.lesson_date DESC",
                (student_id, tutor_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT a.*, b.lesson_date, b.lesson_time, b.subject FROM attendance a "
                "JOIN bookings b ON a.booking_id=b.id "
                "WHERE a.student_id=? ORDER BY b.lesson_date DESC",
                (student_id,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── UY VAZIFALARI METODLARI ──────────────────────────────────────────────
    def create_homework(self, tutor_id: int, student_id: int, title: str,
                        description: str, subject: str, deadline: str) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO homeworks (tutor_id,student_id,title,description,subject,deadline) VALUES (?,?,?,?,?,?)",
            (tutor_id, student_id, title, description, subject, deadline)
        )
        conn.commit()
        hid = cursor.lastrowid
        conn.close()
        return hid

    def get_student_homeworks(self, student_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT h.*, u.first_name as tutor_fn, u.last_name as tutor_ln "
            "FROM homeworks h JOIN users u ON h.tutor_id=u.id "
            "WHERE h.student_id=? ORDER BY h.created_at DESC",
            (student_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def submit_homework(self, hw_id: int, answer: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE homeworks SET status='submitted', student_answer=? WHERE id=?",
            (answer, hw_id)
        )
        conn.commit()
        conn.close()

    def grade_homework(self, hw_id: int, grade: int, feedback: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE homeworks SET status='checked', grade=?, tutor_feedback=? WHERE id=?",
            (grade, feedback, hw_id)
        )
        conn.commit()
        conn.close()

    def get_tutor_homeworks(self, tutor_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT h.*, u.first_name as student_fn, u.last_name as student_ln "
            "FROM homeworks h JOIN users u ON h.student_id=u.id "
            "WHERE h.tutor_id=? ORDER BY h.created_at DESC",
            (tutor_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── TEST METODLARI ───────────────────────────────────────────────────────
    def create_test(self, tutor_id: int, title: str, subject: str, time_limit: int = 30) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO tests (tutor_id,title,subject,time_limit_minutes) VALUES (?,?,?,?)",
            (tutor_id, title, subject, time_limit)
        )
        conn.commit()
        tid = cursor.lastrowid
        conn.close()
        return tid

    def add_question(self, test_id: int, question: str, a: str, b: str, c: str, d: str, correct: str) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO test_questions (test_id,question_text,option_a,option_b,option_c,option_d,correct_option) "
            "VALUES (?,?,?,?,?,?,?)",
            (test_id, question, a, b, c, d, correct.upper())
        )
        conn.commit()
        qid = cursor.lastrowid
        conn.close()
        return qid

    def get_test(self, test_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_test_questions(self, test_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM test_questions WHERE test_id=?", (test_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_tutor_tests(self, tutor_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT t.*, COUNT(tq.id) as question_count "
            "FROM tests t LEFT JOIN test_questions tq ON t.id=tq.test_id "
            "WHERE t.tutor_id=? GROUP BY t.id ORDER BY t.created_at DESC",
            (tutor_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def save_test_result(self, test_id: int, student_id: int, score: int, total: int) -> int:
        pct = round((score / total * 100) if total > 0 else 0, 1)
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO test_results (test_id,student_id,score,total_questions,percentage) VALUES (?,?,?,?,?)",
            (test_id, student_id, score, total, pct)
        )
        conn.commit()
        rid = cursor.lastrowid
        conn.close()
        return rid

    def get_test_results(self, student_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT tr.*, t.title, t.subject FROM test_results tr JOIN tests t ON tr.test_id=t.id "
            "WHERE tr.student_id=? ORDER BY tr.finished_at DESC",
            (student_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── TO'LOV METODLARI ─────────────────────────────────────────────────────
    def create_payment(self, student_id: int, tutor_id: int, amount: float,
                       description: str, due_date: str = None,
                       promo_code: str = None, discount: float = 0) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO payments (student_id,tutor_id,amount,description,due_date,promo_code,discount_amount) "
            "VALUES (?,?,?,?,?,?,?)",
            (student_id, tutor_id, amount, description, due_date, promo_code, discount)
        )
        conn.commit()
        pid = cursor.lastrowid
        conn.close()
        return pid

    def mark_payment_paid(self, payment_id: int):
        conn = self._get_conn()
        conn.execute(
            "UPDATE payments SET status='paid', paid_at=datetime('now','localtime') WHERE id=?",
            (payment_id,)
        )
        conn.commit()
        conn.close()

    def get_student_payments(self, student_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT p.*, u.first_name as tutor_fn, u.last_name as tutor_ln "
            "FROM payments p JOIN users u ON p.tutor_id=u.id "
            "WHERE p.student_id=? ORDER BY p.created_at DESC",
            (student_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_tutor_payments(self, tutor_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT p.*, u.first_name as student_fn, u.last_name as student_ln "
            "FROM payments p JOIN users u ON p.student_id=u.id "
            "WHERE p.tutor_id=? ORDER BY p.created_at DESC",
            (tutor_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── SHARH METODLARI ──────────────────────────────────────────────────────
    def add_review(self, tutor_id: int, student_id: int, rating: int,
                   comment: str, booking_id: int = None) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO reviews (tutor_id,student_id,booking_id,rating,comment) VALUES (?,?,?,?,?)",
            (tutor_id, student_id, booking_id, rating, comment)
        )
        conn.commit()
        rid = cursor.lastrowid
        conn.close()
        self.update_tutor_rating(tutor_id)
        return rid

    def get_tutor_reviews(self, tutor_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT r.*, u.first_name, u.last_name FROM reviews r JOIN users u ON r.student_id=u.id "
            "WHERE r.tutor_id=? ORDER BY r.created_at DESC LIMIT 10",
            (tutor_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── PROMO KOD METODLARI ──────────────────────────────────────────────────
    def create_promo(self, code: str, discount: float, usage_limit: int,
                     expiry: str, created_by: int) -> bool:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO promo_codes (code,discount_percent,usage_limit,expiry_date,created_by) "
                "VALUES (?,?,?,?,?)",
                (code.upper(), discount, usage_limit, expiry, created_by)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def use_promo(self, code: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM promo_codes WHERE code=? AND is_active=1 "
            "AND (expiry_date IS NULL OR expiry_date >= date('now')) "
            "AND used_count < usage_limit",
            (code.upper(),)
        ).fetchone()
        if row:
            conn.execute("UPDATE promo_codes SET used_count=used_count+1 WHERE id=?", (row["id"],))
            conn.commit()
        conn.close()
        return dict(row) if row else None

    # ── STATISTIKA METODLARI ─────────────────────────────────────────────────
    def get_tutor_stats(self, tutor_id: int) -> Dict:
        conn = self._get_conn()
        stats = {}
        # Jami bronlar
        r = conn.execute("SELECT COUNT(*) as cnt FROM bookings WHERE tutor_id=?", (tutor_id,)).fetchone()
        stats["total_bookings"] = r["cnt"]
        # Tasdiqlangan
        r = conn.execute("SELECT COUNT(*) as cnt FROM bookings WHERE tutor_id=? AND status='confirmed'", (tutor_id,)).fetchone()
        stats["confirmed"] = r["cnt"]
        # Jami daromad
        r = conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM payments WHERE tutor_id=? AND status='paid'", (tutor_id,)).fetchone()
        stats["total_income"] = r["total"]
        # Kutilayotgan to'lov
        r = conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM payments WHERE tutor_id=? AND status='pending'", (tutor_id,)).fetchone()
        stats["pending_income"] = r["total"]
        # O'quvchilar soni
        r = conn.execute("SELECT COUNT(DISTINCT student_id) as cnt FROM bookings WHERE tutor_id=?", (tutor_id,)).fetchone()
        stats["unique_students"] = r["cnt"]
        # Reyting
        r = conn.execute("SELECT rating, total_reviews FROM tutor_profiles WHERE user_id=?", (tutor_id,)).fetchone()
        if r:
            stats["rating"] = r["rating"]
            stats["total_reviews"] = r["total_reviews"]
        conn.close()
        return stats

    def get_student_stats(self, student_id: int) -> Dict:
        conn = self._get_conn()
        stats = {}
        r = conn.execute("SELECT COUNT(*) as cnt FROM bookings WHERE student_id=?", (student_id,)).fetchone()
        stats["total_lessons"] = r["cnt"]
        r = conn.execute("SELECT COUNT(*) as cnt FROM attendance WHERE student_id=? AND status='present'", (student_id,)).fetchone()
        stats["attended"] = r["cnt"]
        r = conn.execute("SELECT COUNT(*) as cnt FROM attendance WHERE student_id=? AND status='absent'", (student_id,)).fetchone()
        stats["absent"] = r["cnt"]
        r = conn.execute("SELECT COUNT(*) as cnt FROM homeworks WHERE student_id=?", (student_id,)).fetchone()
        stats["total_hw"] = r["cnt"]
        r = conn.execute("SELECT COUNT(*) as cnt FROM homeworks WHERE student_id=? AND status='submitted'", (student_id,)).fetchone()
        stats["submitted_hw"] = r["cnt"]
        r = conn.execute("SELECT AVG(percentage) as avg_p FROM test_results WHERE student_id=?", (student_id,)).fetchone()
        stats["avg_test_score"] = round(r["avg_p"] or 0, 1)
        conn.close()
        return stats

    def get_top_students(self, tutor_id: int, limit: int = 10) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT u.first_name, u.last_name, "
            "COUNT(DISTINCT b.id) as lessons, "
            "AVG(tr.percentage) as avg_score "
            "FROM users u "
            "LEFT JOIN bookings b ON u.id=b.student_id AND b.tutor_id=? "
            "LEFT JOIN test_results tr ON u.id=tr.student_id "
            "WHERE b.tutor_id=? "
            "GROUP BY u.id ORDER BY avg_score DESC LIMIT ?",
            (tutor_id, tutor_id, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_students_of_tutor(self, tutor_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT u.id, u.first_name, u.last_name, u.telegram_id, u.phone "
            "FROM users u JOIN bookings b ON u.id=b.student_id "
            "WHERE b.tutor_id=?",
            (tutor_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_parent_students(self, parent_telegram_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT u.* FROM users u JOIN parent_links pl ON u.id=pl.student_id "
            "WHERE pl.parent_telegram_id=?",
            (parent_telegram_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def link_parent(self, parent_telegram_id: int, student_id: int):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO parent_links (parent_telegram_id,student_id) VALUES (?,?)",
            (parent_telegram_id, student_id)
        )
        conn.commit()
        conn.close()

    def get_monthly_report(self, tutor_id: int, year: int, month: int) -> Dict:
        conn = self._get_conn()
        m = f"{year}-{month:02d}"
        report = {}
        r = conn.execute(
            "SELECT COUNT(*) as cnt FROM bookings WHERE tutor_id=? AND lesson_date LIKE ?",
            (tutor_id, f"{m}%")
        ).fetchone()
        report["total_lessons"] = r["cnt"]
        r = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as total FROM payments WHERE tutor_id=? AND paid_at LIKE ? AND status='paid'",
            (tutor_id, f"{m}%")
        ).fetchone()
        report["income"] = r["total"]
        r = conn.execute(
            "SELECT COUNT(*) as cnt FROM attendance WHERE tutor_id=? AND status='present' AND marked_at LIKE ?",
            (tutor_id, f"{m}%")
        ).fetchone()
        report["present_count"] = r["cnt"]
        r = conn.execute(
            "SELECT COUNT(*) as cnt FROM attendance WHERE tutor_id=? AND status='absent' AND marked_at LIKE ?",
            (tutor_id, f"{m}%")
        ).fetchone()
        report["absent_count"] = r["cnt"]
        conn.close()
        return report

    def add_reminder(self, user_id: int, booking_id: int, remind_at: str, reminder_type: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO reminders (user_id,booking_id,remind_at,reminder_type) VALUES (?,?,?,?)",
            (user_id, booking_id, remind_at, reminder_type)
        )
        conn.commit()
        conn.close()

    def get_pending_reminders(self) -> List[Dict]:
        conn = self._get_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = conn.execute(
            "SELECT * FROM reminders WHERE is_sent=0 AND remind_at <= ?", (now,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def mark_reminder_sent(self, reminder_id: int):
        conn = self._get_conn()
        conn.execute("UPDATE reminders SET is_sent=1 WHERE id=?", (reminder_id,))
        conn.commit()
        conn.close()


# ─── GLOBAL DB INSTANCE ───────────────────────────────────────────────────────
db = DatabaseManager(DB_PATH)

# ─── KLAVIATURA YORDAMCHILARI ─────────────────────────────────────────────────
class Keyboards:

    @staticmethod
    def main_menu_student() -> ReplyKeyboardMarkup:
        kb = ReplyKeyboardBuilder()
        kb.button(text="📚 Fanlar")
        kb.button(text="📅 Bronlarim")
        kb.button(text="📝 Uy vazifalari")
        kb.button(text="📊 Testlar")
        kb.button(text="💰 To'lovlar")
        kb.button(text="📈 Statistika")
        kb.button(text="🔗 Referal")
        kb.button(text="👤 Profil")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def main_menu_tutor() -> ReplyKeyboardMarkup:
        kb = ReplyKeyboardBuilder()
        kb.button(text="📋 Bronlar")
        kb.button(text="👥 O'quvchilarim")
        kb.button(text="📝 Vazifa berish")
        kb.button(text="📊 Test yaratish")
        kb.button(text="✅ Davomat")
        kb.button(text="💰 To'lovlar")
        kb.button(text="📈 Statistika")
        kb.button(text="📄 Hisobot")
        kb.button(text="👤 Profilim")
        kb.button(text="⚙️ Sozlamalar")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def main_menu_admin() -> ReplyKeyboardMarkup:
        kb = ReplyKeyboardBuilder()
        kb.button(text="👥 Foydalanuvchilar")
        kb.button(text="📊 Umumiy statistika")
        kb.button(text="🎟️ Promo kodlar")
        kb.button(text="📢 Xabar yuborish")
        kb.button(text="✅ Repetitorlarni tasdiqlash")
        kb.button(text="⚙️ Sozlamalar")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def phone_keyboard() -> ReplyKeyboardMarkup:
        kb = ReplyKeyboardBuilder()
        kb.button(text="📱 Telefon raqamimni ulashish", request_contact=True)
        return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)

    @staticmethod
    def role_keyboard() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="👨‍🎓 Men o'quvchiman", callback_data="role_student")
        builder.button(text="👨‍🏫 Men repetitorman", callback_data="role_tutor")
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def subjects_keyboard(selected: List[str] = None) -> InlineKeyboardMarkup:
        if selected is None:
            selected = []
        builder = InlineKeyboardBuilder()
        for subj in SUBJECTS:
            check = "✅ " if subj in selected else ""
            builder.button(text=f"{check}{subj}", callback_data=f"subj_{subj}")
        builder.button(text="✔️ Tasdiqlash", callback_data="subj_done")
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def format_keyboard() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🏠 Offline", callback_data="fmt_offline")
        builder.button(text="💻 Online", callback_data="fmt_online")
        builder.button(text="🔄 Ikkalasi", callback_data="fmt_both")
        builder.adjust(3)
        return builder.as_markup()

    @staticmethod
    def booking_action_keyboard(booking_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Tasdiqlash", callback_data=f"bk_confirm_{booking_id}")
        builder.button(text="❌ Rad etish", callback_data=f"bk_cancel_{booking_id}")
        builder.button(text="🔄 Vaqt taklif qilish", callback_data=f"bk_reschedule_{booking_id}")
        builder.adjust(2, 1)
        return builder.as_markup()

    @staticmethod
    def back_keyboard(cb: str = "back_main") -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Orqaga", callback_data=cb)
        return builder.as_markup()

    @staticmethod
    def rating_keyboard() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for i in range(1, 6):
            builder.button(text=STARS[i-1], callback_data=f"rating_{i}")
        builder.adjust(5)
        return builder.as_markup()

    @staticmethod
    def attendance_keyboard(booking_id: int, student_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Keldi", callback_data=f"att_present_{booking_id}_{student_id}")
        builder.button(text="❌ Kelmadi", callback_data=f"att_absent_{booking_id}_{student_id}")
        builder.button(text="⏰ Kech keldi", callback_data=f"att_late_{booking_id}_{student_id}")
        builder.button(text="📋 Uzrli", callback_data=f"att_excused_{booking_id}_{student_id}")
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def tutors_keyboard(tutors: List[Dict]) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for t in tutors:
            stars = "⭐" * round(t.get("rating", 0)) if t.get("rating") else "🆕"
            builder.button(
                text=f"{t['first_name']} {t['last_name']} {stars}",
                callback_data=f"tutor_{t['user_id']}"
            )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def payment_action_keyboard(payment_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ To'landi", callback_data=f"pay_done_{payment_id}")
        builder.button(text="❌ Bekor qilish", callback_data=f"pay_cancel_{payment_id}")
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def test_list_keyboard(tests: List[Dict]) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for t in tests:
            builder.button(
                text=f"📊 {t['title']} ({t.get('question_count', 0)} savol)",
                callback_data=f"take_test_{t['id']}"
            )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def options_keyboard(test_id: int, q_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for opt in ["A", "B", "C", "D"]:
            builder.button(text=opt, callback_data=f"ans_{test_id}_{q_id}_{opt}")
        builder.adjust(4)
        return builder.as_markup()

    @staticmethod
    def subjects_select_keyboard() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for s in SUBJECTS:
            builder.button(text=s, callback_data=f"book_subj_{s}")
        builder.adjust(2)
        return builder.as_markup()


# ─── RUTER DEFINITSIYALARI ────────────────────────────────────────────────────
main_router = Router()


# ─── MATN YORDAMCHILARI ───────────────────────────────────────────────────────
class Texts:
    @staticmethod
    def tutor_profile(tp: Dict, user: Dict) -> str:
        stars_str = "⭐" * round(tp.get("rating", 0)) if tp.get("rating", 0) > 0 else "🆕 Baholanmagan"
        return (
            f"👨‍🏫 *{tp['first_name']} {tp['last_name']}*\n\n"
            f"📚 *Fanlar:* {tp.get('subjects','—')}\n"
            f"🎓 *Tajriba:* {tp.get('experience','0')} yil\n"
            f"🏫 *Universitet:* {tp.get('university','—')}\n"
            f"🏆 *Sertifikatlar:* {tp.get('certificates','—')}\n"
            f"💰 *Dars narxi:* {tp.get('price_per_hour','—')} so'm/soat\n"
            f"📍 *Joylashuv:* {tp.get('location','—')}\n"
            f"💻 *Format:* {tp.get('format_type','—').capitalize()}\n"
            f"⏰ *Ish vaqti:* {tp.get('work_hours','—')}\n"
            f"👥 *O'quvchilar:* {tp.get('total_students',0)}\n"
            f"⭐ *Reyting:* {tp.get('rating',0)} ({tp.get('total_reviews',0)} sharh)\n{stars_str}\n"
            f"📞 *Telefon:* {user.get('phone','—')}\n"
            f"📱 *Telegram:* @{user.get('username','—')}"
        )

    @staticmethod
    def booking_info(b: Dict) -> str:
        status_map = {
            "pending": "⏳ Kutilmoqda",
            "confirmed": "✅ Tasdiqlangan",
            "cancelled": "❌ Bekor qilingan",
            "completed": "🏁 Yakunlangan",
            "rescheduled": "🔄 Qayta rejalashtirilgan"
        }
        return (
            f"📅 *Bron #{b['id']}*\n"
            f"📚 Fan: {b['subject']}\n"
            f"📆 Sana: {b['lesson_date']}\n"
            f"⏰ Vaqt: {b['lesson_time']}\n"
            f"⏱ Davomiylik: {b.get('duration_minutes', 60)} daqiqa\n"
            f"📊 Holat: {status_map.get(b['status'], b['status'])}"
        )


# ─── /START HANDLER ───────────────────────────────────────────────────────────
@main_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id
    user = db.get_user(tg_id)

    # Admin tekshiruvi
    if tg_id in ADMIN_IDS:
        if not user:
            db.create_user(tg_id, "admin", "Admin", "User",
                           "", message.from_user.username or "")
        await message.answer(
            "👑 *Admin paneliga xush kelibsiz!*",
            reply_markup=Keyboards.main_menu_admin(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Mavjud foydalanuvchi
    if user:
        role_text = "o'quvchi" if user["role"] == "student" else "repetitor"
        await message.answer(
            f"👋 Xush kelibsiz, *{user['first_name']}*!\n"
            f"Siz {role_text} sifatida tizimdasiz.",
            reply_markup=Keyboards.main_menu_student() if user["role"] == "student"
                         else Keyboards.main_menu_tutor(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Yangi foydalanuvchi - referral tekshiruvi
    args = message.text.split()
    referral = args[1] if len(args) > 1 else None
    if referral:
        await state.update_data(referral=referral)

    await message.answer(
        "🎓 *RepetitorBot*ga xush kelibsiz!\n\n"
        "Siz kimsiz?",
        reply_markup=Keyboards.role_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    await state.set_state(RegistrationSG.role)


@main_router.callback_query(RegistrationSG.role, F.data.startswith("role_"))
async def reg_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    await state.update_data(role=role)
    await callback.message.edit_text("👤 Ismingizni kiriting:")
    await state.set_state(RegistrationSG.first_name)
    await callback.answer()


@main_router.message(RegistrationSG.first_name)
async def reg_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text.strip())
    await message.answer("👤 Familiyangizni kiriting:")
    await state.set_state(RegistrationSG.last_name)


@main_router.message(RegistrationSG.last_name)
async def reg_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text.strip())
    await message.answer(
        "📱 Telefon raqamingizni ulashing:",
        reply_markup=Keyboards.phone_keyboard()
    )
    await state.set_state(RegistrationSG.phone)


@main_router.message(RegistrationSG.phone, F.contact)
async def reg_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await _process_phone(message, state, phone)


@main_router.message(RegistrationSG.phone)
async def reg_phone_text(message: Message, state: FSMContext):
    await _process_phone(message, state, message.text.strip())


async def _process_phone(message: Message, state: FSMContext, phone: str):
    await state.update_data(phone=phone)
    data = await state.get_data()

    if data["role"] == "student":
        uid = db.create_user(
            message.from_user.id, "student",
            data["first_name"], data["last_name"], phone,
            message.from_user.username or "",
            data.get("referral")
        )
        await message.answer(
            f"✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n"
            f"👋 Salom, *{data['first_name']}*!\n\n"
            f"Endi fanlarni ko'rib, repetitor bron qilishingiz mumkin.",
            reply_markup=Keyboards.main_menu_student(),
            parse_mode=ParseMode.MARKDOWN
        )
        await state.clear()
        # Referral bonus
        if data.get("referral"):
            ref_user = db.get_user(message.from_user.id)
            if ref_user and ref_user.get("referred_by"):
                referrer = db.get_user_by_id(ref_user["referred_by"])
                if referrer:
                    try:
                        await message.bot.send_message(
                            referrer["telegram_id"],
                            f"🎉 Referalingiz *{data['first_name']}* ro'yxatdan o'tdi!\n"
                            f"Sizga 1 ta bonus dars berildi!",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception:
                        pass
    else:
        # Repetitor - qo'shimcha ma'lumotlar
        await state.update_data(selected_subjects=[])
        await message.answer(
            "📚 O'qitadigan fanlaringizni tanlang (bir nechtasini tanlashingiz mumkin):",
            reply_markup=ReplyKeyboardRemove()
        )
        await message.answer(
            "Fan tanlang:",
            reply_markup=Keyboards.subjects_keyboard([])
        )
        await state.set_state(RegistrationSG.subjects)


@main_router.callback_query(RegistrationSG.subjects, F.data.startswith("subj_"))
async def reg_subjects(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_subjects", [])
    subj = callback.data[5:]

    if subj == "done":
        if not selected:
            await callback.answer("⚠️ Kamida 1 ta fan tanlang!", show_alert=True)
            return
        await state.update_data(selected_subjects=selected)
        await callback.message.edit_text("📅 Necha yillik tajribangiz bor? (Raqam kiriting):")
        await state.set_state(RegistrationSG.experience)
    else:
        if subj in selected:
            selected.remove(subj)
        else:
            selected.append(subj)
        await state.update_data(selected_subjects=selected)
        await callback.message.edit_reply_markup(
            reply_markup=Keyboards.subjects_keyboard(selected)
        )
    await callback.answer()


@main_router.message(RegistrationSG.experience)
async def reg_experience(message: Message, state: FSMContext):
    try:
        exp = int(message.text.strip())
        await state.update_data(experience=exp)
        await message.answer("🏫 Qaysi universitetni tamomlagan siz? (yo'q bo'lsa 'Yo'q' deb yozing):")
        await state.set_state(RegistrationSG.university)
    except ValueError:
        await message.answer("⚠️ Iltimos, raqam kiriting:")


@main_router.message(RegistrationSG.university)
async def reg_university(message: Message, state: FSMContext):
    await state.update_data(university=message.text.strip())
    await message.answer("🏆 Sertifikatlaringiz (IELTS, Xalqaro va boshqa sertifikatlar. Yo'q bo'lsa 'Yo'q' deb yozing):")
    await state.set_state(RegistrationSG.certificates)


@main_router.message(RegistrationSG.certificates)
async def reg_certificates(message: Message, state: FSMContext):
    await state.update_data(certificates=message.text.strip())
    await message.answer("💰 Soatlik dars narxingiz (so'mda):")
    await state.set_state(RegistrationSG.price)


@main_router.message(RegistrationSG.price)
async def reg_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace(",", "").replace(" ", ""))
        await state.update_data(price=price)
        await message.answer(
            "💻 Dars formatini tanlang:",
            reply_markup=Keyboards.format_keyboard()
        )
        await state.set_state(RegistrationSG.format_type)
    except ValueError:
        await message.answer("⚠️ Iltimos, raqam kiriting (masalan: 50000):")


@main_router.callback_query(RegistrationSG.format_type, F.data.startswith("fmt_"))
async def reg_format(callback: CallbackQuery, state: FSMContext):
    fmt = callback.data[4:]
    await state.update_data(format_type=fmt)
    await callback.message.edit_text(
        "⏰ Ish vaqtlaringizni kiriting:\n"
        "Masalan: Dushanba-Juma 09:00-18:00"
    )
    await state.set_state(RegistrationSG.work_hours)
    await callback.answer()


@main_router.message(RegistrationSG.work_hours)
async def reg_work_hours(message: Message, state: FSMContext):
    await state.update_data(work_hours=message.text.strip())
    await message.answer("📍 Joylashuvingizni kiriting (shahar, tuman):")
    await state.set_state(RegistrationSG.location)


@main_router.message(RegistrationSG.location)
async def reg_location(message: Message, state: FSMContext):
    data = await state.get_data()
    subjects_str = ", ".join(data.get("selected_subjects", []))

    uid = db.create_user(
        message.from_user.id, "tutor",
        data["first_name"], data["last_name"],
        data["phone"], message.from_user.username or "",
        data.get("referral")
    )
    user = db.get_user(message.from_user.id)
    db.create_tutor_profile(
        user["id"], subjects_str, data["experience"],
        data["university"], data["certificates"], data["price"],
        data["format_type"], data["work_hours"], message.text.strip()
    )

    await message.answer(
        f"✅ *Profil muvaffaqiyatli yaratildi!*\n\n"
        f"👨‍🏫 {data['first_name']} {data['last_name']}\n"
        f"📚 Fanlar: {subjects_str}\n"
        f"💰 Narx: {data['price']:,.0f} so'm/soat\n\n"
        f"Admin tasdiqlaganidan so'ng profilingiz ko'rinadi.",
        reply_markup=Keyboards.main_menu_tutor(),
        parse_mode=ParseMode.MARKDOWN
    )
    await state.clear()

    # Admin bildirishnomasi
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"🆕 Yangi repetitor ro'yxatdan o'tdi:\n"
                f"*{data['first_name']} {data['last_name']}*\n"
                f"Fanlar: {subjects_str}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass


# ─── O'QUVCHI HANDLERLARI ─────────────────────────────────────────────────────

# Fan tanlash va repetitor qidirish
@main_router.message(F.text == "📚 Fanlar")
async def student_subjects(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "student":
        return
    await message.answer(
        "📚 Qaysi fanda repetitor qidirmoqchisiz?",
        reply_markup=Keyboards.subjects_select_keyboard()
    )


@main_router.callback_query(F.data.startswith("book_subj_"))
async def student_select_subject(callback: CallbackQuery, state: FSMContext):
    subject = callback.data[10:]
    tutors = db.get_tutors_by_subject(subject)
    if not tutors:
        await callback.message.edit_text(
            f"😔 *{subject}* bo'yicha repetitor topilmadi.\n"
            "Boshqa fan tanlang.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back_keyboard("back_subjects")
        )
        await callback.answer()
        return

    await state.update_data(booking_subject=subject)
    await callback.message.edit_text(
        f"📚 *{subject}* bo'yicha repetitorlar:\n"
        f"Birini tanlang:",
        reply_markup=Keyboards.tutors_keyboard(tutors),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@main_router.callback_query(F.data.startswith("tutor_"))
async def view_tutor_profile(callback: CallbackQuery, state: FSMContext):
    tutor_user_id = int(callback.data[6:])
    tp = db.get_tutor_profile(tutor_user_id)
    if not tp:
        await callback.answer("Repetitor topilmadi!", show_alert=True)
        return

    user = db.get_user_by_id(tutor_user_id)
    text = Texts.tutor_profile(tp, user or {})

    reviews = db.get_tutor_reviews(tutor_user_id)
    if reviews:
        text += "\n\n💬 *So'nggi sharhlar:*"
        for r in reviews[:3]:
            stars = "⭐" * r["rating"]
            text += f"\n{stars} — {r['first_name']}: {r.get('comment','')}"

    builder = InlineKeyboardBuilder()
    data = await state.get_data()
    subject = data.get("booking_subject")
    if subject:
        builder.button(text="📅 Bron qilish", callback_data=f"start_booking_{tutor_user_id}")
    builder.button(text="⭐ Baho berish", callback_data=f"review_{tutor_user_id}")
    builder.button(text="⬅️ Orqaga", callback_data="back_subjects")
    builder.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@main_router.callback_query(F.data.startswith("start_booking_"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    tutor_user_id = int(callback.data[14:])
    await state.update_data(booking_tutor_id=tutor_user_id)
    await callback.message.edit_text(
        "📆 Dars sanasini kiriting:\n"
        "Format: *YYYY-MM-DD* (masalan: 2025-06-15)",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.set_state(BookingSG.select_date)
    await callback.answer()


@main_router.message(BookingSG.select_date)
async def booking_date(message: Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d")
        if dt.date() < datetime.now().date():
            await message.answer("⚠️ O'tgan sanani tanlab bo'lmaydi!")
            return
        await state.update_data(booking_date=message.text.strip())
        await message.answer(
            "⏰ Dars vaqtini kiriting:\n"
            "Format: *HH:MM* (masalan: 14:00)",
            parse_mode=ParseMode.MARKDOWN
        )
        await state.set_state(BookingSG.select_time)
    except ValueError:
        await message.answer("⚠️ Noto'g'ri format! YYYY-MM-DD ko'rinishida kiriting:")


@main_router.message(BookingSG.select_time)
async def booking_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%H:%M")
        data = await state.get_data()
        tutor_id = data["booking_tutor_id"]
        lesson_date = data["booking_date"]
        lesson_time = message.text.strip()
        subject = data["booking_subject"]

        # Vaqt konfliktini tekshirish
        conflict = db.check_time_conflict(tutor_id, lesson_date, lesson_time)
        if conflict:
            await message.answer(
                "⚠️ Bu vaqtda repetitorning boshqa darsi bor!\n"
                "Iltimos, boshqa vaqt tanlang:",
            )
            return

        await state.update_data(booking_time=lesson_time)

        tp = db.get_tutor_profile(tutor_id)
        user_info = db.get_user_by_id(tutor_id)
        await message.answer(
            f"📋 *Bron tasdiqlash*\n\n"
            f"👨‍🏫 Repetitor: {tp['first_name']} {tp['last_name']}\n"
            f"📚 Fan: {subject}\n"
            f"📆 Sana: {lesson_date}\n"
            f"⏰ Vaqt: {lesson_time}\n"
            f"💰 Narx: {tp.get('price_per_hour','—')} so'm/soat\n\n"
            f"Tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Ha, bron qilaman", callback_data="confirm_booking")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_booking")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        await state.set_state(BookingSG.confirm)
    except ValueError:
        await message.answer("⚠️ Noto'g'ri format! HH:MM ko'rinishida kiriting:")


@main_router.callback_query(BookingSG.confirm, F.data == "confirm_booking")
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    student = db.get_user(callback.from_user.id)
    tutor_id = data["booking_tutor_id"]

    booking_id = db.create_booking(
        student["id"], tutor_id,
        data["booking_subject"],
        data["booking_date"],
        data["booking_time"]
    )

    # Eslatma qo'shish (30 daqiqa oldin)
    lesson_dt = datetime.strptime(f"{data['booking_date']} {data['booking_time']}", "%Y-%m-%d %H:%M")
    remind_dt = lesson_dt - timedelta(minutes=30)
    db.add_reminder(student["id"], booking_id, remind_dt.strftime("%Y-%m-%d %H:%M"), "lesson_start")
    db.add_reminder(tutor_id, booking_id, remind_dt.strftime("%Y-%m-%d %H:%M"), "lesson_start")

    # Repetitorga bildirishnoma
    tutor_user = db.get_user_by_id(tutor_id)
    try:
        await callback.bot.send_message(
            tutor_user["telegram_id"],
            f"📅 *Yangi bron so'rovi!*\n\n"
            f"👨‍🎓 O'quvchi: {student['first_name']} {student['last_name']}\n"
            f"📚 Fan: {data['booking_subject']}\n"
            f"📆 Sana: {data['booking_date']}\n"
            f"⏰ Vaqt: {data['booking_time']}\n\n"
            f"Tasdiqlaysizmi?",
            reply_markup=Keyboards.booking_action_keyboard(booking_id),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Repetitorga xabar yuborishda xato: {e}")

    await callback.message.edit_text(
        f"✅ Bron so'rovingiz yuborildi!\n"
        f"Bron ID: #{booking_id}\n\n"
        f"Repetitor tasdiqlashini kuting.",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.clear()
    await callback.answer()


@main_router.callback_query(BookingSG.confirm, F.data == "cancel_booking")
async def cancel_booking_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bron bekor qilindi.")
    await callback.answer()


# Bronlarni ko'rish (o'quvchi)
@main_router.message(F.text == "📅 Bronlarim")
async def student_bookings(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "student":
        return
    bookings = db.get_student_bookings(user["id"])
    if not bookings:
        await message.answer("📭 Hali bronlaringiz yo'q.")
        return

    text = "📅 *Bronlaringiz:*\n\n"
    builder = InlineKeyboardBuilder()
    for b in bookings[:10]:
        status_emoji = {"pending": "⏳", "confirmed": "✅", "cancelled": "❌", "completed": "🏁"}.get(b["status"], "❓")
        text += f"{status_emoji} #{b['id']} | {b['subject']} | {b['lesson_date']} {b['lesson_time']}\n"
        if b["status"] == "completed":
            builder.button(
                text=f"⭐ #{b['id']} ga baho",
                callback_data=f"review_{b['tutor_id']}_bk{b['id']}"
            )
    builder.adjust(1)

    await message.answer(text, reply_markup=builder.as_markup() if builder.export() else None,
                         parse_mode=ParseMode.MARKDOWN)


# ─── REPETITOR HANDLERLARI ────────────────────────────────────────────────────

# Bron tasdiqlash
@main_router.callback_query(F.data.startswith("bk_confirm_"))
async def tutor_confirm_booking(callback: CallbackQuery):
    booking_id = int(callback.data[11:])
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer("Bron topilmadi!", show_alert=True)
        return

    db.update_booking_status(booking_id, "confirmed")

    # O'quvchiga bildirishnoma
    student = db.get_user_by_id(booking["student_id"])
    try:
        await callback.bot.send_message(
            student["telegram_id"],
            f"✅ *Broningiz tasdiqlandi!*\n\n"
            f"📚 Fan: {booking['subject']}\n"
            f"📆 Sana: {booking['lesson_date']}\n"
            f"⏰ Vaqt: {booking['lesson_time']}\n\n"
            f"Darsga tayyorlanib boring! 📖",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await callback.message.edit_text(
        f"✅ Bron #{booking_id} tasdiqlandi!\n"
        f"O'quvchiga bildirishnoma yuborildi."
    )
    await callback.answer("Tasdiqlandi!")


@main_router.callback_query(F.data.startswith("bk_cancel_"))
async def tutor_cancel_booking(callback: CallbackQuery):
    booking_id = int(callback.data[10:])
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer("Bron topilmadi!", show_alert=True)
        return

    db.update_booking_status(booking_id, "cancelled")
    student = db.get_user_by_id(booking["student_id"])
    try:
        await callback.bot.send_message(
            student["telegram_id"],
            f"❌ *Broningiz rad etildi.*\n"
            f"📚 Fan: {booking['subject']}\n"
            f"📆 Sana: {booking['lesson_date']}\n"
            f"Boshqa vaqt tanlashingiz mumkin.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await callback.message.edit_text(f"❌ Bron #{booking_id} rad etildi.")
    await callback.answer("Rad etildi!")


@main_router.callback_query(F.data.startswith("bk_reschedule_"))
async def tutor_reschedule(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data[14:])
    await state.update_data(reschedule_booking_id=booking_id)
    await callback.message.edit_text(
        "📆 Yangi sana kiriting (YYYY-MM-DD):"
    )
    await state.set_state(RescheduleOfferSG.new_date)
    await callback.answer()


@main_router.message(RescheduleOfferSG.new_date)
async def reschedule_new_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%Y-%m-%d")
        await state.update_data(reschedule_new_date=message.text.strip())
        await message.answer("⏰ Yangi vaqt kiriting (HH:MM):")
        await state.set_state(RescheduleOfferSG.new_time)
    except ValueError:
        await message.answer("⚠️ Format noto'g'ri! YYYY-MM-DD:")


@main_router.message(RescheduleOfferSG.new_time)
async def reschedule_new_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%H:%M")
        data = await state.get_data()
        booking_id = data["reschedule_booking_id"]
        new_date = data["reschedule_new_date"]
        new_time = message.text.strip()

        booking = db.get_booking(booking_id)
        db.update_booking_status(booking_id, "rescheduled")
        student = db.get_user_by_id(booking["student_id"])

        try:
            builder = InlineKeyboardBuilder()
            builder.button(text="✅ Qabul qilaman", callback_data=f"accept_reschedule_{booking_id}_{new_date}_{new_time}")
            builder.button(text="❌ Rad etaman", callback_data=f"reject_reschedule_{booking_id}")
            await message.bot.send_message(
                student["telegram_id"],
                f"🔄 *Repetitor yangi vaqt taklif qildi:*\n\n"
                f"📚 Fan: {booking['subject']}\n"
                f"📆 Yangi sana: {new_date}\n"
                f"⏰ Yangi vaqt: {new_time}\n\n"
                f"Qabul qilasizmi?",
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

        await message.answer(f"✅ Yangi vaqt taklifi yuborildi: {new_date} {new_time}")
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Format noto'g'ri! HH:MM:")


@main_router.callback_query(F.data.startswith("accept_reschedule_"))
async def accept_reschedule(callback: CallbackQuery):
    parts = callback.data.split("_")
    booking_id = int(parts[2])
    new_date = parts[3]
    new_time = parts[4]
    conn = db._get_conn()
    conn.execute(
        "UPDATE bookings SET lesson_date=?, lesson_time=?, status='confirmed' WHERE id=?",
        (new_date, new_time, booking_id)
    )
    conn.commit()
    conn.close()
    await callback.message.edit_text(
        f"✅ Yangi vaqt qabul qilindi!\n📆 {new_date} ⏰ {new_time}"
    )
    await callback.answer("Qabul qilindi!")


@main_router.callback_query(F.data.startswith("reject_reschedule_"))
async def reject_reschedule(callback: CallbackQuery):
    booking_id = int(callback.data.split("_")[2])
    db.update_booking_status(booking_id, "cancelled")
    await callback.message.edit_text("❌ Qayta rejalashtirish rad etildi.")
    await callback.answer()


# Repetitor bronlarini ko'rish
@main_router.message(F.text == "📋 Bronlar")
async def tutor_bookings(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "tutor":
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Kutilayotganlar", callback_data="tutor_bk_pending")
    builder.button(text="✅ Tasdiqlangan", callback_data="tutor_bk_confirmed")
    builder.button(text="📋 Barchasi", callback_data="tutor_bk_all")
    builder.adjust(2, 1)
    await message.answer("📋 Bronlar bo'limi:", reply_markup=builder.as_markup())


@main_router.callback_query(F.data.startswith("tutor_bk_"))
async def tutor_bookings_filter(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        return
    status = callback.data[9:]
    if status == "all":
        bookings = db.get_tutor_bookings(user["id"])
    else:
        bookings = db.get_tutor_bookings(user["id"], status)

    if not bookings:
        await callback.message.edit_text("📭 Bronlar topilmadi.")
        await callback.answer()
        return

    text = f"📋 *Bronlar ({status}):*\n\n"
    builder = InlineKeyboardBuilder()
    for b in bookings[:15]:
        emoji = {"pending": "⏳", "confirmed": "✅", "cancelled": "❌", "completed": "🏁"}.get(b["status"], "❓")
        text += (f"{emoji} #{b['id']} | {b['subject']}\n"
                 f"   👤 {b['student_fn']} {b['student_ln']}\n"
                 f"   📆 {b['lesson_date']} {b['lesson_time']}\n\n")
        if b["status"] == "confirmed":
            builder.button(
                text=f"✅ #{b['id']} Davomat",
                callback_data=f"mark_att_{b['id']}_{b['student_id']}"
            )
    builder.adjust(1)
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup() if builder.export() else None,
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


# O'quvchilar ro'yxati
@main_router.message(F.text == "👥 O'quvchilarim")
async def tutor_students(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "tutor":
        return
    students = db.get_all_students_of_tutor(user["id"])
    if not students:
        await message.answer("👥 Hali o'quvchilaringiz yo'q.")
        return

    text = "👥 *O'quvchilaringiz:*\n\n"
    for i, s in enumerate(students, 1):
        text += f"{i}. {s['first_name']} {s['last_name']} | 📞 {s.get('phone','—')}\n"
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


# Davomat belgilash
@main_router.callback_query(F.data.startswith("mark_att_"))
async def mark_attendance(callback: CallbackQuery):
    parts = callback.data.split("_")
    booking_id = int(parts[2])
    student_id = int(parts[3])
    await callback.message.edit_text(
        "✅ Davomat belgisi:",
        reply_markup=Keyboards.attendance_keyboard(booking_id, student_id)
    )
    await callback.answer()


@main_router.callback_query(F.data.startswith("att_"))
async def process_attendance(callback: CallbackQuery):
    parts = callback.data.split("_")
    status = parts[1]
    booking_id = int(parts[2])
    student_id = int(parts[3])

    booking = db.get_booking(booking_id)
    tutor = db.get_user(callback.from_user.id)

    db.mark_attendance(booking_id, student_id, tutor["id"], status)
    db.update_booking_status(booking_id, "completed")

    status_text = {"present": "✅ Keldi", "absent": "❌ Kelmadi",
                   "late": "⏰ Kech keldi", "excused": "📋 Uzrli"}[status]

    # O'quvchiga bildirishnoma
    student = db.get_user_by_id(student_id)
    try:
        await callback.bot.send_message(
            student["telegram_id"],
            f"📋 Davomat belgilandi: *{status_text}*\n"
            f"📆 {booking['lesson_date']} {booking['lesson_time']}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await callback.message.edit_text(f"✅ Davomat belgilandi: {status_text}")
    await callback.answer()


# ─── UY VAZIFALARI ────────────────────────────────────────────────────────────

@main_router.message(F.text == "📝 Vazifa berish")
async def tutor_hw_menu(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "tutor":
        return
    students = db.get_all_students_of_tutor(user["id"])
    if not students:
        await message.answer("👥 Hali o'quvchilaringiz yo'q.")
        return

    builder = InlineKeyboardBuilder()
    for s in students:
        builder.button(
            text=f"{s['first_name']} {s['last_name']}",
            callback_data=f"hw_student_{s['id']}"
        )
    builder.adjust(1)
    await message.answer("👤 O'quvchini tanlang:", reply_markup=builder.as_markup())
    await state.set_state(HomeworkSG.select_student)


@main_router.callback_query(HomeworkSG.select_student, F.data.startswith("hw_student_"))
async def hw_select_student(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data[11:])
    await state.update_data(hw_student_id=student_id)
    await callback.message.edit_text("📝 Vazifa sarlavhasini kiriting:")
    await state.set_state(HomeworkSG.title)
    await callback.answer()


@main_router.message(HomeworkSG.title)
async def hw_title(message: Message, state: FSMContext):
    await state.update_data(hw_title=message.text.strip())
    await message.answer("📋 Vazifa matnini/tavsifini kiriting:")
    await state.set_state(HomeworkSG.description)


@main_router.message(HomeworkSG.description)
async def hw_description(message: Message, state: FSMContext):
    await state.update_data(hw_description=message.text.strip())
    await message.answer(
        "📅 Topshirish muddatini kiriting (YYYY-MM-DD):\n"
        "Yoki /skip kiriting:"
    )
    await state.set_state(HomeworkSG.deadline)


@main_router.message(HomeworkSG.deadline)
async def hw_deadline(message: Message, state: FSMContext):
    deadline = None if message.text == "/skip" else message.text.strip()
    data = await state.get_data()
    tutor = db.get_user(message.from_user.id)
    student = db.get_user_by_id(data["hw_student_id"])

    hw_id = db.create_homework(
        tutor["id"], data["hw_student_id"],
        data["hw_title"], data["hw_description"],
        "Umumiy", deadline
    )

    # O'quvchiga bildirishnoma
    try:
        builder = InlineKeyboardBuilder()
        builder.button(text="📤 Javob yuborish", callback_data=f"submit_hw_{hw_id}")
        await message.bot.send_message(
            student["telegram_id"],
            f"📝 *Yangi uy vazifasi!*\n\n"
            f"📌 Sarlavha: {data['hw_title']}\n"
            f"📋 Tavsif: {data['hw_description']}\n"
            f"📅 Muddat: {deadline or 'Korsatilmagan'}\n\n"
            f"👨‍🏫 Repetitor: {tutor['first_name']} {tutor['last_name']}",
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await message.answer(
        f"✅ Vazifa #{hw_id} o'quvchiga yuborildi!",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.clear()


# O'quvchi uy vazifalari
@main_router.message(F.text == "📝 Uy vazifalari")
async def student_homeworks(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return
    hws = db.get_student_homeworks(user["id"])
    if not hws:
        await message.answer("📭 Hali uy vazifalari yo'q.")
        return

    text = "📝 *Uy vazifalari:*\n\n"
    builder = InlineKeyboardBuilder()
    for hw in hws[:10]:
        status_emoji = {"pending": "⏳", "submitted": "📤", "checked": "✅", "overdue": "⚠️"}.get(hw["status"], "❓")
        text += (f"{status_emoji} *{hw['title']}*\n"
                 f"   📆 Muddat: {hw.get('deadline','—')}\n"
                 f"   👨‍🏫 {hw['tutor_fn']} {hw['tutor_ln']}\n\n")
        if hw["status"] == "pending":
            builder.button(text=f"📤 #{hw['id']} Javob", callback_data=f"submit_hw_{hw['id']}")
        if hw["status"] == "checked" and hw.get("grade"):
            text += f"   💯 Baho: {hw['grade']}/10 | 💬 {hw.get('tutor_feedback','')}\n\n"
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup() if builder.export() else None,
                         parse_mode=ParseMode.MARKDOWN)


@main_router.callback_query(F.data.startswith("submit_hw_"))
async def submit_hw_prompt(callback: CallbackQuery, state: FSMContext):
    hw_id = int(callback.data[10:])
    await state.update_data(submit_hw_id=hw_id)
    await callback.message.answer("📤 Javobingizni yozing:")
    await callback.answer()


# ─── TESTLAR ─────────────────────────────────────────────────────────────────

@main_router.message(F.text == "📊 Test yaratish")
async def tutor_create_test(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "tutor":
        return
    await message.answer("📊 Test sarlavhasini kiriting:")
    await state.set_state(TestSG.title)


@main_router.message(TestSG.title)
async def test_title(message: Message, state: FSMContext):
    await state.update_data(test_title=message.text.strip(), test_questions=[])
    await message.answer("📚 Test fani (masalan: Matematika):")
    await state.set_state(TestSG.subject)


@main_router.message(TestSG.subject)
async def test_subject(message: Message, state: FSMContext):
    await state.update_data(test_subject=message.text.strip())
    await message.answer("❓ Savol matnini kiriting:")
    await state.set_state(TestSG.question_text)


@main_router.message(TestSG.question_text)
async def test_question(message: Message, state: FSMContext):
    await state.update_data(current_question=message.text.strip())
    await message.answer("A) variantni kiriting:")
    await state.set_state(TestSG.option_a)


@main_router.message(TestSG.option_a)
async def test_opt_a(message: Message, state: FSMContext):
    await state.update_data(opt_a=message.text.strip())
    await message.answer("B) variantni kiriting:")
    await state.set_state(TestSG.option_b)


@main_router.message(TestSG.option_b)
async def test_opt_b(message: Message, state: FSMContext):
    await state.update_data(opt_b=message.text.strip())
    await message.answer("C) variantni kiriting:")
    await state.set_state(TestSG.option_c)


@main_router.message(TestSG.option_c)
async def test_opt_c(message: Message, state: FSMContext):
    await state.update_data(opt_c=message.text.strip())
    await message.answer("D) variantni kiriting:")
    await state.set_state(TestSG.option_d)


@main_router.message(TestSG.option_d)
async def test_opt_d(message: Message, state: FSMContext):
    await state.update_data(opt_d=message.text.strip())
    builder = InlineKeyboardBuilder()
    for opt in ["A", "B", "C", "D"]:
        builder.button(text=opt, callback_data=f"correct_{opt}")
    builder.adjust(4)
    await message.answer("✅ To'g'ri javobni tanlang:", reply_markup=builder.as_markup())
    await state.set_state(TestSG.correct)


@main_router.callback_query(TestSG.correct, F.data.startswith("correct_"))
async def test_correct(callback: CallbackQuery, state: FSMContext):
    correct = callback.data[8:]
    data = await state.get_data()
    questions = data.get("test_questions", [])
    questions.append({
        "question": data["current_question"],
        "a": data["opt_a"],
        "b": data["opt_b"],
        "c": data["opt_c"],
        "d": data["opt_d"],
        "correct": correct
    })
    await state.update_data(test_questions=questions)

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yana savol qo'shish", callback_data="add_more_q")
    builder.button(text="✅ Testni yakunlash", callback_data="finish_test")
    builder.adjust(1)
    await callback.message.edit_text(
        f"✅ Savol qo'shildi! Jami: {len(questions)} ta savol.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@main_router.callback_query(F.data == "add_more_q")
async def add_more_question(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❓ Keyingi savol matnini kiriting:")
    await state.set_state(TestSG.question_text)
    await callback.answer()


@main_router.callback_query(F.data == "finish_test")
async def finish_test(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tutor = db.get_user(callback.from_user.id)
    questions = data.get("test_questions", [])

    if not questions:
        await callback.answer("⚠️ Kamida 1 ta savol kerak!", show_alert=True)
        return

    test_id = db.create_test(tutor["id"], data["test_title"], data["test_subject"])
    for q in questions:
        db.add_question(test_id, q["question"], q["a"], q["b"], q["c"], q["d"], q["correct"])

    await callback.message.edit_text(
        f"✅ Test yaratildi!\n"
        f"📊 *{data['test_title']}*\n"
        f"📚 Fan: {data['test_subject']}\n"
        f"❓ Savollar: {len(questions)} ta\n"
        f"🆔 Test ID: #{test_id}",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.clear()
    await callback.answer()


# O'quvchi uchun testlar
@main_router.message(F.text == "📊 Testlar")
async def student_tests(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return
    # Repetitorlarning testlarini ko'rsatish
    conn = db._get_conn()
    rows = conn.execute(
        "SELECT t.*, COUNT(tq.id) as question_count FROM tests t "
        "LEFT JOIN test_questions tq ON t.id=tq.test_id "
        "WHERE t.is_active=1 GROUP BY t.id ORDER BY t.created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    tests = [dict(r) for r in rows]

    if not tests:
        await message.answer("📭 Hali testlar yo'q.")
        return

    await message.answer(
        "📊 *Mavjud testlar:*\nBirini tanlang:",
        reply_markup=Keyboards.test_list_keyboard(tests),
        parse_mode=ParseMode.MARKDOWN
    )


@main_router.callback_query(F.data.startswith("take_test_"))
async def take_test(callback: CallbackQuery, state: FSMContext):
    test_id = int(callback.data[10:])
    questions = db.get_test_questions(test_id)
    test = db.get_test(test_id)

    if not questions:
        await callback.answer("Bu testda savollar yo'q!", show_alert=True)
        return

    await state.update_data(
        active_test_id=test_id,
        test_questions_list=[q["id"] for q in questions],
        test_current_idx=0,
        test_answers={},
        test_total=len(questions)
    )

    await _send_test_question(callback.message, state, questions[0])
    await callback.answer()


async def _send_test_question(message, state: FSMContext, question: Dict):
    data = await state.get_data()
    idx = data["test_current_idx"] + 1
    total = data["test_total"]

    text = (
        f"❓ *Savol {idx}/{total}*\n\n"
        f"{question['question_text']}\n\n"
        f"A) {question['option_a']}\n"
        f"B) {question['option_b']}\n"
        f"C) {question['option_c']}\n"
        f"D) {question['option_d']}"
    )

    builder = InlineKeyboardBuilder()
    for opt in ["A", "B", "C", "D"]:
        builder.button(text=opt, callback_data=f"ans_{data['active_test_id']}_{question['id']}_{opt}")
    builder.adjust(4)

    try:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)


@main_router.callback_query(F.data.startswith("ans_"))
async def process_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    test_id = int(parts[1])
    q_id = int(parts[2])
    answer = parts[3]

    data = await state.get_data()
    if data.get("active_test_id") != test_id:
        await callback.answer("Test topilmadi!", show_alert=True)
        return

    answers = data.get("test_answers", {})
    answers[str(q_id)] = answer
    current_idx = data["test_current_idx"] + 1
    await state.update_data(test_answers=answers, test_current_idx=current_idx)

    questions_ids = data["test_questions_list"]
    if current_idx < len(questions_ids):
        conn = db._get_conn()
        next_q = conn.execute("SELECT * FROM test_questions WHERE id=?", (questions_ids[current_idx],)).fetchone()
        conn.close()
        if next_q:
            await _send_test_question(callback.message, state, dict(next_q))
    else:
        # Test tugadi - natijalarni hisoblash
        questions = db.get_test_questions(test_id)
        score = 0
        result_text = f"📊 *Test natijalari:*\n\n"
        for q in questions:
            user_ans = answers.get(str(q["id"]), "")
            correct = q["correct_option"]
            if user_ans == correct:
                score += 1
                result_text += f"✅ {q['question_text'][:30]}...\n"
            else:
                result_text += f"❌ {q['question_text'][:30]}...\n   To'g'ri: {correct}\n"

        total = len(questions)
        pct = round(score / total * 100, 1) if total > 0 else 0
        result_text += f"\n🎯 *Natija: {score}/{total} ({pct}%)*"

        if pct >= 90:
            result_text += "\n🏆 Ajoyib natija!"
        elif pct >= 70:
            result_text += "\n👍 Yaxshi natija!"
        elif pct >= 50:
            result_text += "\n📚 Ko'proq o'qish kerak."
        else:
            result_text += "\n💪 Qaytadan o'rganing!"

        user = db.get_user(callback.from_user.id)
        db.save_test_result(test_id, user["id"], score, total)

        await callback.message.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
        await state.clear()

    await callback.answer()


# ─── TO'LOVLAR ───────────────────────────────────────────────────────────────

@main_router.message(F.text == "💰 To'lovlar")
async def payments_menu(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return

    if user["role"] == "tutor":
        payments = db.get_tutor_payments(user["id"])
        text = "💰 *To'lovlar (Repetitor):*\n\n"
        builder = InlineKeyboardBuilder()
        total_paid = 0
        total_pending = 0
        for p in payments[:15]:
            emoji = {"paid": "✅", "pending": "⏳", "overdue": "⚠️"}.get(p["status"], "❓")
            text += (f"{emoji} {p['student_fn']} {p['student_ln']}\n"
                     f"   💵 {p['amount']:,.0f} so'm | {p['status']}\n"
                     f"   📋 {p.get('description','')}\n\n")
            if p["status"] == "pending":
                total_pending += p["amount"]
                builder.button(text=f"✅ #{p['id']} To'landi", callback_data=f"pay_done_{p['id']}")
            elif p["status"] == "paid":
                total_paid += p["amount"]
        builder.adjust(1)
        text += f"📊 Jami to'langan: *{total_paid:,.0f}* so'm\n"
        text += f"⏳ Kutilayotgan: *{total_pending:,.0f}* so'm"
        await message.answer(text, reply_markup=builder.as_markup() if builder.export() else None,
                             parse_mode=ParseMode.MARKDOWN)

    else:  # student
        payments = db.get_student_payments(user["id"])
        text = "💰 *To'lovlarim:*\n\n"
        for p in payments[:15]:
            emoji = {"paid": "✅", "pending": "⏳", "overdue": "⚠️"}.get(p["status"], "❓")
            text += (f"{emoji} {p['tutor_fn']} {p['tutor_ln']}\n"
                     f"   💵 {p['amount']:,.0f} so'm | {p['status']}\n"
                     f"   📋 {p.get('description','')}\n\n")
        await message.answer(text if payments else "📭 To'lovlar yo'q.", parse_mode=ParseMode.MARKDOWN)


@main_router.callback_query(F.data.startswith("pay_done_"))
async def mark_paid(callback: CallbackQuery):
    payment_id = int(callback.data[9:])
    db.mark_payment_paid(payment_id)
    await callback.message.edit_text(f"✅ To'lov #{payment_id} tasdiqlandi!")
    await callback.answer("To'landi!")


# To'lov yaratish (repetitor uchun)
@main_router.message(F.text == "💳 To'lov yaratish")
async def create_payment_menu(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "tutor":
        return
    students = db.get_all_students_of_tutor(user["id"])
    if not students:
        await message.answer("👥 Hali o'quvchilaringiz yo'q.")
        return

    builder = InlineKeyboardBuilder()
    for s in students:
        builder.button(
            text=f"{s['first_name']} {s['last_name']}",
            callback_data=f"pay_student_{s['id']}"
        )
    builder.adjust(1)
    await message.answer("👤 O'quvchini tanlang:", reply_markup=builder.as_markup())
    await state.set_state(PaymentSG.select_student)


@main_router.callback_query(PaymentSG.select_student, F.data.startswith("pay_student_"))
async def payment_student(callback: CallbackQuery, state: FSMContext):
    student_id = int(callback.data[12:])
    await state.update_data(payment_student_id=student_id)
    await callback.message.edit_text("💵 To'lov miqdorini kiriting (so'mda):")
    await state.set_state(PaymentSG.amount)
    await callback.answer()


@main_router.message(PaymentSG.amount)
async def payment_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "").replace(" ", ""))
        await state.update_data(payment_amount=amount)
        await message.answer("📋 To'lov tavsifi (masalan: Iyun oyi uchun):")
        await state.set_state(PaymentSG.description)
    except ValueError:
        await message.answer("⚠️ Raqam kiriting:")


@main_router.message(PaymentSG.description)
async def payment_description(message: Message, state: FSMContext):
    data = await state.get_data()
    tutor = db.get_user(message.from_user.id)
    student = db.get_user_by_id(data["payment_student_id"])

    pid = db.create_payment(
        data["payment_student_id"], tutor["id"],
        data["payment_amount"], message.text.strip()
    )

    try:
        await message.bot.send_message(
            student["telegram_id"],
            f"💰 *Yangi to'lov hisob-fakturasi!*\n\n"
            f"💵 Miqdor: {data['payment_amount']:,.0f} so'm\n"
            f"📋 Tavsif: {message.text.strip()}\n"
            f"👨‍🏫 Repetitor: {tutor['first_name']} {tutor['last_name']}\n\n"
            f"Iltimos, o'z vaqtida to'lang!",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await message.answer(f"✅ To'lov #{pid} yaratildi va o'quvchiga yuborildi!")
    await state.clear()


# ─── SHARH / REYTING ─────────────────────────────────────────────────────────

@main_router.callback_query(F.data.startswith("review_"))
async def start_review(callback: CallbackQuery, state: FSMContext):
    parts = callback.data[7:].split("_bk")
    tutor_id = int(parts[0])
    booking_id = int(parts[1]) if len(parts) > 1 else None

    user = db.get_user(callback.from_user.id)
    if not user or user["role"] != "student":
        await callback.answer("Faqat o'quvchilar baho bera oladi!", show_alert=True)
        return

    await state.update_data(review_tutor_id=tutor_id, review_booking_id=booking_id)
    await callback.message.answer(
        "⭐ Repetitorga qancha yulduz berasiz?",
        reply_markup=Keyboards.rating_keyboard()
    )
    await state.set_state(ReviewSG.rating)
    await callback.answer()


@main_router.callback_query(ReviewSG.rating, F.data.startswith("rating_"))
async def review_rating(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data[7:])
    await state.update_data(review_rating=rating)
    await callback.message.edit_text(
        f"{'⭐' * rating}\n\nIzoh qoldiring (yoki /skip):"
    )
    await state.set_state(ReviewSG.comment)
    await callback.answer()


@main_router.message(ReviewSG.comment)
async def review_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    comment = "" if message.text == "/skip" else message.text.strip()
    user = db.get_user(message.from_user.id)

    db.add_review(
        data["review_tutor_id"], user["id"],
        data["review_rating"], comment,
        data.get("review_booking_id")
    )

    tutor = db.get_user_by_id(data["review_tutor_id"])
    try:
        await message.bot.send_message(
            tutor["telegram_id"],
            f"⭐ *Yangi sharh keldi!*\n\n"
            f"{'⭐' * data['review_rating']}\n"
            f"💬 {comment or 'Izohsiz'}\n"
            f"👤 {user['first_name']} {user['last_name']}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await message.answer(
        f"✅ Rahmat! {'⭐' * data['review_rating']} bahongiz qabul qilindi.",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.clear()


# ─── STATISTIKA ───────────────────────────────────────────────────────────────

@main_router.message(F.text == "📈 Statistika")
async def statistics(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return

    if user["role"] == "tutor":
        stats = db.get_tutor_stats(user["id"])
        text = (
            f"📈 *Statistikangiz:*\n\n"
            f"📅 Jami bronlar: {stats['total_bookings']}\n"
            f"✅ Tasdiqlangan: {stats['confirmed']}\n"
            f"👥 O'quvchilar: {stats['unique_students']}\n"
            f"💰 Jami daromad: {stats.get('total_income', 0):,.0f} so'm\n"
            f"⏳ Kutilayotgan: {stats.get('pending_income', 0):,.0f} so'm\n"
            f"⭐ Reyting: {stats.get('rating', 0)} ({stats.get('total_reviews', 0)} sharh)"
        )

        # Top o'quvchilar
        top = db.get_top_students(user["id"], 5)
        if top:
            text += "\n\n🏆 *Top o'quvchilar:*\n"
            for i, s in enumerate(top, 1):
                text += f"{i}. {s['first_name']} {s['last_name']} — {round(s['avg_score'] or 0, 1)}%\n"

    else:
        stats = db.get_student_stats(user["id"])
        text = (
            f"📈 *Mening statistikam:*\n\n"
            f"📅 Jami darslar: {stats['total_lessons']}\n"
            f"✅ Qatnashganlar: {stats['attended']}\n"
            f"❌ Qatnashmagan: {stats['absent']}\n"
            f"📝 Uy vazifalari: {stats['total_hw']} ta\n"
            f"📤 Topshirilgan: {stats['submitted_hw']} ta\n"
            f"📊 O'rtacha test natijasi: {stats['avg_test_score']}%"
        )

    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


# Oylik hisobot
@main_router.message(F.text == "📄 Hisobot")
async def monthly_report(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] != "tutor":
        return

    now = datetime.now()
    report = db.get_monthly_report(user["id"], now.year, now.month)
    text = (
        f"📄 *{now.strftime('%B %Y')} hisoboti:*\n\n"
        f"📅 Jami darslar: {report['total_lessons']}\n"
        f"✅ Qatnashdi: {report['present_count']}\n"
        f"❌ Qatnashmadi: {report['absent_count']}\n"
        f"💰 Jami daromad: {report['income']:,.0f} so'm"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


# ─── REFERAL TIZIMI ──────────────────────────────────────────────────────────

@main_router.message(F.text == "🔗 Referal")
async def referral_info(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return
    bot_info = await message.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={user['referral_code']}"
    conn = db._get_conn()
    count = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE referred_by=?", (user["id"],)).fetchone()["cnt"]
    conn.close()
    await message.answer(
        f"🔗 *Referal tizimi*\n\n"
        f"Sizning havolangiz:\n`{link}`\n\n"
        f"👥 Taklif qilganlaringiz: {count} kishi\n"
        f"🎁 Bonus darslar: {user.get('bonus_lessons', 0)} ta\n\n"
        f"Har bir do'stingiz ro'yxatdan o'tsa, ikkalangiz ham bonus dars olasiz!",
        parse_mode=ParseMode.MARKDOWN
    )


# ─── PROFIL ──────────────────────────────────────────────────────────────────

@main_router.message(F.text.in_(["👤 Profil", "👤 Profilim"]))
async def view_profile(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return

    if user["role"] == "tutor":
        tp = db.get_tutor_profile(user["id"])
        if tp:
            text = Texts.tutor_profile(tp, user)
        else:
            text = f"👨‍🏫 *{user['first_name']} {user['last_name']}*\nProfil to'ldirilmagan."
    else:
        text = (
            f"👤 *{user['first_name']} {user['last_name']}*\n\n"
            f"📱 Telefon: {user.get('phone','—')}\n"
            f"📅 Ro'yxatdan o'tgan: {user.get('created_at','—')}\n"
            f"🔗 Referal kodi: `{user.get('referral_code','—')}`"
        )

    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


# ─── ADMIN HANDLERLARI ────────────────────────────────────────────────────────

@main_router.message(F.text == "👥 Foydalanuvchilar")
async def admin_users(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = db._get_conn()
    total = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    students = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE role='student'").fetchone()["cnt"]
    tutors = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE role='tutor'").fetchone()["cnt"]
    conn.close()
    await message.answer(
        f"👥 *Foydalanuvchilar statistikasi:*\n\n"
        f"📊 Jami: {total}\n"
        f"👨‍🎓 O'quvchilar: {students}\n"
        f"👨‍🏫 Repetitorlar: {tutors}",
        parse_mode=ParseMode.MARKDOWN
    )


@main_router.message(F.text == "📊 Umumiy statistika")
async def admin_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = db._get_conn()
    bookings = conn.execute("SELECT COUNT(*) as cnt FROM bookings").fetchone()["cnt"]
    income = conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM payments WHERE status='paid'").fetchone()["total"]
    tests = conn.execute("SELECT COUNT(*) as cnt FROM tests").fetchone()["cnt"]
    hws = conn.execute("SELECT COUNT(*) as cnt FROM homeworks").fetchone()["cnt"]
    conn.close()
    await message.answer(
        f"📊 *Umumiy statistika:*\n\n"
        f"📅 Jami bronlar: {bookings}\n"
        f"💰 Jami daromad: {income:,.0f} so'm\n"
        f"📊 Testlar: {tests}\n"
        f"📝 Vazifalar: {hws}",
        parse_mode=ParseMode.MARKDOWN
    )


@main_router.message(F.text == "🎟️ Promo kodlar")
async def admin_promo(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yangi promo kod", callback_data="create_promo")
    builder.button(text="📋 Barcha kodlar", callback_data="list_promos")
    builder.adjust(1)
    await message.answer("🎟️ Promo kodlar:", reply_markup=builder.as_markup())


@main_router.callback_query(F.data == "create_promo")
async def create_promo_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text("🎟️ Promo kod kiriting (masalan: YANGI2025):")
    await state.set_state(PromoSG.code)
    await callback.answer()


@main_router.message(PromoSG.code)
async def promo_code(message: Message, state: FSMContext):
    await state.update_data(promo_code=message.text.strip().upper())
    await message.answer("💯 Chegirma foizini kiriting (masalan: 20):")
    await state.set_state(PromoSG.discount)


@main_router.message(PromoSG.discount)
async def promo_discount(message: Message, state: FSMContext):
    try:
        disc = float(message.text.strip())
        await state.update_data(promo_discount=disc)
        await message.answer("📅 Muddatini kiriting (YYYY-MM-DD) yoki /skip:")
        await state.set_state(PromoSG.expiry)
    except ValueError:
        await message.answer("Raqam kiriting:")


@main_router.message(PromoSG.expiry)
async def promo_expiry(message: Message, state: FSMContext):
    expiry = None if message.text == "/skip" else message.text.strip()
    data = await state.get_data()
    user = db.get_user(message.from_user.id)
    success = db.create_promo(data["promo_code"], data["promo_discount"], 100, expiry, user["id"])
    if success:
        await message.answer(
            f"✅ Promo kod yaratildi!\n"
            f"🎟️ Kod: *{data['promo_code']}*\n"
            f"💯 Chegirma: {data['promo_discount']}%",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer("⚠️ Bu kod allaqachon mavjud!")
    await state.clear()


@main_router.callback_query(F.data == "list_promos")
async def list_promos(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    conn = db._get_conn()
    rows = conn.execute("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 20").fetchall()
    conn.close()
    if not rows:
        await callback.message.edit_text("📭 Hali promo kodlar yo'q.")
        return
    text = "🎟️ *Promo kodlar:*\n\n"
    for p in rows:
        status = "✅" if p["is_active"] else "❌"
        text += (f"{status} *{p['code']}* — {p['discount_percent']}%\n"
                 f"   Ishlatildi: {p['used_count']}/{p['usage_limit']}\n"
                 f"   Muddat: {p.get('expiry_date','Cheksiz')}\n\n")
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


# Ommaviy xabar yuborish (admin)
@main_router.message(F.text == "📢 Xabar yuborish")
async def admin_broadcast(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("📢 Xabar matnini yozing (barcha foydalanuvchilarga yuboriladi):")


# Ota-ona paneli
@main_router.message(Command("parent"))
async def parent_panel(message: Message):
    students = db.get_parent_students(message.from_user.id)
    if not students:
        await message.answer(
            "👨‍👩‍👧 Ota-ona paneli\n\n"
            "Farzandingizni ulash uchun:\n"
            "Farzandingiz botda /myid buyrug'ini ishlating,\n"
            "keyin ID ni shu yerga yuboring."
        )
        return
    text = "👨‍👩‍👧 *Farzandlarim:*\n\n"
    builder = InlineKeyboardBuilder()
    for s in students:
        text += f"👤 {s['first_name']} {s['last_name']}\n"
        builder.button(
            text=f"📊 {s['first_name']} statistikasi",
            callback_data=f"parent_stats_{s['id']}"
        )
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)


@main_router.callback_query(F.data.startswith("parent_stats_"))
async def parent_student_stats(callback: CallbackQuery):
    student_id = int(callback.data[13:])
    stats = db.get_student_stats(student_id)
    student = db.get_user_by_id(student_id)
    text = (
        f"📊 *{student['first_name']} {student['last_name']} statistikasi:*\n\n"
        f"📅 Jami darslar: {stats['total_lessons']}\n"
        f"✅ Qatnashgan: {stats['attended']}\n"
        f"❌ Qatnashmagan: {stats['absent']}\n"
        f"📝 Uy vazifalari: {stats['total_hw']} ta\n"
        f"📤 Topshirilgan: {stats['submitted_hw']} ta\n"
        f"📊 O'rtacha test: {stats['avg_test_score']}%"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@main_router.message(Command("myid"))
async def my_id(message: Message):
    user = db.get_user(message.from_user.id)
    if user:
        await message.answer(
            f"🆔 Sizning ID raqamingiz: `{user['id']}`\n\n"
            f"Ota-onangizga shu IDni yubering.",
            parse_mode=ParseMode.MARKDOWN
        )


# Orqaga navigatsiya
@main_router.callback_query(F.data == "back_subjects")
async def back_to_subjects(callback: CallbackQuery):
    await callback.message.edit_text(
        "📚 Qaysi fanda repetitor qidirmoqchisiz?",
        reply_markup=Keyboards.subjects_select_keyboard()
    )
    await callback.answer()


@main_router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user:
        await callback.message.edit_text("🏠 Asosiy menyu")
    await callback.answer()


# ─── REMINDER TASK ────────────────────────────────────────────────────────────
async def reminder_task(bot: Bot):
    """Eslatmalar yuborish - har 60 soniyada tekshiradi"""
    while True:
        try:
            reminders = db.get_pending_reminders()
            for r in reminders:
                user = db.get_user_by_id(r["user_id"])
                if not user:
                    continue
                booking = db.get_booking(r["booking_id"]) if r.get("booking_id") else None
                try:
                    text = (
                        f"⏰ *Eslatma!*\n\n"
                        f"📅 30 daqiqadan so'ng dars boshlanadi!\n"
                    )
                    if booking:
                        text += (f"📚 Fan: {booking['subject']}\n"
                                 f"📆 Sana: {booking['lesson_date']}\n"
                                 f"⏰ Vaqt: {booking['lesson_time']}")
                    await bot.send_message(user["telegram_id"], text, parse_mode=ParseMode.MARKDOWN)
                    db.mark_reminder_sent(r["id"])
                except (TelegramForbiddenError, TelegramBadRequest):
                    db.mark_reminder_sent(r["id"])
                except Exception as e:
                    logger.error(f"Reminder yuborishda xato: {e}")
        except Exception as e:
            logger.error(f"Reminder task xatosi: {e}")
        await asyncio.sleep(60)


# ─── XATO HANDLERLARI ────────────────────────────────────────────────────────
@main_router.errors()
async def error_handler(event, exception: Exception):
    logger.error(f"Xato yuz berdi: {type(exception).__name__}: {exception}")
    if hasattr(event, "message") and event.message:
        try:
            await event.message.answer(
                "⚠️ Xato yuz berdi. Iltimos, qaytadan urinib ko'ring.\n"
                "Muammo davom etsa /start bosing."
            )
        except Exception:
            pass
    return True


# ─── ASOSIY FUNKSIYA ─────────────────────────────────────────────────────────
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="myid", description="Mening ID raqamim"),
        BotCommand(command="parent", description="Ota-ona paneli"),
    ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN muhit o'zgaruvchisi o'rnatilmagan!")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(main_router)

    await set_commands(bot)
    logger.info("RepetitorBot ishga tushdi! 🚀")

    # Reminder taskni polling bilan birga ishga tushirish
    async def on_startup(bot: Bot):
        asyncio.create_task(reminder_task(bot))

    dp.startup.register(on_startup)

    # Bot polling
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())