import os
import re
import sqlite3
from datetime import datetime

import streamlit as st
from PIL import Image

# =========================
# PARADIGMHUB (Boat inventory + service + photos)
# =========================

# 1) Page setup
st.set_page_config(page_title="ParadigmHub", page_icon="🚤", layout="wide")

# 2) Logo (put logo.png in the SAME folder as this app.py)
LOGO_PATH = "logo.png"

def show_logo(center=True, width=650):
    if not os.path.exists(LOGO_PATH):
        return

    if center:
        c1, c2, c3 = st.columns([1, 3, 1])
        with c2:
            st.image(LOGO_PATH, width=width)
    else:
        st.image(LOGO_PATH, width=width)

# 3) Password gate (Render env var: BOATHUB_PASSWORD)
def require_password():
    if "authed" not in st.session_state:
        st.session_state.authed = False

    if st.session_state.authed:
        return

    # Login UI
    show_logo(center=True, width=700)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown("### Login")
    pw = st.text_input("Password", type="password")

    if st.button("Sign in", use_container_width=True):
        real_pw = os.environ.get("BOATHUB_PASSWORD", "")
        if not real_pw:
            st.error("Server password is not set (BOATHUB_PASSWORD).")
        elif pw == real_pw:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("Wrong password.")

    st.stop()

require_password()

# 4) Storage paths
# - On Render: set env var RENDER=1 and mount a disk at /data
# - Local: saves to your app folder
if os.environ.get("RENDER"):
    DATA_DIR = "/data"
else:
    DATA_DIR = os.path.abspath(os.path.dirname(__file__))

DB_PATH = os.path.join(DATA_DIR, "boats.db")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")

STATUSES = [
    "For Sale",
    "Customer Service",
    "On Hold",
    "Sold",
    "Delivered",
    "Storage",
    "Other",
]

STATUS_BADGE = {
    "For Sale": ("#10B981", "FOR SALE"),
    "Customer Service": ("#38BDF8", "SERVICE"),
    "On Hold": ("#F59E0B", "ON HOLD"),
    "Sold": ("#A78BFA", "SOLD"),
    "Delivered": ("#22C55E", "DELIVERED"),
    "Storage": ("#94A3B8", "STORAGE"),
    "Other": ("#F472B6", "OTHER"),
}

# 5) Modern CSS
st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px; }
      header, footer { visibility: hidden; height: 0px; }

      .card {
        background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.03));
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 18px;
        padding: 16px 16px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.25);
      }

      .titlebar {
        display:flex; align-items:center; justify-content:space-between;
        gap: 10px;
      }

      .badge {
        display:inline-flex;
        align-items:center;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.15);
        background: rgba(0,0,0,0.15);
        font-weight: 800;
        font-size: 12px;
        letter-spacing: 0.12em;
      }

      .muted { color: rgba(229,231,235,0.75); font-size: 13px; }

      .stButton > button {
        border-radius: 14px !important;
        border: 1px solid rgba(148,163,184,0.20) !important;
        padding: 0.55rem 0.85rem !important;
      }

      .stTextInput input, .stTextArea textarea, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 14px !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# DB + FILE HELPERS
# =========================
def ensure_storage():
    os.makedirs(PHOTOS_DIR, exist_ok=True)

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    ensure_storage()
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
        conn.execute("PRAGMA foreign_keys = ON;")

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "boat"

def status_badge_html(status: str) -> str:
    color, label = STATUS_BADGE.get(status, ("#94A3B8", status.upper()))
    return f"""<span class="badge" style="border-color:{color}; color:{color}">{label}</span>"""

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

def save_uploaded_images(boat_id: int, make: str, model: str, files) -> int:
    ensure_storage()
    count = 0
    base = slugify(f"{boat_id}-{make}-{model}")
    for f in files:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"

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

# init database
init_db()

# =========================
# UI
# =========================
st.markdown('<div class="card">', unsafe_allow_html=True)
show_logo(center=False, width=700)
st.markdown('<div class="muted">Inventory + service tracking with photo uploads</div>', unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)
st.write("")

with st.sidebar:
    st.markdown("### Controls")
    mode = st.radio("Mode", ["Browse", "Add New"], index=0)
    st.markdown("---")
    search = st.text_input("Search", value="", placeholder="make, model, HIN, stock, customer…")
    status_filter = st.selectbox("Status filter", ["All"] + STATUSES, index=0)

boats_all = list_boats("", "All")
for_sale = sum(1 for b in boats_all if b["status"] == "For Sale")
service = sum(1 for b in boats_all if b["status"] == "Customer Service")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total boats", len(boats_all))
m2.metric("For Sale", for_sale)
m3.metric("Service", service)
m4.metric("Updated today", sum(1 for b in boats_all if (b["updated_at"] or "").startswith(datetime.now().date().isoformat())))

st.write("")

