import os
import bcrypt
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# ==========================================
# 1. BAZA ULANISHI
# ==========================================
def get_db_engine():
    if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
        db_url = st.secrets["postgres"]["url"]
        if "postgresql+psycopg://" in db_url:
            db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
            
        try:
            temp_engine = create_engine(
                db_url,
                connect_args={"connect_timeout": 5},
                pool_pre_ping=True,
                pool_recycle=300
            )
            with temp_engine.connect() as conn:
                pass
            return temp_engine
        except Exception:
            pass # Xatolik bo'lsa ekranga hech narsa chiqarmaydi
            
    return create_engine("sqlite:///data/app.db", connect_args={"check_same_thread": False})

engine = get_db_engine()
UPLOAD_DIR = "uploads"
LOGO_PATH = "logo.png"

def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                factory_name TEXT NOT NULL,
                role TEXT NOT NULL,
                is_verified INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_tasks (
                id SERIAL PRIMARY KEY,
                factory_name TEXT NOT NULL,
                cert_code TEXT NOT NULL,
                task_title TEXT NOT NULL,
                assigned_role TEXT NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                file_evidence TEXT,
                comment TEXT
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_certificates (
                cert_code TEXT PRIMARY KEY,
                cert_name TEXT NOT NULL
            );
        """))

        result = conn.execute(text("SELECT COUNT(*) FROM custom_certificates")).fetchone()
        if result[0] == 0:
            default_certs = [
                {"code": "BSCI", "name": "Amfori BSCI Social Audit"},
                {"code": "SMETA", "name": "SEDEX SMETA 4-Pillar Audit"},
                {"code": "GOTS", "name": "Global Organic Textile Standard"},
                {"code": "OEKO-TEX", "name": "OEKO-TEX Standard 100"},
                {"code": "ISO 45001", "name": "ISO 45001 Safety Management"}
            ]
            for cert in default_certs:
                conn.execute(text("INSERT INTO custom_certificates (cert_code, cert_name) VALUES (:code, :name)"), cert)

def create_user_if_not_exists(email, password, full_name, factory_name, role):
    with engine.begin() as conn:
        res = conn.execute(text("SELECT COUNT(*) FROM users WHERE email = :email"), {"email": email}).fetchone()
        if res[0] == 0:
            salt = bcrypt.gensalt()
            pwd_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
            conn.execute(text("""
                INSERT INTO users (email, password_hash, full_name, factory_name, role, is_verified)
                VALUES (:email, :pwd_hash, :full_name, :factory_name, :role, 1)
            """), {
                "email": email, "pwd_hash": pwd_hash, "full_name": full_name, 
                "factory_name": factory_name, "role": role
            })

def create_user(email, password, full_name, factory_name, role):
    try:
        with engine.begin() as conn:
            res = conn.execute(text("SELECT COUNT(*) FROM users WHERE email = :email"), {"email": email}).fetchone()
            if res[0] > 0:
                return False, "Bu email allaqachon mavjud!"
            
            salt = bcrypt.gensalt()
            pwd_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
            conn.execute(text("""
                INSERT INTO users (email, password_hash, full_name, factory_name, role, is_verified)
                VALUES (:email, :pwd_hash, :full_name, :factory_name, :role, 1)
            """), {
                "email": email, "pwd_hash": pwd_hash, "full_name": full_name, 
                "factory_name": factory_name, "role": role
            })
            return True, "Foydalanuvchi muvaffaqiyatli yaratildi!"
    except Exception as e:
        return False, f"Xatolik yuz berdi: {str(e)}"

def get_all_certificates():
    with engine.connect() as conn:
        df = pd.read_sql("SELECT cert_code, cert_name FROM custom_certificates", conn)
        return dict(zip(df['cert_code'], df['cert_name']))

def add_custom_certificate(cert_code, cert_name):
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO custom_certificates (cert_code, cert_name) VALUES (:code, :name)"), 
                         {"code": cert_code.strip(), "name": cert_name.strip()})
            return True, "Sertifikat muvaffaqiyatli qo'shildi!"
    except Exception:
        return False, "Ushbu sertifikat kodi allaqachon mavjud!"

def update_custom_certificate(cert_code, new_cert_name):
    with engine.begin() as conn:
        conn.execute(text("UPDATE custom_certificates SET cert_name = :name WHERE cert_code = :code"), 
                     {"name": new_cert_name.strip(), "code": cert_code})
    return True, "Sertifikat nomi muvaffaqiyatli o'zgartirildi!"

def delete_custom_certificate(cert_code):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM custom_certificates WHERE cert_code = :code"), {"code": cert_code})
        conn.execute(text("DELETE FROM document_tasks WHERE cert_code = :code"), {"code": cert_code})
    return True, f"'{cert_code}' sertifikati o'chirildi!"

def verify_login(email, password):
    with engine.connect() as conn:
        res = conn.execute(text("SELECT id, password_hash, full_name, factory_name, role FROM users WHERE email = :email"), {"email": email}).fetchone()
        if res and bcrypt.checkpw(password.encode('utf-8'), res[1].encode('utf-8')):
            return {
                "id": res[0],
                "email": email,
                "full_name": res[2],
                "factory_name": res[3],
                "role": res[4]
            }
    return None

def add_single_document_task(factory_name, cert_code, task_title, assigned_role, due_date):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO document_tasks (factory_name, cert_code, task_title, assigned_role, due_date, status)
            VALUES (:factory_name, :cert_code, :task_title, :assigned_role, :due_date, 'PENDING')
        """), {
            "factory_name": factory_name, "cert_code": cert_code,
            "task_title": task_title, "assigned_role": assigned_role,
            "due_date": str(due_date)
        })

