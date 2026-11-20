# -*- coding: utf-8 -*-
"""
เครื่องมืออัปเดตราคาต้นทุน 2S Metal อัตโนมัติ
ดึงราคาเรียลไทม์จากระบบ 2S Metal DConnect และบันทึกลงฐานข้อมูล พร้อมเตรียมไฟล์สำหรับเว็บ
"""
import sys
import os
import shutil
from datetime import datetime

# Set encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import database as db
from scraper_2smetal import fetch_2smetal_live
import firebase_sync

def main():
    print("=" * 60)
    print("   2S Metal Pro - เครื่องมืออัปเดตราคาต้นทุนเรียลไทม์")
    print("   (ดึงราคาล่าสุดจาก https://www.2smetal.com/dconnect3)")
    print("=" * 60)
    print()

    settings = db.get_all_settings()
    default_user = settings.get("2s_username", "sujindamoo79@gmail.com")
    default_pass = settings.get("2s_password", "Pjow2439")

    print(f"บัญชี 2S Metal: {default_user}")
    print("[1/3] กำลังเชื่อมต่อและล็อกอินเข้าสู่ระบบ 2S Metal DConnect...")

    success, msg, products = fetch_2smetal_live(default_user, default_pass)

    if not success or not products:
        print(f"\n❌ การเชื่อมต่อล้มเหลว: {msg}")
        print("\nหากมีการเปลี่ยนรหัสผ่าน กรุณาตรวจสอบหรืออัปเดตในระบบ")
        input("\nกด Enter เพื่อปิดหน้าต่าง...")
        return

    print(f"\n[2/3] {msg}")
    print(f"กำลังเปรียบเทียบราคาและบันทึกลงฐานข้อมูล ({len(products)} รายการ)...")

    count = db.batch_upsert_supplier_products(products)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.set_setting("last_sync_time", now_str)
    db.set_setting("sync_status", f"ดึงข้อมูลสำเร็จสด ({count} รายการ)")

    print(f"[3/3] กำลังสร้างไฟล์ข้อมูลสำหรับเว็บและมือถือ (Cloud Bundle)...")
    bundle = firebase_sync.generate_cloud_bundle()

    price_up = bundle.get("price_up_count", 0)
    price_down = bundle.get("price_down_count", 0)
    price_same = bundle.get("price_same_count", 0)

    print()
    print("=" * 60)
    print("   🎉 อัปเดตราคาเรียบร้อยแล้ว!")
    print("=" * 60)
    print(f"   • สินค้า 2S ทั้งหมด:   {len(products):,} รายการ")
    print(f"   • รายการที่ราคาปรับขึ้น: 🔺 {price_up} รายการ")
    print(f"   • รายการที่ราคาปรับลง: 🔻 {price_down} รายการ")
    print(f"   • เวลาอัปเดต:          {now_str}")
    print("=" * 60)
    print()
    print("👉 ขั้นตอนต่อไป:")
    print("   นำไฟล์ 'cloud_data.json' และ 'supplier_products.json'")
    print("   ไปอัปโหลดขึ้น GitHub Repository เพื่อให้ราคาบนมือถืออัปเดตทันที!")
    print()
    input("กด Enter เพื่อปิดหน้าต่าง...")

if __name__ == "__main__":
    main()
