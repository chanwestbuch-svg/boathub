import os
import re
import csv
import io
import zipfile
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

import streamlit as st
from PIL import Image

# Optional (for Buyer Packet PDF)
REPORTLAB_OK = True
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
except Exception:
    REPORTLAB_OK = False


# =========================
# Page setup
# =========================
st.set_page_config(page_title="BoatHub", page_icon="🚤", layout="wide")

# =========================
# Query param helpers
# =========================
def qp_get(key: str, default: str = "") -> str:
    try:
        v = st.query_params.get(key, default)
        if isinstance(v, list):
            return v[0] if v else default
        return v or default
    except Exception:
        qp = st.experimental_get_query_params()
        return (qp.get(key, [default]) or [default])[0]

def qp_set(**kwargs):
    """
    qp_set(page="for_sale_all", boat="123", token="abc")
    Use value None to remove a key.
    """
    try:
        for k, v in kwargs.items():
            if v is None:
                if k in st.query_params:
                    del st.query_params[k]
            else:
                st.query_params[k] = str(v)
    except Exception:
        # old streamlit fallback
        curr = st.experimental_get_query_params()
        for k, v in kwargs.items():
            if v is None:
                curr.pop(k, None)
            else:
                curr[k] = str(v)
        st.experimental_set_query_params(**curr)

def qp_current_url_hint() -> str:
    """
    Streamlit doesn't give full URL cleanly; we show just the query string hint.
    """
    try:
        items = dict(st.query_params)
    except Exception:
        items = st.experimental_get_query_params()
    parts = []
    for k, v in items.items():
        if isinstance(v, list):
            if v:
                parts.append(f"{k}={v[0]}")
        else:
            parts.append(f"{k}={v}")
    return "?" + "&".join(parts) if parts else ""


# =========================
# Storage paths (Local vs Render)
# =========================
if os.environ.get("RENDER") or os.path.exists("/data"):
    DATA_DIR = "/data"
else:
    DATA_DIR = os.path.abspath(os.path.dirname(__file__))

DB_PATH = os.path.join(DATA_DIR, "boats.db")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
FILES_DIR = os.path.join(DATA_DIR, "files")

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