if mode == "Add New":
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("## Add a boat")

    with st.form("add_boat_form"):
        c1, c2, c3 = st.columns(3)
        stock_number = c1.text_input("Stock # (optional)")
        year = c2.number_input("Year", min_value=1900, max_value=2100, value=2025, step=1)
        status_in = c3.selectbox("Status", STATUSES, index=0)

        c4, c5, c6 = st.columns(3)
        make = c4.text_input("Make *")
        model = c5.text_input("Model *")
        hin = c6.text_input("HIN / Serial (optional)")

        c7, c8, c9 = st.columns(3)
        length_ft = c7.number_input("Length (ft)", min_value=0.0, max_value=200.0, value=0.0, step=0.5)
        engine = c8.text_input("Engine (optional)")
        location = c9.text_input("Location (optional)", value="Showroom")

        c10, c11 = st.columns(2)
        customer_name = c10.text_input("Customer name (if service)")
        customer_phone = c11.text_input("Customer phone (optional)")

        notes = st.text_area("Notes", height=120)

        uploaded = st.file_uploader(
            "Photos (multi-select)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
        )

        submitted = st.form_submit_button("Create Boat")

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

else:
    boats = list_boats(search, status_filter)

    left, right = st.columns([1, 2], gap="large")

    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("## Browse")
        st.caption(f"{len(boats)} result(s). Select one.")

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

        selected_label = st.selectbox("Boat", labels, index=0)
        selected_id = id_by_label[selected_label]
        st.markdown("</div>", unsafe_allow_html=True)

    boat = get_boat(selected_id)
    photos = get_photos(selected_id)

    with right:
        st.markdown('<div class="card">', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="titlebar">
              <div>
                <div style="font-size:22px; font-weight:900;">Boat #{boat['id']} — {boat['year'] or ''} {boat['make']} {boat['model']}</div>
                <div class="muted">Last updated: {boat['updated_at']}</div>
              </div>
              <div>{status_badge_html(boat['status'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        a, b, c, d = st.columns(4)
        a.write(f"**Stock #:** {boat['stock_number'] or '—'}")
        b.write(f"**HIN:** {boat['hin'] or '—'}")
        c.write(f"**Location:** {boat['location'] or '—'}")
        d.write(f"**Length:** {boat['length_ft'] or '—'} ft")

        e, f = st.columns(2)
        e.write(f"**Engine:** {boat['engine'] or '—'}")
        f.write(f"**Customer:** {boat['customer_name'] or '—'}")

        if boat["customer_phone"]:
            st.write(f"**Customer phone:** {boat['customer_phone']}")

        st.write(f"**Notes:** {boat['notes'] or '—'}")

        st.markdown("---")
        st.markdown("### Photos")

        if photos:
            cols = st.columns(3)
            for i, p in enumerate(photos):
                path = os.path.join(PHOTOS_DIR, p["filename"])
                with cols[i % 3]:
                    if os.path.exists(path):
                        st.image(path, use_container_width=True)
                    else:
                        st.warning("Missing file on disk.")
                    if st.button("Delete photo", key=f"delphoto_{p['id']}"):
                        delete_photo(p["id"])
                        st.rerun()
        else:
            st.info("No photos yet.")

        st.markdown("### Add more photos")
        more = st.file_uploader(
            "Upload more",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="more_photos",
        )
        if more and st.button("Save uploaded photos"):
            n = save_uploaded_images(selected_id, boat["make"], boat["model"], more)
            st.success(f"Uploaded {n} photo(s).")
            st.rerun()

        st.markdown("---")
        st.markdown("### Edit details")
        with st.form("edit_form"):
            e1, e2, e3 = st.columns(3)
            stock_number = e1.text_input("Stock #", value=boat["stock_number"] or "")
            year = e2.number_input("Year", min_value=1900, max_value=2100, value=int(boat["year"] or 2025), step=1)
            status_in = e3.selectbox("Status", STATUSES, index=STATUSES.index(boat["status"]))

            e4, e5, e6 = st.columns(3)
            make = e4.text_input("Make *", value=boat["make"] or "")
            model = e5.text_input("Model *", value=boat["model"] or "")
            hin = e6.text_input("HIN / Serial", value=boat["hin"] or "")

            e7, e8, e9 = st.columns(3)
            length_ft = e7.number_input("Length (ft)", min_value=0.0, max_value=200.0, value=float(boat["length_ft"] or 0.0), step=0.5)
            engine = e8.text_input("Engine", value=boat["engine"] or "")
            location = e9.text_input("Location", value=boat["location"] or "")

            e10, e11 = st.columns(2)
            customer_name = e10.text_input("Customer name", value=boat["customer_name"] or "")
            customer_phone = e11.text_input("Customer phone", value=boat["customer_phone"] or "")

            notes = st.text_area("Notes", value=boat["notes"] or "", height=120)

            save = st.form_submit_button("Save changes")

        if save:
            if not make.strip() or not model.strip():
                st.error("Make and Model are required.")
            else:
                update_boat(selected_id, {
                    "stock_number": stock_number.strip() or None,
                    "year": int(year) if year else None,
                    "make": make.strip(),
                    "model": model.strip() or None,
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
        if st.button("Delete this boat (and all photos)", type="primary"):
            delete_boat(selected_id)
            st.warning("Boat deleted.")
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)