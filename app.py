import os
import re
import sqlite3
from datetime import datetime
from typing import List, Optional

import streamlit as st
from PIL import Image

APP_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(APP_DIR, "boats.db")
PHOTOS_DIR = os.path.join(APP_DIR, "photos")

STATUSES = [
    "For Sale",
    "Customer Service",
    "On Hold",
    "Sold",
    "Delivered",
    "Storage",
    "Other",
]

def ensure_storage():
    os.makedirs(PHOTOS_DIR, exist_ok=True)

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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
        conn.execute("PRAGMA foreign_keys = ON;")

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

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
    # Delete photos from disk too
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

def save_uploaded_images(boat_id: int, make: str, model: str, files) -> int:
    count = 0
    base = slugify(f"{boat_id}-{make}-{model}")
    for f in files:
        # Keep original extension if possible
        name = f.name
        ext = os.path.splitext(name)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"
        out_name = f"{base}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{count}{ext}"
        out_path = os.path.join(PHOTOS_DIR, out_name)

        # Re-save via PIL to avoid weird formats + limit size a bit
        img = Image.open(f)
        img = img.convert("RGB")
        # Optional: resize to max 2000px
        max_side = 2000
        w, h = img.size
        scale = min(1.0, max_side / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))
        img.save(out_path, quality=88)

        add_photo(boat_id, out_name)
        count += 1
    return count

# ---------------- UI ----------------

ensure_storage()
init_db()

st.set_page_config(page_title="Boat Inventory & Service Tracker", layout="wide")
st.title("Boat Inventory & Service Tracker")

with st.sidebar:
    st.header("Search / Filter")
    search = st.text_input("Search (make/model/HIN/stock/customer)", value="")
    status = st.selectbox("Status", ["All"] + STATUSES, index=0)
    st.divider()
    st.header("Actions")
    mode = st.radio("Mode", ["Browse Boats", "Add New Boat"], index=0)

if mode == "Add New Boat":
    st.subheader("Add a boat")
    with st.form("add_boat_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        stock_number = c1.text_input("Stock # (optional)")
        year = c2.number_input("Year (optional)", min_value=1900, max_value=2100, value=2025, step=1)
        status_in = c3.selectbox("Status", STATUSES, index=0)

        c4, c5, c6 = st.columns(3)
        make = c4.text_input("Make", value="")
        model = c5.text_input("Model", value="")
        hin = c6.text_input("HIN / Serial (optional)", value="")

        c7, c8, c9 = st.columns(3)
        length_ft = c7.number_input("Length (ft, optional)", min_value=0.0, max_value=200.0, value=0.0, step=0.5)
        engine = c8.text_input("Engine (optional)", value="")
        location = c9.text_input("Location (optional)", value="Showroom")

        c10, c11 = st.columns(2)
        customer_name = c10.text_input("Customer name (if service)", value="")
        customer_phone = c11.text_input("Customer phone (optional)", value="")

        notes = st.text_area("Notes", value="", height=120)

        uploaded = st.file_uploader(
            "Upload photos (JPG/PNG/WEBP). You can select multiple files.",
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
                st.success(f"Boat created (ID {boat_id}). Uploaded {n} photo(s).")
            else:
                st.success(f"Boat created (ID {boat_id}).")
            st.info("Switch to 'Browse Boats' in the sidebar to view/edit it.")

else:
    boats = list_boats(search, status)

    st.subheader("Boats")
    st.caption(f"Showing {len(boats)} result(s). Click a boat to view details.")

    # List with a simple selector
    left, right = st.columns([1, 2], gap="large")

    with left:
        if not boats:
            st.warning("No boats match your search/filter.")
            st.stop()

        options = []
        for b in boats:
            label = f"#{b['id']} • {b['year'] or ''} {b['make']} {b['model']} • {b['status']}"
            if b["stock_number"]:
                label += f" • Stock {b['stock_number']}"
            if b["customer_name"]:
                label += f" • {b['customer_name']}"
            options.append((label, b["id"]))

        selected_label = st.selectbox(
            "Select a boat",
            [o[0] for o in options],
            index=0,
        )
        selected_id = dict(options)[selected_label]

    boat = get_boat(selected_id)
    photos = get_photos(selected_id)

    with right:
        st.markdown(f"### Boat #{boat['id']} — {boat['year'] or ''} {boat['make']} {boat['model']}")
        meta_cols = st.columns(4)
        meta_cols[0].write(f"**Status:** {boat['status']}")
        meta_cols[1].write(f"**Stock #:** {boat['stock_number'] or '—'}")
        meta_cols[2].write(f"**HIN:** {boat['hin'] or '—'}")
        meta_cols[3].write(f"**Location:** {boat['location'] or '—'}")

        st.write(f"**Length:** {boat['length_ft'] or '—'} ft")
        st.write(f"**Engine:** {boat['engine'] or '—'}")
        st.write(f"**Customer:** {boat['customer_name'] or '—'}  {('('+boat['customer_phone']+')') if boat['customer_phone'] else ''}")
        st.write(f"**Notes:** {boat['notes'] or '—'}")
        st.caption(f"Last updated: {boat['updated_at']}")

        st.divider()
        st.markdown("### Photos")
        if photos:
            # Show in grid
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
            st.info("No photos yet for this boat.")

        st.divider()
        st.markdown("### Add more photos")
        more = st.file_uploader(
            "Upload more photos",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="more_photos",
        )
        if more and st.button("Save uploaded photos"):
            n = save_uploaded_images(selected_id, boat["make"], boat["model"], more)
            st.success(f"Uploaded {n} photo(s).")
            st.rerun()

        st.divider()
        st.markdown("### Edit boat details")
        with st.form("edit_form"):
            c1, c2, c3 = st.columns(3)
            stock_number = c1.text_input("Stock #", value=boat["stock_number"] or "")
            year = c2.number_input("Year", min_value=1900, max_value=2100, value=int(boat["year"] or 2025), step=1)
            status_in = c3.selectbox("Status", STATUSES, index=STATUSES.index(boat["status"]))

            c4, c5, c6 = st.columns(3)
            make = c4.text_input("Make", value=boat["make"] or "")
            model = c5.text_input("Model", value=boat["model"] or "")
            hin = c6.text_input("HIN / Serial", value=boat["hin"] or "")

            c7, c8, c9 = st.columns(3)
            length_ft = c7.number_input("Length (ft)", min_value=0.0, max_value=200.0, value=float(boat["length_ft"] or 0.0), step=0.5)
            engine = c8.text_input("Engine", value=boat["engine"] or "")
            location = c9.text_input("Location", value=boat["location"] or "")

            c10, c11 = st.columns(2)
            customer_name = c10.text_input("Customer name", value=boat["customer_name"] or "")
            customer_phone = c11.text_input("Customer phone", value=boat["customer_phone"] or "")

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

        st.divider()
        st.markdown("### Danger zone")
        if st.button("Delete this boat (and its photos)", type="primary"):
            delete_boat(selected_id)
            st.warning("Boat deleted.")
            st.rerun()