def get_document_tasks(factory_name, cert_code=None, role=None):
    with engine.connect() as conn:
        if role and role not in ["super_admin", "factory_admin", "compliance_manager", "ceo"]:
            query = text("SELECT * FROM document_tasks WHERE factory_name = :factory_name AND cert_code = :cert_code AND assigned_role = :role")
            return pd.read_sql(query, conn, params={"factory_name": factory_name, "cert_code": cert_code, "role": role})
        elif cert_code:
            query = text("SELECT * FROM document_tasks WHERE factory_name = :factory_name AND cert_code = :cert_code")
            return pd.read_sql(query, conn, params={"factory_name": factory_name, "cert_code": cert_code})
        else:
            query = text("SELECT * FROM document_tasks WHERE factory_name = :factory_name")
            return pd.read_sql(query, conn, params={"factory_name": factory_name})

def submit_task_evidence(task_id, file_obj, comment=""):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, file_obj.name)
    with open(file_path, "wb") as f:
        f.write(file_obj.getbuffer())
        
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE document_tasks SET status = 'UNDER_REVIEW', file_evidence = :file_evidence, comment = :comment WHERE id = :id
        """), {"file_evidence": file_obj.name, "comment": comment, "id": task_id})

def approve_task_status(task_id, is_approved, feedback=""):
    new_status = 'APPROVED' if is_approved else 'PENDING'
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE document_tasks SET status = :status, comment = :comment WHERE id = :id
        """), {"status": new_status, "comment": feedback, "id": task_id})

init_db()
create_user_if_not_exists("admin@auditreadiness.uz", "Admin123!@#", "Shohruh Shuxratov", "Sulton Styles", "super_admin")
create_user_if_not_exists("compliance@sulton.uz", "Comp123!@#", "Shohruh Compliance", "Sulton Styles", "compliance_manager")
create_user_if_not_exists("ceo@sulton.uz", "CEO123!@#", "Bosh Direktor (CEO)", "Sulton Styles", "ceo")
create_user_if_not_exists("ecologist@sulton.uz", "Eco123!@#", "Ekolog Mas'uli", "Sulton Styles", "ecologist")
create_user_if_not_exists("hr@sulton.uz", "HR123!@#", "HR Mas'uli", "Sulton Styles", "hr_manager")
create_user_if_not_exists("tradeunion@sulton.uz", "Union123!@#", "Kasaba Uyushmasi Raisi", "Sulton Styles", "trade_union")
create_user_if_not_exists("osh@sulton.uz", "OSH123!@#", "OSH / Mehnat Muhofazasi", "Sulton Styles", "osh_manager")

# ==========================================
# 2. STREAMLIT CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Sulton Certificates",
    page_icon="📜",
    layout="wide"
)

