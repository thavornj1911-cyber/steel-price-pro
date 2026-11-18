import os
import re
import json
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.2smetal.com"
LOGIN_PAGE_URL = f"{BASE_URL}/dconnect3"
AUTH_API_URL = f"{BASE_URL}/dconnect3/Home/Authen"
PRODUCT_PAGE_URL = f"{BASE_URL}/dconnect3/product"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "th,en-US;q=0.9,en;q=0.8",
}

def clean_num(val_str: Any) -> float:
    if val_str is None:
        return 0.0
    if isinstance(val_str, (int, float)):
        return float(val_str)
    s = str(val_str).replace(',', '').replace('฿', '').replace('บาท', '').strip()
    match = re.search(r'[-+]?\d*\.?\d+', s)
    return float(match.group(0)) if match else 0.0

def fetch_2smetal_live(username: str = "", password: str = "", session_cookie: str = "") -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Connects to 2S Metal DConnect:
    Option A: Uses existing session cookie if provided.
    Option B: Performs automated login using Username & Password.
    Returns: (success: bool, message: str, products: List[Dict])
    """
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.verify = False

    try:
        # Case 1: Session cookie provided directly
        if session_cookie.strip():
            cookie_val = session_cookie.strip()
            if "laravel_session=" in cookie_val:
                match = re.search(r'laravel_session=([^;]+)', cookie_val)
                if match:
                    cookie_val = match.group(1).strip()

            session.cookies.set("laravel_session", cookie_val, domain="www.2smetal.com")
            resp = session.get(PRODUCT_PAGE_URL, timeout=15, allow_redirects=True)

            if "login-box" in resp.text or "Authen" in resp.text:
                return False, "Session Cookie หมดอายุแล้ว กรุณาล็อกอินใหม่หรือกรอกชื่อผู้ใช้/รหัสผ่าน", []

            products = parse_2smetal_html(resp.text)
            if products:
                return True, f"ดึงข้อมูลสำเร็จผ่าน Session Cookie (พบสินค้า {len(products)} รายการ)", products
            else:
                return False, "เข้าหน้าสินค้าได้แต่ไม่พบตารางสินค้า (อาจไม่มีสิทธิ์หรือโครงสร้างหน้าเว็บเปลี่ยน)", []

        # Case 2: Username & Password provided
        if not username.strip() or not password.strip():
            return False, "กรุณากรอก Username และ Password ของ 2S Metal หรือระบุ Session Cookie", []

        # Step 1: GET login page to obtain CSRF and cookies
        init_resp = session.get(LOGIN_PAGE_URL, timeout=12)
        xsrf_token = None
        for cookie in session.cookies:
            if cookie.name == "XSRF-TOKEN":
                xsrf_token = urllib.parse.unquote(cookie.value)
                break

        if not xsrf_token:
            return False, "ไม่สามารถดึง XSRF-TOKEN จากระบบ 2S Metal ได้", []

        # Step 2: POST /dconnect3/Home/Authen
        auth_headers = {
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_PAGE_URL
        }
        auth_payload = {
            "UserName": username.strip(),
            "Password": password.strip()
        }

        auth_resp = session.post(AUTH_API_URL, json=auth_payload, headers=auth_headers, timeout=12)
        if auth_resp.status_code != 200:
            return False, f"เชื่อมต่อระบบล็อกอินไม่สำเร็จ (HTTP {auth_resp.status_code})", []

        auth_data = auth_resp.json()
        check_user = auth_data.get("return", {}).get("CheckUser", "")

        if check_user != "Pass":
            error_msg = check_user or "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
            return False, f"ล็อกอินไม่สำเร็จ: {error_msg}", []

        # Step 3: Authenticated! Fetch live products via 2S DConnect API
        # All 48 distinct categories discovered from live 2S Metal DConnect menu
        cat_codes = [
            'AG', 'AN', 'AW', 'BP', 'BS', 'BW', 'CE', 'CF', 'CL', 'CM',
            'CW', 'EM', 'FB', 'FM', 'GC', 'GP', 'GR', 'GS', 'GZ', 'HB',
            'KM', 'LC', 'LG', 'LT', 'MS', 'NA', 'PA', 'PC', 'PG', 'PL',
            'PW', 'PZ', 'QP', 'RB', 'RP', 'RW', 'SB', 'SP', 'SQ', 'SR',
            'SS', 'TP', 'WA', 'WD', 'WG', 'WI', 'WM', 'WT'
        ]
        products = []
        seen_codes = set()
        for code in cat_codes:
            url = f"https://www.2smetal.com/dconnect3/products/GetProduct/{code}/0/0/0/0/0"
            try:
                r = session.get(url, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    for p in data.get("products", []):
                        p_name = p.get("ProductName") or ""
                        p_code = p.get("ProductCode") or f"2S-{p.get('ProductID')}"
                        p_price = clean_num(p.get("Price"))
                        if p_name and p_price > 0 and p_code not in seen_codes:
                            seen_codes.add(p_code)
                            thick = p.get("ProductThickness")
                            sz = p.get("ProsizeGroup") or ""
                            spec = f"{sz} หนา {thick}mm" if thick and thick != '.00' else sz
                            quan = p.get("QuanAvai")
                            stock = f"พร้อมส่ง ({quan} เส้น)" if quan and str(quan) != '0' else "เช็คสต๊อก"
                            products.append({
                                "supplier_code": p_code,
                                "name": p_name,
                                "spec": spec.strip(),
                                "category": classify_2s_category(p_name),
                                "unit": p.get("Unit") or "เส้น",
                                "current_cost": p_price,
                                "stock_status": stock
                            })
            except Exception:
                continue

        if products:
            return True, f"เชื่อมต่อ 2S Metal สำเร็จ! อัปเดตสินค้าสด {len(products)} รายการ", products
        else:
            return False, "ล็อกอินสำเร็จ แต่ไม่สามารถดึงรายการสินค้าได้", []

    except requests.exceptions.RequestException as e:
        return False, f"เกิดข้อผิดพลาดในการเชื่อมต่อเครือข่าย: {str(e)}", []
    except Exception as e:
        return False, f"ข้อผิดพลาด: {str(e)}", []

def parse_2smetal_html(html_text: str) -> List[Dict[str, Any]]:
    """
    Parses products from 2S Metal DConnect HTML table or cards.
    Handles various standard layouts (DataTables, AdminLTE boxes, table rows).
    """
    products = []
    soup = BeautifulSoup(html_text, 'html.parser')

    # Try 1: Search for HTML tables
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue

        # Look at header to find column indices
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(['th', 'td'])]
        code_col, name_col, price_col, spec_col, unit_col, stock_col = -1, -1, -1, -1, -1, -1

        for i, h in enumerate(headers):
            if any(k in h for k in ['รหัส', 'code', 'item']):
                code_col = i
            elif any(k in h for k in ['สินค้า', 'ชื่อ', 'รายละเอียด', 'description', 'name', 'รายการ']):
                name_col = i
            elif any(k in h for k in ['ราคา', 'price', 'ต้นทุน', 'หน่วยละ', 'บาท']):
                price_col = i
            elif any(k in h for k in ['สเปก', 'ขนาด', 'spec', 'หนา', 'มม.']):
                spec_col = i
            elif any(k in h for k in ['หน่วย', 'unit']):
                unit_col = i
            elif any(k in h for k in ['สถานะ', 'สต๊อก', 'stock', 'คงเหลือ']):
                stock_col = i

        # If columns detected, parse rows
        if name_col != -1 or price_col != -1:
            for tr in rows[1:]:
                tds = tr.find_all('td')
                if len(tds) <= max(name_col, price_col):
                    continue

                code = tds[code_col].get_text(strip=True) if code_col != -1 and code_col < len(tds) else ""
                name = tds[name_col].get_text(strip=True) if name_col != -1 and name_col < len(tds) else ""
                price_str = tds[price_col].get_text(strip=True) if price_col != -1 and price_col < len(tds) else "0"
                spec = tds[spec_col].get_text(strip=True) if spec_col != -1 and spec_col < len(tds) else ""
                unit = tds[unit_col].get_text(strip=True) if unit_col != -1 and unit_col < len(tds) else "เส้น"
                stock = tds[stock_col].get_text(strip=True) if stock_col != -1 and stock_col < len(tds) else "พร้อมส่ง"

                price = clean_num(price_str)
                if name and price > 0:
                    products.append({
                        "supplier_code": code or f"2S-{len(products)+1:04d}",
                        "name": name,
                        "spec": spec,
                        "category": classify_2s_category(name),
                        "unit": unit or "เส้น",
                        "current_cost": price,
                        "stock_status": stock
                    })

    # Try 2: If no table matched, look for product cards or list items
    if not products:
        card_items = soup.select('.product-item, .item-box, .box-product, .card-product, .product-card')
        for card in card_items:
            name_el = card.select_one('.product-name, .name, .title, h4, h5')
            price_el = card.select_one('.product-price, .price, .cost, strong')
            code_el = card.select_one('.product-code, .code, .sku')
            spec_el = card.select_one('.product-spec, .spec, .size')

            if name_el and price_el:
                name = name_el.get_text(strip=True)
                price = clean_num(price_el.get_text(strip=True))
                code = code_el.get_text(strip=True) if code_el else f"2S-{len(products)+1:04d}"
                spec = spec_el.get_text(strip=True) if spec_el else ""

                if name and price > 0:
                    products.append({
                        "supplier_code": code,
                        "name": name,
                        "spec": spec,
                        "category": classify_2s_category(name),
                        "unit": "เส้น",
                        "current_cost": price,
                        "stock_status": "พร้อมส่ง"
                    })

    return products

def extract_embedded_json(html_text: str) -> List[Dict[str, Any]]:
    """Looks for window.products or var products = [...] embedded in scripts."""
    products = []
    matches = re.findall(r'(?:var|let|const|window\.)\s*(?:products|items|productList|data)\s*=\s*(\[.*?\]);', html_text, re.DOTALL)
    for m in matches:
        try:
            data = json.loads(m)
            if isinstance(data, list):
                for item in data:
                    name = item.get("name") or item.get("title") or item.get("ProductName") or item.get("StkDes") or ""
                    price = clean_num(item.get("price") or item.get("cost") or item.get("UnitPrice") or item.get("Price") or 0)
                    code = item.get("code") or item.get("sku") or item.get("ProductCode") or ""
                    if name and price > 0:
                        products.append({
                            "supplier_code": str(code),
                            "name": str(name),
                            "spec": str(item.get("spec", "")),
                            "category": classify_2s_category(str(name)),
                            "unit": str(item.get("unit", "เส้น")),
                            "current_cost": price,
                            "stock_status": "พร้อมส่ง"
                        })
        except:
            pass
    return products

def classify_2s_category(name: str) -> str:
    n = name.lower()
    if 'ประปา' in n:
        return 'ท่อประปา (Galvanized Pipe)'
    elif 'gi' in n or 'กัลวาไนซ์' in n or 'ชุบสังกะสี' in n or 'ขาว' in n or 'pre-zinc' in n or ' g ' in n or n.startswith('g ') or n.endswith(' g'):
        return 'เหล็กกัลวาไนซ์ (GI)'
    elif 'shs' in n or ('กล่อง' in n and 'แบน' not in n and 'rhs' not in n and 'ท่อแบน' not in n):
        return 'เหล็กกล่องดำ (SHS/Square)'
    elif 'rhs' in n or 'กล่องแบน' in n or 'ท่อแบน' in n or 'ไม้ขีด' in n:
        return 'เหล็กกล่องแบน (RHS/Rectangular)'
    elif 'ท่อดำ' in n or 'แป๊ปดำ' in n or 'ท่อกลม' in n or 'pipe' in n:
        return 'ท่อเหล็กดำ (Round Pipe)'
    elif 'ตัวซี' in n or 'เหล็กซี' in n or 'c-channel' in n:
        return 'เหล็กตัวซี (C-Channel)'
    elif 'ฉาก' in n or 'angle' in n:
        return 'เหล็กฉาก (Equal Angle)'
    elif 'แบน' in n or 'flat' in n:
        return 'เหล็กแบน (Flat Bar)'
    elif 'รางน้ำ' in n or 'channel' in n:
        return 'เหล็กรางน้ำ (Channel Steel)'
    elif 'ข้ออ้อย' in n or 'db' in n or 'rb' in n or 'เส้นกลม' in n:
        return 'เหล็กเส้นก่อสร้าง (Rebar/Round)'
    elif 'แผ่น' in n or 'plate' in n:
        return 'เหล็กแผ่นดำ (Steel Plate)'
    return 'เหล็กรูปพรรณ 2S Metal'

# ----------------- Sample 2S Metal Catalog Generator -----------------
def get_sample_2smetal_catalog() -> List[Dict[str, Any]]:
    """
    Standard comprehensive 2S Metal steel catalog with realistic current market factory prices.
    Used for initial instant readiness and demonstration.
    """
    catalog = [
        # --- เหล็กกล่องดำ (SHS) ---
        {"supplier_code": "2S-SHS-019-15", "name": "เหล็กกล่อง 3/4x3/4 (19x19mm) หนา 1.5mm ดำ", "spec": "19x19x1.5mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 145.00},
        {"supplier_code": "2S-SHS-025-12", "name": "เหล็กกล่อง 1x1 (25x25mm) หนา 1.2mm ดำ", "spec": "25x25x1.2mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 152.00},
        {"supplier_code": "2S-SHS-025-15", "name": "เหล็กกล่อง 1x1 (25x25mm) หนา 1.5mm ดำ", "spec": "25x25x1.5mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 182.00},
        {"supplier_code": "2S-SHS-025-18", "name": "เหล็กกล่อง 1x1 (25x25mm) หนา 1.8mm ดำ", "spec": "25x25x1.8mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 218.00},
        {"supplier_code": "2S-SHS-032-15", "name": "เหล็กกล่อง 1 1/4x1 1/4 (32x32mm) หนา 1.5mm ดำ", "spec": "32x32x1.5mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 225.00},
        {"supplier_code": "2S-SHS-038-15", "name": "เหล็กกล่อง 1 1/2x1 1/2 (38x38mm) หนา 1.5mm ดำ", "spec": "38x38x1.5mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 288.00},
        {"supplier_code": "2S-SHS-038-18", "name": "เหล็กกล่อง 1 1/2x1 1/2 (38x38mm) หนา 1.8mm ดำ", "spec": "38x38x1.8mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 335.00},
        {"supplier_code": "2S-SHS-038-20", "name": "เหล็กกล่อง 1 1/2x1 1/2 (38x38mm) หนา 2.0mm ดำ", "spec": "38x38x2.0mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 370.00},
        {"supplier_code": "2S-SHS-050-15", "name": "เหล็กกล่อง 2x2 (50x50mm) หนา 1.5mm ดำ", "spec": "50x50x1.5mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 380.00},
        {"supplier_code": "2S-SHS-050-18", "name": "เหล็กกล่อง 2x2 (50x50mm) หนา 1.8mm ดำ", "spec": "50x50x1.8mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 448.00},
        {"supplier_code": "2S-SHS-050-20", "name": "เหล็กกล่อง 2x2 (50x50mm) หนา 2.0mm ดำ", "spec": "50x50x2.0mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 495.00},
        {"supplier_code": "2S-SHS-050-23", "name": "เหล็กกล่อง 2x2 (50x50mm) หนา 2.3mm ดำ", "spec": "50x50x2.3mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 570.00},
        {"supplier_code": "2S-SHS-075-20", "name": "เหล็กกล่อง 3x3 (75x75mm) หนา 2.0mm ดำ", "spec": "75x75x2.0mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 765.00},
        {"supplier_code": "2S-SHS-075-23", "name": "เหล็กกล่อง 3x3 (75x75mm) หนา 2.3mm ดำ", "spec": "75x75x2.3mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 875.00},
        {"supplier_code": "2S-SHS-100-20", "name": "เหล็กกล่อง 4x4 (100x100mm) หนา 2.0mm ดำ", "spec": "100x100x2.0mm 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 1025.00},
        {"supplier_code": "2S-SHS-100-23", "name": "เหล็กกล่อง 4x4 (100x100mm) หนา 2.3mm ดำ", "spec": "100x100x2.3mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 1180.00},
        {"supplier_code": "2S-SHS-100-32", "name": "เหล็กกล่อง 4x4 (100x100mm) หนา 3.2mm ดำ", "spec": "100x100x3.2mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 1590.00},
        {"supplier_code": "2S-SHS-150-32", "name": "เหล็กกล่อง 6x6 (150x150mm) หนา 3.2mm ดำ", "spec": "150x150x3.2mm มอก. 6ม.", "category": "เหล็กกล่องดำ (SHS/Square)", "unit": "เส้น", "current_cost": 2420.00},

        # --- เหล็กกล่องแบน/ไม้ขีด (RHS) ---
        {"supplier_code": "2S-RHS-050-25-15", "name": "เหล็กกล่องแบน 2x1 (50x25mm) หนา 1.5mm ดำ", "spec": "50x25x1.5mm 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 285.00},
        {"supplier_code": "2S-RHS-050-25-18", "name": "เหล็กกล่องแบน 2x1 (50x25mm) หนา 1.8mm ดำ", "spec": "50x25x1.8mm 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 338.00},
        {"supplier_code": "2S-RHS-075-38-15", "name": "เหล็กกล่องแบน 3x1.5 (75x38mm) หนา 1.5mm ดำ", "spec": "75x38x1.5mm 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 435.00},
        {"supplier_code": "2S-RHS-075-38-20", "name": "เหล็กกล่องแบน 3x1.5 (75x38mm) หนา 2.0mm ดำ", "spec": "75x38x2.0mm 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 560.00},
        {"supplier_code": "2S-RHS-100-50-20", "name": "เหล็กกล่องแบน 4x2 (100x50mm) หนา 2.0mm ดำ", "spec": "100x50x2.0mm มอก. 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 755.00},
        {"supplier_code": "2S-RHS-100-50-23", "name": "เหล็กกล่องแบน 4x2 (100x50mm) หนา 2.3mm ดำ", "spec": "100x50x2.3mm มอก. 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 860.00},
        {"supplier_code": "2S-RHS-125-50-23", "name": "เหล็กกล่องแบน 5x2 (125x50mm) หนา 2.3mm ดำ", "spec": "125x50x2.3mm มอก. 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 1030.00},
        {"supplier_code": "2S-RHS-150-50-23", "name": "เหล็กกล่องแบน 6x2 (150x50mm) หนา 2.3mm ดำ", "spec": "150x50x2.3mm มอก. 6ม.", "category": "เหล็กกล่องแบน (RHS/Rectangular)", "unit": "เส้น", "current_cost": 1190.00},

        # --- ท่อเหล็กดำ (Round Pipe) ---
        {"supplier_code": "2S-PIP-015-15", "name": "ท่อดำ 1/2 นิ้ว (OD 21.7mm) หนา 1.5mm", "spec": "1/2\" (21.7) x 1.5mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 128.00},
        {"supplier_code": "2S-PIP-020-15", "name": "ท่อดำ 3/4 นิ้ว (OD 27.2mm) หนา 1.5mm", "spec": "3/4\" (27.2) x 1.5mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 165.00},
        {"supplier_code": "2S-PIP-025-15", "name": "ท่อดำ 1 นิ้ว (OD 34.0mm) หนา 1.5mm", "spec": "1\" (34.0) x 1.5mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 210.00},
        {"supplier_code": "2S-PIP-032-15", "name": "ท่อดำ 1 1/4 นิ้ว (OD 42.7mm) หนา 1.5mm", "spec": "1 1/4\" (42.7) x 1.5mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 268.00},
        {"supplier_code": "2S-PIP-040-18", "name": "ท่อดำ 1 1/2 นิ้ว (OD 48.6mm) หนา 1.8mm", "spec": "1 1/2\" (48.6) x 1.8mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 365.00},
        {"supplier_code": "2S-PIP-050-18", "name": "ท่อดำ 2 นิ้ว (OD 60.5mm) หนา 1.8mm", "spec": "2\" (60.5) x 1.8mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 460.00},
        {"supplier_code": "2S-PIP-050-20", "name": "ท่อดำ 2 นิ้ว (OD 60.5mm) หนา 2.0mm", "spec": "2\" (60.5) x 2.0mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 505.00},
        {"supplier_code": "2S-PIP-065-20", "name": "ท่อดำ 2 1/2 นิ้ว (OD 76.3mm) หนา 2.0mm", "spec": "2 1/2\" (76.3) x 2.0mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 645.00},
        {"supplier_code": "2S-PIP-080-20", "name": "ท่อดำ 3 นิ้ว (OD 89.1mm) หนา 2.0mm", "spec": "3\" (89.1) x 2.0mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 755.00},
        {"supplier_code": "2S-PIP-100-23", "name": "ท่อดำ 4 นิ้ว (OD 114.3mm) หนา 2.3mm", "spec": "4\" (114.3) x 2.3mm 6ม.", "category": "ท่อเหล็กดำ (Round Pipe)", "unit": "เส้น", "current_cost": 1130.00},

        # --- เหล็กกัลวาไนซ์ GI (Pre-zinc) ---
        {"supplier_code": "2S-GI-SHS-025-12", "name": "เหล็กกล่องGI 1x1 หนา 1.2mm ขาว/ฟ้า", "spec": "25x25x1.2mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 138.00},
        {"supplier_code": "2S-GI-SHS-025-15", "name": "เหล็กกล่องGI 1x1 หนา 1.5mm ขาว/เหลือง", "spec": "25x25x1.5mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 168.00},
        {"supplier_code": "2S-GI-SHS-032-15", "name": "เหล็กกล่องGI 1 1/4x1 1/4 หนา 1.5mm ขาว/เหลือง", "spec": "32x32x1.5mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 215.00},
        {"supplier_code": "2S-GI-SHS-038-15", "name": "เหล็กกล่องGI 1 1/2x1 1/2 หนา 1.5mm ขาว/เหลือง", "spec": "38x38x1.5mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 258.00},
        {"supplier_code": "2S-GI-SHS-050-15", "name": "เหล็กกล่องGI 2x2 หนา 1.5mm ขาว/เหลือง", "spec": "50x50x1.5mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 345.00},
        {"supplier_code": "2S-GI-SHS-050-18", "name": "เหล็กกล่องGI 2x2 หนา 1.8mm ขาว/แดง", "spec": "50x50x1.8mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 410.00},
        {"supplier_code": "2S-GI-SHS-075-18", "name": "เหล็กกล่องGI 3x3 หนา 1.8mm ขาว/แดง", "spec": "75x75x1.8mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 625.00},
        {"supplier_code": "2S-GI-SHS-100-18", "name": "เหล็กกล่องGI 4x4 หนา 1.8mm ขาว/แดง", "spec": "100x100x1.8mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 840.00},
        {"supplier_code": "2S-GI-RHS-050-25-15", "name": "เหล็กกล่องแบนGI 2x1 หนา 1.5mm ขาว/เหลือง", "spec": "50x25x1.5mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 255.00},
        {"supplier_code": "2S-GI-RHS-075-38-15", "name": "เหล็กกล่องแบนGI 3x1.5 หนา 1.5mm ขาว/เหลือง", "spec": "75x38x1.5mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 390.00},
        {"supplier_code": "2S-GI-RHS-100-50-18", "name": "เหล็กกล่องแบนGI 4x2 หนา 1.8mm ขาว/แดง", "spec": "100x50x1.8mm GI 6ม.", "category": "เหล็กกัลวาไนซ์ (GI)", "unit": "เส้น", "current_cost": 635.00},

        # --- เหล็กตัวซี (C-Channel) ---
        {"supplier_code": "2S-CCH-075-45-16", "name": "เหล็กตัวซี 75x45x15 หนา 1.6mm", "spec": "75x45x15x1.6mm 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 285.00},
        {"supplier_code": "2S-CCH-075-45-20", "name": "เหล็กตัวซี 75x45x15 หนา 2.0mm", "spec": "75x45x15x2.0mm 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 355.00},
        {"supplier_code": "2S-CCH-100-50-16", "name": "เหล็กตัวซี 100x50x20 หนา 1.6mm", "spec": "100x50x20x1.6mm 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 365.00},
        {"supplier_code": "2S-CCH-100-50-20", "name": "เหล็กตัวซี 100x50x20 หนา 2.0mm", "spec": "100x50x20x2.0mm 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 450.00},
        {"supplier_code": "2S-CCH-100-50-23", "name": "เหล็กตัวซี 100x50x20 หนา 2.3mm มอก.", "spec": "100x50x20x2.3mm มอก. 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 520.00},
        {"supplier_code": "2S-CCH-100-50-32", "name": "เหล็กตัวซี 100x50x20 หนา 3.2mm มอก.", "spec": "100x50x20x3.2mm มอก. 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 710.00},
        {"supplier_code": "2S-CCH-125-50-23", "name": "เหล็กตัวซี 125x50x20 หนา 2.3mm มอก.", "spec": "125x50x20x2.3mm มอก. 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 625.00},
        {"supplier_code": "2S-CCH-150-50-23", "name": "เหล็กตัวซี 150x50x20 หนา 2.3mm มอก.", "spec": "150x50x20x2.3mm มอก. 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 725.00},
        {"supplier_code": "2S-CCH-150-65-32", "name": "เหล็กตัวซี 150x65x20 หนา 3.2mm มอก.", "spec": "150x65x20x3.2mm มอก. 6ม.", "category": "เหล็กตัวซี (C-Channel)", "unit": "เส้น", "current_cost": 1050.00},

        # --- เหล็กฉาก (Equal Angle) ---
        {"supplier_code": "2S-ANG-025-025-30", "name": "เหล็กฉาก 1x1 นิ้ว (25x25mm) หนา 3.0mm", "spec": "25x25x3.0mm มอก. 6ม.", "category": "เหล็กฉาก (Equal Angle)", "unit": "เส้น", "current_cost": 210.00},
        {"supplier_code": "2S-ANG-030-030-30", "name": "เหล็กฉาก 1 1/4x1 1/4 นิ้ว (30x30mm) หนา 3.0mm", "spec": "30x30x3.0mm มอก. 6ม.", "category": "เหล็กฉาก (Equal Angle)", "unit": "เส้น", "current_cost": 255.00},
        {"supplier_code": "2S-ANG-040-040-30", "name": "เหล็กฉาก 1 1/2x1 1/2 นิ้ว (40x40mm) หนา 3.0mm", "spec": "40x40x3.0mm มอก. 6ม.", "category": "เหล็กฉาก (Equal Angle)", "unit": "เส้น", "current_cost": 345.00},
        {"supplier_code": "2S-ANG-050-050-30", "name": "เหล็กฉาก 2x2 นิ้ว (50x50mm) หนา 3.0mm", "spec": "50x50x3.0mm มอก. 6ม.", "category": "เหล็กฉาก (Equal Angle)", "unit": "เส้น", "current_cost": 435.00},
        {"supplier_code": "2S-ANG-050-050-40", "name": "เหล็กฉาก 2x2 นิ้ว (50x50mm) หนา 4.0mm มอก.", "spec": "50x50x4.0mm มอก. 6ม.", "category": "เหล็กฉาก (Equal Angle)", "unit": "เส้น", "current_cost": 575.00},
        {"supplier_code": "2S-ANG-050-050-50", "name": "เหล็กฉาก 2x2 นิ้ว (50x50mm) หนา 5.0mm มอก.", "spec": "50x50x5.0mm มอก. 6ม.", "category": "เหล็กฉาก (Equal Angle)", "unit": "เส้น", "current_cost": 710.00},
        {"supplier_code": "2S-ANG-075-075-60", "name": "เหล็กฉาก 3x3 นิ้ว (75x75mm) หนา 6.0mm มอก.", "spec": "75x75x6.0mm มอก. 6ม.", "category": "เหล็กฉาก (Equal Angle)", "unit": "เส้น", "current_cost": 1420.00},

        # --- เหล็กแบน (Flat Bar) ---
        {"supplier_code": "2S-FLT-025-30", "name": "เหล็กแบน 1 นิ้ว (25mm) หนา 3.0mm", "spec": "25x3.0mm 6ม.", "category": "เหล็กแบน (Flat Bar)", "unit": "เส้น", "current_cost": 115.00},
        {"supplier_code": "2S-FLT-032-30", "name": "เหล็กแบน 1 1/4 นิ้ว (32mm) หนา 3.0mm", "spec": "32x3.0mm 6ม.", "category": "เหล็กแบน (Flat Bar)", "unit": "เส้น", "current_cost": 145.00},
        {"supplier_code": "2S-FLT-038-30", "name": "เหล็กแบน 1 1/2 นิ้ว (38mm) หนา 3.0mm", "spec": "38x3.0mm 6ม.", "category": "เหล็กแบน (Flat Bar)", "unit": "เส้น", "current_cost": 175.00},
        {"supplier_code": "2S-FLT-050-30", "name": "เหล็กแบน 2 นิ้ว (50mm) หนา 3.0mm", "spec": "50x3.0mm 6ม.", "category": "เหล็กแบน (Flat Bar)", "unit": "เส้น", "current_cost": 230.00},
        {"supplier_code": "2S-FLT-050-45", "name": "เหล็กแบน 2 นิ้ว (50mm) หนา 4.5mm", "spec": "50x4.5mm 6ม.", "category": "เหล็กแบน (Flat Bar)", "unit": "เส้น", "current_cost": 340.00},

        # --- เหล็กรางน้ำ (Channel Steel) ---
        {"supplier_code": "2S-CHN-075-40-50", "name": "เหล็กรางน้ำ 3 นิ้ว (75x40mm) หนา 5.0mm มอก.", "spec": "75x40x5.0mm มอก. 6ม.", "category": "เหล็กรางน้ำ (Channel Steel)", "unit": "เส้น", "current_cost": 1080.00},
        {"supplier_code": "2S-CHN-100-50-50", "name": "เหล็กรางน้ำ 4 นิ้ว (100x50mm) หนา 5.0mm มอก.", "spec": "100x50x5.0mm มอก. 6ม.", "category": "เหล็กรางน้ำ (Channel Steel)", "unit": "เส้น", "current_cost": 1520.00},
        {"supplier_code": "2S-CHN-125-65-60", "name": "เหล็กรางน้ำ 5 นิ้ว (125x65mm) หนา 6.0mm มอก.", "spec": "125x65x6.0mm มอก. 6ม.", "category": "เหล็กรางน้ำ (Channel Steel)", "unit": "เส้น", "current_cost": 2480.00},
        {"supplier_code": "2S-CHN-150-75-65", "name": "เหล็กรางน้ำ 6 นิ้ว (150x75mm) หนา 6.5mm มอก.", "spec": "150x75x6.5mm มอก. 6ม.", "category": "เหล็กรางน้ำ (Channel Steel)", "unit": "เส้น", "current_cost": 3450.00},

        # --- เหล็กข้ออ้อย & เส้นกลม (Rebar / Round) ---
        {"supplier_code": "2S-RB-006", "name": "เหล็กเส้นกลม SR24 ขนาด RB6 ความยาว 10ม.", "spec": "RB6 SR24 10ม.", "category": "เหล็กเส้นก่อสร้าง (Rebar/Round)", "unit": "เส้น", "current_cost": 55.00},
        {"supplier_code": "2S-RB-009", "name": "เหล็กเส้นกลม SR24 ขนาด RB9 ความยาว 10ม.", "spec": "RB9 SR24 10ม.", "category": "เหล็กเส้นก่อสร้าง (Rebar/Round)", "unit": "เส้น", "current_cost": 122.00},
        {"supplier_code": "2S-DB-012", "name": "เหล็กข้ออ้อย SD40 ขนาด DB12 ความยาว 10ม.", "spec": "DB12 SD40 มอก. 10ม.", "category": "เหล็กเส้นก่อสร้าง (Rebar/Round)", "unit": "เส้น", "current_cost": 218.00},
        {"supplier_code": "2S-DB-016", "name": "เหล็กข้ออ้อย SD40 ขนาด DB16 ความยาว 10ม.", "spec": "DB16 SD40 มอก. 10ม.", "category": "เหล็กเส้นก่อสร้าง (Rebar/Round)", "unit": "เส้น", "current_cost": 388.00},
        {"supplier_code": "2S-DB-020", "name": "เหล็กข้ออ้อย SD40 ขนาด DB20 ความยาว 10ม.", "spec": "DB20 SD40 มอก. 10ม.", "category": "เหล็กเส้นก่อสร้าง (Rebar/Round)", "unit": "เส้น", "current_cost": 605.00},
        {"supplier_code": "2S-DB-025", "name": "เหล็กข้ออ้อย SD40 ขนาด DB25 ความยาว 10ม.", "spec": "DB25 SD40 มอก. 10ม.", "category": "เหล็กเส้นก่อสร้าง (Rebar/Round)", "unit": "เส้น", "current_cost": 945.00},

        # --- ท่อประปา / ท่อเหล็กอาบสังกะสี (Galvanized Pipe / มอก. 277 / BS 1387) ---
        # 1. คาดเหลือง (BS-S ชนิดบาง/เบา)
        {"supplier_code": "2S-GAL-YEL-015", "name": "ท่อประปา 1/2 นิ้ว (15mm) คาดเหลือง BS-S", "spec": "1/2\" (21.7) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 195.00},
        {"supplier_code": "2S-GAL-YEL-020", "name": "ท่อประปา 3/4 นิ้ว (20mm) คาดเหลือง BS-S", "spec": "3/4\" (27.2) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 248.00},
        {"supplier_code": "2S-GAL-YEL-025", "name": "ท่อประปา 1 นิ้ว (25mm) คาดเหลือง BS-S", "spec": "1\" (34.0) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 355.00},
        {"supplier_code": "2S-GAL-YEL-032", "name": "ท่อประปา 1 1/4 นิ้ว (32mm) คาดเหลือง BS-S", "spec": "1 1/4\" (42.7) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 505.00},
        {"supplier_code": "2S-GAL-YEL-040", "name": "ท่อประปา 1 1/2 นิ้ว (40mm) คาดเหลือง BS-S", "spec": "1 1/2\" (48.6) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 570.00},
        {"supplier_code": "2S-GAL-YEL-050", "name": "ท่อประปา 2 นิ้ว (50mm) คาดเหลือง BS-S 1.9มม.", "spec": "2\" (60.5) คาดเหลือง BS-S 1.9mm 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 715.00},
        {"supplier_code": "2S-GAL-YEL-065", "name": "ท่อประปา 2 1/2 นิ้ว (65mm) คาดเหลือง BS-S", "spec": "2 1/2\" (76.3) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 1010.00},
        {"supplier_code": "2S-GAL-YEL-080", "name": "ท่อประปา 3 นิ้ว (80mm) คาดเหลือง BS-S", "spec": "3\" (89.1) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 1290.00},
        {"supplier_code": "2S-GAL-YEL-100", "name": "ท่อประปา 4 นิ้ว (100mm) คาดเหลือง BS-S", "spec": "4\" (114.3) คาดเหลือง BS-S 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 1950.00},

        # 2. คาดน้ำเงิน (BS-M มอก. ชนิดปานกลาง/มาตรฐาน)
        {"supplier_code": "2S-GAL-BLU-015", "name": "ท่อประปา 1/2 นิ้ว (15mm) คาดน้ำเงิน มอก. BS-M", "spec": "1/2\" (21.7x2.6) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 145.00},
        {"supplier_code": "2S-GAL-BLU-020", "name": "ท่อประปา 3/4 นิ้ว (20mm) คาดน้ำเงิน มอก. BS-M", "spec": "3/4\" (27.2x2.6) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 190.00},
        {"supplier_code": "2S-GAL-BLU-025", "name": "ท่อประปา 1 นิ้ว (25mm) คาดน้ำเงิน มอก. BS-M", "spec": "1\" (34.0x3.2) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 242.00},
        {"supplier_code": "2S-GAL-BLU-032", "name": "ท่อประปา 1 1/4 นิ้ว (32mm) คาดน้ำเงิน มอก. BS-M", "spec": "1 1/4\" (42.7x3.2) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 312.00},
        {"supplier_code": "2S-GAL-BLU-040", "name": "ท่อประปา 1 1/2 นิ้ว (40mm) คาดน้ำเงิน มอก. BS-M", "spec": "1 1/2\" (48.6x3.2) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 350.00},
        {"supplier_code": "2S-GAL-BLU-050", "name": "ท่อประปา 2 นิ้ว (50mm) คาดน้ำเงิน มอก. BS-M", "spec": "2\" (60.5x3.6) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 528.00},
        {"supplier_code": "2S-GAL-BLU-065", "name": "ท่อประปา 2 1/2 นิ้ว (65mm) คาดน้ำเงิน มอก. BS-M", "spec": "2 1/2\" (76.3x3.6) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 618.00},
        {"supplier_code": "2S-GAL-BLU-080", "name": "ท่อประปา 3 นิ้ว (80mm) คาดน้ำเงิน มอก. BS-M", "spec": "3\" (89.1x4.0) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 890.00},
        {"supplier_code": "2S-GAL-BLU-100", "name": "ท่อประปา 4 นิ้ว (100mm) คาดน้ำเงิน มอก. BS-M", "spec": "4\" (114.3x4.5) คาดน้ำเงิน มอก. 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 1390.00},

        # 3. คาดแดง (BS-H หนาพิเศษ)
        {"supplier_code": "2S-GAL-RED-015", "name": "ท่อประปา 1/2 นิ้ว คาดแดง BS-H", "spec": "1/2\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 215.00},
        {"supplier_code": "2S-GAL-RED-020", "name": "ท่อประปา 3/4 นิ้ว คาดแดง BS-H", "spec": "3/4\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 275.00},
        {"supplier_code": "2S-GAL-RED-025", "name": "ท่อประปา 1 นิ้ว คาดแดง BS-H", "spec": "1\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 395.00},
        {"supplier_code": "2S-GAL-RED-032", "name": "ท่อประปา 1 1/4 นิ้ว คาดแดง BS-H", "spec": "1 1/4\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 545.00},
        {"supplier_code": "2S-GAL-RED-040", "name": "ท่อประปา 1 1/2 นิ้ว คาดแดง BS-H", "spec": "1 1/2\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 620.00},
        {"supplier_code": "2S-GAL-RED-050", "name": "ท่อประปา 2 นิ้ว คาดแดง BS-H", "spec": "2\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 845.00},
        {"supplier_code": "2S-GAL-RED-080", "name": "ท่อประปา 3 นิ้ว คาดแดง BS-H", "spec": "3\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 1580.00},
        {"supplier_code": "2S-GAL-RED-100", "name": "ท่อประปา 4 นิ้ว คาดแดง BS-H", "spec": "4\" คาดแดง หนาพิเศษ 6ม.", "category": "ท่อประปา (Galvanized Pipe)", "unit": "เส้น", "current_cost": 2250.00},

        # 4. แป๊ปประปาสำเร็จสั้น (เกลียวหัวท้าย)
        {"supplier_code": "2S-NIP-015-10", "name": "แป๊ปประปาสำเร็จ 1/2 นิ้ว x 10 ซม.", "spec": "1/2\" x 10cm เกลียวหัวท้าย", "category": "ท่อประปา (Galvanized Pipe)", "unit": "ท่อน", "current_cost": 18.00},
        {"supplier_code": "2S-NIP-015-20", "name": "แป๊ปประปาสำเร็จ 1/2 นิ้ว x 20 ซม.", "spec": "1/2\" x 20cm เกลียวหัวท้าย", "category": "ท่อประปา (Galvanized Pipe)", "unit": "ท่อน", "current_cost": 32.00},
        {"supplier_code": "2S-NIP-015-25", "name": "แป๊ปประปาสำเร็จ 1/2 นิ้ว x 25 ซม.", "spec": "1/2\" x 25cm เกลียวหัวท้าย", "category": "ท่อประปา (Galvanized Pipe)", "unit": "ท่อน", "current_cost": 40.00},
        {"supplier_code": "2S-NIP-015-30", "name": "แป๊ปประปาสำเร็จ 1/2 นิ้ว x 30 ซม.", "spec": "1/2\" x 30cm เกลียวหัวท้าย", "category": "ท่อประปา (Galvanized Pipe)", "unit": "ท่อน", "current_cost": 46.00},
        {"supplier_code": "2S-NIP-020-30", "name": "แป๊ปประปาสำเร็จ 3/4 นิ้ว x 30 ซม.", "spec": "3/4\" x 30cm เกลียวหัวท้าย", "category": "ท่อประปา (Galvanized Pipe)", "unit": "ท่อน", "current_cost": 58.00},
        {"supplier_code": "2S-NIP-025-30", "name": "แป๊ปประปาสำเร็จ 1 นิ้ว x 30 ซม.", "spec": "1\" x 30cm เกลียวหัวท้าย", "category": "ท่อประปา (Galvanized Pipe)", "unit": "ท่อน", "current_cost": 75.00},
    ]
    return catalog
