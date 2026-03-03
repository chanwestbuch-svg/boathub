import os
import re
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
# Simple Login Gate
# =========================
def require_password():
    real_pw = os.environ.get("BOATHUB_PASSWORD", "").strip()
    if not real_pw:
        return

    if "authed" not in st.session_state:
        st.session_state.authed = False

    if st.session_state.authed:
        return

    st.markdown(
        """
        <div style="max-width:520px;margin:40px auto;padding:24px;border-radius:18px;
                    border:1px solid rgba(148,163,184,0.25);
                    background:rgba(255,255,255,0.06);
                    box-shadow:0 20px 50px rgba(0,0,0,0.25);">
          <div style="font-size:26px;font-weight:900;letter-spacing:-0.02em;">🔒 BoatHub Login</div>
          <div style="opacity:.75;margin-top:6px;">Enter the shop password to continue.</div>
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
STATUSES = ["For Sale", "Customer Service", "On Hold", "Sold", "Delivered", "Storage", "Other"]

STATUS_COLOR = {
    "For Sale": "#22C55E",
    "Customer Service": "#38BDF8",
    "On Hold": "#F59E0B",
    "Sold": "#A78BFA",
    "Delivered": "#10B981",
    "Storage": "#94A3B8",
    "Other": "#F472B6",
}

DOC_CATEGORIES = ["Warranty", "Invoice", "Service Order", "Registration", "Manual", "Other"]

ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# =========================
# Modern CSS
# =========================
st.markdown(
    """
<style>
/* Page background + spacing */
.stApp {
  background:
    radial-gradient(1200px 600px at 20% -10%, rgba(56,189,248,0.18), transparent 60%),
    radial-gradient(1000px 700px at 110% 10%, rgba(167,139,250,0.18), transparent 55%),
    radial-gradient(900px 500px at 20% 110%, rgba(34,197,94,0.12), transparent 55%),
    linear-gradient(180deg, rgba(3,7,18,1) 0%, rgba(8,12,24,1) 100%);
}

.block-container{
  padding-top: 1.25rem;
  padding-bottom: 2.5rem;
  max-width: 1480px;
}

/* Hide Streamlit chrome a bit */
header { visibility: hidden; height: 0; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Card styles */
.bh-surface{
  border-radius: 22px;
  border: 1px solid rgba(148,163,184,0.18);
  background: rgba(255,255,255,0.06);
  box-shadow: 0 18px 60px rgba(0,0,0,0.35);
}

.bh-panel{
  border-radius: 22px;
  border: 1px solid rgba(148,163,184,0.18);
  background: rgba(255,255,255,0.05);
  box-shadow: 0 14px 45px rgba(0,0,0,0.32);
  padding: 16px 16px;
}

.bh-title{
  font-size: 28px;
  font-weight: 950;
  letter-spacing: -0.03em;
  margin: 0;
}
.bh-sub{
  opacity: .74;
  font-size: 13px;
  margin-top: 4px;
}

/* Badge */
.bh-badge {
  display:inline-flex; align-items:center;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(0,0,0,0.22);
  font-weight: 900;
  font-size: 12px;
  letter-spacing: 0.10em;
}

/* Stat cards */
.bh-stats{
  display:grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.bh-stat{
  border-radius: 18px;
  border: 1px solid rgba(148,163,184,0.18);
  background: rgba(255,255,255,0.05);
  box-shadow: 0 12px 40px rgba(0,0,0,0.28);
  padding: 14px 14px;
}
.bh-stat-k{ opacity:.75; font-size:12px; }
.bh-stat-v{ font-size:30px; font-weight:950; letter-spacing:-0.02em; margin-top:4px; }

@media (max-width: 1100px){
  .bh-stats{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 768px){
  .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
  .bh-stats{ grid-template-columns: 1fr; }
  input, textarea { font-size:16px !important; } /* prevents iPhone zoom */
}

/* Buttons + inputs */
.stButton>button{
  border-radius: 14px !important;
  border: 1px solid rgba(148,163,184,0.22) !important;
  padding: 0.62rem 0.9rem !important;
}
.stTextInput input, .stTextArea textarea, .stNumberInput input{
  border-radius: 14px !important;
}

/* Tabs a bit cleaner */
.stTabs [data-baseweb="tab"]{
  font-weight: 800;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# DB helpers
# =========================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def init_db():
    with db() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

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

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "boat"

def badge_html(status: str) -> str:
    color = STATUS_COLOR.get(status, "#94A3B8")
    return f'<span class="bh-badge" style="color:{color}; border-color:{color};">{status.upper()}</span>'

def insert_boat(data: dict) -> int:
    t = now_iso()
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO boats (
                stock_number, year, make, model, hin, length_ft, engine, location,
                status, customer_name, customer_phone, notes, created_at, updated_at
            ) VALUES (
                :stock_number, :year, :make, :model, :hin, :length_ft, :engine, :location,
                :status, :customer_name, :customer_phone, :notes, :created_at, :updated_at
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
                customer_name=:customer_name,
                customer_phone=:customer_phone,
                notes=:notes,
                updated_at=:updated_at
            WHERE id=:id
        """, {**data, "updated_at": t, "id": boat_id})

def get_boat(boat_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM boats WHERE id=?", (boat_id,)).fetchone()

def list_boats(query: str = "", status: str = "All"):
    q = f"%{query.strip()}%"
    with db() as conn:
        if status == "All":
            return conn.execute("""
                SELECT * FROM boats
                WHERE (make LIKE ? OR model LIKE ? OR hin LIKE ? OR stock_number LIKE ? OR customer_name LIKE ?)
                ORDER BY updated_at DESC
            """, (q, q, q, q, q)).fetchall()
        return conn.execute("""
            SELECT * FROM boats
            WHERE status = ?
              AND (make LIKE ? OR model LIKE ? OR hin LIKE ? OR stock_number LIKE ? OR customer_name LIKE ?)
            ORDER BY updated_at DESC
        """, (status, q, q, q, q, q)).fetchall()

# Photos
def add_photo(boat_id: int, filename: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO boat_photos (boat_id, filename, uploaded_at)
            VALUES (?, ?, ?)
        """, (boat_id, filename, now_iso()))

def get_photos(boat_id: int):
    with db() as conn:
        return conn.execute("""
            SELECT * FROM boat_photos
            WHERE boat_id=?
            ORDER BY uploaded_at DESC
        """, (boat_id,)).fetchall()

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
        max_side = 2200
        w, h = img.size
        scale = min(1.0, max_side / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))

        img.save(out_path, quality=88)
        add_photo(boat_id, out_name)
        count += 1
    return count

# Files
def add_file(boat_id: int, filename: str, original_name: str, category: str, ext: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO boat_files (boat_id, filename, original_name, category, ext, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (boat_id, filename, original_name, category, ext, now_iso()))

def get_files(boat_id: int):
    with db() as conn:
        return conn.execute("""
            SELECT * FROM boat_files
            WHERE boat_id=?
            ORDER BY uploaded_at DESC
        """, (boat_id,)).fetchall()

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
# Init
# =========================
init_db()

# =========================
# Header bar (logo + title + quick actions)
# =========================
h1, h2, h3 = st.columns([1.2, 4.5, 2.3], vertical_alignment="center")

with h1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=230)
    else:
        st.write("")

with h2:
    st.markdown(
        """
<div class="bh-panel">
  <div class="bh-title">BoatHub</div>
  <div class="bh-sub">Inventory + service tracking with photos and documents</div>
</div>
""",
        unsafe_allow_html=True,
    )

with h3:
    st.markdown(
        f"""
<div class="bh-panel" style="display:flex;flex-direction:column;gap:10px;">
  <div style="opacity:.72;font-size:12px;">
    <b>DB:</b> {DB_PATH}<br/>
    <b>Photos:</b> {PHOTOS_DIR}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

st.write("")

# =========================
# Sidebar (controls)
# =========================
with st.sidebar:
    st.markdown("### Controls")
    mode = st.radio("Mode", ["Browse", "Add New"], index=0)
    st.markdown("---")
    search = st.text_input("Search", value="", placeholder="make, model, HIN, stock, customer…")
    status_filter = st.selectbox("Status filter", ["All"] + STATUSES, index=0)
    st.markdown("---")
    st.caption("Tip: iPhone users can use the tabs (Overview / Photos / Documents / Edit).")

# =========================
# Stat cards (modern)
# =========================
all_boats = list_boats("", "All")
total = len(all_boats)
for_sale = sum(1 for b in all_boats if b["status"] == "For Sale")
service = sum(1 for b in all_boats if b["status"] == "Customer Service")
today_prefix = datetime.now().date().isoformat()
updated_today = sum(1 for b in all_boats if (b["updated_at"] or "").startswith(today_prefix))

st.markdown(
    f"""
<div class="bh-stats">
  <div class="bh-stat"><div class="bh-stat-k">Total</div><div class="bh-stat-v">{total}</div></div>
  <div class="bh-stat"><div class="bh-stat-k">For Sale</div><div class="bh-stat-v">{for_sale}</div></div>
  <div class="bh-stat"><div class="bh-stat-k">Service</div><div class="bh-stat-v">{service}</div></div>
  <div class="bh-stat"><div class="bh-stat-k">Updated today</div><div class="bh-stat-v">{updated_today}</div></div>
</div>
""",
    unsafe_allow_html=True,
)

st.write("")

# =========================
# Add New
# =========================
if mode == "Add New":
    st.markdown('<div class="bh-panel">', unsafe_allow_html=True)
    st.markdown("## Add a boat")

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

        c7, c8 = st.columns(2)
        length_ft = c7.number_input("Length (ft, optional)", min_value=0.0, max_value=200.0, value=0.0, step=0.5)
        engine = c8.text_input("Engine (optional)")

        st.markdown("### Customer (only if service)")
        c9, c10 = st.columns(2)
        customer_name = c9.text_input("Customer name (optional)")
        customer_phone = c10.text_input("Customer phone (optional)")

        notes = st.text_area("Notes", height=120)

        uploaded = st.file_uploader(
            "Upload photos (you can select multiple)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
        )

        submitted = st.form_submit_button("Create Boat", use_container_width=True)

    if submitted:
        if not make.strip() or not model.strip():
            st.error("Make and Model are required.")
        else:
            boat_id = insert_boat({
                "stock_number": stock_number.strip() or None,
                "year": int(year) if year else None,
                "make": make.strip(),
                "model": model.strip(),
                "hin": hin.strip() or None,
                "length_ft": float(length_ft) if length_ft else None,
                "engine": engine.strip() or None,
                "location": location.strip() or None,
                "status": status_in,
                "customer_name": customer_name.strip() or None,
                "customer_phone": customer_phone.strip() or None,
                "notes": notes.strip() or None,
            })
            if uploaded:
                n = save_uploaded_images(boat_id, make, model, uploaded)
                st.success(f"Created Boat #{boat_id}. Uploaded {n} photo(s).")
            else:
                st.success(f"Created Boat #{boat_id}.")
            st.info("Switch to Browse to view/edit it.")

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# Browse + Details (spaced cards)
# =========================
else:
    boats = list_boats(search, status_filter)

    left, right = st.columns([1.05, 2.15], gap="large")

    with left:
        st.markdown('<div class="bh-panel">', unsafe_allow_html=True)
        st.markdown("## Browse")
        st.caption(f"{len(boats)} result(s).")

        if not boats:
            st.warning("No boats match your search/filter.")
            st.markdown("</div>", unsafe_allow_html=True)
            st.stop()

        labels = []
        id_by_label = {}
        for b in boats:
            label = f"#{b['id']} • {b['year'] or ''} {b['make']} {b['model']} • {b['status']}"
            if b["stock_number"]:
                label += f" • Stock {b['stock_number']}"
            if b["customer_name"]:
                label += f" • {b['customer_name']}"
            labels.append(label)
            id_by_label[label] = b["id"]

        selected_label = st.selectbox("Select a boat", labels, index=0)
        selected_id = id_by_label[selected_label]
        st.markdown("</div>", unsafe_allow_html=True)

    boat = get_boat(selected_id)
    photos = get_photos(selected_id)
    docs = get_files(selected_id)

    with right:
        st.markdown('<div class="bh-panel">', unsafe_allow_html=True)

        st.markdown(
            f"""
<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
  <div>
    <div style="font-size:22px;font-weight:950;letter-spacing:-0.02em;">
      Boat #{boat['id']} — {boat['year'] or ''} {boat['make']} {boat['model']}
    </div>
    <div class="bh-sub">Last updated: {boat['updated_at']}</div>
  </div>
  <div>{badge_html(boat['status'])}</div>
</div>
""",
            unsafe_allow_html=True,
        )

        tab_overview, tab_photos, tab_docs, tab_edit = st.tabs(["Overview", "Photos", "Documents", "Edit"])

        with tab_overview:
            g1, g2 = st.columns(2)
            with g1:
                st.write(f"**Stock #:** {boat['stock_number'] or '—'}")
                st.write(f"**HIN:** {boat['hin'] or '—'}")
                st.write(f"**Location:** {boat['location'] or '—'}")
            with g2:
                st.write(f"**Length:** {boat['length_ft'] or '—'} ft")
                st.write(f"**Engine:** {boat['engine'] or '—'}")
                st.write(f"**Status:** {boat['status']}")

            st.markdown("### Customer")
            c1, c2 = st.columns(2)
            c1.write(f"**Name:** {boat['customer_name'] or '—'}")
            c2.write(f"**Phone:** {boat['customer_phone'] or '—'}")

            st.markdown("### Notes")
            st.write(boat["notes"] or "—")

        with tab_photos:
            st.markdown("### Gallery")
            if photos:
                for p in photos:
                    path = os.path.join(PHOTOS_DIR, p["filename"])
                    if os.path.exists(path):
                        st.image(path, use_container_width=True)
                    else:
                        st.warning("A photo file is missing on disk.")
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
            st.markdown("### Documents")
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
            with st.form("edit_form"):
                status_in = st.selectbox("Status", STATUSES, index=STATUSES.index(boat["status"]))

                c1, c2 = st.columns(2)
                make = c1.text_input("Make *", value=boat["make"] or "")
                model = c2.text_input("Model *", value=boat["model"] or "")

                c3, c4 = st.columns(2)
                year = c3.number_input("Year", min_value=1900, max_value=2100,
                                       value=int(boat["year"] or datetime.now().year), step=1)
                stock_number = c4.text_input("Stock #", value=boat["stock_number"] or "")

                c5, c6 = st.columns(2)
                hin = c5.text_input("HIN / Serial", value=boat["hin"] or "")
                location = c6.text_input("Location", value=boat["location"] or "")

                c7, c8 = st.columns(2)
                length_ft = c7.number_input("Length (ft)", min_value=0.0, max_value=200.0,
                                            value=float(boat["length_ft"] or 0.0), step=0.5)
                engine = c8.text_input("Engine", value=boat["engine"] or "")

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
                    update_boat(selected_id, {
                        "stock_number": stock_number.strip() or None,
                        "year": int(year) if year else None,
                        "make": make.strip(),
                        "model": model.strip(),
                        "hin": hin.strip() or None,
                        "length_ft": float(length_ft) if length_ft else None,
                        "engine": engine.strip() or None,
                        "location": location.strip() or None,
                        "status": status_in,
                        "customer_name": customer_name.strip() or None,
                        "customer_phone": customer_phone.strip() or None,
                        "notes": notes.strip() or None,
                    })
                    st.success("Saved.")
                    st.rerun()

            st.markdown("---")
            st.markdown("### Danger zone")
            if st.button("Delete this boat (and all photos + documents)", type="primary", use_container_width=True):
                delete_boat(selected_id)
                st.warning("Boat deleted.")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)