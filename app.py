import os
import re
import sqlite3
from datetime import datetime
from typing import Optional, List

import streamlit as st
from PIL import Image

# ---------------------------
# App Config
# ---------------------------
st.set_page_config(
    page_title="BoatHub",
    page_icon="🚤",
    layout="wide",
)

# ---------------------------
# Simple Login Gate
# ---------------------------
def require_password():
    """
    Requires BOATHUB_PASSWORD environment variable to be set on Render.
    Locally, you can leave it blank and it will not block (optional).
    """
    real_pw = os.environ.get("BOATHUB_PASSWORD", "").strip()

    # If no password is set, don't block (handy for local dev).
    # On Render, set BOATHUB_PASSWORD so it prompts.
    if not real_pw:
        return

    if "authed" not in st.session_state:
        st.session_state.authed = False

    if st.session_state.authed:
        return

    st.markdown("## 🔒 BoatHub Login")
    pw = st.text_input("Password", type="password")
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Sign in", use_container_width=True):
            if pw == real_pw:
                st.session_state.authed = True
                st.rerun()
            else:
                st.error("Wrong password.")
    st.stop()

require_password()

# ---------------------------
# Storage paths (Local vs Render)
# ---------------------------
# On Render with a Disk mounted at /data, keep database + photos there
if os.environ.get("RENDER") or os.path.exists("/data"):
    DATA_DIR = "/data"
else:
    DATA_DIR = os.path.abspath(os.path.dirname(__file__))

DB_PATH = os.path.join(DATA_DIR, "boats.db")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

# ---------------------------
# Constants
# ---------------------------
STATUSES = [
    "For Sale",
    "Customer Service",
    "On Hold",
    "Sold",
    "Delivered",
    "Storage",
    "Other",
]

STATUS_COLOR = {
    "For Sale": "#10B981",
    "Customer Service": "#38BDF8",
    "On Hold": "#F59E0B",
    "Sold": "#A78BFA",
    "Delivered": "#22C55E",
    "Storage": "#94A3B8",
    "Other": "#F472B6",
}

# ---------------------------
# Modern + Responsive CSS
# ---------------------------
st.markdown(
    """
<style>
/* General spacing */
.block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1400px; }

/* Header card */
.bh-card {
  background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.03));
  border: 1px solid rgba(148, 163, 184, 0.20);
  border-radius: 18px;
  padding: 16px 16px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.22);
}
.bh-title { font-size: 26px; font-weight: 800; margin: 0; }
.bh-sub { color: rgba(229,231,235,0.75); margin-top: 4px; font-size: 13px; }

/* Badge */
.bh-badge {
  display:inline-flex; align-items:center;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(0,0,0,0.18);
  font-weight: 800;
  font-size: 12px;
  letter-spacing: 0.10em;
}

/* Buttons nicer */
.stButton > button {
  border-radius: 14px !important;
  border: 1px solid rgba(148,163,184,0.20) !important;
  padding: 0.60rem 0.85rem !important;
}

/* Inputs nicer */
.stTextInput input, .stTextArea textarea, .stNumberInput input {
  border-radius: 14px !important;
}

/* Mobile tweaks */
@media (max-width: 768px) {
  .block-container { padding-left: 0.85rem; padding-right: 0.85rem; }
  .stButton > button { width: 100%; }
  input, textarea { font-size: 16px !important; } /* prevents iPhone zoom */
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------
# Database helpers
# ---------------------------
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

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "boat"

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

def delete_boat(boat_id: int):
    photos = get_photos(boat_id)
    with db() as conn:
        conn.execute("DELETE FROM boats WHERE id=?", (boat_id,))
    # delete photo files
    for p in photos:
        path = os.path.join(PHOTOS_DIR, p["filename"])
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

def add_photo(boat_id: int, filename: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO boat_photos (boat_id, filename, uploaded_at)
            VALUES (?, ?, ?)
        """, (boat_id, filename, now_iso()))

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