APP_DIR = os.path.abspath(os.path.dirname(__file__))
ASSETS_DIR = os.path.join(APP_DIR, "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "paradigm_logo.png")


# =========================
# Constants
# =========================
STATUSES = ["For Sale", "Customer Service", "On Hold", "Sold", "Delivered", "Storage", "Other"]

DEFAULT_CATEGORIES = [
    "Inventory - New",
    "Inventory - Used",
    "Service",
    "Consignment",
    "Demo",
    "Warranty",
    "Other",
    "Uncategorized",
]

DOC_CATEGORIES = ["Warranty", "Invoice", "Service Order", "Registration", "Manual", "Other"]
ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

PRIORITIES = ["Low", "Normal", "High", "Urgent"]

SERVICE_STAGES = [
    "Intake",
    "Diagnosing",
    "Waiting Parts",
    "In Progress",
    "QC",
    "Ready For Pickup",
    "Completed",
]

BADGE_LABEL = {
    "For Sale": "FOR SALE",
    "Customer Service": "SERVICE",
    "On Hold": "ON HOLD",
    "Sold": "SOLD",
    "Delivered": "DELIVERED",
    "Storage": "STORAGE",
    "Other": "OTHER",
}
BADGE_STYLE = {
    "For Sale": ("#111827", "#FFFFFF", "#111827"),
    "Customer Service": ("#FFFFFF", "#111827", "#111827"),
    "On Hold": ("#F3F4F6", "#111827", "#111827"),
    "Sold": ("#E5E7EB", "#111827", "#E5E7EB"),
    "Delivered": ("#FFFFFF", "#111827", "#111827"),
    "Storage": ("#F3F4F6", "#111827", "#111827"),
    "Other": ("#FFFFFF", "#111827", "#111827"),
}


# =========================
# CSS (clean black/white premium)
# =========================
st.markdown(
    """
<style>
.stApp { background: #F6F7FB; }
.block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; max-width: 1480px; }

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; height: 0; }

section[data-testid="stSidebar"] {
  background: #FFFFFF;
  border-right: 1px solid rgba(17,24,39,0.10);
}

.bh-title { font-size: 30px; font-weight: 950; letter-spacing: -0.035em; margin: 0; color: #0B1220; }
.bh-sub { margin-top: 6px; color: rgba(15,23,42,0.70); font-size: 13px; }
.bh-kicker { font-size: 12px; letter-spacing: 0.12em; font-weight: 800; color: rgba(15,23,42,0.55); text-transform: uppercase; }

.bh-card {
  background: #FFFFFF;
  border: 1px solid rgba(17,24,39,0.10);
  border-radius: 22px;
  box-shadow: 0 22px 70px rgba(15,23,42,0.08);
  padding: 18px 18px;
}
.bh-card-tight {
  background: #FFFFFF;
  border: 1px solid rgba(17,24,39,0.10);
  border-radius: 22px;
  box-shadow: 0 18px 55px rgba(15,23,42,0.07);
  padding: 16px 16px;
}

.bh-badge {
  display:inline-flex;
  align-items:center;
  padding: 7px 12px;
  border-radius: 999px;
  font-weight: 900;
  font-size: 12px;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.bh-pill {
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding: 8px 12px;
  border-radius: 999px;
  border:1px solid rgba(17,24,39,0.12);
  background:#FFFFFF;
  font-weight:900;
  color:#0B1220;
}

.bh-grid {
  display:grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
@media (max-width: 1200px){ .bh-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px){ .bh-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px){ .bh-grid { grid-template-columns: 1fr; } }

.bh-card-item {
  background:#FFFFFF;
  border:1px solid rgba(17,24,39,0.10);
  border-radius:20px;
  box-shadow:0 18px 50px rgba(15,23,42,0.07);
  overflow:hidden;
}
.bh-card-item-top {
  height: 160px;
  background: rgba(17,24,39,0.06);
}
.bh-card-item-body {
  padding: 12px 12px 14px 12px;
}
.bh-card-title {
  font-size: 15px;
  font-weight: 950;
  letter-spacing: -0.02em;
  color:#0B1220;
}
.bh-card-meta {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(15,23,42,0.65);
}
.bh-card-price {
  margin-top: 10px;
  font-size: 16px;
  font-weight: 950;
  color:#0B1220;
}
.bh-card-actions {
  display:flex;
  gap:10px;
  margin-top: 10px;
}

.bh-kpi {
  display:grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
@media (max-width: 1100px){ .bh-kpi { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px){ .bh-kpi { grid-template-columns: 1fr; } }

.bh-kpi-box {
  background:#FFFFFF;
  border:1px solid rgba(17,24,39,0.10);
  border-radius:18px;
  box-shadow:0 14px 40px rgba(15,23,42,0.06);
  padding:14px 14px;
}
.bh-kpi-k { color: rgba(15,23,42,0.60); font-size: 12px; font-weight: 800; letter-spacing: 0.10em; text-transform: uppercase; }
.bh-kpi-v { margin-top: 6px; font-size: 30px; font-weight: 950; letter-spacing: -0.02em; color: #0B1220; }

.stButton>button {
  border-radius: 14px !important;
  border: 1px solid rgba(17,24,39,0.15) !important;
  background: #111827 !important;
  color: #FFFFFF !important;
  padding: 0.62rem 0.95rem !important;
}
.stButton>button:hover { background: #0B1220 !important; }

.stTextInput input, .stTextArea textarea, .stNumberInput input {
  border-radius: 14px !important;
  border: 1px solid rgba(17,24,39,0.12) !important;
  background: #FFFFFF !important;
  color: #0B1220 !important;
}
div[data-baseweb="select"] > div {
  border-radius: 14px !important;
  border: 1px solid rgba(17,24,39,0.12) !important;
  background: #FFFFFF !important;
}

@media (max-width: 768px) {
  .block-container { padding-left: 0.95rem; padding-right: 0.95rem; }
  input, textarea { font-size: 16px !important; } /* iPhone zoom fix */
  div[data-testid="stHorizontalBlock"] { flex-direction: column !important; }
  div[data-testid="column"] { width: 100% !important; }
}

.stTabs [data-baseweb="tab"] { font-weight: 900; }
</style>
""",
    unsafe_allow_html=True,
)


# =========================
# Helpers
# =========================
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "boat"

def safe_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    base = base.replace("/", "_").replace("\\", "_")
    base = re.sub(r"[^a-zA-Z0-9._ -]+", "_", base)
    return base[:160]

def badge_html(status: str) -> str:
    bg, fg, border = BADGE_STYLE.get(status, ("#FFFFFF", "#111827", "#111827"))
    label = BADGE_LABEL.get(status, (status or "").upper())
    return f'<span class="bh-badge" style="background:{bg};color:{fg};border:1px solid {border};">{label}</span>'

def money(v) -> str:
    try:
        if v is None:
            return "—"
        v = float(v)
        if v <= 0:
            return "—"
        return "${:,.0f}".format(v)
    except Exception:
        return "—"

def parse_yyyy_mm_dd(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


# =========================
# DB
# =========================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

def ensure_column(conn, table: str, col: str, col_def: str):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS boats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_number TEXT,
            year INTEGER,
            make TEXT,
            model TEXT,
            hin TEXT,
            length_ft REAL,
            engine TEXT,
            location TEXT,
            status TEXT NOT NULL,
            category TEXT,
            tags TEXT,
            sale_price REAL,
            msrp REAL,
            hours REAL,
            work_order TEXT,
            assigned_tech TEXT,
            priority TEXT,
            service_stage TEXT,
            service_due_date TEXT,
            service_completed_at TEXT,
            customer_name TEXT,
            customer_phone TEXT,
            notes TEXT,
            public_description TEXT,
            public_hide INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS boat_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boat_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY(boat_id) REFERENCES boats(id) ON DELETE CASCADE
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS boat_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boat_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            category TEXT NOT NULL,
            ext TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY(boat_id) REFERENCES boats(id) ON DELETE CASCADE
        )
        """)

        # Migrations (adds columns without wiping data)
        ensure_column(conn, "boats", "category", "TEXT")
        ensure_column(conn, "boats", "tags", "TEXT")
        ensure_column(conn, "boats", "sale_price", "REAL")
        ensure_column(conn, "boats", "msrp", "REAL")
        ensure_column(conn, "boats", "hours", "REAL")
        ensure_column(conn, "boats", "work_order", "TEXT")
        ensure_column(conn, "boats", "assigned_tech", "TEXT")
        ensure_column(conn, "boats", "priority", "TEXT")
        ensure_column(conn, "boats", "service_stage", "TEXT")
        ensure_column(conn, "boats", "service_due_date", "TEXT")
        ensure_column(conn, "boats", "service_completed_at", "TEXT")
        ensure_column(conn, "boats", "public_description", "TEXT")
        ensure_column(conn, "boats", "public_hide", "INTEGER DEFAULT 0")

        conn.execute("UPDATE boats SET category='Uncategorized' WHERE category IS NULL OR TRIM(category)=''")
        conn.execute("UPDATE boats SET priority='Normal' WHERE priority IS NULL OR TRIM(priority)=''")
        conn.execute("UPDATE boats SET public_hide=0 WHERE public_hide IS NULL")

init_db()

def distinct_values(col: str):
    with db() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT {col} as v FROM boats WHERE {col} IS NOT NULL AND TRIM({col})<>'' ORDER BY {col}"
        ).fetchall()
        return [r["v"] for r in rows if r["v"] is not None]


# =========================
# Auth / Roles + Public mode
# =========================
PUBLIC_TOKEN = (os.environ.get("BOATHUB_PUBLIC_TOKEN") or "").strip()
PUBLIC_CONTACT = (os.environ.get("BOATHUB_PUBLIC_CONTACT") or "").strip()

def public_access_allowed() -> bool:
    if not PUBLIC_TOKEN:
        return False
    if qp_get("public", "0") != "1":
        return False
    return qp_get("token", "") == PUBLIC_TOKEN

def require_login():
    """
    Roles:
      - Admin: full access
      - Sales: sales + inventory + buyer packets
      - Service: service board + service records
    """
    # Public mode bypass:
    if public_access_allowed():
        st.session_state.role = "Public"
        st.session_state.authed = True
        return

    admin_pw = (os.environ.get("BOATHUB_ADMIN_PASSWORD") or "").strip()
    sales_pw = (os.environ.get("BOATHUB_SALES_PASSWORD") or "").strip()
    service_pw = (os.environ.get("BOATHUB_SERVICE_PASSWORD") or "").strip()
    fallback_pw = (os.environ.get("BOATHUB_PASSWORD") or "").strip()

    # If no passwords set, no login required
    if not (admin_pw or sales_pw or service_pw or fallback_pw):
        st.session_state.role = "Admin"
        st.session_state.authed = True
        return

    if "authed" not in st.session_state:
        st.session_state.authed = False
    if "role" not in st.session_state:
        st.session_state.role = "Admin"

    if st.session_state.authed:
        return

    # If only fallback is set, we treat it as Admin for simplicity (you can add role passwords later)
    role_picker_enabled = bool(admin_pw or sales_pw or service_pw)

    st.markdown(
        """
        <div style="
            max-width:560px;margin:48px auto;padding:26px 26px;
            border-radius:22px;border:1px solid rgba(17,24,39,0.12);
            background:#ffffff; box-shadow:0 20px 60px rgba(15,23,42,0.10);">
          <div style="font-size:28px;font-weight:950;letter-spacing:-0.03em;">🔒 BoatHub Login</div>
          <div style="margin-top:6px;color:rgba(15,23,42,0.72);">Sign in to access your shop system.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if role_picker_enabled:
        role = st.selectbox("Role", ["Admin", "Sales", "Service"], index=0)
    else:
        role = "Admin"

    pw = st.text_input("Password", type="password")

    if st.button("Sign in", use_container_width=True):
        def ok_for_role():
            if role == "Admin":
                return (admin_pw and pw == admin_pw) or (fallback_pw and pw == fallback_pw)
            if role == "Sales":
                return (sales_pw and pw == sales_pw) or (fallback_pw and pw == fallback_pw)
            if role == "Service":
                return (service_pw and pw == service_pw) or (fallback_pw and pw == fallback_pw)
            return False

        if ok_for_role():
            st.session_state.authed = True
            st.session_state.role = role
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

require_login()

ROLE = st.session_state.get("role", "Admin")

def can_admin(): return ROLE == "Admin"
def can_sales(): return ROLE in ("Admin", "Sales")
def can_service(): return ROLE in ("Admin", "Service")
def is_public(): return ROLE == "Public"


# =========================
# CRUD
# =========================
def boat_exists(hin: str, stock: str) -> bool:
    hin = (hin or "").strip()
    stock = (stock or "").strip()
    if not hin and not stock:
        return False
    with db() as conn:
        if hin and conn.execute("SELECT 1 FROM boats WHERE hin=? LIMIT 1", (hin,)).fetchone():
            return True
        if stock and conn.execute("SELECT 1 FROM boats WHERE stock_number=? LIMIT 1", (stock,)).fetchone():
            return True
    return False

def insert_boat(data: dict) -> int:
    t = now_iso()
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO boats (
                stock_number, year, make, model, hin, length_ft, engine, location,
                status, category, tags, sale_price, msrp, hours, work_order, assigned_tech, priority,
                service_stage, service_due_date, service_completed_at,
                customer_name, customer_phone, notes,
                public_description, public_hide,
                created_at, updated_at
            ) VALUES (
                :stock_number, :year, :make, :model, :hin, :length_ft, :engine, :location,
                :status, :category, :tags, :sale_price, :msrp, :hours, :work_order, :assigned_tech, :priority,
                :service_stage, :service_due_date, :service_completed_at,
                :customer_name, :customer_phone, :notes,
                :public_description, :public_hide,
                :created_at, :updated_at
            )
        """, {**data, "created_at": t, "updated_at": t})
        return int(cur.lastrowid)

ALLOWED_UPDATE_COLS = {
    "stock_number", "year", "make", "model", "hin", "length_ft", "engine", "location",
    "status", "category", "tags", "sale_price", "msrp", "hours", "work_order", "assigned_tech", "priority",
    "service_stage", "service_due_date", "service_completed_at",
    "customer_name", "customer_phone", "notes",
    "public_description", "public_hide",
}

def update_fields(boat_id: int, fields: dict):
    parts = []
    params = []
    for k, v in fields.items():
        if k in ALLOWED_UPDATE_COLS:
            parts.append(f"{k}=?")
            params.append(v)
    parts.append("updated_at=?")
    params.append(now_iso())
    params.append(boat_id)
    with db() as conn:
        conn.execute(f"UPDATE boats SET {', '.join(parts)} WHERE id=?", tuple(params))

def get_boat(boat_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM boats WHERE id=?", (boat_id,)).fetchone()

def delete_boat(boat_id: int):
    photos = get_photos(boat_id)
    with db() as conn:
        conn.execute("DELETE FROM boats WHERE id=?", (boat_id,))

    for p in photos:
        pth = os.path.join(PHOTOS_DIR, p["filename"])
        if os.path.exists(pth):
            try:
                os.remove(pth)
            except OSError:
                pass

    boat_folder = os.path.join(FILES_DIR, str(boat_id))
    if os.path.isdir(boat_folder):
        try:
            for child in Path(boat_folder).glob("*"):
                try:
                    child.unlink()
                except OSError:
                    pass
            try:
                Path(boat_folder).rmdir()
            except OSError:
                pass
        except OSError:
            pass


# =========================
# Photos
# =========================
def add_photo(boat_id: int, filename: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO boat_photos (boat_id, filename, uploaded_at) VALUES (?, ?, ?)",
            (boat_id, filename, now_iso()),
        )

def get_photos(boat_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM boat_photos WHERE boat_id=? ORDER BY uploaded_at DESC",
            (boat_id,),
        ).fetchall()

def get_first_photo_path(boat_id: int):
    photos = get_photos(boat_id)
    if not photos:
        return None
    p = os.path.join(PHOTOS_DIR, photos[0]["filename"])
    return p if os.path.exists(p) else None

def delete_photo(photo_id: int):
    with db() as conn:
        row = conn.execute("SELECT filename FROM boat_photos WHERE id=?", (photo_id,)).fetchone()
        if not row:
            return
        filename = row["filename"]
        conn.execute("DELETE FROM boat_photos WHERE id=?", (photo_id,))
    path = os.path.join(PHOTOS_DIR, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

def save_uploaded_images(boat_id: int, make: str, model: str, files) -> int:
    count = 0
    base = slugify(f"{boat_id}-{make}-{model}")
    for f in files:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in IMAGE_EXTS:
            continue
        out_name = f"{base}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{count}{ext}"
        out_path = os.path.join(PHOTOS_DIR, out_name)

        img = Image.open(f).convert("RGB")
        max_side = 2400
        w, h = img.size
        scale = min(1.0, max_side / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))
        img.save(out_path, quality=88)

        add_photo(boat_id, out_name)
        count += 1
    return count


# =========================
# Documents
# =========================
def add_file(boat_id: int, filename: str, original_name: str, category: str, ext: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO boat_files (boat_id, filename, original_name, category, ext, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (boat_id, filename, original_name, category, ext, now_iso()))

def get_files(boat_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM boat_files WHERE boat_id=? ORDER BY uploaded_at DESC",
            (boat_id,),
        ).fetchall()

def delete_file(file_id: int):
    with db() as conn:
        row = conn.execute("SELECT boat_id, filename FROM boat_files WHERE id=?", (file_id,)).fetchone()
        if not row:
            return
        boat_id = int(row["boat_id"])
        filename = row["filename"]
        conn.execute("DELETE FROM boat_files WHERE id=?", (file_id,))

    boat_folder = os.path.join(FILES_DIR, str(boat_id))
    path = os.path.join(boat_folder, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

def save_uploaded_docs(boat_id: int, make: str, model: str, category: str, files) -> int:
    boat_folder = os.path.join(FILES_DIR, str(boat_id))
    os.makedirs(boat_folder, exist_ok=True)

    base = slugify(f"{boat_id}-{make}-{model}")
    count = 0

    for f in files:
        original = f.name
        ext = os.path.splitext(original)[1].lower()
        if ext not in ALLOWED_EXTS:
            continue

        safe_cat = slugify(category)
        out_name = f"{base}-{safe_cat}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{count}{ext}"
        out_path = os.path.join(boat_folder, out_name)

        with open(out_path, "wb") as out:
            out.write(f.getbuffer())

        add_file(boat_id, out_name, original, category, ext)
        count += 1

    return count


# =========================
# Lists for “pages”
# =========================
VIEW_CONFIG = {
    "for_sale_new": {"title": "New Boats For Sale", "where": "status=? AND category=?", "params": ["For Sale", "Inventory - New"]},
    "for_sale_used": {"title": "Used Boats For Sale", "where": "status=? AND category=?", "params": ["For Sale", "Inventory - Used"]},
    "for_sale_all": {"title": "All Boats For Sale", "where": "status=?", "params": ["For Sale"]},
    "service_list": {"title": "Service Boats (List)", "where": "(status=? OR category=?)", "params": ["Customer Service", "Service"]},
    "on_hold": {"title": "On Hold", "where": "status=?", "params": ["On Hold"]},
    "sold": {"title": "Sold", "where": "status=?", "params": ["Sold"]},
    "delivered": {"title": "Delivered", "where": "status=?", "params": ["Delivered"]},
    "storage": {"title": "Storage", "where": "status=?", "params": ["Storage"]},
    "all": {"title": "All Boats", "where": "", "params": []},
}

PUBLIC_VIEW_CONFIG = {
    "public_for_sale_all": {"title": "Boats For Sale", "where": "status=? AND public_hide=0", "params": ["For Sale"]},
    "public_for_sale_new": {"title": "New Boats For Sale", "where": "status=? AND category=? AND public_hide=0", "params": ["For Sale", "Inventory - New"]},
    "public_for_sale_used": {"title": "Used Boats For Sale", "where": "status=? AND category=? AND public_hide=0", "params": ["For Sale", "Inventory - Used"]},
}

def list_boats(where_sql: str, params: list, search_text: str, sort_mode: str, public_mode: bool):
    conds = []
    p = []

    if where_sql:
        conds.append(f"({where_sql})")
        p.extend(params)

    s = (search_text or "").strip()
    if s:
        q = f"%{s}%"
        # Public: don't search customer data
        if public_mode:
            conds.append("(make LIKE ? OR model LIKE ? OR category LIKE ? OR tags LIKE ?)")
            p.extend([q, q, q, q])
        else:
            conds.append("""
                (make LIKE ? OR model LIKE ? OR hin LIKE ? OR stock_number LIKE ? OR customer_name LIKE ?
                 OR category LIKE ? OR tags LIKE ?)
            """)
            p.extend([q, q, q, q, q, q, q])

    where = "WHERE " + " AND ".join(conds) if conds else ""

    order_map = {
        "Recently Updated": "updated_at DESC",
        "Year (Newest)": "year DESC, updated_at DESC",
        "Year (Oldest)": "year ASC, updated_at DESC",
        "Make (A-Z)": "make ASC, model ASC, year DESC",
        "Category": "category ASC, updated_at DESC",
        "Price (High)": "sale_price DESC, msrp DESC, updated_at DESC",
        "Price (Low)": "sale_price ASC, msrp ASC, updated_at DESC",
    }
    order_sql = order_map.get(sort_mode, "updated_at DESC")

    with db() as conn:
        return conn.execute(f"SELECT * FROM boats {where} ORDER BY {order_sql}", tuple(p)).fetchall()

def service_boats_all():
    with db() as conn:
        return conn.execute(
            "SELECT * FROM boats WHERE (status=? OR category=?) ORDER BY priority DESC, service_due_date ASC, updated_at DESC",
            ("Customer Service", "Service"),
        ).fetchall()


# =========================
# Exports / Zip packet
# =========================
def boats_to_csv_bytes(rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "id","year","make","model","status","category","sale_price","msrp","stock_number","hin","location",
        "service_stage","service_due_date","priority","work_order","assigned_tech",
        "customer_name","customer_phone","tags","updated_at"
    ])
    for b in rows:
        w.writerow([
            b["id"], b["year"], b["make"], b["model"], b["status"], b["category"],
            b["sale_price"], b["msrp"], b["stock_number"], b["hin"], b["location"],
            b["service_stage"], b["service_due_date"], b["priority"], b["work_order"], b["assigned_tech"],
            b["customer_name"], b["customer_phone"], b["tags"], b["updated_at"]
        ])
    return out.getvalue().encode("utf-8")

def zip_one_boat(boat_id: int) -> bytes:
    boat = get_boat(boat_id)
    if not boat:
        return b""

    photos = get_photos(boat_id)
    docs = get_files(boat_id)

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in photos:
            p_path = os.path.join(PHOTOS_DIR, p["filename"])
            if os.path.exists(p_path):
                z.write(p_path, arcname=f"photos/{p['filename']}")

        boat_folder = os.path.join(FILES_DIR, str(boat_id))
        for d in docs:
            f_path = os.path.join(boat_folder, d["filename"])
            if os.path.exists(f_path):
                z.write(
                    f_path,
                    arcname=f"documents/{safe_filename(d['category'])}/{safe_filename(d['original_name'])}"
                )

        summary = (
            f"Boat #{boat['id']}\n"
            f"Year/Make/Model: {boat['year']} {boat['make']} {boat['model']}\n"
            f"Status: {boat['status']}\n"
            f"Category: {boat['category']}\n"
            f"Sale Price: {boat['sale_price']}\n"
            f"MSRP: {boat['msrp']}\n"
            f"Stock: {boat['stock_number']}\n"
            f"HIN: {boat['hin']}\n"
            f"Location: {boat['location']}\n"
            f"Service Stage: {boat['service_stage']}\n"
            f"Service Due: {boat['service_due_date']}\n"
            f"Updated: {boat['updated_at']}\n"
        )
        z.writestr("boat_summary.txt", summary)

    mem.seek(0)
    return mem.read()


# =========================
# Buyer Packet PDF
# =========================
def generate_buyer_packet_pdf(boat_id: int) -> bytes:
    """
    Generates a simple PDF with main details + up to 4 photos.
    Requires reportlab (see requirements.txt below).
    """
    boat = get_boat(boat_id)
    if not boat:
        return b""

    if not REPORTLAB_OK:
        return b""

    photos = get_photos(boat_id)
    photo_paths = []
    for p in photos[:6]:
        pth = os.path.join(PHOTOS_DIR, p["filename"])
        if os.path.exists(pth):
            photo_paths.append(pth)

    mem = io.BytesIO()
    c = canvas.Canvas(mem, pagesize=letter)
    W, H = letter

    # Header
    c.setTitle(f"Buyer Packet - Boat {boat_id}")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(0.75 * inch, H - 0.9 * inch, f"Buyer Packet")
    c.setFont("Helvetica", 12)
    c.drawString(0.75 * inch, H - 1.2 * inch, f"{boat['year'] or ''} {boat['make'] or ''} {boat['model'] or ''}".strip())

    # Details box
    y = H - 1.55 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(0.75 * inch, y, "Details")
    y -= 0.18 * inch
    c.setFont("Helvetica", 10)

    lines = [
        f"Price: {money(boat['sale_price'])}    MSRP: {money(boat['msrp'])}",
        f"Stock #: {boat['stock_number'] or '—'}    HIN: {boat['hin'] or '—'}",
        f"Category: {boat['category'] or '—'}    Status: {boat['status'] or '—'}",
        f"Length (ft): {boat['length_ft'] or '—'}    Engine: {boat['engine'] or '—'}",
        f"Location: {boat['location'] or '—'}",
    ]
    for ln in lines:
        c.drawString(0.75 * inch, y, ln)
        y -= 0.18 * inch

    # Public description (better than notes)
    desc = (boat["public_description"] or "").strip()
    if desc:
        y -= 0.10 * inch
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0.75 * inch, y, "Description")
        y -= 0.18 * inch
        c.setFont("Helvetica", 10)
        # simple wrap
        wrap_width = 95
        words = desc.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > wrap_width:
                c.drawString(0.75 * inch, y, line)
                y -= 0.16 * inch
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            c.drawString(0.75 * inch, y, line)
            y -= 0.16 * inch

    # Photos (up to 4 per PDF page)
    y -= 0.25 * inch
    if photo_paths:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0.75 * inch, y, "Photos")
        y -= 0.15 * inch

        # 2 columns photo layout
        max_w = 3.35 * inch
        max_h = 2.35 * inch
        x_left = 0.75 * inch
        x_right = 4.05 * inch
        x = x_left
        col = 0

        for i, pth in enumerate(photo_paths[:4]):
            if y - max_h < 0.9 * inch:
                c.showPage()
                y = H - 1.0 * inch
                x = x_left
                col = 0

            try:
                img = Image.open(pth)
                iw, ih = img.size
                scale = min(max_w / iw, max_h / ih)
                dw = iw * scale
                dh = ih * scale
                c.drawImage(ImageReader(pth), x, y - dh, width=dw, height=dh, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

            col += 1
            if col % 2 == 1:
                x = x_right
            else:
                x = x_left
                y -= (max_h + 0.25 * inch)

    # Footer
    c.setFont("Helvetica", 8)
    c.drawString(0.75 * inch, 0.6 * inch, f"Generated: {now_iso()}  •  BoatHub")

    c.save()
    mem.seek(0)
    return mem.read()


# =========================
# Header
# =========================
h1, h2 = st.columns([1.2, 4.8], vertical_alignment="center")
with h1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=240)
with h2:
    if is_public():
        st.markdown(
            """
            <div class="bh-card">
              <div class="bh-kicker">Public Inventory</div>
              <div class="bh-title">Boats For Sale</div>
              <div class="bh-sub">Browse our current inventory. Photos and basic details shown.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="bh-card">
              <div class="bh-kicker">Paradigm • Dealer Ops</div>
              <div class="bh-title">BoatHub</div>
              <div class="bh-sub">Dashboard • Inventory Cards • Service Kanban • Buyer Packets • Public For-Sale Link</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")


# =========================
# Sidebar (logout + role)
# =========================
with st.sidebar:
    if not is_public():
        st.markdown(f"**Signed in as:** {ROLE}")
        if st.button("Logout", use_container_width=True):
            st.session_state.authed = False
            st.session_state.role = "Admin"
            qp_set(page=None, boat=None)  # clear selection
            st.rerun()
        st.markdown("---")

    st.markdown("### Quick tips")
    st.caption("• Sales uses **For Sale** pages + Buyer Packet.\n• Service uses **Service Board**.\n• Admin can do everything.\n• Public link shows **For Sale** boats only.")


# =========================
# Navigation pages
# =========================
def nav_pages_for_role():
    if is_public():
        return [
            ("Boats For Sale", "public_for_sale_all"),
            ("New Boats For Sale", "public_for_sale_new"),
            ("Used Boats For Sale", "public_for_sale_used"),
        ]
    if can_admin():
        return [
            ("Dashboard", "dashboard"),
            ("New Boats For Sale", "for_sale_new"),
            ("Used Boats For Sale", "for_sale_used"),
            ("All Boats For Sale", "for_sale_all"),
            ("Service Board", "service_board"),
            ("Service Boats (List)", "service_list"),
            ("On Hold", "on_hold"),
            ("Sold", "sold"),
            ("Delivered", "delivered"),
            ("Storage", "storage"),
            ("All Boats", "all"),
            ("Add New Boat", "add"),
            ("Tools / Export / Backup", "tools"),
            ("Public Link", "public_link"),
        ]
    if can_sales():
        return [
            ("Dashboard", "dashboard"),
            ("New Boats For Sale", "for_sale_new"),
            ("Used Boats For Sale", "for_sale_used"),
            ("All Boats For Sale", "for_sale_all"),
            ("On Hold", "on_hold"),
            ("Sold", "sold"),
            ("All Boats", "all"),
            ("Add New Boat", "add"),
            ("Tools / Export", "tools"),
            ("Public Link", "public_link"),
        ]
    # Service
    return [
        ("Dashboard", "dashboard"),
        ("Service Board", "service_board"),
        ("Service Boats (List)", "service_list"),
        ("All Boats", "all"),
        ("Add New Boat", "add"),
        ("Tools / Export", "tools"),
    ]

PAGES = nav_pages_for_role()
LABELS = [p[0] for p in PAGES]
LABEL_TO_KEY = {label: key for label, key in PAGES}
KEY_TO_LABEL = {key: label for label, key in PAGES}

default_page = PAGES[0][1]
page_key = qp_get("page", default_page)
if page_key not in KEY_TO_LABEL:
    page_key = default_page

# =========================
# Top nav row (dropdown “pages”)
# =========================
nav_col, search_col, sort_col, view_col = st.columns([1.35, 1.30, 1.10, 0.95], vertical_alignment="bottom")

with nav_col:
    selected_label = st.selectbox("Go to page", LABELS, index=LABELS.index(KEY_TO_LABEL[page_key]))
    selected_key = LABEL_TO_KEY[selected_label]
    if selected_key != page_key:
        qp_set(page=selected_key, boat=None)
        st.rerun()

# Search only on browse pages
search_text = ""
sort_mode = "Recently Updated"
view_mode = "Cards"

BROWSE_PAGES_INTERNAL = {"for_sale_new","for_sale_used","for_sale_all","service_list","on_hold","sold","delivered","storage","all"}
BROWSE_PAGES_PUBLIC = {"public_for_sale_all","public_for_sale_new","public_for_sale_used"}

if page_key in (BROWSE_PAGES_INTERNAL | BROWSE_PAGES_PUBLIC):
    with search_col:
        search_text = st.text_input("Search this page", value="", placeholder="make, model, stock, HIN, tags…")
    with sort_col:
        sort_mode = st.selectbox("Sort", ["Recently Updated","Year (Newest)","Year (Oldest)","Make (A-Z)","Category","Price (High)","Price (Low)"], index=0)
    with view_col:
        view_mode = st.selectbox("View", ["Cards", "Table"], index=0)
else:
    with search_col:
        st.caption("")
    with sort_col:
        st.caption("")
    with view_col:
        st.caption("")

st.write("")


# =========================
# Dashboard
# =========================
def render_dashboard():
    rows_all = list_boats("", [], "", "Recently Updated", public_mode=False)

    total = len(rows_all)
    for_sale = sum(1 for b in rows_all if b["status"] == "For Sale")
    service = sum(1 for b in rows_all if b["status"] == "Customer Service" or b["category"] == "Service")
    sold = sum(1 for b in rows_all if b["status"] == "Sold")

    # Pipeline value
    pipeline = 0.0
    for b in rows_all:
        if b["status"] == "For Sale":
            v = b["sale_price"] if (b["sale_price"] or 0) > 0 else (b["msrp"] or 0)
            pipeline += float(v or 0)

    # Service alerts
    svc = service_boats_all()
    today = date.today()
    due_soon_cutoff = today + timedelta(days=3)

    overdue = 0
    due_soon = 0
    for b in svc:
        if (b["service_stage"] or "Intake") == "Completed":
            continue
        d = parse_yyyy_mm_dd(b["service_due_date"] or "")
        if not d:
            continue
        if d < today:
            overdue += 1
        elif today <= d <= due_soon_cutoff:
            due_soon += 1

    st.markdown(
        f"""
        <div class="bh-kpi">
          <div class="bh-kpi-box"><div class="bh-kpi-k">Total Boats</div><div class="bh-kpi-v">{total}</div></div>
          <div class="bh-kpi-box"><div class="bh-kpi-k">For Sale</div><div class="bh-kpi-v">{for_sale}</div></div>
          <div class="bh-kpi-box"><div class="bh-kpi-k">Service Backlog</div><div class="bh-kpi-v">{service}</div></div>
          <div class="bh-kpi-box"><div class="bh-kpi-k">Pipeline Value</div><div class="bh-kpi-v">${pipeline:,.0f}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    c1, c2 = st.columns([1.25, 1.75], gap="large")

    with c1:
        st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
        st.markdown("### Service Alerts")
        st.write(f"**Overdue:** {overdue}")
        st.write(f"**Due in next 3 days:** {due_soon}")

        if overdue or due_soon:
            st.info("Go to **Service Board** to move stages and manage due dates.")
        else:
            st.success("No urgent service due dates right now.")

        st.markdown("---")
        st.markdown("### Quick Jump")
        q1, q2 = st.columns(2)
        if q1.button("Open For Sale", use_container_width=True):
            qp_set(page="for_sale_all", boat=None); st.rerun()
        if q2.button("Open Service Board", use_container_width=True):
            qp_set(page="service_board", boat=None); st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
        st.markdown("### What’s moving lately")
        recent = rows_all[:20]
        table = []
        for b in recent:
            table.append({
                "ID": b["id"],
                "Boat": f"{b['year'] or ''} {b['make'] or ''} {b['model'] or ''}".strip(),
                "Status": b["status"],
                "Category": b["category"],
                "Updated": b["updated_at"],
            })
        st.dataframe(table, use_container_width=True, hide_index=True, height=430)
        st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Inventory Cards renderer
# =========================
def render_cards(rows, public_mode: bool):
    # Build a simple HTML grid container; actual card contents are Streamlit widgets.
    st.markdown('<div class="bh-grid">', unsafe_allow_html=True)

    cols = st.columns(4)
    for i, b in enumerate(rows):
        with cols[i % 4]:
            st.markdown('<div class="bh-card-item">', unsafe_allow_html=True)

            # image
            img_path = get_first_photo_path(int(b["id"]))
            if img_path:
                st.image(img_path, use_container_width=True)
            else:
                st.markdown('<div class="bh-card-item-top"></div>', unsafe_allow_html=True)

            st.markdown('<div class="bh-card-item-body">', unsafe_allow_html=True)

            title = f"{b['year'] or ''} {b['make'] or ''} {b['model'] or ''}".strip()
            st.markdown(f'<div class="bh-card-title">{title}</div>', unsafe_allow_html=True)

            meta = f"{b['status']} • {b['category']}"
            if b["stock_number"]:
                meta += f" • Stock {b['stock_number']}"
            st.markdown(f'<div class="bh-card-meta">{meta}</div>', unsafe_allow_html=True)

            price_line = money(b["sale_price"])
            if price_line == "—":
                price_line = money(b["msrp"])
            st.markdown(f'<div class="bh-card-price">{price_line}</div>', unsafe_allow_html=True)

            # actions
            a1, a2 = st.columns(2)
            if a1.button("Open", key=f"open_{page_key}_{b['id']}", use_container_width=True):
                qp_set(page=page_key, boat=b["id"])
                st.rerun()

            if (not public_mode) and can_sales() and b["status"] == "For Sale":
                if a2.button("Buyer PDF", key=f"pdf_{page_key}_{b['id']}", use_container_width=True):
                    qp_set(page=page_key, boat=b["id"], pdf="1")
                    st.rerun()
            else:
                a2.caption("")

            st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Boat details panel
# =========================
def render_boat_details(boat_id: int, public_mode: bool):
    boat = get_boat(boat_id)
    if not boat:
        st.warning("Boat not found.")
        return

    photos = get_photos(boat_id)
    docs = get_files(boat_id)

    st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
          <div>
            <div style="font-size:22px;font-weight:950;letter-spacing:-0.02em;color:#0B1220;">
              Boat #{boat['id']} — {boat['year'] or ''} {boat['make'] or ''} {boat['model'] or ''}
            </div>
            <div class="bh-sub">Category: <b>{boat['category']}</b> • Updated: {boat['updated_at']}</div>
          </div>
          <div>{badge_html(boat['status'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Buyer packet shortcut if requested
    if (not public_mode) and can_sales() and qp_get("pdf", "0") == "1":
        qp_set(pdf=None)
        if REPORTLAB_OK:
            pdf_bytes = generate_buyer_packet_pdf(boat_id)
            if pdf_bytes:
                st.download_button(
                    "Download Buyer Packet PDF",
                    data=pdf_bytes,
                    file_name=f"buyer_packet_boat_{boat_id}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                st.error("Could not generate PDF.")
        else:
            st.error("Buyer Packet needs reportlab. Add it to requirements.txt (see below).")

    if public_mode:
        tabs = st.tabs(["Overview", "Photos"])
    else:
        tabs = st.tabs(["Overview", "Photos", "Documents", "Edit"])

    # Overview
    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Stock #:** {boat['stock_number'] or '—'}")
            st.write(f"**HIN:** {boat['hin'] or '—'}")
            st.write(f"**Location:** {boat['location'] or '—'}")
            st.write(f"**Tags:** {boat['tags'] or '—'}")
        with c2:
            st.write(f"**Sale Price:** {money(boat['sale_price'])}")
            st.write(f"**MSRP:** {money(boat['msrp'])}")
            st.write(f"**Hours:** {boat['hours'] or '—'}")
            st.write(f"**Engine:** {boat['engine'] or '—'}")

        # Service fields (hide in public)
        if not public_mode:
            st.markdown("### Service")
            s1, s2 = st.columns(2)
            s1.write(f"**Stage:** {boat['service_stage'] or 'Intake'}")
            s1.write(f"**Due Date:** {boat['service_due_date'] or '—'}")
            s2.write(f"**Work Order #:** {boat['work_order'] or '—'}")
            s2.write(f"**Assigned Tech:** {boat['assigned_tech'] or '—'}")
            st.write(f"**Priority:** {boat['priority'] or 'Normal'}")

            st.markdown("### Customer")
            x1, x2 = st.columns(2)
            x1.write(f"**Name:** {boat['customer_name'] or '—'}")
            x2.write(f"**Phone:** {boat['customer_phone'] or '—'}")

            st.markdown("### Notes (internal)")
            st.write(boat["notes"] or "—")

        # Public description
        pub_desc = (boat["public_description"] or "").strip()
        if public_mode:
            st.markdown("### Description")
            st.write(pub_desc or "Call for details.")
            if PUBLIC_CONTACT:
                st.markdown("### Contact")
                st.write(PUBLIC_CONTACT)
        else:
            st.markdown("### Public description (shows on public for-sale link)")
            st.write(pub_desc or "—")

    # Photos
    with tabs[1]:
        st.markdown("### Gallery")
        if photos:
            cols = st.columns(3)
            for i, p in enumerate(photos):
                path = os.path.join(PHOTOS_DIR, p["filename"])
                with cols[i % 3]:
                    if os.path.exists(path):
                        st.image(path, use_container_width=True)
                    else:
                        st.warning("Missing file on disk.")
                    if not public_mode:
                        if st.button("Delete photo", key=f"delphoto_{p['id']}", use_container_width=True):
                            delete_photo(p["id"])
                            st.rerun()
        else:
            st.info("No photos yet.")

        if not public_mode:
            st.markdown("---")
            st.markdown("### Upload more photos")
            more = st.file_uploader(
                "Select photos",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key=f"more_photos_{boat_id}",
            )
            if more and st.button("Save uploaded photos", use_container_width=True, key=f"save_more_{boat_id}"):
                n = save_uploaded_images(boat_id, boat["make"], boat["model"], more)
                st.success(f"Uploaded {n} photo(s).")
                st.rerun()

    if public_mode:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Documents
    with tabs[2]:
        st.markdown("### Documents (Warranty / Invoice / Service Order / etc.)")
        view_cat = st.selectbox("View document type", ["All"] + DOC_CATEGORIES, index=0, key=f"view_cat_{boat_id}")
        shown = docs if view_cat == "All" else [d for d in docs if d["category"] == view_cat]

        if shown:
            for d in shown:
                boat_folder = os.path.join(FILES_DIR, str(boat_id))
                file_path = os.path.join(boat_folder, d["filename"])
                ext = (d["ext"] or "").lower()
                title = d["original_name"]

                st.markdown(f"**{title}**")
                st.caption(f"Type: {d['category']} • Uploaded: {d['uploaded_at']}")

                if ext in IMAGE_EXTS and os.path.exists(file_path):
                    st.image(file_path, use_container_width=True)

                b1, b2 = st.columns([1, 1])
                with b1:
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as fp:
                            st.download_button(
                                "Download",
                                data=fp.read(),
                                file_name=safe_filename(title),
                                mime="application/octet-stream",
                                use_container_width=True,
                                key=f"dl_{d['id']}",
                            )
                    else:
                        st.warning("Missing file on disk")
                with b2:
                    if st.button("Delete", key=f"deldoc_{d['id']}", use_container_width=True):
                        delete_file(d["id"])
                        st.rerun()

                st.markdown("---")
        else:
            st.info("No documents uploaded yet for this boat.")

        st.markdown("### Upload new documents")
        up_cat = st.selectbox("Document type", DOC_CATEGORIES, index=0, key=f"upload_cat_{boat_id}")
        uploads = st.file_uploader(
            "Choose files",
            type=["pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key=f"doc_upload_{boat_id}",
        )
        if uploads and st.button("Save documents", use_container_width=True, key=f"save_docs_{boat_id}"):
            n = save_uploaded_docs(boat_id, boat["make"], boat["model"], up_cat, uploads)
            st.success(f"Uploaded {n} file(s).")
            st.rerun()

    # Edit
    with tabs[3]:
        st.markdown("### Edit boat")

        categories_for_form = sorted(set(DEFAULT_CATEGORIES + distinct_values("category")))

        # Role-based editing (simple)
        # Sales can edit pricing + public + basic; Service can edit service fields + customer; Admin can edit everything.
        disable_sales_fields = not can_sales()
        disable_service_fields = not can_service()

        with st.form(f"edit_form_{boat_id}"):
            top1, top2 = st.columns(2)
            with top1:
                status_in = st.selectbox("Status", STATUSES, index=max(0, STATUSES.index(boat["status"])), disabled=is_public())
                category_in = st.selectbox(
                    "Category",
                    categories_for_form + ["Custom (type below)"],
                    index=max(0, categories_for_form.index(boat["category"]) if boat["category"] in categories_for_form else 0),
                    disabled=is_public(),
                )
                category_custom = ""
                if category_in == "Custom (type below)":
                    category_custom = st.text_input("Custom category name", value=(boat["category"] or ""), disabled=is_public())
            with top2:
                make_in = st.text_input("Make", value=boat["make"] or "", disabled=is_public())
                model_in = st.text_input("Model", value=boat["model"] or "", disabled=is_public())
                year_in = st.number_input("Year", min_value=1900, max_value=2100, value=int(boat["year"] or datetime.now().year), step=1, disabled=is_public())

            a1, a2 = st.columns(2)
            stock_in = a1.text_input("Stock #", value=boat["stock_number"] or "", disabled=is_public())
            hin_in = a2.text_input("HIN", value=boat["hin"] or "", disabled=is_public())

            b1, b2 = st.columns(2)
            location_in = b1.text_input("Location", value=boat["location"] or "", disabled=is_public())
            tags_in = b2.text_input("Tags", value=boat["tags"] or "", disabled=is_public())

            st.markdown("### Sales")
            s1, s2 = st.columns(2)
            sale_price_in = s1.number_input("Sale Price", min_value=0.0, value=float(boat["sale_price"] or 0.0), step=500.0, disabled=disable_sales_fields)
            msrp_in = s2.number_input("MSRP", min_value=0.0, value=float(boat["msrp"] or 0.0), step=500.0, disabled=disable_sales_fields)

            st.markdown("### Service")
            sv1, sv2 = st.columns(2)
            stage_in = sv1.selectbox("Service Stage", SERVICE_STAGES, index=max(0, SERVICE_STAGES.index((boat["service_stage"] or "Intake"))), disabled=disable_service_fields)
            due_default = parse_yyyy_mm_dd(boat["service_due_date"] or "") or date.today()
            due_in = sv2.date_input("Service Due Date", value=due_default, disabled=disable_service_fields)

            sv3, sv4 = st.columns(2)
            work_order_in = sv3.text_input("Work Order #", value=boat["work_order"] or "", disabled=disable_service_fields)
            tech_in = sv4.text_input("Assigned Tech", value=boat["assigned_tech"] or "", disabled=disable_service_fields)

            sv5, sv6 = st.columns(2)
            priority_in = sv5.selectbox("Priority", PRIORITIES, index=max(0, PRIORITIES.index((boat["priority"] or "Normal"))), disabled=disable_service_fields)
            hours_in = sv6.number_input("Hours", min_value=0.0, value=float(boat["hours"] or 0.0), step=1.0, disabled=disable_service_fields)

            st.markdown("### Customer")
            c1, c2 = st.columns(2)
            cust_name_in = c1.text_input("Customer name", value=boat["customer_name"] or "", disabled=disable_service_fields)
            cust_phone_in = c2.text_input("Customer phone", value=boat["customer_phone"] or "", disabled=disable_service_fields)

            notes_in = st.text_area("Internal notes", value=boat["notes"] or "", height=120, disabled=disable_service_fields)

            st.markdown("### Public For-Sale Website")
            pub1, pub2 = st.columns(2)
            pub_hide_in = pub1.checkbox("Hide this boat from public site", value=bool(boat["public_hide"] or 0), disabled=disable_sales_fields)
            pub_desc_in = st.text_area("Public description", value=boat["public_description"] or "", height=120, disabled=disable_sales_fields)

            save = st.form_submit_button("Save changes", use_container_width=True, disabled=is_public())

        if save:
            final_cat = category_custom.strip() if category_in == "Custom (type below)" else category_in
            final_cat = (final_cat or "").strip() or "Uncategorized"

            # Completed stage sets completed date automatically (nice)
            completed_at = boat["service_completed_at"]
            if stage_in == "Completed" and not completed_at:
                completed_at = now_iso()
            if stage_in != "Completed":
                completed_at = None

            update_fields(boat_id, {
                "status": status_in,
                "category": final_cat,
                "make": make_in.strip(),
                "model": model_in.strip(),
                "year": int(year_in) if year_in else None,
                "stock_number": stock_in.strip() or None,
                "hin": hin_in.strip() or None,
                "location": location_in.strip() or None,
                "tags": tags_in.strip() or None,
                "sale_price": float(sale_price_in) if sale_price_in and float(sale_price_in) > 0 else None,
                "msrp": float(msrp_in) if msrp_in and float(msrp_in) > 0 else None,
                "service_stage": stage_in,
                "service_due_date": due_in.isoformat() if due_in else None,
                "service_completed_at": completed_at,
                "work_order": work_order_in.strip() or None,
                "assigned_tech": tech_in.strip() or None,
                "priority": priority_in,
                "hours": float(hours_in) if hours_in and float(hours_in) > 0 else None,
                "customer_name": cust_name_in.strip() or None,
                "customer_phone": cust_phone_in.strip() or None,
                "notes": notes_in.strip() or None,
                "public_hide": 1 if pub_hide_in else 0,
                "public_description": pub_desc_in.strip() or None,
            })
            st.success("Saved.")
            st.rerun()

        st.markdown("---")
        st.markdown("### Boat packet + Delete")
        z1, z2 = st.columns(2)
        if z1.button("Download Boat Packet ZIP", use_container_width=True):
            z = zip_one_boat(boat_id)
            st.download_button(
                "Download ZIP now",
                data=z,
                file_name=f"boat_{boat_id}_packet.zip",
                mime="application/zip",
                use_container_width=True,
                key=f"zip_dl_{boat_id}",
            )
        if can_admin():
            confirm = st.text_input("Type DELETE to confirm deletion", value="", key=f"del_confirm_{boat_id}")
            if st.button("Delete this boat (and all files)", type="primary", use_container_width=True, key=f"del_btn_{boat_id}"):
                if confirm.strip().upper() != "DELETE":
                    st.error("Type DELETE first.")
                else:
                    delete_boat(boat_id)
                    st.warning("Boat deleted.")
                    qp_set(boat=None)
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Service Board (Kanban)
# =========================
def render_service_board():
    st.markdown('<div class="bh-card">', unsafe_allow_html=True)
    st.markdown("## Service Board (Technician Workload)")
    st.caption("Move jobs through stages. Due date alerts show overdue / due soon.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.write("")

    rows = service_boats_all()
    today = date.today()
    soon_cutoff = today + timedelta(days=3)

    overdue_list = []
    due_soon_list = []
    for b in rows:
        if (b["service_stage"] or "Intake") == "Completed":
            continue
        d = parse_yyyy_mm_dd(b["service_due_date"] or "")
        if not d:
            continue
        if d < today:
            overdue_list.append(b)
        elif today <= d <= soon_cutoff:
            due_soon_list.append(b)

    a1, a2, a3 = st.columns(3)
    a1.markdown(f'<span class="bh-pill">Overdue: {len(overdue_list)}</span>', unsafe_allow_html=True)
    a2.markdown(f'<span class="bh-pill">Due soon (3 days): {len(due_soon_list)}</span>', unsafe_allow_html=True)
    a3.markdown(f'<span class="bh-pill">Total service boats: {len(rows)}</span>', unsafe_allow_html=True)

    st.write("")
    mode = st.selectbox("View mode", ["Board", "List"], index=0)

    def stage_of(b):
        return (b["service_stage"] or "Intake").strip() or "Intake"

    if mode == "List":
        table = []
        for b in rows:
            table.append({
                "ID": b["id"],
                "Boat": f"{b['year'] or ''} {b['make'] or ''} {b['model'] or ''}".strip(),
                "Stage": stage_of(b),
                "Due": b["service_due_date"] or "",
                "Priority": b["priority"] or "Normal",
                "Tech": b["assigned_tech"] or "",
                "WO": b["work_order"] or "",
                "Customer": b["customer_name"] or "",
            })
        st.dataframe(table, use_container_width=True, hide_index=True, height=520)
        st.info("Tap a boat in the main pages to edit details, or use the board view to move stages.")
        return

    # Board view
    cols = st.columns(len(SERVICE_STAGES))
    by_stage = {s: [] for s in SERVICE_STAGES}
    for b in rows:
        s = stage_of(b)
        if s not in by_stage:
            s = "Intake"
        by_stage[s].append(b)

    for idx, stage in enumerate(SERVICE_STAGES):
        with cols[idx]:
            st.markdown(f"### {stage}")
            stage_rows = by_stage.get(stage, [])
            # show most urgent first: overdue then due soon
            def urgency_key(b):
                d = parse_yyyy_mm_dd(b["service_due_date"] or "")
                pr = PRIORITIES.index(b["priority"] or "Normal") if (b["priority"] or "Normal") in PRIORITIES else 1
                # overdue first
                overdue_flag = 0
                if d and d < today:
                    overdue_flag = -2
                elif d and d <= soon_cutoff:
                    overdue_flag = -1
                return (overdue_flag, -pr, b["service_due_date"] or "9999-12-31")
            stage_rows = sorted(stage_rows, key=urgency_key)

            for b in stage_rows:
                boat_id = int(b["id"])
                title = f"#{boat_id} {b['make']} {b['model']}"
                due = parse_yyyy_mm_dd(b["service_due_date"] or "")
                overdue_txt = ""
                if due:
                    if due < today:
                        overdue_txt = "⚠️ OVERDUE"
                    elif due <= soon_cutoff:
                        overdue_txt = "⏳ Due soon"

                with st.expander(f"{title} • {b['priority'] or 'Normal'} {overdue_txt}".strip()):
                    st.write(f"**Customer:** {b['customer_name'] or '—'}")
                    st.write(f"**Work Order:** {b['work_order'] or '—'}")
                    st.write(f"**Tech:** {b['assigned_tech'] or '—'}")
                    st.write(f"**Due:** {b['service_due_date'] or '—'}")

                    # quick controls
                    st_stage = st.selectbox("Stage", SERVICE_STAGES, index=max(0, SERVICE_STAGES.index(stage_of(b))), key=f"sb_stage_{boat_id}")
                    st_due = st.date_input("Due date", value=due or today, key=f"sb_due_{boat_id}")
                    st_tech = st.text_input("Tech", value=b["assigned_tech"] or "", key=f"sb_tech_{boat_id}")
                    st_wo = st.text_input("Work Order", value=b["work_order"] or "", key=f"sb_wo_{boat_id}")
                    st_pr = st.selectbox("Priority", PRIORITIES, index=max(0, PRIORITIES.index((b["priority"] or "Normal"))), key=f"sb_pr_{boat_id}")

                    u1, u2 = st.columns(2)
                    if u1.button("Save", use_container_width=True, key=f"sb_save_{boat_id}", disabled=not can_service()):
                        completed_at = b["service_completed_at"]
                        if st_stage == "Completed" and not completed_at:
                            completed_at = now_iso()
                        if st_stage != "Completed":
                            completed_at = None

                        update_fields(boat_id, {
                            "service_stage": st_stage,
                            "service_due_date": st_due.isoformat() if st_due else None,
                            "assigned_tech": st_tech.strip() or None,
                            "work_order": st_wo.strip() or None,
                            "priority": st_pr,
                            "service_completed_at": completed_at,
                        })
                        st.success("Updated.")
                        st.rerun()

                    if u2.button("Open Boat", use_container_width=True, key=f"sb_open_{boat_id}"):
                        qp_set(page="service_list", boat=str(boat_id))
                        st.rerun()


# =========================
# Add New Boat
# =========================
def render_add_boat():
    st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
    st.markdown("## Add New Boat")

    categories_for_form = sorted(set(DEFAULT_CATEGORIES + distinct_values("category")))

    # Service users: default to Service + Customer Service
    default_category = "Service" if can_service() and not can_sales() else "Inventory - New"
    default_status = "Customer Service" if can_service() and not can_sales() else "For Sale"

    with st.form("add_boat_form"):
        cat_pick = st.selectbox("Category", categories_for_form + ["Custom (type below)"], index=max(0, (categories_for_form + ["Custom (type below)"]).index(default_category) if default_category in categories_for_form else 0))
        cat_custom = ""
        if cat_pick == "Custom (type below)":
            cat_custom = st.text_input("Custom category name")

        status_in = st.selectbox("Status", STATUSES, index=max(0, STATUSES.index(default_status)))

        c1, c2 = st.columns(2)
        make = c1.text_input("Make *")
        model = c2.text_input("Model *")

        c3, c4 = st.columns(2)
        year = c3.number_input("Year", min_value=1900, max_value=2100, value=datetime.now().year, step=1)
        stock_number = c4.text_input("Stock # (optional)")

        c5, c6 = st.columns(2)
        hin = c5.text_input("HIN / Serial (optional)")
        location = c6.text_input("Location (optional)", value="Showroom")

        tags = st.text_input("Tags (optional)")

        st.markdown("### Sales (optional)")
        s1, s2 = st.columns(2)
        sale_price = s1.number_input("Sale Price", min_value=0.0, value=0.0, step=500.0, disabled=not can_sales())
        msrp = s2.number_input("MSRP", min_value=0.0, value=0.0, step=500.0, disabled=not can_sales())

        st.markdown("### Service (optional)")
        sv1, sv2 = st.columns(2)
        stage = sv1.selectbox("Service Stage", SERVICE_STAGES, index=0, disabled=not can_service())
        due = sv2.date_input("Service Due Date", value=date.today(), disabled=not can_service())

        sv3, sv4 = st.columns(2)
        work_order = sv3.text_input("Work Order #", disabled=not can_service())
        assigned_tech = sv4.text_input("Assigned Tech", disabled=not can_service())

        sv5, sv6 = st.columns(2)
        priority = sv5.selectbox("Priority", PRIORITIES, index=1, disabled=not can_service())
        hours = sv6.number_input("Hours", min_value=0.0, value=0.0, step=1.0, disabled=not can_service())

        st.markdown("### Customer (service)")
        cc1, cc2 = st.columns(2)
        customer_name = cc1.text_input("Customer name", disabled=not can_service())
        customer_phone = cc2.text_input("Customer phone", disabled=not can_service())

        notes = st.text_area("Internal notes", height=120, disabled=not can_service())

        st.markdown("### Public For-Sale Website")
        pub_hide = st.checkbox("Hide from public site", value=False, disabled=not can_sales())
        pub_desc = st.text_area("Public description", height=120, disabled=not can_sales())

        uploaded = st.file_uploader("Upload photos (multi-select)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

        submitted = st.form_submit_button("Create Boat", use_container_width=True)

    if submitted:
        final_cat = (cat_custom.strip() if cat_pick == "Custom (type below)" else cat_pick).strip() or "Uncategorized"
        if not make.strip() or not model.strip():
            st.error("Make and Model are required.")
        else:
            if boat_exists(hin, stock_number):
                st.warning("Heads up: A boat already exists with that HIN or Stock #. Double-check before continuing.")

            completed_at = None
            if stage == "Completed":
                completed_at = now_iso()

            boat_id = insert_boat({
                "stock_number": stock_number.strip() or None,
                "year": int(year) if year else None,
                "make": make.strip(),
                "model": model.strip(),
                "hin": hin.strip() or None,
                "length_ft": None,
                "engine": None,
                "location": location.strip() or None,
                "status": status_in,
                "category": final_cat,
                "tags": tags.strip() or None,
                "sale_price": float(sale_price) if can_sales() and float(sale_price) > 0 else None,
                "msrp": float(msrp) if can_sales() and float(msrp) > 0 else None,
                "hours": float(hours) if can_service() and float(hours) > 0 else None,
                "work_order": work_order.strip() or None,
                "assigned_tech": assigned_tech.strip() or None,
                "priority": priority if can_service() else "Normal",
                "service_stage": stage if can_service() else None,
                "service_due_date": due.isoformat() if can_service() and due else None,
                "service_completed_at": completed_at,
                "customer_name": customer_name.strip() or None,
                "customer_phone": customer_phone.strip() or None,
                "notes": notes.strip() or None,
                "public_description": pub_desc.strip() or None,
                "public_hide": 1 if pub_hide else 0,
            })

            if uploaded:
                n = save_uploaded_images(boat_id, make, model, uploaded)
                st.success(f"Created Boat #{boat_id}. Uploaded {n} photo(s).")
            else:
                st.success(f"Created Boat #{boat_id}.")

            st.info("Use the dropdown at the top to go to the right page (For Sale / Service / etc.).")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Tools page
# =========================
def render_tools(current_rows):
    st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
    st.markdown("## Tools / Export / Backup")

    st.markdown("### Export what you're viewing (CSV)")
    st.download_button(
        "Download CSV",
        data=boats_to_csv_bytes(current_rows),
        file_name=f"boathub_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.markdown("---")
    st.markdown("### Download ONE boat packet (ZIP)")
    st.caption("Includes that boat’s photos + documents + summary text file.")
    boat_id_for_zip = st.number_input("Boat ID", min_value=1, value=int(qp_get("boat", "1") or "1"), step=1)
    if st.button("Generate ZIP", use_container_width=True):
        z = zip_one_boat(int(boat_id_for_zip))
        if not z:
            st.error("Boat not found.")
        else:
            st.download_button(
                "Download ZIP now",
                data=z,
                file_name=f"boat_{boat_id_for_zip}_packet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                use_container_width=True,
            )

    if can_admin():
        st.markdown("---")
        st.markdown("### Backup database (boats.db)")
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as fp:
                st.download_button(
                    "Download boats.db backup",
                    data=fp.read(),
                    file_name=f"boats_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/octet-stream",
                    use_container_width=True,
                )

    st.markdown("---")
    st.markdown("### Buyer Packet PDF support")
    if REPORTLAB_OK:
        st.success("PDF is enabled (reportlab installed).")
    else:
        st.warning("PDF not enabled. Add `reportlab` to requirements.txt (see below).")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Public link page
# =========================
def render_public_link():
    st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
    st.markdown("## Public For-Sale Link")

    if not PUBLIC_TOKEN:
        st.warning("Set an environment variable on Render named **BOATHUB_PUBLIC_TOKEN** to enable the public site.")
        st.caption("Example token: 9x8s7a6k5p4q3w2e (any long random string).")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.success("Public mode is enabled.")

    st.markdown("### Your public pages (share these links)")
    st.caption("These links show ONLY boats with Status = For Sale AND Public Hide = OFF.")

    # We can’t know your domain here; you will copy your site base URL and paste this query.
    token_query = f"?public=1&token={PUBLIC_TOKEN}&page=public_for_sale_all"
    token_query_new = f"?public=1&token={PUBLIC_TOKEN}&page=public_for_sale_new"
    token_query_used = f"?public=1&token={PUBLIC_TOKEN}&page=public_for_sale_used"

    st.code(token_query, language="text")
    st.code(token_query_new, language="text")
    st.code(token_query_used, language="text")

    st.markdown("### How to use it (simple)")
    st.write("1) Copy your Render site URL (example: https://YOURAPP.onrender.com)")
    st.write("2) Paste one of the query strings above after it.")
    st.write("3) Send that full link to customers.")

    if PUBLIC_CONTACT:
        st.markdown("### Public contact info currently set")
        st.write(PUBLIC_CONTACT)
    else:
        st.info("Optional: set **BOATHUB_PUBLIC_CONTACT** to show phone/address on public pages.")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Browse page renderer (cards + table + details)
# =========================
def render_browse_page(view_key: str, public_mode: bool):
    cfg = (PUBLIC_VIEW_CONFIG.get(view_key) if public_mode else VIEW_CONFIG.get(view_key)) or {"title": "Boats", "where": "", "params": []}
    where = cfg.get("where", "")
    params = cfg.get("params", [])

    rows = list_boats(where, params, search_text, sort_mode, public_mode=public_mode)

    st.markdown('<div class="bh-card">', unsafe_allow_html=True)
    st.markdown(f"## {cfg['title']}")
    st.caption(f"{len(rows)} boat(s).")
    st.markdown("</div>", unsafe_allow_html=True)
    st.write("")

    if not rows:
        st.info("No boats on this page yet.")
        return rows

    # Determine selected boat
    boat_param = qp_get("boat", "")
    selected_id = int(rows[0]["id"])
    if boat_param.strip().isdigit():
        maybe = int(boat_param.strip())
        if any(int(b["id"]) == maybe for b in rows):
            selected_id = maybe

    left, right = st.columns([1.20, 2.00], gap="large")

    with left:
        st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
        st.markdown("### Boats")

        if view_mode == "Cards":
            # show cards (this is the wow upgrade)
            render_cards(rows[:60], public_mode=public_mode)
            if len(rows) > 60:
                st.caption("Showing first 60 boats in card view (use search to narrow).")
        else:
            table = []
            for b in rows[:400]:
                table.append({
                    "ID": b["id"],
                    "Year": b["year"],
                    "Make": b["make"],
                    "Model": b["model"],
                    "Status": b["status"],
                    "Category": b["category"],
                    "Price": money(b["sale_price"]) if (b["sale_price"] or 0) > 0 else money(b["msrp"]),
                    "Location": b["location"] or "",
                })
            st.dataframe(table, use_container_width=True, hide_index=True, height=420)

        st.markdown("---")
        labels = []
        id_by_label = {}
        for b in rows:
            label = f"#{b['id']} • {b['year'] or ''} {b['make']} {b['model']} • {b['status']} • {b['category']}"
            labels.append(label)
            id_by_label[label] = int(b["id"])

        pick = st.selectbox("Open a boat", labels, index=labels.index(next(l for l in labels if id_by_label[l] == selected_id)))
        if id_by_label[pick] != selected_id:
            qp_set(page=view_key, boat=id_by_label[pick])
            st.rerun()

        st.markdown("---")
        st.download_button(
            "Download THIS page as CSV",
            data=boats_to_csv_bytes(rows),
            file_name=f"boathub_{view_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        render_boat_details(selected_id, public_mode=public_mode)

    return rows


# =========================
# ROUTER
# =========================
if page_key == "dashboard" and not is_public():
    render_dashboard()
    current_rows_for_tools = list_boats("", [], "", "Recently Updated", public_mode=False)

elif page_key == "service_board" and not is_public():
    render_service_board()
    current_rows_for_tools = service_boats_all()

elif page_key == "add" and not is_public():
    render_add_boat()
    current_rows_for_tools = list_boats("", [], "", "Recently Updated", public_mode=False)

elif page_key == "tools" and not is_public():
    # tools needs something for CSV; if you're on tools directly, just export all boats
    current_rows_for_tools = list_boats("", [], "", "Recently Updated", public_mode=False)
    render_tools(current_rows_for_tools)

elif page_key == "public_link" and not is_public():
    render_public_link()
    current_rows_for_tools = list_boats("status=?", ["For Sale"], "", "Recently Updated", public_mode=False)

elif is_public() and page_key in PUBLIC_VIEW_CONFIG:
    current_rows_for_tools = render_browse_page(page_key, public_mode=True)

elif (not is_public()) and page_key in VIEW_CONFIG:
    current_rows_for_tools = render_browse_page(page_key, public_mode=False)

elif is_public():
    # If public hits an invalid page
    qp_set(page="public_for_sale_all")
    st.rerun()

else:
    # fallback
    qp_set(page=default_page)
    st.rerun()