import os
import io
import csv
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, HTTPException, Body, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
from express_reader import load_steel_from_express, load_products_from_csv
from scraper_2smetal import fetch_2smetal_live, parse_2smetal_html, get_sample_2smetal_catalog
from matcher import find_best_matches

# Initialize database
db.init_db()

app = FastAPI(title="2S Metal Steel Cost & Pricing App", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# ----------------- Models -----------------
class ShopProductIn(BaseModel):
    code: str
    name: str
    category: str = "เหล็ก"
    unit: str = "เส้น"
    selling_price: float = 0.0
    standard_cost: float = 0.0

class MappingIn(BaseModel):
    shop_product_id: int
    supplier_product_id: int
    multiplier: float = 1.0
    notes: str = ""

class SyncRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    session_cookie: Optional[str] = None

class PastedHTMLRequest(BaseModel):
    html_content: str

class SettingsIn(BaseModel):
    settings: Dict[str, str]

class QuickCalcRequest(BaseModel):
    selling_price: float
    cost: float

# ----------------- APIs -----------------
@app.get("/api/status")
def get_status():
    settings = db.get_all_settings()
    shop_count = len(db.get_shop_products())
    supp_count = len(db.get_supplier_products())
    mappings = db.get_all_mappings()
    mapped_count = len(mappings)

    return {
        "shop_products_count": shop_count,
        "supplier_products_count": supp_count,
        "mapped_count": mapped_count,
        "unmapped_count": max(0, shop_count - mapped_count),
        "last_sync_time": settings.get("last_sync_time", "ยังไม่ได้ดึงข้อมูล"),
        "sync_status": settings.get("sync_status", "พร้อมใช้งาน"),
        "express_path": settings.get("express_path", "Z:/jkc2569"),
        "has_credentials": bool(settings.get("2s_username") or settings.get("2s_session_cookie"))
    }

@app.get("/api/matrix")
def get_matrix(
    search: str = Query("", description="Search by code or name"),
    category: str = Query("", description="Filter by category"),
    mapping_filter: str = Query("all", description="all, mapped, unmapped"),
    margin_filter: str = Query("all", description="all, loss, warning, good")
):
    items = db.get_pricing_matrix(search, category, mapping_filter, margin_filter)
    
    # Calculate summary stats for the current view
    total_items = len(items)
    mapped_items = sum(1 for it in items if it["is_mapped"])
    loss_count = sum(1 for it in items if it.get("margin_status") == "loss")
    warning_count = sum(1 for it in items if it.get("margin_status") == "warning")
    good_count = sum(1 for it in items if it.get("margin_status") == "good")
    
    valid_margins = [it["normal_margin_pct"] for it in items if it["is_mapped"] and it["effective_cost"] > 0]
    avg_margin = sum(valid_margins) / len(valid_margins) if valid_margins else 0.0

    # Calculate category counts across all shop products for the Slicer
    all_shop = db.get_shop_products()
    cat_counts = {}
    for s in all_shop:
        c = s.get("category") or "เหล็ก"
        cat_counts[c] = cat_counts.get(c, 0) + 1

    factors = db.get_cost_factors()
    return {
        "items": items,
        "cost_config": factors,
        "category_counts": cat_counts,
        "total_shop_count": len(all_shop),
        "stats": {
            "total_items": total_items,
            "mapped_items": mapped_items,
            "loss_count": loss_count,
            "warning_count": warning_count,
            "good_count": good_count,
            "avg_margin_pct": round(avg_margin, 2)
        }
    }

@app.post("/api/calc-discount")
def quick_calculate(req: QuickCalcRequest):
    price = req.selling_price
    cost = req.cost
    profit = price - cost
    margin_pct = (profit / price * 100.0) if price > 0 else 0.0
    markup_pct = (profit / cost * 100.0) if cost > 0 else 0.0

    settings = db.get_all_settings()
    low_thresh = float(settings.get("low_margin_threshold", 8.0))
    good_thresh = float(settings.get("good_margin_threshold", 15.0))

    if profit < 0:
        status = "loss"
        status_label = "ขาดทุน!"
    elif margin_pct < low_thresh:
        status = "warning"
        status_label = "กำไรต่ำ"
    elif margin_pct >= good_thresh:
        status = "good"
        status_label = "กำไรดี"
    else:
        status = "normal"
        status_label = "ปกติ"

    return {
        "selling_price": round(price, 2),
        "cost": round(cost, 2),
        "profit": round(profit, 2),
        "margin_pct": round(margin_pct, 2),
        "markup_pct": round(markup_pct, 2),
        "status": status,
        "status_label": status_label
    }

# ----------------- Shop Products Endpoints -----------------
@app.get("/api/shop-products")
def list_shop_products(search: str = "", category: str = ""):
    return db.get_shop_products(search, category)

@app.post("/api/shop-products")
def save_shop_product(prod: ShopProductIn):
    pid = db.upsert_shop_product(
        prod.code, prod.name, prod.category, prod.unit, prod.selling_price, prod.standard_cost
    )
    return {"success": True, "id": pid}

@app.delete("/api/shop-products/{product_id}")
def delete_shop_product_endpoint(product_id: int):
    success = db.delete_shop_product(product_id)
    return {"success": success, "message": "ลบสินค้าของร้านเรียบร้อยแล้ว"}

class BatchDeleteIn(BaseModel):
    product_ids: List[int]

@app.post("/api/shop-products/delete-batch")
def delete_shop_products_batch_endpoint(req: BatchDeleteIn):
    count = db.delete_shop_products_batch(req.product_ids)
    return {"success": True, "count": count, "message": f"ลบสินค้าเรียบร้อย {count} รายการ"}

@app.post("/api/shop-products/delete-all")
def delete_all_shop_products_endpoint():
    count = db.delete_all_shop_products()
    return {"success": True, "count": count, "message": f"ล้างสินค้าของร้านทั้งหมดเรียบร้อย {count} รายการ"}

@app.post("/api/shop-products/import-express")
def import_from_express():
    settings = db.get_all_settings()
    path = settings.get("express_path", "Z:/jkc2569")
    try:
        items = load_steel_from_express(path, group_prefix="13")
        count = db.batch_upsert_shop_products(items)

        # Clean up excluded prefixes if any exist
        excluded_prefixes = ['1304', '1305', '1306', '1307', '1311']
        conn = db.get_connection()
        c = conn.cursor()
        for p in excluded_prefixes:
            c.execute("DELETE FROM shop_products WHERE code LIKE ?", (f"{p}%",))
        conn.commit()
        conn.close()

        return {"success": True, "message": f"นำเข้าสินค้าเหล็กจาก Express สำเร็จ {count} รายการ", "count": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/shop-products/import-csv")
async def import_csv(file: UploadFile = File(...)):
    content = await file.read()
    try:
        text = content.decode('utf-8')
    except:
        text = content.decode('cp874', errors='ignore')
    
    items = load_products_from_csv(text)
    if not items:
        raise HTTPException(status_code=400, detail="ไม่พบข้อมูลสินค้าที่ถูกต้องในไฟล์ CSV")
    
    count = db.batch_upsert_shop_products(items)
    return {"success": True, "message": f"นำเข้าสินค้าจาก CSV สำเร็จ {count} รายการ", "count": count}

# ----------------- Supplier (2S Metal) Endpoints -----------------
@app.get("/api/supplier-products")
def list_supplier_products(search: str = "", category: str = ""):
    return db.get_supplier_products(search, category)

@app.delete("/api/supplier-products/{product_id}")
def delete_supplier_product_endpoint(product_id: int):
    success = db.delete_supplier_product(product_id)
    return {"success": success, "message": "ลบสินค้า 2S Metal เรียบร้อยแล้ว"}

@app.post("/api/supplier-products/delete-all")
def delete_all_supplier_products_endpoint():
    count = db.delete_all_supplier_products()
    return {"success": True, "count": count, "message": f"ล้างข้อมูลสินค้า 2S Metal เรียบร้อย {count} รายการ"}

@app.post("/api/supplier/sync-live")
def sync_supplier_live(req: SyncRequest = Body(...)):
    settings = db.get_all_settings()
    username = req.username or settings.get("2s_username", "")
    password = req.password or settings.get("2s_password", "")
    session_cookie = req.session_cookie or settings.get("2s_session_cookie", "")

    success, message, products = fetch_2smetal_live(username, password, session_cookie)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if success and products:
        count = db.batch_upsert_supplier_products(products)
        db.set_setting("last_sync_time", now)
        db.set_setting("sync_status", f"ดึงข้อมูลสำเร็จ ({count} รายการ)")
        return {"success": True, "message": message, "count": count, "synced_at": now}
    else:
        db.set_setting("sync_status", f"ข้อผิดพลาด: {message}")
        return {"success": False, "message": message, "count": 0}

@app.post("/api/supplier/import-sample")
def import_sample_catalog():
    catalog = get_sample_2smetal_catalog()
    count = db.batch_upsert_supplier_products(catalog)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.set_setting("last_sync_time", f"{now} (ข้อมูลมาตรฐาน 2S Metal)")
    db.set_setting("sync_status", f"โหลดแค็ตตาล็อกมาตรฐาน {count} รายการเรียบร้อย")
    return {"success": True, "message": f"โหลดแค็ตตาล็อกมาตรฐาน 2S Metal สำเร็จ {count} รายการ", "count": count}

@app.post("/api/supplier/import-pasted")
def import_pasted_html(req: PastedHTMLRequest):
    html = req.html_content.strip()
    if not html:
        raise HTTPException(status_code=400, detail="กรุณาระบุเนื้อหา HTML หรือตาราง")

    products = parse_2smetal_html(html)
    if not products:
        raise HTTPException(status_code=400, detail="ไม่พบตารางรายการสินค้าในข้อมูลที่วาง กรุณาตรวจสอบว่าก็อปปี้ตารางสินค้ามาครบถ้วน")

    count = db.batch_upsert_supplier_products(products)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.set_setting("last_sync_time", f"{now} (นำเข้าจากการวางตาราง)")
    return {"success": True, "message": f"นำเข้าสินค้า 2S Metal สำเร็จ {count} รายการ", "count": count}

# ----------------- Mapping Endpoints -----------------
@app.get("/api/mappings")
def list_mappings():
    return db.get_all_mappings()

@app.post("/api/mappings")
def create_mapping(m: MappingIn):
    db.save_mapping(m.shop_product_id, m.supplier_product_id, m.multiplier, m.notes)
    return {"success": True, "message": "บันทึกการจับคู่สินค้าเรียบร้อยแล้ว"}

@app.delete("/api/mappings/{mapping_id}")
def remove_mapping(mapping_id: int):
    db.delete_mapping(mapping_id)
    return {"success": True, "message": "ยกเลิกการจับคู่เรียบร้อย"}

@app.post("/api/mappings/clear-all")
def clear_all_mappings():
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM product_mappings")
    count = c.rowcount
    conn.commit()
    conn.close()
    return {"success": True, "message": f"ล้างการจับคู่สินค้าทั้งหมดเรียบร้อยแล้ว", "count": count}

@app.get("/api/mappings/backup")
def export_mappings_backup_endpoint():
    data = db.export_mappings_backup()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename=mappings_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"}
    )

class MappingBackupIn(BaseModel):
    mappings: List[Dict[str, Any]]

@app.post("/api/mappings/restore")
def restore_mappings_endpoint(req: MappingBackupIn):
    count = db.import_mappings_backup(req.mappings)
    return {"success": True, "count": count, "message": f"กู้คืนการจับคู่สำเร็จ {count} รายการ"}

@app.get("/api/mappings/suggest/{shop_id}")
def suggest_mapping(shop_id: int):
    shop_items = db.get_shop_products()
    shop_item = next((it for it in shop_items if it["id"] == shop_id), None)
    if not shop_item:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้าของร้าน")

    supplier_items = db.get_supplier_products()
    suggestions = find_best_matches(shop_item, supplier_items, top_n=6)
    return {
        "shop_product": shop_item,
        "suggestions": suggestions
    }

@app.post("/api/mappings/auto-link-high-confidence")
def auto_link_high_confidence():
    """Automatically links unmapped products that have very high matching score (>= 80)."""
    shop_items = db.get_shop_products()
    supplier_items = db.get_supplier_products()
    existing_mappings = {m["shop_product_id"]: m for m in db.get_all_mappings()}

    linked_count = 0
    for s in shop_items:
        if s["id"] in existing_mappings:
            continue
        matches = find_best_matches(s, supplier_items, top_n=1)
        if matches and matches[0]["match_score"] >= 80.0:
            db.save_mapping(s["id"], matches[0]["id"], multiplier=1.0, notes="Auto-matched")
            linked_count += 1

    return {"success": True, "linked_count": linked_count, "message": f"จับคู่อัตโนมัติสำเร็จ {linked_count} รายการ"}

# ----------------- Settings Endpoints -----------------
@app.get("/api/settings")
def get_settings():
    s = db.get_all_settings()
    # Mask password for security display
    if s.get("2s_password"):
        s["has_password"] = True
        s["2s_password"] = "******"
    else:
        s["has_password"] = False
    return s

@app.post("/api/settings")
def save_settings(req: SettingsIn):
    for k, v in req.settings.items():
        if k == "2s_password" and v == "******":
            continue # do not overwrite with mask
        db.set_setting(k, str(v))
    return {"success": True, "message": "บันทึกการตั้งค่าเรียบร้อย"}

# ----------------- Export Endpoints -----------------
@app.get("/api/export-csv")
def export_csv(
    search: str = "",
    category: str = "",
    mapping_filter: str = "all",
    margin_filter: str = "all"
):
    items = db.get_pricing_matrix(search, category, mapping_filter, margin_filter)

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Thai fonts perfectly
    output.write('\ufeff')
    writer = csv.writer(output)

    # Headers
    writer.writerow([
        "รหัสสินค้า", "ชื่อสินค้าของร้าน", "หมวดหมู่", "หน่วย",
        "สินค้า 2S Metal ที่ผูกไว้", "สเปก 2S", "ราคาตั้ง 2S ไม่รวม VAT (บาท)", "ตัวคูณ", "ต้นทุนสุทธิ รวม VAT ลด 1% (บาท)",
        "ราคาขายหน้าร้าน (บาท)", "กำไรปกติ (บาท)", "% กำไรปกติ คิดจากราคาขาย (%)", "สถานะกำไร"
    ])

    for it in items:
        writer.writerow([
            it.get("shop_code", ""),
            it.get("shop_name", ""),
            it.get("shop_category", ""),
            it.get("shop_unit", ""),
            it.get("supplier_name", "") or "ยังไม่จับคู่",
            it.get("supplier_spec", ""),
            it.get("supplier_cost", 0.0),
            it.get("multiplier", 1.0),
            it.get("effective_cost", 0.0),
            it.get("selling_price", 0.0),
            it.get("normal_profit", 0.0),
            it.get("normal_margin_pct", 0.0),
            it.get("status_label", "")
        ])

    output.seek(0)
    filename = f"steel_price_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ----------------- Firebase Cloud Sync -----------------
@app.post("/api/sync-firebase")
def sync_firebase_endpoint():
    try:
        import firebase_sync
        success, message = firebase_sync.sync_all_to_firebase()
        return {"success": success, "message": message}
    except Exception as e:
        return {"success": False, "message": f"เกิดข้อผิดพลาดในการซิงค์: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    print("Starting 2S Metal Steel Pricing Application...")
    uvicorn.run(app, host="127.0.0.1", port=8099)
