import os
import re
import csv
import io
import zipfile
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st
from PIL import Image

# =========================
# Page setup
# =========================
st.set_page_config(
    page_title="BoatHub",
    page_icon="🚤",
    layout="wide",
)

# =========================
# Login Gate (optional)
# =========================
def require_password():
    """
    If BOATHUB_PASSWORD is set (Render), app requires login.
    If not set (local), it won't block.
    """
    real_pw = os.environ.get("BOATHUB_PASSWORD", "").strip()
    if not real_pw:
        return

    if "authed" not in st.session_state:
        st.session_state.authed = False

    if st.session_state.authed:
        return

    st.markdown(
        """
        <div style="
            max-width:520px;margin:48px auto;padding:26px 26px;
            border-radius:22px;border:1px solid rgba(17,24,39,0.12);
            background:#ffffff; box-shadow:0 20px 60px rgba(15,23,42,0.10);">
          <div style="font-size:28px;font-weight:950;letter-spacing:-0.03em;">🔒 BoatHub Login</div>
          <div style="margin-top:6px;color:rgba(15,23,42,0.72);">Enter the shop password to continue.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pw = st.text_input("Password", type="password", label_visibility="collapsed")
    if st.button("Sign in", use_container_width=True):
        if pw == real_pw:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

require_password()

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
STATUSES = [
    "For Sale",
    "Customer Service",
    "On Hold",
    "Sold",
    "Delivered",
    "Storage",
    "Other",
]

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

DOC_CATEGORIES = [
    "Warranty",
    "Invoice",
    "Service Order",
    "Registration",
    "Manual",
    "Other",
]

ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

PRIORITIES = ["Low", "Normal", "High", "Urgent"]

BADGE_LABEL = {
    "For Sale": "FOR SALE",
    "Customer Service": "SERVICE",
    "On Hold": "ON HOLD",
    "Sold": "SOLD",
    "Delivered": "DELIVERED",
    "Storage": "STORAGE",
    "Other": "OTHER",
}

# Clean black/white badge styles: (bg, fg, border)
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
# CSS (Clean black/white premium)
# =========================
st.markdown(
    """
<style>
.stApp { background: #F6F7FB; }
.block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; max-width: 1480px; }

section[data-testid="stSidebar"] {
  background: #FFFFFF;
  border-right: 1px solid rgba(17,24,39,0.10);
}

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; height: 0; }

.bh-title {
  font-size: 30px;
  font-weight: 950;
  letter-spacing: -0.035em;
  margin: 0;
  color: #0B1220;
}
.bh-sub {
  margin-top: 6px;
  color: rgba(15,23,42,0.70);
  font-size: 13px;
}
.bh-kicker {
  font-size: 12px;
  letter-spacing: 0.12em;
  font-weight: 800;
  color: rgba(15,23,42,0.55);
  text-transform: uppercase;
}

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