def get_boat(boat_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM boats WHERE id=?", (boat_id,)).fetchone()

def get_photos(boat_id: int):
    with db() as conn:
        return conn.execute("""
            SELECT * FROM boat_photos
            WHERE boat_id=?
            ORDER BY uploaded_at DESC
        """, (boat_id,)).fetchall()

def list_boats(query: str = "", status: str = "All"):
    q = f"%{query.strip()}%"
    with db() as conn:
        if status == "All":
            rows = conn.execute("""
                SELECT * FROM boats
                WHERE (make LIKE ? OR model LIKE ? OR hin LIKE ? OR stock_number LIKE ? OR customer_name LIKE ?)
                ORDER BY updated_at DESC
            """, (q, q, q, q, q)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM boats
                WHERE status = ?
                  AND (make LIKE ? OR model LIKE ? OR hin LIKE ? OR stock_number LIKE ? OR customer_name LIKE ?)
                ORDER BY updated_at DESC
            """, (status, q, q, q, q, q)).fetchall()
    return rows

def save_uploaded_images(boat_id: int, make: str, model: str, files) -> int:
    count = 0
    base = slugify(f"{boat_id}-{make}-{model}")
    for f in files:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"

        out_name = f"{base}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{count}{ext}"
        out_path = os.path.join(PHOTOS_DIR, out_name)

        img = Image.open(f).convert("RGB")

        # Resize for speed (good for mobile too)
        max_side = 2200
        w, h = img.size
        scale = min(1.0, max_side / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))

        img.save(out_path, quality=88)
        add_photo(boat_id, out_name)
        count += 1

    return count

def badge_html(status: str) -> str:
    color = STATUS_COLOR.get(status, "#94A3B8")
    return f'<span class="bh-badge" style="color:{color}; border-color:{color};">{status.upper()}</span>'

# ---------------------------
# Init DB
# ---------------------------
init_db()

# ---------------------------
# Header
# ---------------------------
st.markdown(
    f"""
<div class="bh-card">
  <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap;">
    <div>
      <div class="bh-title">🚤 BoatHub</div>
      <div class="bh-sub">Inventory + service tracking with photo uploads</div>
    </div>
    <div class="bh-sub"><b>DB:</b> {DB_PATH} &nbsp; • &nbsp; <b>Photos:</b> {PHOTOS_DIR}</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.write("")

# ---------------------------
# Sidebar controls
# ---------------------------
with st.sidebar:
    st.markdown("### Controls")
    mode = st.radio("Mode", ["Browse", "Add New"], index=0)
    st.markdown("---")
    search = st.text_input("Search", value="", placeholder="make, model, HIN, stock, customer…")
    status_filter = st.selectbox("Status filter", ["All"] + STATUSES, index=0)
    st.markdown("---")
    st.caption("Tip: works great on iPhone—use the tabs on the right.")

# ---------------------------
# Quick metrics
# ---------------------------
all_boats = list_boats("", "All")
total = len(all_boats)
for_sale = sum(1 for b in all_boats if b["status"] == "For Sale")
service = sum(1 for b in all_boats if b["status"] == "Customer Service")

today_prefix = datetime.now().date().isoformat()
updated_today = sum(1 for b in all_boats if (b["updated_at"] or "").startswith(today_prefix))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", total)
m2.metric("For Sale", for_sale)
m3.metric("Service", service)
m4.metric("Updated today", updated_today)

st.write("")

# ---------------------------
# Add New Boat
# ---------------------------
if mode == "Add New":
    st.markdown('<div class="bh-card">', unsafe_allow_html=True)
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

# ---------------------------
# Browse + Detail View
# ---------------------------
else:
    boats = list_boats(search, status_filter)

    left, right = st.columns([1, 2], gap="large")

    with left:
        st.markdown('<div class="bh-card">', unsafe_allow_html=True)
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

    with right:
        st.markdown('<div class="bh-card">', unsafe_allow_html=True)

        st.markdown(
            f"""
<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap;">
  <div>
    <div style="font-size:22px; font-weight:800;">Boat #{boat['id']} — {boat['year'] or ''} {boat['make']} {boat['model']}</div>
    <div class="bh-sub">Last updated: {boat['updated_at']}</div>
  </div>
  <div>{badge_html(boat['status'])}</div>
</div>
""",
            unsafe_allow_html=True,
        )

        # Tabs are great for iPhone AND desktop
        tab_overview, tab_photos, tab_edit = st.tabs(["Overview", "Photos", "Edit"])

        with tab_overview:
            st.write(f"**Stock #:** {boat['stock_number'] or '—'}")
            st.write(f"**HIN:** {boat['hin'] or '—'}")
            st.write(f"**Location:** {boat['location'] or '—'}")
            st.write(f"**Length:** {boat['length_ft'] or '—'} ft")
            st.write(f"**Engine:** {boat['engine'] or '—'}")

            st.markdown("### Customer")
            st.write(f"**Name:** {boat['customer_name'] or '—'}")
            st.write(f"**Phone:** {boat['customer_phone'] or '—'}")

            st.markdown("### Notes")
            st.write(boat["notes"] or "—")

        with tab_photos:
            st.markdown("### Gallery")
            if photos:
                # Always 1-per-row looks best on phones; still clean on desktop
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

        with tab_edit:
            st.markdown("### Edit boat details")
            with st.form("edit_form"):
                status_in = st.selectbox("Status", STATUSES, index=STATUSES.index(boat["status"]))

                c1, c2 = st.columns(2)
                make = c1.text_input("Make *", value=boat["make"] or "")
                model = c2.text_input("Model *", value=boat["model"] or "")

                c3, c4 = st.columns(2)
                year = c3.number_input("Year", min_value=1900, max_value=2100, value=int(boat["year"] or datetime.now().year), step=1)
                stock_number = c4.text_input("Stock #", value=boat["stock_number"] or "")

                c5, c6 = st.columns(2)
                hin = c5.text_input("HIN / Serial", value=boat["hin"] or "")
                location = c6.text_input("Location", value=boat["location"] or "")

                c7, c8 = st.columns(2)
                length_ft = c7.number_input("Length (ft)", min_value=0.0, max_value=200.0, value=float(boat["length_ft"] or 0.0), step=0.5)
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
            if st.button("Delete this boat (and all photos)", type="primary", use_container_width=True):
                delete_boat(selected_id)
                st.warning("Boat deleted.")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)