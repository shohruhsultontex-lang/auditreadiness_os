import sqlite3
import bcrypt
import os

DB_PATH = os.path.join("data", "app.db")

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Foydalanuvchilar (Users) jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            factory_name TEXT NOT NULL,
            role TEXT NOT NULL, -- 'super_admin', 'factory_admin', 'department_user'
            is_verified INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # CAP (Corrective Action Plan) Tasks jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cap_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factory_name TEXT NOT NULL,
            department TEXT NOT NULL,
            title TEXT NOT NULL,
            standard TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING', -- 'PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED'
            risk_level TEXT DEFAULT 'MEDIUM', -- 'ZERO_TOLERANCE', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
            responsible TEXT,
            due_date TEXT,
            evidence_image TEXT,
            consultant_comment TEXT
        )
    ''')

    conn.commit()
    conn.close()

def create_user(email, password, full_name, factory_name, role):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    salt = bcrypt.gensalt()
    pwd_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    try:
        cursor.execute('''
            INSERT INTO users (email, password_hash, full_name, factory_name, role, is_verified)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (email, pwd_hash, full_name, factory_name, role))
        conn.commit()
        return True, "Foydalanuvchi muvaffaqiyatli yaratildi!"
    except sqlite3.IntegrityError:
        return False, "Bu email pochtasi bilan foydalanuvchi allaqachon mavjud!"
    finally:
        conn.close()

def verify_login(email, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, full_name, factory_name, role FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()

    if user and bcrypt.checkpw(password.encode('utf-8'), user[1].encode('utf-8')):
        return {
            "id": user[0],
            "email": email,
            "full_name": user[2],
            "factory_name": user[3],
            "role": user[4]
        }
    return None

if __name__ == "__main__":
    init_db()
    # Dastlabki Super Admin yaratish
    success, msg = create_user("admin@auditreadiness.uz", "Admin123!@#", "Shohruh Shuxratov", "Consulting HQ", "super_admin")
    print(msg)
import streamlit as st
from database import verify_login, create_user

# Sahifa sozlamalari
st.set_page_config(
    page_title="AuditReadiness OS",
    page_icon="🛡️",
    layout="wide"
)

# Session state ni initsializasiya qilish
if "user" not in st.session_state:
    st.session_state.user = None

# Custom CSS uslublari (soddalashtirilgan ko'rinishda)
st.markdown("", unsafe_allow_html=True)

# LOGIN OYNASI
def login_page():
    st.markdown("