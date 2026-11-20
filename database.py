import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "steel_pricing.db")

def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Shop Products
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shop_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT DEFAULT '',
        unit TEXT DEFAULT 'เส้น',
        selling_price REAL DEFAULT 0.0,
        standard_cost REAL DEFAULT 0.0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # Supplier Products (2S Metal)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS supplier_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_name TEXT DEFAULT '2S Metal',
        supplier_code TEXT,
        name TEXT NOT NULL,
        spec TEXT DEFAULT '',
        category TEXT DEFAULT '',
        unit TEXT DEFAULT 'เส้น',
        current_cost REAL DEFAULT 0.0,
        prev_cost REAL DEFAULT 0.0,
        stock_status TEXT DEFAULT 'พร้อมส่ง',
        updated_at TEXT
    )
    """)

    # Product Mappings (ร้านค้า <-> 2S Metal)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS product_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_product_id INTEGER UNIQUE NOT NULL,
        supplier_product_id INTEGER NOT NULL,
        multiplier REAL DEFAULT 1.0,
        notes TEXT DEFAULT '',
        updated_at TEXT,
        FOREIGN KEY (shop_product_id) REFERENCES shop_products(id) ON DELETE CASCADE,
        FOREIGN KEY (supplier_product_id) REFERENCES supplier_products(id) ON DELETE CASCADE
    )
    """)

    # Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Seed default settings if not exists
    default_settings = {
        "2s_username": "",
        "2s_password": "",
        "2s_session_cookie": "",
        "express_path": "Z:/jkc2569",
        "low_margin_threshold": "8.0",
        "good_margin_threshold": "15.0",
        "supplier_vat_pct": "7.0",
        "supplier_discount_pct": "1.0",
        "include_vat": "1",
        "last_sync_time": "",
        "sync_status": "พร้อมใช้งาน"
    }
    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()

    # If product_mappings is empty but auto_backup exists, restore safely
    try:
        backup_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mappings_auto_backup.json")
        if os.path.exists(backup_file):
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM product_mappings")
            cnt = c.fetchone()[0]
            conn.close()
            if cnt == 0:
                with open(backup_file, "r", encoding="utf-8") as f:
                    bk_data = json.load(f)
                if bk_data:
                    import_mappings_backup(bk_data)
    except:
        pass

# ----------------- Settings Helpers -----------------
def get_cost_factors() -> Dict[str, Any]:
    """
    Returns VAT and supplier trade discount factors.
    Default formula: ต้นทุนสุทธิ = ราคาตั้ง 2S x (1 - ส่วนลด 1%) x (1 + VAT 7%)
    e.g. Factor = 0.99 x 1.07 = 1.0593
    """
    settings = get_all_settings()
    vat_pct = float(settings.get("supplier_vat_pct", 7.0))
    discount_pct = float(settings.get("supplier_discount_pct", 1.0))
    include_vat = settings.get("include_vat", "1") != "0"

    discount_factor = max(0.0, 1.0 - (discount_pct / 100.0))
    vat_factor = (1.0 + (vat_pct / 100.0)) if include_vat else 1.0
    cost_factor = discount_factor * vat_factor

    return {
        "vat_pct": vat_pct if include_vat else 0.0,
        "discount_pct": discount_pct,
        "include_vat": include_vat,
        "cost_factor": round(cost_factor, 6)
    }
def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()