.bh-stats {
  display:grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.bh-stat {
  background: #FFFFFF;
  border: 1px solid rgba(17,24,39,0.10);
  border-radius: 18px;
  box-shadow: 0 14px 40px rgba(15,23,42,0.06);
  padding: 14px 14px;
}
.bh-stat-k {
  color: rgba(15,23,42,0.60);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.10em;
  text-transform: uppercase;
}
.bh-stat-v {
  margin-top: 6px;
  font-size: 30px;
  font-weight: 950;
  letter-spacing: -0.02em;
  color: #0B1220;
}
@media (max-width: 1100px){
  .bh-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 768px){
  .bh-stats { grid-template-columns: 1fr; }
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
  input, textarea { font-size: 16px !important; } /* stops iPhone zoom */
  div[data-testid="stHorizontalBlock"] { flex-direction: column !important; }
  div[data-testid="column"] { width: 100% !important; }
}

.stTabs [data-baseweb="tab"] { font-weight: 900; }
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# DB helpers + migrations
# =========================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # Helps multiple users a bit
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

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
            customer_name TEXT,
            customer_phone TEXT,
            notes TEXT,
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

        # ---- Migrations (adds new “best features” columns without deleting your data)
        ensure_column(conn, "boats", "category", "TEXT")
        ensure_column(conn, "boats", "tags", "TEXT")
        ensure_column(conn, "boats", "sale_price", "REAL")
        ensure_column(conn, "boats", "msrp", "REAL")
        ensure_column(conn, "boats", "hours", "REAL")
        ensure_column(conn, "boats", "work_order", "TEXT")
        ensure_column(conn, "boats", "assigned_tech", "TEXT")
        ensure_column(conn, "boats", "priority", "TEXT")

        # Fill blanks so filtering works
        conn.execute("UPDATE boats SET category='Uncategorized' WHERE category IS NULL OR TRIM(category)=''")
        conn.execute("UPDATE boats SET priority='Normal' WHERE priority IS NULL OR TRIM(priority)=''")

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "boat"

def badge_html(status: str) -> str:
    bg, fg, border = BADGE_STYLE.get(status, ("#FFFFFF", "#111827", "#111827"))
    label = BADGE_LABEL.get(status, status.upper())
    return f'<span class="bh-badge" style="background:{bg};color:{fg};border:1px solid {border};">{label}</span>'

def distinct_values(col: str):
    with db() as conn:
        rows = conn.execute(f"SELECT DISTINCT {col} as v FROM boats WHERE {col} IS NOT NULL AND TRIM({col})<>'' ORDER BY {col}").fetchall()
        return [r["v"] for r in rows if r["v"] is not None]

# =========================
# CRUD
# =========================
def boat_exists(hin: str | None, stock: str | None) -> bool:
    hin = (hin or "").strip()
    stock = (stock or "").strip()
    if not hin and not stock:
        return False
    with db() as conn:
        if hin:
            r = conn.execute("SELECT 1 FROM boats WHERE hin=? LIMIT 1", (hin,)).fetchone()
            if r:
                return True
        if stock:
            r = conn.execute("SELECT 1 FROM boats WHERE stock_number=? LIMIT 1", (stock,)).fetchone()
            if r:
                return True
    return False

def insert_boat(data: dict) -> int:
    t = now_iso()
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO boats (
                stock_number, year, make, model, hin, length_ft, engine, location,
                status, category, tags, sale_price, msrp, hours, work_order, assigned_tech, priority,
                customer_name, customer_phone, notes, created_at, updated_at
            ) VALUES (
                :stock_number, :year, :make, :model, :hin, :length_ft, :engine, :location,
                :status, :category, :tags, :sale_price, :msrp, :hours, :work_order, :assigned_tech, :priority,
                :customer_name, :customer_phone, :notes, :created_at, :updated_at
            )
        """, {**data, "created_at": t, "updated_at": t})
        return int(cur.lastrowid)

def update_boat(boat_id: int, data: dict):
    t = now_iso()
    with db() as conn:
        conn.execute("""
            UPDATE boats SET
                stock_number=:stock_number,
                year=:year,
                make=:make,
                model=:model,
                hin=:hin,
                length_ft=:length_ft,
                engine=:engine,
                location=:location,
                status=:status,
                category=:category,
                tags=:tags,
                sale_price=:sale_price,
                msrp=:msrp,
                hours=:hours,
                work_order=:work_order,
                assigned_tech=:assigned_tech,
                priority=:priority,
                customer_name=:customer_name,
                customer_phone=:customer_phone,
                notes=:notes,
                updated_at=:updated_at
            WHERE id=:id
        """, {**data, "updated_at": t, "id": boat_id})

def get_boat(boat_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM boats WHERE id=?", (boat_id,)).fetchone()

def list_boats_filtered(
    query: str,
    statuses: list[str],
    categories: list[str],
    makes: list[str],
    year_min: int | None,
    year_max: int | None,
    only_with_photos: bool,
    only_with_docs: bool,
    sort_mode: str,
):
    q = f"%{query.strip()}%"
    conditions = []
    params: list = []

    if query.strip():
        conditions.append("""
        (
          make LIKE ? OR model LIKE ? OR hin LIKE ? OR stock_number LIKE ? OR customer_name LIKE ?
          OR category LIKE ? OR tags LIKE ?
        )
        """)
        params.extend([q, q, q, q, q, q, q])

    if statuses:
        placeholders = ",".join(["?"] * len(statuses))
        conditions.append(f"status IN ({placeholders})")
        params.extend(statuses)

    if categories:
        placeholders = ",".join(["?"] * len(categories))
        conditions.append(f"category IN ({placeholders})")
        params.extend(categories)

    if makes:
        placeholders = ",".join(["?"] * len(makes))
        conditions.append(f"make IN ({placeholders})")
        params.extend(makes)

    if year_min is not None and year_max is not None:
        conditions.append("(year IS NOT NULL AND year BETWEEN ? AND ?)")
        params.extend([year_min, year_max])

    if only_with_photos:
        conditions.append("EXISTS (SELECT 1 FROM boat_photos bp WHERE bp.boat_id = boats.id)")

    if only_with_docs:
        conditions.append("EXISTS (SELECT 1 FROM boat_files bf WHERE bf.boat_id = boats.id)")

    where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    order_map = {
        "Recently Updated": "updated_at DESC",
        "Year (Newest)": "year DESC, updated_at DESC",
        "Year (Oldest)": "year ASC, updated_at DESC",
        "Make (A-Z)": "make ASC, model ASC, year DESC",
        "Status": "status ASC, updated_at DESC",
        "Category": "category ASC, updated_at DESC",
    }
    order_sql = order_map.get(sort_mode, "updated_at DESC")

    with db() as conn:
        return conn.execute(f"SELECT * FROM boats {where_sql} ORDER BY {order_sql}", tuple(params)).fetchall()

# =========================
# Photos
# =========================
def add_photo(boat_id: int, filename: str):
    with db() as conn:
        conn.execute("INSERT INTO boat_photos (boat_id, filename, uploaded_at) VALUES (?, ?, ?)",
                     (boat_id, filename, now_iso()))

def get_photos(boat_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM boat_photos WHERE boat_id=? ORDER BY uploaded_at DESC", (boat_id,)).fetchall()

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
# Documents / Files
# =========================
def add_file(boat_id: int, filename: str, original_name: str, category: str, ext: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO boat_files (boat_id, filename, original_name, category, ext, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (boat_id, filename, original_name, category, ext, now_iso()))

def get_files(boat_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM boat_files WHERE boat_id=? ORDER BY uploaded_at DESC", (boat_id,)).fetchall()

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

def delete_boat(boat_id: int):
    photos = get_photos(boat_id)

    with db() as conn:
        conn.execute("DELETE FROM boats WHERE id=?", (boat_id,))

    for p in photos:
        path = os.path.join(PHOTOS_DIR, p["filename"])
        if os.path.exists(path):
            try:
                os.remove(path)
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
# Exports / Backups
# =========================
def boats_to_csv_bytes(rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "id","year","make","model","status","category","stock_number","hin","location",
        "sale_price","msrp","hours","work_order","assigned_tech","priority","customer_name","customer_phone","tags","updated_at"
    ])
    for b in rows:
        w.writerow([
            b["id"], b["year"], b["make"], b["model"], b["status"], b["category"], b["stock_number"], b["hin"], b["location"],
            b["sale_price"], b["msrp"], b["hours"], b["work_order"], b["assigned_tech"], b["priority"],
            b["customer_name"], b["customer_phone"], b["tags"], b["updated_at"]
        ])
    return out.getvalue().encode("utf-8")

def zip_one_boat(boat_id: int) -> bytes:
    """
    Creates a ZIP containing:
    - Photos for that boat
    - Documents for that boat
    """
    boat = get_boat(boat_id)
    if not boat:
        return b""

    photos = get_photos(boat_id)
    docs = get_files(boat_id)

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Photos (stored as filenames)
        for p in photos:
            p_path = os.path.join(PHOTOS_DIR, p["filename"])
            if os.path.exists(p_path):
                z.write(p_path, arcname=f"photos/{p['filename']}")

        # Docs (stored in files/<boat_id>/)
        boat_folder = os.path.join(FILES_DIR, str(boat_id))
        for d in docs:
            f_path = os.path.join(boat_folder, d["filename"])
            if os.path.exists(f_path):
                z.write(f_path, arcname=f"documents/{d['category']}/{d['original_name']}")

        # Simple text summary
        summary = (
            f"Boat #{boat['id']}\n"
            f"Year/Make/Model: {boat['year']} {boat['make']} {boat['model']}\n"
            f"Status: {boat['status']}\n"
            f"Category: {boat['category']}\n"
            f"Stock: {boat['stock_number']}\n"
            f"HIN: {boat['hin']}\n"
            f"Location: {boat['location']}\n"
            f"Updated: {boat['updated_at']}\n"
        )
        z.writestr("boat_summary.txt", summary)

    mem.seek(0)
    return mem.read()

# =========================
# Init DB
# =========================
init_db()

# =========================
# Header
# =========================
h1, h2 = st.columns([1.2, 4.8], vertical_alignment="center")
with h1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=240)
with h2:
    st.markdown(
        """
        <div class="bh-card">
          <div class="bh-kicker">Paradigm • Dealer Ops</div>
          <div class="bh-title">BoatHub</div>
          <div class="bh-sub">Browse by Category • Upload Photos + Documents • Export + Backup</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# =========================
# Sidebar Filters (Browse)
# =========================
with st.sidebar:
    st.markdown("### Browse Filters")

    search = st.text_input("Search", value="", placeholder="make, model, category, tags, HIN, stock, customer…")

    # Dynamic lists
    category_choices = sorted(set(DEFAULT_CATEGORIES + distinct_values("category")))
    make_choices = distinct_values("make")

    sel_categories = st.multiselect("Category", category_choices, default=category_choices)
    sel_statuses = st.multiselect("Status", STATUSES, default=STATUSES)

    sel_makes = st.multiselect("Make", make_choices, default=make_choices)

    only_photos = st.checkbox("Only boats WITH photos", value=False)
    only_docs = st.checkbox("Only boats WITH documents", value=False)

    # Year slider based on data
    years = [y for y in distinct_values("year") if isinstance(y, int)]
    if years:
        y_min, y_max = min(years), max(years)
        year_range = st.slider("Year range", min_value=int(y_min), max_value=int(y_max), value=(int(y_min), int(y_max)))
    else:
        year_range = None

    sort_mode = st.selectbox(
        "Sort",
        ["Recently Updated", "Year (Newest)", "Year (Oldest)", "Make (A-Z)", "Status", "Category"],
        index=0,
    )

    st.markdown("---")
    st.caption("Tip: Use the tabs on the main page to Browse / Add / Tools.")

# =========================
# Stats
# =========================
all_rows = list_boats_filtered(
    query="",
    statuses=STATUSES,
    categories=sorted(set(DEFAULT_CATEGORIES + distinct_values("category"))),
    makes=distinct_values("make"),
    year_min=None,
    year_max=None,
    only_with_photos=False,
    only_with_docs=False,
    sort_mode="Recently Updated",
)

total = len(all_rows)
for_sale = sum(1 for b in all_rows if b["status"] == "For Sale")
service = sum(1 for b in all_rows if b["status"] == "Customer Service")
sold = sum(1 for b in all_rows if b["status"] == "Sold")

st.markdown(
    f"""
    <div class="bh-stats">
      <div class="bh-stat"><div class="bh-stat-k">Total</div><div class="bh-stat-v">{total}</div></div>
      <div class="bh-stat"><div class="bh-stat-k">For Sale</div><div class="bh-stat-v">{for_sale}</div></div>
      <div class="bh-stat"><div class="bh-stat-k">Service</div><div class="bh-stat-v">{service}</div></div>
      <div class="bh-stat"><div class="bh-stat-k">Sold</div><div class="bh-stat-v">{sold}</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")

# =========================
# Main Tabs
# =========================
tab_browse, tab_add, tab_tools = st.tabs(["Browse Boats", "Add New Boat", "Tools / Export / Backup"])

# =========================
# Compute filtered browse rows
# =========================
year_min = year_range[0] if year_range else None
year_max = year_range[1] if year_range else None

filtered = list_boats_filtered(
    query=search,
    statuses=sel_statuses,
    categories=sel_categories,
    makes=sel_makes,
    year_min=year_min,
    year_max=year_max,
    only_with_photos=only_photos,
    only_with_docs=only_docs,
    sort_mode=sort_mode,
)

# =========================
# ADD TAB
# =========================
with tab_add:
    st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
    st.markdown("## Add a boat")

    # Category selector with “custom”
    existing_categories = sorted(set(DEFAULT_CATEGORIES + distinct_values("category")))
    category_pick = st.selectbox("Category", existing_categories + ["Custom (type below)"], index=0)
    category_custom = ""
    if category_pick == "Custom (type below)":
        category_custom = st.text_input("Custom category name")

    with st.form("add_boat_form"):
        status_in = st.selectbox("Status", STATUSES, index=0)

        c1, c2 = st.columns(2)
        make = c1.text_input("Make *")
        model = c2.text_input("Model *")

        c3, c4 = st.columns(2)
        year = c3.number_input("Year", min_value=1900, max_value=2100, value=datetime.now().year, step=1)
        stock_number = c4.text_input("Stock # (optional)")

        c5, c6 = st.columns(2)
        hin = c5.text_input("HIN / Serial (optional)")
        location = c6.text_input("Location (optional)", value="Showroom")

        tags = st.text_input("Tags (optional)", help="Example: blue, tri-toon, yamaha, warranty")

        st.markdown("### Optional Sales / Service fields")
        with st.expander("Open extra fields", expanded=False):
            e1, e2 = st.columns(2)
            sale_price = e1.number_input("Sale Price (optional)", min_value=0.0, value=0.0, step=500.0)
            msrp = e2.number_input("MSRP (optional)", min_value=0.0, value=0.0, step=500.0)

            e3, e4 = st.columns(2)
            hours = e3.number_input("Hours (optional)", min_value=0.0, value=0.0, step=1.0)
            priority = e4.selectbox("Priority", PRIORITIES, index=1)

            e5, e6 = st.columns(2)
            work_order = e5.text_input("Work Order # (optional)")
            assigned_tech = e6.text_input("Assigned Tech (optional)")

            e7, e8 = st.columns(2)
            length_ft = e7.number_input("Length (ft, optional)", min_value=0.0, max_value=200.0, value=0.0, step=0.5)
            engine = e8.text_input("Engine (optional)")

        st.markdown("### Customer (only if service)")
        c9, c10 = st.columns(2)
        customer_name = c9.text_input("Customer name (optional)")
        customer_phone = c10.text_input("Customer phone (optional)")

        notes = st.text_area("Notes", height=120)

        uploaded = st.file_uploader(
            "Upload photos (multi-select)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
        )

        submitted = st.form_submit_button("Create Boat", use_container_width=True)

    if submitted:
        final_category = (category_custom.strip() if category_pick == "Custom (type below)" else category_pick).strip()
        if not final_category:
            final_category = "Uncategorized"

        if not make.strip() or not model.strip():
            st.error("Make and Model are required.")
        else:
            # Duplicate warning (does NOT block, just warns)
            if boat_exists(hin, stock_number):
                st.warning("Heads up: A boat already exists with that HIN or Stock #. Double-check before continuing.")

            boat_id = insert_boat({
                "stock_number": stock_number.strip() or None,
                "year": int(year) if year else None,
                "make": make.strip(),
                "model": model.strip(),
                "hin": hin.strip() or None,
                "length_ft": float(locals().get("length_ft", 0.0)) or None,
                "engine": (locals().get("engine", "") or "").strip() or None,
                "location": location.strip() or None,
                "status": status_in,
                "category": final_category,
                "tags": tags.strip() or None,
                "sale_price": float(locals().get("sale_price", 0.0)) or None,
                "msrp": float(locals().get("msrp", 0.0)) or None,
                "hours": float(locals().get("hours", 0.0)) or None,
                "work_order": (locals().get("work_order", "") or "").strip() or None,
                "assigned_tech": (locals().get("assigned_tech", "") or "").strip() or None,
                "priority": (locals().get("priority", "Normal") or "Normal"),
                "customer_name": customer_name.strip() or None,
                "customer_phone": customer_phone.strip() or None,
                "notes": notes.strip() or None,
            })

            if uploaded:
                n = save_uploaded_images(boat_id, make, model, uploaded)
                st.success(f"Created Boat #{boat_id}. Uploaded {n} photo(s).")
            else:
                st.success(f"Created Boat #{boat_id}.")

            st.info("Now click the 'Browse Boats' tab to view it.")

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# BROWSE TAB
# =========================
with tab_browse:
    left, right = st.columns([1.05, 2.15], gap="large")

    with left:
        st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
        st.markdown("## Browse")
        st.caption(f"{len(filtered)} result(s) with your filters.")

        if not filtered:
            st.warning("No boats match your filters.")
            st.markdown("</div>", unsafe_allow_html=True)
            st.stop()

        labels = []
        id_by_label = {}
        for b in filtered:
            label = f"#{b['id']} • {b['year'] or ''} {b['make']} {b['model']} • {b['status']} • {b['category']}"
            labels.append(label)
            id_by_label[label] = b["id"]

        selected_label = st.selectbox("Select a boat", labels, index=0)
        selected_id = id_by_label[selected_label]

        st.markdown("</div>", unsafe_allow_html=True)

    boat = get_boat(selected_id)
    photos = get_photos(selected_id)
    docs = get_files(selected_id)

    with right:
        st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
              <div>
                <div style="font-size:22px;font-weight:950;letter-spacing:-0.02em;color:#0B1220;">
                  Boat #{boat['id']} — {boat['year'] or ''} {boat['make']} {boat['model']}
                </div>
                <div class="bh-sub">Category: <b>{boat['category']}</b> • Last updated: {boat['updated_at']}</div>
              </div>
              <div>{badge_html(boat['status'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_overview, tab_photos, tab_docs, tab_edit = st.tabs(["Overview", "Photos", "Documents", "Edit"])

        with tab_overview:
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Stock #:** {boat['stock_number'] or '—'}")
                st.write(f"**HIN:** {boat['hin'] or '—'}")
                st.write(f"**Location:** {boat['location'] or '—'}")
                st.write(f"**Tags:** {boat['tags'] or '—'}")
            with c2:
                st.write(f"**Sale Price:** {boat['sale_price'] or '—'}")
                st.write(f"**MSRP:** {boat['msrp'] or '—'}")
                st.write(f"**Hours:** {boat['hours'] or '—'}")
                st.write(f"**Priority:** {boat['priority'] or 'Normal'}")

            st.markdown("### Service")
            c3, c4 = st.columns(2)
            c3.write(f"**Work Order #:** {boat['work_order'] or '—'}")
            c4.write(f"**Assigned Tech:** {boat['assigned_tech'] or '—'}")

            st.markdown("### Customer")
            c5, c6 = st.columns(2)
            c5.write(f"**Name:** {boat['customer_name'] or '—'}")
            c6.write(f"**Phone:** {boat['customer_phone'] or '—'}")

            st.markdown("### Notes")
            st.write(boat["notes"] or "—")

        with tab_photos:
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
                        if st.button("Delete photo", key=f"delphoto_{p['id']}", use_container_width=True):
                            delete_photo(p["id"])
                            st.rerun()
            else:
                st.info("No photos yet.")

            st.markdown("---")
            st.markdown("### Upload more photos")
            more = st.file_uploader(
                "Select photos",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="more_photos",
            )
            if more and st.button("Save uploaded photos", use_container_width=True):
                n = save_uploaded_images(selected_id, boat["make"], boat["model"], more)
                st.success(f"Uploaded {n} photo(s).")
                st.rerun()

        with tab_docs:
            st.markdown("### Documents (Warranty / Invoice / Service Order / etc.)")

            ccat1, ccat2 = st.columns([2, 3])
            with ccat1:
                view_cat = st.selectbox("View category", ["All"] + DOC_CATEGORIES, index=0)
            with ccat2:
                st.caption("Allowed: PDF, DOC, DOCX, JPG/PNG/WEBP")

            shown = docs if view_cat == "All" else [d for d in docs if d["category"] == view_cat]

            if shown:
                for d in shown:
                    boat_folder = os.path.join(FILES_DIR, str(selected_id))
                    file_path = os.path.join(boat_folder, d["filename"])
                    ext = (d["ext"] or "").lower()
                    title = d["original_name"]

                    st.markdown(f"**{title}**")
                    st.caption(f"Category: {d['category']} • Uploaded: {d['uploaded_at']}")

                    if ext in IMAGE_EXTS and os.path.exists(file_path):
                        st.image(file_path, use_container_width=True)

                    b1, b2 = st.columns([1, 1])
                    with b1:
                        if os.path.exists(file_path):
                            with open(file_path, "rb") as fp:
                                st.download_button(
                                    "Download",
                                    data=fp.read(),
                                    file_name=title,
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
                st.info("No documents uploaded yet for this category.")

            st.markdown("### Upload new documents")
            up_cat = st.selectbox("Upload category", DOC_CATEGORIES, index=0, key="upload_cat")

            uploads = st.file_uploader(
                "Choose files",
                type=["pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="doc_upload",
            )

            if uploads and st.button("Save documents", use_container_width=True):
                n = save_uploaded_docs(selected_id, boat["make"], boat["model"], up_cat, uploads)
                st.success(f"Uploaded {n} file(s).")
                st.rerun()

        with tab_edit:
            st.markdown("### Edit boat details")

            # Category editor with custom option
            cat_list = sorted(set(DEFAULT_CATEGORIES + distinct_values("category")))
            cat_pick = st.selectbox("Category", cat_list + ["Custom (type below)"], index=max(0, cat_list.index(boat["category"]) if boat["category"] in cat_list else 0))
            cat_custom = ""
            if cat_pick == "Custom (type below)":
                cat_custom = st.text_input("Custom category name", value=boat["category"] if boat["category"] not in cat_list else "")

            with st.form("edit_form"):
                status_in = st.selectbox("Status", STATUSES, index=STATUSES.index(boat["status"]))

                e1, e2 = st.columns(2)
                make = e1.text_input("Make *", value=boat["make"] or "")
                model = e2.text_input("Model *", value=boat["model"] or "")

                e3, e4 = st.columns(2)
                year = e3.number_input("Year", min_value=1900, max_value=2100,
                                       value=int(boat["year"] or datetime.now().year), step=1)
                stock_number = e4.text_input("Stock #", value=boat["stock_number"] or "")

                e5, e6 = st.columns(2)
                hin = e5.text_input("HIN / Serial", value=boat["hin"] or "")
                location = e6.text_input("Location", value=boat["location"] or "")

                tags = st.text_input("Tags", value=boat["tags"] or "")

                st.markdown("### Optional Sales / Service fields")
                with st.expander("Open extra fields", expanded=False):
                    x1, x2 = st.columns(2)
                    sale_price = x1.number_input("Sale Price", min_value=0.0, value=float(boat["sale_price"] or 0.0), step=500.0)
                    msrp = x2.number_input("MSRP", min_value=0.0, value=float(boat["msrp"] or 0.0), step=500.0)

                    x3, x4 = st.columns(2)
                    hours = x3.number_input("Hours", min_value=0.0, value=float(boat["hours"] or 0.0), step=1.0)
                    priority = x4.selectbox("Priority", PRIORITIES, index=PRIORITIES.index(boat["priority"] or "Normal"))

                    x5, x6 = st.columns(2)
                    work_order = x5.text_input("Work Order #", value=boat["work_order"] or "")
                    assigned_tech = x6.text_input("Assigned Tech", value=boat["assigned_tech"] or "")

                st.markdown("### Customer")
                c9, c10 = st.columns(2)
                customer_name = c9.text_input("Customer name", value=boat["customer_name"] or "")
                customer_phone = c10.text_input("Customer phone", value=boat["customer_phone"] or "")

                notes = st.text_area("Notes", value=boat["notes"] or "", height=120)

                save = st.form_submit_button("Save changes", use_container_width=True)

            if save:
                if not make.strip() or not model.strip():
                    st.error("Make and Model are required.")
                else:
                    final_cat = (cat_custom.strip() if cat_pick == "Custom (type below)" else cat_pick).strip()
                    if not final_cat:
                        final_cat = "Uncategorized"

                    update_boat(selected_id, {
                        "stock_number": stock_number.strip() or None,
                        "year": int(year) if year else None,
                        "make": make.strip(),
                        "model": model.strip(),
                        "hin": hin.strip() or None,
                        "length_ft": boat["length_ft"],
                        "engine": boat["engine"],
                        "location": location.strip() or None,
                        "status": status_in,
                        "category": final_cat,
                        "tags": tags.strip() or None,
                        "sale_price": float(sale_price) if sale_price else None,
                        "msrp": float(msrp) if msrp else None,
                        "hours": float(hours) if hours else None,
                        "work_order": work_order.strip() or None,
                        "assigned_tech": assigned_tech.strip() or None,
                        "priority": priority or "Normal",
                        "customer_name": customer_name.strip() or None,
                        "customer_phone": customer_phone.strip() or None,
                        "notes": notes.strip() or None,
                    })
                    st.success("Saved.")
                    st.rerun()

            st.markdown("---")
            st.markdown("### Danger zone")
            confirm = st.text_input("Type DELETE to confirm boat deletion", value="", key="del_confirm")
            if st.button("Delete this boat (and all photos + documents)", type="primary", use_container_width=True):
                if confirm.strip().upper() != "DELETE":
                    st.error("Type DELETE in the box above first.")
                else:
                    delete_boat(selected_id)
                    st.warning("Boat deleted.")
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# =========================
# TOOLS TAB
# =========================
with tab_tools:
    st.markdown('<div class="bh-card-tight">', unsafe_allow_html=True)
    st.markdown("## Tools / Export / Backup")

    st.markdown("### Export filtered list (CSV)")
    csv_bytes = boats_to_csv_bytes(filtered)
    st.download_button(
        "Download CSV of current filtered boats",
        data=csv_bytes,
        file_name=f"boathub_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

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
    else:
        st.warning("Database file not found.")

    st.markdown("---")
    st.markdown("### Download ONE boat packet (ZIP)")
    st.caption("Includes that boat’s photos + documents + a summary text file.")
    boat_id_for_zip = st.number_input("Boat ID", min_value=1, value=int(filtered[0]["id"]) if filtered else 1, step=1)
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

    st.markdown("</div>", unsafe_allow_html=True)