import os
import struct
import csv
from typing import List, Dict, Any, Tuple, Optional

def parse_dbf_raw(path: str) -> Tuple[bytes, int, int, int, List[Tuple[str, str, int, int, int]]]:
    """Ultra-fast raw binary parser for FoxPro/dBase DBF files with CP874 decoding."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"DBF file not found: {path}")

    with open(path, 'rb') as f:
        data = f.read()

    if len(data) < 32:
        return b"", 0, 0, 0, []

    num_recs, header_len, rec_len = struct.unpack('<IHH', data[4:12])
    fields = []
    pos = 32
    f_offset = 1 # byte 0 is delete flag
    while pos < header_len - 1:
        if data[pos] == 0x0D:
            break
        name = data[pos:pos+11].replace(b'\x00', b'').decode('ascii', errors='ignore').strip()
        ftype = chr(data[pos+11])
        flen = data[pos+16]
        fdec = data[pos+17]
        fields.append((name, ftype, f_offset, flen, fdec))
        f_offset += flen
        pos += 32

    return data, num_recs, header_len, rec_len, fields

def classify_steel_category(code: str, name: str = "") -> Optional[str]:
    """
    Classifies steel products strictly by product code prefix according to user rules:
    - 130101 -> ท่อประปา
    - 130102 -> เหล็กรูปดำ
    - 130103 -> เหล็กรูปขาว
    - 130104 -> ไม่ค่อยได้ขาย
    - 130105 -> เหล็กฉาก
    - 130106 -> ไม่ค่อยได้ขาย
    - 130107 -> เหล็กเส้น
    - 130108 -> กลมดำ
    - 130109 -> แบนรีด
    - 130110 -> ไวร์เมช
    - 130111 -> แปรสำเร็จ
    - 1302   -> เพลท
    - 1303   -> ปอก
    - 1304-1307 -> None (ลบทิ้ง ไม่แสดง)
    - 1308   -> ลวด
    - 1309   -> กิ๊ปลวดหนาม
    - 1310   -> ตะแกรง ตาข่าย
    - 1311   -> None (ลบทิ้ง ไม่แสดง)
    """
    c = str(code).strip()
    if c.startswith('130101'): return 'ท่อประปา'
    if c.startswith('130102'): return 'เหล็กรูปดำ'
    if c.startswith('130103'): return 'เหล็กรูปขาว'
    if c.startswith('130104'): return 'ไม่ค่อยได้ขาย'
    if c.startswith('130105'): return 'เหล็กฉาก'
    if c.startswith('130106'): return 'ไม่ค่อยได้ขาย'
    if c.startswith('130107'): return 'เหล็กเส้น'
    if c.startswith('130108'): return 'กลมดำ'
    if c.startswith('130109'): return 'แบนรีด'
    if c.startswith('130110'): return 'ไวร์เมช'
    if c.startswith('130111'): return 'แปรสำเร็จ'
    if c.startswith('1302'):   return 'เพลท'
    if c.startswith('1303'):   return 'ปอก'
    if c.startswith(('1304', '1305', '1306', '1307', '1311')): return None
    if c.startswith('1308'):   return 'ลวด'
    if c.startswith('1309'):   return 'กิ๊ปลวดหนาม'
    if c.startswith('1310'):   return 'ตะแกรง ตาข่าย'
    if 'ไวร์เมช' in (name or '') and c.startswith('1301'): return 'ไวร์เมช'
    return None

def load_steel_from_express(data_path: str = "Z:/jkc2569", group_prefix: str = "13") -> List[Dict[str, Any]]:
    """
    Scans STMAS.DBF in Express directory and returns structural steel products.
    """
    stmas_path = os.path.join(data_path, "STMAS.DBF")
    if not os.path.exists(stmas_path):
        raise FileNotFoundError(f"ไม่พบไฟล์ STMAS.DBF ในโฟลเดอร์ {data_path}")

    data, num_recs, header_len, rec_len, fields = parse_dbf_raw(stmas_path)
    fmap = {f[0]: f for f in fields}

    f_cod = fmap.get('STKCOD')
    f_des = fmap.get('STKDES')
    f_grp = fmap.get('STKGRP')
    f_spr1 = fmap.get('SELLPR1')
    f_lspr = fmap.get('LSELLPR')
    f_upr = fmap.get('UNITPR')
    f_std = fmap.get('STDPRC')
    f_qu = fmap.get('QUCOD')

    if not f_cod or not f_des:
        raise ValueError("รูปแบบ STMAS.DBF ไม่ถูกต้อง (ไม่มี STKCOD หรือ STKDES)")

    products = []
    offset = header_len

    for _ in range(num_recs):
        if offset + rec_len > len(data):
            break
        
        # Check deleted flag
        if data[offset] != 0x2A:
            cod = data[offset+f_cod[2]:offset+f_cod[2]+f_cod[3]].decode('cp874', errors='ignore').replace('\xa0', ' ').strip()
            des = data[offset+f_des[2]:offset+f_des[2]+f_des[3]].decode('cp874', errors='ignore').replace('\xa0', ' ').strip()
            grp = data[offset+f_grp[2]:offset+f_grp[2]+f_grp[3]].decode('cp874', errors='ignore').replace('\xa0', ' ').strip() if f_grp else ''

            # Filter strictly by category rules based on product code prefix
            cat = classify_steel_category(cod, des)
            if not cat:
                offset += rec_len
                continue

            spr1 = struct.unpack('<d', data[offset+f_spr1[2]:offset+f_spr1[2]+8])[0] if f_spr1 else 0.0
            lspr = struct.unpack('<d', data[offset+f_lspr[2]:offset+f_lspr[2]+8])[0] if f_lspr else 0.0
            upr = struct.unpack('<d', data[offset+f_upr[2]:offset+f_upr[2]+8])[0] if f_upr else 0.0
            std = struct.unpack('<d', data[offset+f_std[2]:offset+f_std[2]+8])[0] if f_std else 0.0
            qu = data[offset+f_qu[2]:offset+f_qu[2]+f_qu[3]].decode('cp874', errors='ignore').strip() if f_qu else 'เส้น'

            sell_price = spr1 if spr1 > 0 else lspr
            cost = upr if upr > 0 else std

            products.append({
                "code": cod,
                "name": des,
                "category": cat,
                "unit": qu or "เส้น",
                "selling_price": round(sell_price, 2),
                "standard_cost": round(cost, 2)
            })

        offset += rec_len

    return products

def load_products_from_csv(file_content: str) -> List[Dict[str, Any]]:
    """
    Loads products from CSV content with auto-detect headers.
    """
    reader = csv.reader(file_content.splitlines())
    rows = list(reader)
    if not rows:
        return []

    headers = [h.strip().lower() for h in rows[0]]
    code_idx = -1
    name_idx = -1
    price_idx = -1
    cost_idx = -1
    cat_idx = -1
    unit_idx = -1

    for i, h in enumerate(headers):
        if h in ['code', 'stkcod', 'รหัส', 'รหัสสินค้า', 'sku']:
            code_idx = i
        elif h in ['name', 'stkdes', 'ชื่อ', 'ชื่อสินค้า', 'รายละเอียด']:
            name_idx = i
        elif h in ['price', 'selling_price', 'sellpr1', 'ราคา', 'ราคาขาย', 'ราคาหน้าร้าน']:
            price_idx = i
        elif h in ['cost', 'standard_cost', 'unitpr', 'ทุน', 'ต้นทุน']:
            cost_idx = i
        elif h in ['category', 'group', 'หมวดหมู่', 'หมวด']:
            cat_idx = i
        elif h in ['unit', 'หน่วย', 'หน่วยนับ']:
            unit_idx = i

    if code_idx == -1 or name_idx == -1:
        # Fallback to positional: col 0 = code, col 1 = name, col 2 = price
        code_idx, name_idx, price_idx = 0, 1, 2

    products = []
    for r in rows[1:]:
        if not r or len(r) <= max(code_idx, name_idx):
            continue
        code = r[code_idx].strip()
        name = r[name_idx].strip()
        if not code or not name:
            continue

        try:
            price = float(r[price_idx].replace(',', '')) if price_idx != -1 and price_idx < len(r) and r[price_idx].strip() else 0.0
        except:
            price = 0.0

        try:
            cost = float(r[cost_idx].replace(',', '')) if cost_idx != -1 and cost_idx < len(r) and r[cost_idx].strip() else 0.0
        except:
            cost = 0.0

        cat = r[cat_idx].strip() if cat_idx != -1 and cat_idx < len(r) else (classify_steel_category(code, name) or "เหล็ก")
        unit = r[unit_idx].strip() if unit_idx != -1 and unit_idx < len(r) else "เส้น"

        products.append({
            "code": code,
            "name": name,
            "category": cat,
            "unit": unit or "เส้น",
            "selling_price": price,
            "standard_cost": cost
        })

    return products
