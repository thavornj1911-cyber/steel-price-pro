import os
import json
import requests
from datetime import datetime
from typing import Dict, Any, Tuple
import database as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "serviceAccountKey.json")
FIREBASE_CONFIG_FILE = os.path.join(BASE_DIR, "static", "firebase-config.js")

def generate_cloud_bundle() -> Dict[str, Any]:
    """
    Builds the complete pricing matrix bundle ready for Firestore.
    Contains shop products, mapped 2S costs, profit margins, categories, and settings.
    """
    settings = db.get_all_settings()
    factors = db.get_cost_factors()
    
    # Get all pricing matrix items with mappings & 2S costs
    matrix_items = db.get_pricing_matrix(search="", category="", mapping_filter="all", margin_filter="all")
    
    # Category counts for slicers
    all_shop = db.get_shop_products()
    cat_counts = {}
    for s in all_shop:
        c = s.get("category") or "เหล็ก"
        cat_counts[c] = cat_counts.get(c, 0) + 1

    mappings = db.get_all_mappings()
    
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M น.")
    
    bundle = {
        "items": matrix_items,
        "cost_config": factors,
        "category_counts": cat_counts,
        "total_shop_count": len(all_shop),
        "mapped_count": len(mappings),
        "last_sync_time": f"ซิงค์สดเมื่อ {now_str}",
        "updated_at": datetime.now().isoformat(),
        "read_only": True
    }
    return bundle

def export_local_bundle_file() -> str:
    """Exports cloud_data.json locally for static hosting or testing."""
    bundle = generate_cloud_bundle()
    out_path = os.path.join(BASE_DIR, "static", "cloud_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    return out_path

def sync_to_firestore_rest(project_id: str, bundle: Dict[str, Any], api_key: str = "") -> Tuple[bool, str]:
    """
    Writes bundle to Cloud Firestore via Firestore REST API.
    Does not require any npm or heavy binary dependencies.
    Document path: projects/{project_id}/databases/(default)/documents/meta/pricing_bundle
    """
    url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/meta/pricing_bundle"
    if api_key:
        url += f"?key={api_key}"

    # Firestore REST requires typed value format
    payload = {
        "fields": {
            "data_json": {"stringValue": json.dumps(bundle, ensure_ascii=False)},
            "updated_at": {"stringValue": bundle.get("updated_at", "")},
            "last_sync_time": {"stringValue": bundle.get("last_sync_time", "")},
            "total_items": {"integerValue": str(len(bundle.get("items", [])))},
            "mapped_count": {"integerValue": str(bundle.get("mapped_count", 0))}
        }
    }

    try:
        resp = requests.patch(url, json=payload, timeout=15)
        if resp.status_code in [200, 201]:
            return True, f"ซิงค์ขึ้น Cloud Firestore สำเร็จ ({len(bundle.get('items', []))} รายการ)"
        else:
            return False, f"Firestore REST API แจ้งเตือน (HTTP {resp.status_code}): {resp.text[:200]}"
    except Exception as e:
        return False, f"เกิดข้อผิดพลาดในการเชื่อมต่อ Firestore: {str(e)}"

def sync_all_to_firebase() -> Tuple[bool, str]:
    """
    Master sync function called by server API and CLI.
    Checks config and pushes bundle to Firestore and updates local bundle.
    """
    # 1. Always update local static bundle for PWA/offline & GitHub Pages
    bundle = generate_cloud_bundle()
    export_local_bundle_file()
    
    # 2. Check if firebase-config.js has real project_id
    project_id = ""
    api_key = ""
    if os.path.exists(FIREBASE_CONFIG_FILE):
        try:
            with open(FIREBASE_CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                import re
                proj_m = re.search(r'projectId:\s*["\']([^"\']+)["\']', content)
                api_m = re.search(r'apiKey:\s*["\']([^"\']+)["\']', content)
                if proj_m and proj_m.group(1) != "YOUR_PROJECT_ID":
                    project_id = proj_m.group(1).strip()
                if api_m and api_m.group(1) != "YOUR_API_KEY":
                    api_key = api_m.group(1).strip()
        except:
            pass

    # 3. If ServiceAccountKey exists, try firebase-admin first
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            if not firebase_admin._apps:
                cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
                firebase_admin.initialize_app(cred)
            db_fs = firestore.client()
            doc_ref = db_fs.collection("meta").document("pricing_bundle")
            doc_ref.set({
                "data_json": json.dumps(bundle, ensure_ascii=False),
                "updated_at": bundle.get("updated_at", ""),
                "last_sync_time": bundle.get("last_sync_time", ""),
                "total_items": len(bundle.get("items", [])),
                "mapped_count": bundle.get("mapped_count", 0)
            })
            return True, f"ซิงค์ข้อมูลผ่าน Service Account ขึ้น Cloud Firestore สำเร็จเรียบร้อย! ({len(bundle.get('items', []))} รายการ)"
        except Exception as e:
            # Fall back to REST if project_id is available
            pass

    # 4. If project_id is available, sync via Firestore REST API
    if project_id:
        success, msg = sync_to_firestore_rest(project_id, bundle, api_key)
        if success:
            return True, msg
        else:
            return False, f"อัปเดตไฟล์ในเครื่องสำเร็จ แต่การส่งขึ้น Firestore แจ้งว่า: {msg}"

    return True, f"สร้างไฟล์ข้อมูลสำหรับ Cloud สำเร็จ ({len(bundle.get('items', []))} รายการ)! พร้อมนำขึ้น Firebase/GitHub"

if __name__ == "__main__":
    success, msg = sync_all_to_firebase()
    print("Result:", success)
    print("Message:", msg)