st.markdown("", unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

if "selected_cert" not in st.session_state:
    st.session_state.selected_cert = "BSCI"

ROLE_LABELS = {
    "super_admin": "Compliance Manager",
    "compliance_manager": "Compliance Manager",
    "ceo": "CEO / Bosh Direktor",
    "factory_admin": "Fabrika Rahbari",
    "ecologist": "Ecologist (Ekolog)",
    "hr_manager": "HR Manager",
    "trade_union": "Trade Union Chairman (Kasaba Uyushmasi)",
    "osh_manager": "OSH Manager (Mehnat Muhofazasi)"
}

def login_page():
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    with col_l2:
        if os.path.exists(LOGO_PATH):
            st.image(LOGO_PATH, width=220)
            
        st.title("🛡️ Sulton Certificates")
        st.caption("Sulton Tex Group — Xalqaro Audit va Sertifikatlashtirish Platformasi")
        st.divider()
        
        st.subheader("Tizimga kirish")
        email = st.text_input("Email pochta")
        password = st.text_input("Parol", type="password")
        
        if st.button("Kirish", use_container_width=True, type="primary"):
            if email and password:
                user = verify_login(email, password)
                if user:
                    st.session_state.user = user
                    st.success(f"Xush kelibsiz, {user['full_name']}!")
                    st.rerun()
                else:
                    st.error("Email yoki parol noto'g'ri!")
            else:
                st.warning("Iltimos, barcha maydonlarni to'ldiring!")

def admin_user_management():
    st.header("👤 Foydalanuvchilarni boshqarish (Admin & Compliance)")
    st.info("Yangi fabrika xodimi yoki Rahbariyat uchun login va parol shakllantirish")
    
    with st.form("create_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_email = st.text_input("Foydalanuvchi Email pochtasi")
            new_password = st.text_input("Vaqtinchalik Parol", type="password")
            full_name = st.text_input("Ism va Familiya")
        with col2:
            factory_name = st.text_input("Fabrika yoki Kompaniya nomi", value="Sulton Styles")
            role = st.selectbox("Tizimdagi roli", [
                ("ceo", "CEO / Bosh Direktor (Faqat Ko'rish)"),
                ("hr_manager", "HR Manager"),
                ("ecologist", "Ecologist (Ekolog)"),
                ("trade_union", "Trade Union Chairman (Kasaba Uyushmasi)"),
                ("osh_manager", "OSH Manager (Mehnat Muhofazasi)"),
                ("compliance_manager", "Compliance Manager"),
                ("factory_admin", "Fabrika Rahbari / Admin")
            ], format_func=lambda x: x[1])
            
        submit = st.form_submit_button("Foydalanuvchini yaratish")
        
        if submit:
            if new_email and new_password and full_name and factory_name:
                success, msg = create_user(new_email, new_password, full_name, factory_name, role[0])
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("Barcha maydonlarni to'liq to'ldiring!")

def main_dashboard():
    user = st.session_state.user
    cert_dict = get_all_certificates()
    
    with st.sidebar:
        if os.path.exists(LOGO_PATH):
            st.image(LOGO_PATH, width=200)
        
        st.title("Sulton Certificates")
        st.write(f"👤 **{user['full_name']}**")
        st.caption(f"🏢 {user['factory_name']} | Rol: **{ROLE_LABELS.get(user['role'], 'Compliance Manager')}**")
        st.divider()
        
        st.subheader("🎯 Sertifikatlarga:")
        cert_keys = list(cert_dict.keys())
        
        if cert_keys:
            if st.session_state.selected_cert not in cert_keys:
                st.session_state.selected_cert = cert_keys[0]
                
            current_index = cert_keys.index(st.session_state.selected_cert)
            
            selected_cert_code = st.selectbox(
                "Sertifikatni tanlang:",
                cert_keys,
                index=current_index,
                format_func=lambda x: f"{x} - {cert_dict[x]}"
            )
            
            if selected_cert_code != st.session_state.selected_cert:
                st.session_state.selected_cert = selected_cert_code
                st.rerun()

            st.info(f"Hozirgi standart: **{st.session_state.selected_cert}**")
        else:
            st.warning("Hozircha sertifikatlar mavjud emas!")

        if user['role'] in ['super_admin', 'compliance_manager']:
            with st.expander("🛠️ Sertifikatlarni Boshqarish"):
                tab_add, tab_edit, tab_del = st.tabs(["➕ Qo'shish", "✏️ Tahrirlash", "🗑️ O'chirish"])
                
                with tab_add:
                    new_c_code = st.text_input("Kodi (masalan: HIGG):", key="add_code")
                    new_c_name = st.text_input("Nomi (masalan: Higg Index FEM):", key="add_name")
                    if st.button("Saqlash", key="btn_add_cert"):
                        if new_c_code and new_c_name:
                            ok, msg = add_custom_certificate(new_c_code, new_c_name)
                            if ok:
                                st.session_state.selected_cert = new_c_code.strip()
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                        else:
                            st.warning("To'ldiring!")

                with tab_edit:
                    if cert_keys:
                        edit_target_code = st.selectbox("Tahrirlanadigan sertifikat:", cert_keys, key="edit_target")
                        edited_name = st.text_input("Yangi nomi:", value=cert_dict.get(edit_target_code, ""), key="edit_name")
                        if st.button("Nomini Yangilash", key="btn_edit_cert"):
                            if edited_name:
                                update_custom_certificate(edit_target_code, edited_name)
                                st.success("Yangilandi!")
                                st.rerun()

                with tab_del:
                    if cert_keys:
                        del_target_code = st.selectbox("O'chiriladigan sertifikat:", cert_keys, key="del_target")
                        if st.button("❌ Baza bilan o'chirish", key="btn_del_cert", type="primary"):
                            ok, msg = delete_custom_certificate(del_target_code)
                            st.warning(msg)
                            st.rerun()

        st.divider()

        menu_options = [
            "📊 Axborotlar oynasi", 
            "📑 Hujjatlar"
        ]
        if user['role'] in ['super_admin', 'compliance_manager']:
            menu_options.append("⚙️ Admin: User Qo'shish")
            
        choice = st.radio("Bo'limlar", menu_options)
        
        st.divider()
        if st.button("Tizimdan chiqish", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    active_cert = st.session_state.selected_cert
    active_cert_full_name = cert_dict.get(active_cert, active_cert)

    # 1. AXBOROTLAR OYNASI
    if choice == "📊 Axborotlar oynasi":
        st.title(f"📊 Axborotlar oynasi — [{active_cert}]")
        st.caption(f"{user['factory_name']} kompaniyasining **{active_cert_full_name}** standarti bo'yicha tayyorgarlik holati")
        
        doc_tasks_df = get_document_tasks(user['factory_name'], active_cert)
        total_docs = len(doc_tasks_df)
        
        approved_docs = len(doc_tasks_df[doc_tasks_df['status'] == 'APPROVED']) if total_docs > 0 else 0
        under_review_docs = len(doc_tasks_df[doc_tasks_df['status'] == 'UNDER_REVIEW']) if total_docs > 0 else 0
        pending_docs = len(doc_tasks_df[doc_tasks_df['status'] == 'PENDING']) if total_docs > 0 else 0
        doc_percentage = int((approved_docs / total_docs) * 100) if total_docs > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Auditga Tayyorgarlik", f"{doc_percentage}%", "Tasdiqlangan Hujjatlar")
        col2.metric("Tasdiqlangan Hujjatlar", f"{approved_docs} / {total_docs}", f"{doc_percentage}% Tayyor")
        col3.metric("Tekshiruvdagi Hujjatlar", f"{under_review_docs} ta", "Compliance Ko'rmoqda")
        col4.metric("Kutilayotgan Hujjatlar", f"{pending_docs} ta", "Ijro jarayonida")
        
        if user['role'] == 'ceo':
            st.divider()
            st.subheader("👔 CEO Boshqaruv Hisoboti:")
            st.progress(doc_percentage / 100)
            if doc_percentage >= 80:
                st.success("🎉 Fabrika xalqaro auditdan muvaffaqiyatli o'tish uchun YUQORI darajada tayyor!")
            elif doc_percentage >= 50:
                st.warning("⚠️ Tayyorgarlik O'RTA darajada. Ayrim bo'limlar topshiriqlarni tezlashtirishi kerak.")
            else:
                st.error("🚨 Tayyorgarlik DARAJASI PAST! Mas'ul xodimlar topshiriqlarni kechiktirmoqda.")

        st.divider()
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader(f"{active_cert} Hujjatlar va Topshiriqlar Holati")
            if total_docs > 0:
                fig_doc = px.pie(
                    doc_tasks_df, 
                    names="status", 
                    title=f"Hujjatlar Bajarilishi (Jami: {total_docs} ta)",
                    color="status",
                    color_discrete_map={"APPROVED":"#2e7d32", "UNDER_REVIEW":"#1565c0", "PENDING":"#ef6c00"},
                    template="plotly_dark"
                )
                st.plotly_chart(fig_doc, use_container_width=True)
            else:
                st.info("Hali Hujjatlar bo'limida topshiriqlar yuklanmagan.")
            
        with col_chart2:
            st.subheader(f"{active_cert} bo'yicha Mas'ullar Kesimida Holat")
            if total_docs > 0:
                df_role_chart = doc_tasks_df.groupby(["assigned_role", "status"]).size().reset_index(name="Soni")
                fig_bar = px.bar(df_role_chart, x="assigned_role", y="Soni", color="status", barmode="group", title="Mas'ullar Kesimida Hujjatlar", template="plotly_dark")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Statistika shakllanishi uchun topshiriqlar qo'shing.")

    # 2. HUJJATLAR
    elif choice == "📑 Hujjatlar":
        st.title(f"📑 Hujjatlar va Topshiriqlar Paneli — [{active_cert}]")
        st.caption(f"**{active_cert_full_name}** standarti doirasida topshiriqlar, ijro va Compliance tasdiqlash jarayoni")
        
        if user['role'] in ['super_admin', 'compliance_manager', 'factory_admin']:
            st.subheader("➕ Mas'ul Xodimlarga Topshiriq va Muddat Biriktirish")
            
            with st.form("add_task_form"):
                col_t, col_r, col_d = st.columns([2, 1.5, 1])
                
                with col_t:
                    task_title_input = st.text_input("Topshiriq / Hujjat Nomi:", placeholder="Masalan: Yong'in xavfsizligi hujjati va deklaratsiyasi")
                with col_r:
                    assigned_role_input = st.selectbox("Mas'ul Xodimni Tanlang:", [
                        ("hr_manager", "HR Manager"),
                        ("ecologist", "Ecologist (Ekolog)"),
                        ("trade_union", "Trade Union Chairman (Kasaba Uyushmasi)"),
                        ("osh_manager", "OSH Manager (Mehnat Muhofazasi)")
                    ], format_func=lambda x: x[1])
                with col_d:
                    due_date_input = st.date_input("Bajarish Muddati (Deadline):")
                
                submit_task = st.form_submit_button("Topshiriqni Saqlash va Xodimga Yuborish")
                
                if submit_task:
                    if task_title_input:
                        add_single_document_task(
                            user['factory_name'], 
                            active_cert, 
                            task_title_input, 
                            assigned_role_input[0], 
                            due_date_input
                        )
                        st.success(f"Topshiriq muvaffaqiyatli saqlandi va **{assigned_role_input[1]}** profiliga biriktirildi!")
                        st.rerun()
                    else:
                        st.warning("Iltimos, topshiriq nomini kiriting!")
            
            st.divider()

        if user['role'] in ['super_admin', 'compliance_manager']:
            st.subheader("🔍 Compliance Manager: Kelib Tushgan Hujjatlarni Tekshirish va Tasdiqlash")
            review_df = get_document_tasks(user['factory_name'], active_cert)
            
            under_review_tasks = review_df[review_df['status'] == 'UNDER_REVIEW']
            if not under_review_tasks.empty:
                for _, task in under_review_tasks.iterrows():
                    with st.expander(f"🔹 Topshiriq #{task['id']}: {task['task_title']} ({task['assigned_role']})", expanded=True):
                        col_info, col_file = st.columns([2, 1])
                        
                        with col_info:
                            st.write(f"**Bajarish muddati:** {task['due_date']}")
                            st.write(f"**Xodim izohi:** {task['comment'] if task['comment'] else 'Izoh yoq'}")
                            st.write(f"**Yuklangan fayl:** `{task['file_evidence']}`")

                        with col_file:
                            file_path = os.path.join(UPLOAD_DIR, str(task['file_evidence']))
                            if os.path.exists(file_path):
                                with open(file_path, "rb") as fp:
                                    st.download_button(
                                        label="📥 Faylni kompyuterga yuklab olish",
                                        data=fp,
                                        file_name=str(task['file_evidence']),
                                        key=f"dl_{task['id']}"
                                    )
                                if task['file_evidence'].lower().endswith(('.png', '.jpg', '.jpeg')):
                                    st.image(file_path, caption="Yuklangan Foto-dalil", use_container_width=True)
                            else:
                                st.info("Eski test fayli (diskda yo'q)")

                        st.divider()
                        col_act1, col_act2 = st.columns([3, 1])
                        with col_act1:
                            feedback = st.text_input("Compliance izohi / Fikr:", key=f"fb_{task['id']}")
                        with col_act2:
                            st.write("")
                            if st.button("✅ Tasdiqlash", key=f"app_{task['id']}", type="primary"):
                                approve_task_status(task['id'], True, feedback)
                                st.success(f"ID #{task['id']} Tasdiqlandi!")
                                st.rerun()
                            if st.button("❌ Rad etish", key=f"rej_{task['id']}"):
                                approve_task_status(task['id'], False, feedback)
                                st.warning(f"ID #{task['id']} Qaytarildi!")
                                st.rerun()
            else:
                st.info("Hozircha tekshiruv va tasdiqlash kutilayotgan yangi hujjatlar yo'q.")
            st.divider()

        st.subheader(f"📂 Hujjatlar va Fayllar Reestri ({ROLE_LABELS.get(user['role'], 'Compliance Manager')})")
        doc_tasks = get_document_tasks(user['factory_name'], active_cert, user['role'])
        
        if not doc_tasks.empty:
            st.dataframe(doc_tasks[["id", "task_title", "assigned_role", "due_date", "status", "file_evidence", "comment"]], use_container_width=True)
            
            st.subheader("📥 Barcha yuklangan fayllar paneli (Yuklab olish va Ko'rish):")
            
            has_files = False
            for _, r_task in doc_tasks.iterrows():
                f_name = str(r_task['file_evidence'])
                if f_name and f_name != 'None' and f_name != 'nan':
                    has_files = True
                    f_path = os.path.join(UPLOAD_DIR, f_name)
                    
                    with st.container():
                        col_t_title, col_t_dl = st.columns([3, 1])
                        col_t_title.markdown(f"📄 **{r_task['task_title']}** | Mas'ul: `{r_task['assigned_role']}` | Holat: **{r_task['status']}**\n\nFayl nomi: `{f_name}`")
                        
                        if os.path.exists(f_path):
                            with open(f_path, "rb") as f_data:
                                col_t_dl.download_button(
                                    label="📥 Faylni yuklab olish",
                                    data=f_data,
                                    file_name=f_name,
                                    key=f"main_dl_{r_task['id']}",
                                    type="primary"
                                )
                            if f_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                                st.image(f_path, width=300, caption=f"Foto-dalil: {f_name}")
                        else:
                            col_t_dl.warning("⚠️ Fayl diskda yo'q (Eski yozuv)")
                        st.divider()
                        
            if not has_files:
                st.info("Hozircha biror bir topshiriq uchun fayl yuklanmagan.")

            if user['role'] not in ['ceo', 'super_admin', 'compliance_manager']:
                st.subheader("📤 Topshiriqni Bajarish va Hujjat / Rasm Yuklash")
                pending_tasks = doc_tasks[doc_tasks['status'].isin(['PENDING', 'UNDER_REVIEW'])]
                if not pending_tasks.empty:
                    col_sel, col_up = st.columns(2)
                    with col_sel:
                        task_to_done = st.selectbox("Topshiriqni tanlang (ID):", pending_tasks['id'].tolist(), format_func=lambda x: f"ID #{x} - {pending_tasks[pending_tasks['id']==x]['task_title'].values[0]}")
                        emp_comment = st.text_input("Izoh (Ixtiyoriy):")
                    with col_up:
                        task_file = st.file_uploader("Tayyorlangan hujjat yoki fotoni yuklang (PDF/DOCX/PNG/JPG):", type=["pdf", "docx", "png", "jpg"])
                    
                    if st.button("Hujjatni Yuborish (Compliance Tekshiruviga)"):
                        if task_file:
                            submit_task_evidence(task_to_done, task_file, emp_comment)
                            st.success("Hujjat saqlandi! Pastki panelda ko'rishingiz mumkin.")
                            st.rerun()
                        else:
                            st.warning("Iltimos, fayl biriktiring!")
                else:
                    st.balloons()
                    st.success("Barcha topshiriqlar tasdiqlangan!")
        else:
            st.info(f"{active_cert} standarti bo'yicha topshiriqlar mavjud emas.")

    # 3. ADMIN USER QO'SHISH
    elif choice == "⚙️ Admin: User Qo'shish" and user['role'] in ['super_admin', 'compliance_manager']:
        admin_user_management()

if __name__ == "__main__":
    if st.session_state.user is None:
        login_page()
    else:
        main_dashboard()
