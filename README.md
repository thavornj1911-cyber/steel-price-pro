# 2S Metal Steel Cost & Margin Pro (Mobile & Web App)

ระบบเช็คต้นทุนเหล็ก 2S Metal เปรียบเทียบกับราคาขายหน้าร้าน พร้อมจำลองกำไรและส่วนลดแบบเรียลไทม์ รองรับทั้งการเปิดบนคอมพิวเตอร์ที่ร้าน และบนโทรศัพท์มือถือผ่าน GitHub / Firebase 

---

## 📁 โครงสร้างไฟล์ในโฟลเดอร์นี้

```
steel-price-app/
├── index.html               # หน้าเว็บหลัก (Mobile Card View & Desktop Table View)
├── app.js                   # ระบบคำนวณกำไร, ฟิลเตอร์ Slicer, โหมดมือถือ & Local
├── styles.css               # สไตล์และธีมสี
├── manifest.json            # การตั้งค่า Progressive Web App (PWA)
├── sw.js                    # Service Worker สำหรับโหลดเร็วและออฟไลน์
├── firebase-config.js       # ไฟล์สำหรับใส่ค่า Firebase Configuration
├── cloud_data.json          # ข้อมูลสินค้าและราคาต้นทุน 2S ที่ซิงค์พร้อมขึ้น Cloud (213 รายการ)
├── icons/                   # ไอคอนแอปบนหน้าจอมือถือ (192x192, 512x512)
│
├── sync_cloud.bat           # ดับเบิ้ลคลิกเพื่อส่งราคาล่าสุดและรายการที่ผูกขึ้น Cloud
├── run_app.bat              # ดับเบิ้ลคลิกเพื่อเปิดระบบบนคอมพิวเตอร์ที่ร้าน
│
├── database.py              # ระบบฐานข้อมูล SQLite ในร้าน
├── express_reader.py        # ตัวอ่านข้อมูลจาก Express (DBF)
├── scraper_2smetal.py       # ตัวดึงราคาต้นทุนสดจาก 2S Metal DConnect (48 หมวด)
├── firebase_sync.py         # ตัวแปลงและซิงค์ข้อมูลขึ้น Firebase / Cloud
├── server.py                # เซิร์ฟเวอร์ FastAPI บนคอมที่ร้าน
│
├── .gitignore               # ป้องกันไม่ให้รหัสผ่าน 2S หรือไฟล์ฐานข้อมูลร้านหลุดขึ้น GitHub
└── firebase.json            # ไฟล์สำหรับ Deploy ขึ้น Firebase Hosting
```

---

## 🚀 วิธีเอาไฟล์ขึ้น GitHub (เลือกวิธีที่สะดวก)

### วิธีที่ 1: ใช้โปรแกรม GitHub Desktop (ง่ายที่สุด)
1. เปิดโปรแกรม **GitHub Desktop**
2. เลือก **File -> Add Local Repository** แล้วเลือกโฟลเดอร์นี้ (`steel-price-app`)
3. ถ้าโปรแกรมถามว่ายังไม่มี Git repository ให้กด **"create a repository"**
4. ตั้งชื่อ Repository เช่น `steel-price-app`
   > **ข้อสำคัญ:** แนะนำให้ติ๊กเลือกเป็น **Private** (เพื่อความปลอดภัยของข้อมูลราคาในร้าน)
5. กดปุ่ม **"Publish repository"** เพื่อส่งไฟล์ขึ้น GitHub ได้ทันที

### วิธีที่ 2: ใช้คำสั่ง Git ผ่าน Terminal / Command Prompt
```bash
cd "C:\Users\jkc\OneDrive - KMITL\Desktop\steel-price-app"
git init
git add .
git commit -m "Initial commit for 2S Metal Steel Pricing App"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/steel-price-app.git
git push -u origin main
```

---

## 📱 วิธีเปิดดูบนโทรศัพท์มือถือ

### ตัวเลือก A: เปิดผ่าน GitHub Pages (ฟรี 100% ไม่ต้องติดตั้งอะไรเพิ่ม)
1. เข้าไปที่หน้า Repository ของคุณบน GitHub
2. ไปที่ **Settings -> Pages**
3. ในหมวด **Branch** เลือก `main` และโฟลเดอร์ `/ (root)` แล้วกด **Save**
4. รอประมาณ 1 นาที จะได้ลิงก์ เช่น `https://<YOUR_USERNAME>.github.io/steel-price-app/`
5. นำลิงก์นี้ไปเปิดใน **Safari (iPhone)** หรือ **Chrome (Android)** บนโทรศัพท์มือถือ
6. **ทำเป็นแอปบนหน้าจอมือถือ:**
   - **iPhone (Safari):** กดปุ่ม Share (สี่เหลี่ยมลูกศรชี้ขึ้น) -> เลือก **"Add to Home Screen (เพิ่มไปยังหน้าจอโฮม)"**
   - **Android (Chrome):** กดจุด 3 จุดมุมขวาบน -> เลือก **"Install App"** หรือ **"Add to Home Screen"**

---

### ตัวเลือก B: เปิดผ่าน Firebase (Firestore + Firebase Hosting)
1. เข้าไปที่ [console.firebase.google.com](https://console.firebase.google.com) แล้วสร้างโปรเจกต์ใหม่
2. ไปที่ **Project Settings (รูปเฟือง) -> General -> Your apps -> Web (`</>`)**
3. คัดลอกค่า `firebaseConfig` มาใส่ในไฟล์ `firebase-config.js`
4. ไปที่ **Firestore Database** แล้วกด **Create database** (เลือก location: `asia-southeast1`)
5. รันคำสั่ง `firebase deploy` ผ่าน Firebase CLI

---

## 🔄 การอัปเดตราคาจากคอมร้านขึ้นโทรศัพท์มือถือ

เมื่อคอมพิวเตอร์ที่ร้านมีการเปลี่ยนแปลง เช่น:
- มีการดึงราคาใหม่จาก Express
- มีการดึงราคาต้นทุนใหม่จาก 2S Metal
- มีการแก้ไขการผูกสินค้า

👉 **วิธีอัปเดต:** ให้ดับเบิ้ลคลิกที่ไฟล์ **`sync_cloud.bat`** (หรือกดปุ่ม "ซิงค์ขึ้น Cloud" บนหน้าเว็บในคอมร้าน)  
ระบบจะรวมข้อมูลและอัปเดตขึ้น Cloud ให้ทันที เมื่อหยิบโทรศัพท์ขึ้นมาเปิดใหม่ ข้อมูลราคาจะเป็นข้อมูลล่าสุดทันทีครับ!