def get_all_settings() -> Dict[str, str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    rows = c.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

# ----------------- Shop Products Helpers -----------------
def get_shop_products(search: str = "", category: str = "") -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM shop_products WHERE is_active = 1"
    params = []
    if search:
        query += " AND (code LIKE ? OR name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY code ASC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def upsert_shop_product(code: str, name: str, category: str, unit: str, selling_price: float, standard_cost: float = 0.0) -> int:
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
    INSERT INTO shop_products (code, name, category, unit, selling_price, standard_cost, is_active, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
    ON CONFLICT(code) DO UPDATE SET
        name = excluded.name,
        category = excluded.category,
        unit = excluded.unit,
        selling_price = excluded.selling_price,
        standard_cost = excluded.standard_cost,
        updated_at = excluded.updated_at
    """, (code, name, category, unit, selling_price, standard_cost, now, now))
    prod_id = c.lastrowid
    conn.commit()
    conn.close()


    return prod_id

def batch_upsert_shop_products(products: List[Dict[str, Any]]) -> int:
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for p in products:
        c.execute("""
        INSERT INTO shop_products (code, name, category, unit, selling_price, standard_cost, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            unit = excluded.unit,
            selling_price = excluded.selling_price,
            standard_cost = excluded.standard_cost,
            updated_at = excluded.updated_at
        """, (
            p.get("code", "").strip(),
            p.get("name", "").strip(),
            p.get("category", "เหล็ก"),
            p.get("unit", "เส้น"),
            float(p.get("selling_price", 0.0)),
            float(p.get("standard_cost", 0.0)),
            now, now
        ))
        count += 1
    conn.commit()
    conn.close()


    return count

def delete_shop_product(prod_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM product_mappings WHERE shop_product_id = ?", (prod_id,))
    c.execute("DELETE FROM shop_products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()


    return True

def delete_shop_products_batch(ids: List[int]) -> int:
    if not ids:
        return 0
    conn = get_connection()
    c = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    c.execute(f"DELETE FROM product_mappings WHERE shop_product_id IN ({placeholders})", ids)
    c.execute(f"DELETE FROM shop_products WHERE id IN ({placeholders})", ids)
    count = c.rowcount
    conn.commit()
    conn.close()


    return count

def delete_all_shop_products() -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM product_mappings")
    c.execute("DELETE FROM shop_products")
    count = c.rowcount
    conn.commit()
    conn.close()


    return count

# ----------------- Supplier Products Helpers -----------------
def get_supplier_products(search: str = "", category: str = "") -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM supplier_products WHERE 1=1"
    params = []

    # Support tokenized multi-word search (e.g., 'กล่อง 2x2 1.5' or 'ท่อ 1 1/2')
    if search:
        tokens = [t.strip() for t in search.split() if t.strip()]
        for t in tokens:
            query += " AND (supplier_code LIKE ? OR name LIKE ? OR spec LIKE ? OR category LIKE ?)"
            pat = f"%{t}%"
            params.extend([pat, pat, pat, pat])

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY category ASC, name ASC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    factors = get_cost_factors()
    cf = factors["cost_factor"]
    for r in rows:
        cur_cost = float(r.get("current_cost") or 0.0)
        prev_cost = float(r.get("prev_cost") or 0.0)
        net_cur = round(cur_cost * cf, 2)
        net_prev = round(prev_cost * cf, 2)
        r["raw_cost"] = round(cur_cost, 2)
        r["net_cost"] = net_cur
        r["prev_net_cost"] = net_prev
        r["cost_factor"] = cf
        r["discount_pct"] = factors["discount_pct"]
        r["vat_pct"] = factors["vat_pct"]
        r["include_vat"] = factors["include_vat"]

        diff_c = round(cur_cost - prev_cost, 2)
        diff_p = round(((cur_cost - prev_cost) / prev_cost) * 100.0, 2) if prev_cost > 0 else 0.0
        r["diff_cost"] = diff_c
        r["diff_pct"] = diff_p
        r["price_trend"] = "up" if diff_c > 0.01 else ("down" if diff_c < -0.01 else "same")

    return rows

def delete_supplier_product(prod_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM product_mappings WHERE supplier_product_id = ?", (prod_id,))
    c.execute("DELETE FROM supplier_products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()


    return True

def delete_all_supplier_products() -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM product_mappings")
    c.execute("DELETE FROM supplier_products")
    count = c.rowcount
    conn.commit()
    conn.close()


    return count

def batch_upsert_supplier_products(products: List[Dict[str, Any]]) -> int:
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for p in products:
        name = p.get("name", "").strip()
        code = p.get("supplier_code", "").strip()
        cost = float(p.get("current_cost", 0.0))
        spec = p.get("spec", "").strip()
        cat = p.get("category", "").strip()
        unit = p.get("unit", "เส้น").strip()
        stock = p.get("stock_status", "พร้อมส่ง").strip()

        # Check existing to track price movement (prev_cost)
        if code:
            c.execute("SELECT id, current_cost, prev_cost FROM supplier_products WHERE supplier_code = ?", (code,))
        else:
            c.execute("SELECT id, current_cost, prev_cost FROM supplier_products WHERE name = ?", (name,))
        existing = c.fetchone()

        if existing:
            old_cost = float(existing["current_cost"] or 0.0)
            old_prev = float(existing["prev_cost"] or 0.0) if "prev_cost" in existing.keys() else old_cost
            if cost > 0 and abs(cost - old_cost) > 0.001:
                prev_cost = old_cost  # Cost changed! Track old cost
            else:
                prev_cost = old_prev if old_prev > 0 else old_cost

            c.execute("""
            UPDATE supplier_products SET
                name = ?,
                supplier_code = ?,
                spec = ?,
                category = ?,
                unit = ?,
                prev_cost = ?,
                current_cost = ?,
                stock_status = ?,
                updated_at = ?
            WHERE id = ?
            """, (name, code, spec, cat, unit, prev_cost, cost, stock, now, existing["id"]))
        else:
            c.execute("""
            INSERT INTO supplier_products (supplier_name, supplier_code, name, spec, category, unit, current_cost, prev_cost, stock_status, updated_at)
            VALUES ('2S Metal', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (code, name, spec, cat, unit, cost, cost, stock, now))
        count += 1

    conn.commit()
    conn.close()


    return count

# ----------------- Mapping Helpers -----------------
def get_all_mappings() -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT 
        m.id as mapping_id,
        m.shop_product_id,
        m.supplier_product_id,
        m.multiplier,
        m.notes,
        m.updated_at as mapped_at,
        s.code as shop_code,
        s.name as shop_name,
        s.selling_price as shop_selling_price,
        s.unit as shop_unit,
        s.category as shop_category,
        sp.supplier_code,
        sp.name as supplier_name,
        sp.spec as supplier_spec,
        sp.current_cost as supplier_cost,
        sp.prev_cost as supplier_prev_cost,
        sp.unit as supplier_unit,
        sp.stock_status as supplier_stock
    FROM product_mappings m
    JOIN shop_products s ON m.shop_product_id = s.id
    JOIN supplier_products sp ON m.supplier_product_id = sp.id
    ORDER BY s.code ASC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    factors = get_cost_factors()
    cf = factors["cost_factor"]
    for r in rows:
        mult = float(r.get("multiplier") or 1.0)
        raw_cost = float(r.get("supplier_cost") or 0.0)
        r["raw_effective_cost"] = round(raw_cost * mult, 2)
        r["effective_cost"] = round(raw_cost * mult * cf, 2)
        r["cost_factor"] = cf
    return rows

def save_mapping(shop_product_id: int, supplier_product_id: int, multiplier: float = 1.0, notes: str = "") -> int:
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
    INSERT INTO product_mappings (shop_product_id, supplier_product_id, multiplier, notes, updated_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(shop_product_id) DO UPDATE SET
        supplier_product_id = excluded.supplier_product_id,
        multiplier = excluded.multiplier,
        notes = excluded.notes,
        updated_at = excluded.updated_at
    """, (shop_product_id, supplier_product_id, multiplier, notes, now))
    conn.commit()
    conn.close()



    # Automatic safety backup to persistent JSON
    try:
        backup_data = export_mappings_backup()
        backup_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mappings_auto_backup.json")
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
    except:
        pass

    return True

def delete_mapping(mapping_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM product_mappings WHERE id = ?", (mapping_id,))
    conn.commit()
    conn.close()



    # Update auto backup
    try:
        backup_data = export_mappings_backup()
        backup_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mappings_auto_backup.json")
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
    except:
        pass

    return True

def export_mappings_backup() -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT 
        s.code as shop_code,
        s.name as shop_name,
        sp.supplier_code,
        sp.name as supplier_name,
        m.multiplier,
        m.notes,
        m.updated_at
    FROM product_mappings m
    JOIN shop_products s ON m.shop_product_id = s.id
    JOIN supplier_products sp ON m.supplier_product_id = sp.id
    ORDER BY s.code ASC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def import_mappings_backup(records: List[Dict[str, Any]]) -> int:
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success_count = 0

    for r in records:
        shop_code = str(r.get("shop_code", "")).strip()
        supp_code = str(r.get("supplier_code", "")).strip()
        supp_name = str(r.get("supplier_name", "")).strip()
        mult = float(r.get("multiplier", 1.0))
        notes = str(r.get("notes", ""))

        if not shop_code:
            continue

        c.execute("SELECT id FROM shop_products WHERE code = ?", (shop_code,))
        shop_row = c.fetchone()
        if not shop_row:
            continue
        shop_id = shop_row["id"]

        supp_id = None
        if supp_code:
            c.execute("SELECT id FROM supplier_products WHERE supplier_code = ?", (supp_code,))
            supp_row = c.fetchone()
            if supp_row:
                supp_id = supp_row["id"]

        if not supp_id and supp_name:
            c.execute("SELECT id FROM supplier_products WHERE name = ?", (supp_name,))
            supp_row = c.fetchone()
            if supp_row:
                supp_id = supp_row["id"]

        if supp_id:
            c.execute("""
            INSERT INTO product_mappings (shop_product_id, supplier_product_id, multiplier, notes, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(shop_product_id) DO UPDATE SET
                supplier_product_id = excluded.supplier_product_id,
                multiplier = excluded.multiplier,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """, (shop_id, supp_id, mult, notes, now))
            success_count += 1

    conn.commit()
    conn.close()


    return success_count

# ----------------- Price Matrix & Calculator Core -----------------
def get_pricing_matrix(search: str = "", category: str = "", mapping_filter: str = "all", margin_filter: str = "all", price_trend_filter: str = "all") -> List[Dict[str, Any]]:
    """
    Returns full comparison sheet between shop selling price and 2S Metal supplier cost,
    calculating normal profit, margin %, price movement trends (up/down/same), and status.
    """
    conn = get_connection()
    c = conn.cursor()

    query = """
    SELECT 
        s.id as shop_id,
        s.code as shop_code,
        s.name as shop_name,
        s.category as shop_category,
        s.unit as shop_unit,
        s.selling_price as shop_selling_price,
        s.standard_cost as shop_std_cost,
        m.id as mapping_id,
        m.multiplier,
        m.notes as mapping_notes,
        sp.id as supplier_id,
        sp.supplier_code,
        sp.name as supplier_name,
        sp.spec as supplier_spec,
        sp.unit as supplier_unit,
        sp.current_cost as supplier_cost,
        sp.prev_cost as supplier_prev_cost,
        sp.stock_status,
        sp.updated_at as cost_updated_at
    FROM shop_products s
    LEFT JOIN product_mappings m ON s.id = m.shop_product_id
    LEFT JOIN supplier_products sp ON m.supplier_product_id = sp.id
    WHERE s.is_active = 1
    """
    params = []
    if search:
        query += " AND (s.code LIKE ? OR s.name LIKE ? OR sp.name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if category:
        query += " AND s.category = ?"
        params.append(category)

    query += " ORDER BY s.code ASC"
    c.execute(query, params)
    raw_rows = [dict(r) for r in c.fetchall()]
    conn.close()

    settings = get_all_settings()
    low_thresh = float(settings.get("low_margin_threshold", 8.0))
    good_thresh = float(settings.get("good_margin_threshold", 15.0))
    factors = get_cost_factors()
    cf = factors["cost_factor"]

    results = []
    for row in raw_rows:
        is_mapped = row["mapping_id"] is not None and row["supplier_cost"] is not None
        
        # Mapping filter
        if mapping_filter == "mapped" and not is_mapped:
            continue
        if mapping_filter == "unmapped" and is_mapped:
            continue

        multiplier = float(row.get("multiplier") or 1.0)
        selling_price = float(row.get("shop_selling_price") or 0.0)
        raw_supplier_cost = float(row.get("supplier_cost") or 0.0) if is_mapped else 0.0
        effective_cost = raw_supplier_cost * multiplier * cf

        # Price movement
        raw_prev_cost = float(row.get("supplier_prev_cost") or 0.0) if is_mapped else 0.0
        prev_cost = raw_prev_cost * multiplier * cf
        price_trend = "same"
        diff_cost = 0.0
        diff_pct = 0.0
        raw_diff_cost = 0.0
        raw_diff_pct = 0.0

        if is_mapped and prev_cost > 0:
            diff_cost = round(effective_cost - prev_cost, 2)
            diff_pct = round(((effective_cost - prev_cost) / prev_cost) * 100.0, 2)
            raw_diff_cost = round(raw_supplier_cost - raw_prev_cost, 2)
            raw_diff_pct = round(((raw_supplier_cost - raw_prev_cost) / raw_prev_cost) * 100.0, 2) if raw_prev_cost > 0 else 0.0

            if diff_cost > 0.01:
                price_trend = "up"
            elif diff_cost < -0.01:
                price_trend = "down"

        # Price trend filter
        if price_trend_filter == "up" and price_trend != "up":
            continue
        if price_trend_filter == "down" and price_trend != "down":
            continue
        if price_trend_filter == "same" and (price_trend != "same" or not is_mapped):
            continue

        # Normal Profit & Margin
        if is_mapped and effective_cost > 0 and selling_price > 0:
            profit = selling_price - effective_cost
            margin_pct = (profit / selling_price) * 100.0
            markup_pct = (profit / effective_cost) * 100.0

            if margin_pct < 0:
                margin_status = "loss"      # ขาดทุน (แดงเข้ม)
                status_label = "ขาดทุน!"
            elif margin_pct < low_thresh:
                margin_status = "warning"   # กำไรต่ำ (ส้ม/แดง)
                status_label = "กำไรต่ำ"
            elif margin_pct >= good_thresh:
                margin_status = "good"      # กำไรดี (เขียว)
                status_label = "กำไรดี"
            else:
                margin_status = "normal"    # กำไรปานกลาง (เหลือง/เขียวอ่อน)
                status_label = "ปกติ"
        else:
            profit = 0.0
            margin_pct = 0.0
            markup_pct = 0.0
            margin_status = "no_data"
            status_label = "ยังไม่ผูกสินค้า" if not is_mapped else "ไม่มีราคาต้นทุน"

        # Margin filter
        if margin_filter == "loss" and margin_status != "loss":
            continue
        if margin_filter == "warning" and margin_status != "warning":
            continue
        if margin_filter == "good" and margin_status != "good":
            continue

        item = {
            **row,
            "is_mapped": is_mapped,
            "multiplier": multiplier,
            "raw_supplier_cost": round(raw_supplier_cost, 2),
            "raw_prev_cost": round(raw_prev_cost, 2),
            "raw_diff_cost": raw_diff_cost,
            "raw_diff_pct": raw_diff_pct,
            "effective_cost": round(effective_cost, 2),
            "prev_effective_cost": round(prev_cost, 2),
            "diff_cost": diff_cost,
            "diff_pct": diff_pct,
            "cost_adjustment_factor": round(cf, 4),
            "vat_pct": factors["vat_pct"],
            "discount_pct": factors["discount_pct"],
            "include_vat": factors["include_vat"],
            "price_trend": price_trend,
            "selling_price": round(selling_price, 2),
            "normal_profit": round(profit, 2),
            "normal_margin_pct": round(margin_pct, 2),
            "normal_markup_pct": round(markup_pct, 2),
            "margin_status": margin_status,
            "status_label": status_label,
            # Discount fields initialized to normal price
            "discount_selling_price": round(selling_price, 2),
            "discount_profit": round(profit, 2),
            "discount_margin_pct": round(margin_pct, 2)
        }
        results.append(item)

    # Sort profit from high to low by default (mapped items with highest profit first, unmapped at bottom)
    results.sort(key=lambda x: (
        1 if x["is_mapped"] else 0,
        x["normal_profit"] if x["is_mapped"] else -999999,
        x["normal_margin_pct"] if x["is_mapped"] else -999999
    ), reverse=True)

    return results

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_FILE)
