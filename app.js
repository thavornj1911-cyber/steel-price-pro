// 2S Metal Steel Pricing & Margin Application Frontend Logic

const STEEL_CATEGORIES = [
    'ท่อประปา',
    'เหล็กรูปดำ',
    'เหล็กรูปขาว',
    'เหล็กฉาก',
    'เหล็กเส้น',
    'กลมดำ',
    'แบนรีด',
    'ไวร์เมช',
    'แปรสำเร็จ',
    'เพลท',
    'ปอก',
    'ลวด',
    'กิ๊ปลวดหนาม',
    'ตะแกรง ตาข่าย',
    'ไม่ค่อยได้ขาย'
];

let appState = {
    matrix: [],
    supplierProducts: [],
    shopProducts: [],
    mappings: [],
    settings: {},
    discounts: {}, // { shop_id: custom_price }
    activeTab: 'pricing',
    viewMode: 'table', // 'cards' (mobile) or 'table' (desktop)
    filterDebounceTimer: null,
    selectedShopForMapping: null,
    mappingFilterType: 'unmapped',
    selectedCategory: '',
    mapSelectedCategory: '',
    categoryCounts: {},
    totalShopCount: 0
};

document.addEventListener('DOMContentLoaded', async () => {
    lucide.createIcons();
    initViewMode();

    // Register Service Worker for PWA (Progressive Web App)
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('./sw.js')
            .then(reg => console.log('PWA Service Worker registered:', reg.scope))
            .catch(err => console.log('PWA Service Worker registration skipped/failed:', err));
    }

    renderCategorySlicers();
    await loadInitialData();
});

// ----------------- View Mode Switcher (Mobile Cards vs Desktop Table) -----------------
function setViewMode(mode) {
    appState.viewMode = mode;
    const cardsContainer = document.getElementById('matrixCardsContainer');
    const tableContainer = document.getElementById('matrixTableContainer');
    const btnCards = document.getElementById('viewBtnCards');
    const btnTable = document.getElementById('viewBtnTable');

    if (mode === 'cards') {
        if (cardsContainer) cardsContainer.classList.remove('hidden');
        if (tableContainer) tableContainer.classList.add('hidden');
        if (btnCards) btnCards.className = 'flex items-center space-x-1 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-white text-blue-700 shadow-sm transition';
        if (btnTable) btnTable.className = 'flex items-center space-x-1 px-2.5 py-1.5 rounded-md text-xs font-semibold text-slate-600 hover:text-slate-900 transition';
    } else {
        if (cardsContainer) cardsContainer.classList.add('hidden');
        if (tableContainer) tableContainer.classList.remove('hidden');
        if (btnTable) btnTable.className = 'flex items-center space-x-1 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-white text-blue-700 shadow-sm transition';
        if (btnCards) btnCards.className = 'flex items-center space-x-1 px-2.5 py-1.5 rounded-md text-xs font-semibold text-slate-600 hover:text-slate-900 transition';
    }
    try {
        localStorage.setItem('steel_view_mode', mode);
    } catch(e) {}
}

function initViewMode() {
    let saved = null;
    try {
        saved = localStorage.getItem('steel_view_mode');
    } catch(e) {}
    // If mobile screen (width < 768px), default to cards view, else table view
    const defaultMode = saved || (window.innerWidth < 768 ? 'cards' : 'table');
    setViewMode(defaultMode);
}

// ----------------- Data Loading (Dual Mode: Local Shop Server vs Cloud/Firebase) -----------------
async function loadInitialData() {
    const isLocal = (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') && (window.location.port === '8099' || window.location.port === '8000');
    
    if (isLocal) {
        try {
            await Promise.all([
                fetchStatus(),
                fetchSettings(),
                fetchMatrix(),
                fetchSupplierProducts()
            ]);
            return;
        } catch (e) {
            console.warn("Local server fetch failed, trying cloud fallback...", e);
        }
    }

    // Cloud Mode (Running on Mobile / Firebase Hosting / GitHub Pages)
    await loadCloudMode();
}

async function loadCloudMode() {
    appState.isCloudMode = true;
    applyCloudUIRestrictions();

    // 1. Try Firebase Firestore if configured
    if (window.firebaseConfig && window.firebaseConfig.projectId && window.firebaseConfig.projectId !== "YOUR_PROJECT_ID") {
        try {
            if (typeof firebase !== 'undefined') {
                if (!firebase.apps.length) {
                    firebase.initializeApp(window.firebaseConfig);
                }
                const dbFs = firebase.firestore();
                const doc = await dbFs.collection('meta').doc('pricing_bundle').get();
                if (doc.exists) {
                    const data = doc.data();
                    const bundle = data.data_json ? JSON.parse(data.data_json) : data;
                    renderCloudBundle(bundle);
                    showToast("☁️ โหลดข้อมูลสดจาก Cloud Firestore สำเร็จ", "success");
                    return;
                }
            }
        } catch (err) {
            console.warn("Firestore fetch error, falling back to static bundle:", err);
        }
    }

    // 2. Fallback: Load pre-synced cloud_data.json
    try {
        const res = await fetch('./cloud_data.json');
        if (res.ok) {
            const bundle = await res.json();
            renderCloudBundle(bundle);
            showToast("📱 โหมดมือถือ: โหลดข้อมูลราคาล่าสุดสำเร็จ", "info");
        } else {
            showToast("ไม่พบข้อมูลบน Cloud กรุณากด 'ซิงค์ขึ้น Cloud' จากคอมที่ร้านก่อน", "warning");
        }
    } catch (e) {
        console.error("Cloud load error:", e);
        showToast("ไม่สามารถโหลดข้อมูล Cloud ได้", "error");
    }
}

function applyCloudUIRestrictions() {
    // Hide administrative buttons not needed on mobile reader
    const syncBtn = document.querySelector('button[onclick="openSyncModal()"]');
    if (syncBtn) syncBtn.classList.add('hidden');
    const expressBtn = document.querySelector('button[onclick="importExpressAuto()"]');
    if (expressBtn) expressBtn.classList.add('hidden');
    const cloudSyncBtn = document.querySelector('button[onclick="syncToCloud()"]');
    if (cloudSyncBtn) cloudSyncBtn.classList.add('hidden');

    // On mobile phone: Only keep 'เทียบราคา & จำลองกำไร' tab, hide Admin tabs
    const tabMapping = document.getElementById('tabBtn-mapping');
    if (tabMapping) tabMapping.classList.add('hidden');
    const tabShop = document.getElementById('tabBtn-shop');
    if (tabShop) tabShop.classList.add('hidden');
    const tabSettings = document.getElementById('tabBtn-settings');
    if (tabSettings) tabSettings.classList.add('hidden');

    // Load saved mobile discounts from localStorage
    try {
        const savedDiscounts = localStorage.getItem('steel_mobile_discounts');
        if (savedDiscounts) {
            appState.discounts = JSON.parse(savedDiscounts);
        }
    } catch(e) {}
}

function renderCloudBundle(bundle) {
    appState.allCloudItems = bundle.items || [];
    appState.matrix = bundle.items || [];
    appState.categoryCounts = bundle.category_counts || {};
    appState.totalShopCount = bundle.total_shop_count || appState.matrix.length;
    
    // Header sync time indicator
    const headerLastSync = document.getElementById('headerLastSync');
    if (headerLastSync) {
        headerLastSync.innerHTML = `
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            ${bundle.last_sync_time || 'ซิงค์จาก Cloud'}
        `;
    }

    if (bundle.cost_config) {
        const cfg = bundle.cost_config;
        const bannerText = document.getElementById('bannerCostFactorText');
        if (bannerText) {
            bannerText.textContent = `ต้นทุน 2S: รวม VAT ${cfg.vat_pct}% ลด ${cfg.discount_pct}% (×${cfg.cost_factor})`;
        }
    }

    renderCategorySlicers();
    filterMatrixClientSide();
}

function filterMatrixClientSide() {
    const search = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
    const category = appState.selectedCategory !== undefined ? appState.selectedCategory : (document.getElementById('categoryFilter')?.value || '');
    const mapping = document.getElementById('mappingFilter')?.value || 'all';
    const margin = document.getElementById('marginFilter')?.value || 'all';

    let items = appState.allCloudItems || [];

    if (category) {
        items = items.filter(it => it.shop_category === category);
    }

    if (search) {
        const tokens = search.split(/\s+/).filter(Boolean);
        items = items.filter(it => {
            const text = `${it.shop_code} ${it.shop_name} ${it.shop_category} ${it.supplier_name || ''} ${it.supplier_spec || ''}`.toLowerCase();
            return tokens.every(tok => text.includes(tok));
        });
    }

    if (mapping === 'mapped') {
        items = items.filter(it => it.is_mapped);
    } else if (mapping === 'unmapped') {
        items = items.filter(it => !it.is_mapped);
    }

    const lowThresh = parseFloat(appState.settings['low_margin_threshold'] || 8.0);
    const goodThresh = parseFloat(appState.settings['good_margin_threshold'] || 15.0);

    if (margin === 'loss') {
        items = items.filter(it => it.margin_status === 'loss');
    } else if (margin === 'warning') {
        items = items.filter(it => it.margin_status === 'warning');
    } else if (margin === 'good') {
        items = items.filter(it => it.margin_status === 'good');
    }

    appState.matrix = items;

    // Calculate stats
    const totalItems = items.length;
    const mappedItems = items.filter(it => it.is_mapped).length;
    const lossCount = items.filter(it => it.margin_status === 'loss').length;
    const warningCount = items.filter(it => it.margin_status === 'warning').length;
    const goodCount = items.filter(it => it.margin_status === 'good').length;
    const validMargins = items.filter(it => it.is_mapped && it.effective_cost > 0).map(it => it.normal_margin_pct);
    const avgMargin = validMargins.length ? (validMargins.reduce((a, b) => a + b, 0) / validMargins.length).toFixed(1) : "0.0";

    const stats = {
        total_items: totalItems,
        mapped_items: mappedItems,
        loss_count: lossCount,
        warning_count: warningCount,
        good_count: goodCount,
        avg_margin_pct: avgMargin
    };

    renderStats(stats);
    renderMatrixTable(items);
    renderMatrixCards(items);
}

// Cloud sync trigger from Header
async function syncToCloud() {
    showToast("กำลังเตรียมและส่งข้อมูลขึ้น Cloud (Firebase)...", "info");
    try {
        const res = await fetch('/api/sync-firebase', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(`☁️ ${data.message}`, "success");
        } else {
            showToast(`แจ้งเตือน: ${data.message || data.detail}`, "warning");
        }
    } catch (e) {
        showToast("ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์เพื่อซิงค์ข้อมูลได้", "error");
    }
}

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        document.getElementById('headerLastSync').innerHTML = `
            <span class="w-2 h-2 rounded-full ${data.has_credentials ? 'bg-emerald-400' : 'bg-amber-400'} animate-pulse"></span>
            ${data.last_sync_time || 'ยังไม่ได้ดึงข้อมูล'}
        `;

        const badgeUnmapped = document.getElementById('badgeUnmapped');
        if (data.unmapped_count > 0) {
            badgeUnmapped.textContent = data.unmapped_count;
            badgeUnmapped.classList.remove('hidden');
        } else {
            badgeUnmapped.classList.add('hidden');
        }
    } catch (e) {
        console.error(e);
    }
}

async function fetchSettings() {
    try {
        const res = await fetch('/api/settings');
        appState.settings = await res.json();
        
        document.getElementById('setting2sUser').value = appState.settings['2s_username'] || '';
        document.getElementById('setting2sCookie').value = appState.settings['2s_session_cookie'] || '';
        document.getElementById('settingExpressPath').value = appState.settings['express_path'] || 'Z:/jkc2569';
        document.getElementById('settingLowMargin').value = appState.settings['low_margin_threshold'] || '8.0';
        document.getElementById('settingGoodMargin').value = appState.settings['good_margin_threshold'] || '15.0';

        // Cost Calculation Settings
        const discEl = document.getElementById('settingSupplierDiscount');
        if (discEl) discEl.value = appState.settings['supplier_discount_pct'] || '1.0';
        const vatEl = document.getElementById('settingSupplierVat');
        if (vatEl) vatEl.value = appState.settings['supplier_vat_pct'] || '7.0';
        const incVatEl = document.getElementById('settingIncludeVat');
        if (incVatEl) incVatEl.checked = (appState.settings['include_vat'] !== '0');

        // Pre-fill modal fields
        document.getElementById('syncModalUser').value = appState.settings['2s_username'] || '';
        document.getElementById('syncModalCookie').value = appState.settings['2s_session_cookie'] || '';
    } catch (e) {
        console.error(e);
    }
}

async function fetchMatrix() {
    if (appState.isCloudMode) {
        filterMatrixClientSide();
        return;
    }
    const search = document.getElementById('searchInput').value;
    const category = appState.selectedCategory !== undefined ? appState.selectedCategory : document.getElementById('categoryFilter').value;
    const mapping = document.getElementById('mappingFilter').value;
    const margin = document.getElementById('marginFilter').value;

    const params = new URLSearchParams({
        search: search,
        category: category,
        mapping_filter: mapping,
        margin_filter: margin
    });

    try {
        const res = await fetch(`/api/matrix?${params.toString()}`);
        const data = await res.json();
        appState.matrix = data.items;

        if (data.category_counts) {
            appState.categoryCounts = data.category_counts;
        }
        if (data.total_shop_count !== undefined) {
            appState.totalShopCount = data.total_shop_count;
        }
        renderCategorySlicers();
        
        if (data.cost_config) {
            const cfg = data.cost_config;
            const bannerText = document.getElementById('bannerCostFactorText');
            if (bannerText) {
                if (cfg.include_vat) {
                    bannerText.textContent = `ต้นทุน 2S: รวม VAT ${cfg.vat_pct}% ลด ${cfg.discount_pct}% (×${cfg.cost_factor})`;
                } else {
                    bannerText.textContent = `ต้นทุน 2S: ลด ${cfg.discount_pct}% (ไม่รวม VAT) (×${cfg.cost_factor})`;
                }
            }
        }

        renderStats(data.stats);
        renderMatrixTable(data.items);
        renderMatrixCards(data.items);
    } catch (e) {
        console.error("Matrix error:", e);
    }
}

// ----------------- Category Slicer Logic -----------------
function renderCategorySlicers() {
    const container = document.getElementById('categorySlicerContainer');
    if (!container) return;

    const counts = appState.categoryCounts || {};
    const totalCount = appState.totalShopCount || (appState.matrix ? appState.matrix.length : 0);
    const activeCat = appState.selectedCategory || '';

    // "ทั้งหมด" button
    const isAllActive = !activeCat;
    let html = `
        <button type="button" onclick="selectCategorySlicer('')" 
                class="category-slicer-btn px-3 py-1.5 rounded-lg text-xs transition flex items-center space-x-1.5 cursor-pointer ${isAllActive ? 'bg-blue-600 text-white font-bold shadow ring-2 ring-blue-300' : 'bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium'}">
            <span>ทั้งหมด</span>
            <span class="px-1.5 py-0.2 rounded-full text-[10px] ${isAllActive ? 'bg-blue-800 text-white' : 'bg-slate-200 text-slate-700'}">${totalCount}</span>
        </button>
    `;

    STEEL_CATEGORIES.forEach(cat => {
        const count = counts[cat] || 0;
        const isActive = activeCat === cat;
        html += `
            <button type="button" onclick="selectCategorySlicer('${escapeHtml(cat)}')" 
                    class="category-slicer-btn px-3 py-1.5 rounded-lg text-xs transition flex items-center space-x-1.5 cursor-pointer ${isActive ? 'bg-blue-600 text-white font-bold shadow ring-2 ring-blue-300' : 'bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium'}">
                <span>${escapeHtml(cat)}</span>
                <span class="px-1.5 py-0.2 rounded-full text-[10px] ${isActive ? 'bg-blue-800 text-white' : 'bg-slate-200 text-slate-700'}">${count}</span>
            </button>
        `;
    });

    container.innerHTML = html;
}

function selectCategorySlicer(cat) {
    appState.selectedCategory = cat;
    const catSelect = document.getElementById('categoryFilter');
    if (catSelect && catSelect.value !== cat) {
        catSelect.value = cat;
    }

    const badge = document.getElementById('activeSlicerBadge');
    if (badge) {
        if (!cat) {
            badge.textContent = `หมวดหมู่: ทั้งหมด (${appState.totalShopCount || 0})`;
            badge.className = 'text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-0.5 rounded-full';
        } else {
            const cnt = (appState.categoryCounts && appState.categoryCounts[cat]) || 0;
            badge.textContent = `หมวดหมู่: ${cat} (${cnt})`;
            badge.className = 'text-xs font-semibold text-white bg-blue-600 px-2.5 py-0.5 rounded-full shadow-sm';
        }
    }

    renderCategorySlicers();
    fetchMatrix();
}

function onCategorySelectChange(cat) {
    selectCategorySlicer(cat);
}

async function fetchSupplierProducts() {
    try {
        const res = await fetch('/api/supplier-products');
        appState.supplierProducts = await res.json();
        renderSupplierTable(appState.supplierProducts);
    } catch (e) {
        console.error(e);
    }
}

async function fetchShopProducts() {
    try {
        const res = await fetch('/api/shop-products');
        appState.shopProducts = await res.json();
        renderShopTable(appState.shopProducts);
    } catch (e) {
        console.error(e);
    }
}

// ----------------- Rendering -----------------
function renderStats(stats) {
    if (!stats) return;
    document.getElementById('statTotal').textContent = stats.total_items.toLocaleString();
    document.getElementById('statMapped').textContent = `ผูกแล้ว ${stats.mapped_items.toLocaleString()} รายการ`;
    document.getElementById('statAvgMargin').textContent = `${stats.avg_margin_pct}%`;
    document.getElementById('statGood').textContent = `กำไรดี (>15%) : ${stats.good_count}`;
    document.getElementById('statWarning').textContent = stats.warning_count;
    document.getElementById('statLoss').textContent = stats.loss_count;
}

function renderMatrixTable(items) {
    const tbody = document.getElementById('matrixTableBody');
    if (!items || items.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="11" class="py-12 text-center text-slate-400">
                    <div class="flex flex-col items-center justify-center space-y-2">
                        <i data-lucide="inbox" class="w-10 h-10 text-slate-300"></i>
                        <span class="text-slate-500 font-medium">ไม่พบรายการสินค้าที่ตรงกับเงื่อนไข</span>
                        <p class="text-xs text-slate-400">กดปุ่ม "ดึงจาก Express" หรือ "โหลดแค็ตตาล็อก 2S Metal" ด้านบนเพื่อเริ่มใช้งาน</p>
                    </div>
                </td>
            </tr>
        `;
        lucide.createIcons();
        document.getElementById('tableCountText').textContent = 'แสดง 0 รายการ';
        return;
    }

    document.getElementById('tableCountText').textContent = `แสดง ${items.length} รายการ`;

    const lowThresh = parseFloat(appState.settings['low_margin_threshold'] || 8.0);
    const goodThresh = parseFloat(appState.settings['good_margin_threshold'] || 15.0);

    let html = '';
    items.forEach((item, index) => {
        const shopId = item.shop_id;
        const isMapped = item.is_mapped;
        const effCost = item.effective_cost;
        const normalPrice = item.selling_price;
        const normalProfit = item.normal_profit;
        const normalMargin = item.normal_margin_pct;

        // Discounted/Bargained price in memory
        const discountPrice = appState.discounts[shopId] !== undefined ? appState.discounts[shopId] : normalPrice;
        
        // Calculate discounted metrics
        let discProfit = 0;
        let discMargin = 0;
        let discStatus = 'no_data';
        
        if (isMapped && effCost > 0 && discountPrice > 0) {
            discProfit = discountPrice - effCost;
            discMargin = (discProfit / discountPrice) * 100.0;
            
            if (discProfit < 0) discStatus = 'loss';
            else if (discMargin < lowThresh) discStatus = 'warning';
            else if (discMargin >= goodThresh) discStatus = 'good';
            else discStatus = 'normal';
        }

        // Price trend arrow
        let trendIcon = '';
        if (item.price_trend === 'up') {
            trendIcon = `<span class="text-rose-500 font-bold text-xs" title="ราคาปรับขึ้นจากเดิม">▲</span>`;
        } else if (item.price_trend === 'down') {
            trendIcon = `<span class="text-emerald-500 font-bold text-xs" title="ราคาปรับลงจากเดิม">▼</span>`;
        }

        // Badges for Normal Margin (คิดจากราคาขาย)
        const marginTooltip = isMapped && normalPrice > 0 ? `title="คิดกำไรจากราคาขาย: (กำไร ฿${normalProfit.toFixed(2)} ÷ ราคาขาย ฿${normalPrice.toFixed(2)}) × 100 = ${normalMargin}%"` : '';
        let normalBadge = '';
        if (!isMapped) {
            normalBadge = `<span class="text-[11px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">ยังไม่ผูก</span>`;
        } else if (item.margin_status === 'loss') {
            normalBadge = `<span ${marginTooltip} class="text-[11px] font-bold text-rose-700 bg-rose-100 px-2.5 py-0.5 rounded-full animate-pulse cursor-help">ขาดทุน (${normalMargin}%)</span>`;
        } else if (item.margin_status === 'warning') {
            normalBadge = `<span ${marginTooltip} class="text-[11px] font-semibold text-amber-800 bg-amber-100 px-2.5 py-0.5 rounded-full cursor-help">${normalMargin}% (ต่ำ)</span>`;
        } else if (item.margin_status === 'good') {
            normalBadge = `<span ${marginTooltip} class="text-[11px] font-semibold text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full cursor-help">${normalMargin}% (ดี)</span>`;
        } else {
            normalBadge = `<span ${marginTooltip} class="text-[11px] font-semibold text-sky-800 bg-sky-100 px-2.5 py-0.5 rounded-full cursor-help">${normalMargin}%</span>`;
        }

        // Row highlighting if loss
        const rowClass = discStatus === 'loss' ? 'bg-rose-50/70 hover:bg-rose-100/60' : 'hover:bg-slate-50/80';

        html += `
        <tr class="${rowClass} transition group" id="row-${shopId}">
            <td class="py-3 px-3 text-center text-xs text-slate-400">${index + 1}</td>
            
            <!-- Shop Product -->
            <td class="py-3 px-3">
                <div class="font-medium text-slate-800 flex items-center space-x-1.5">
                    <span class="text-[11px] font-mono text-slate-400 bg-slate-100 px-1 py-0.5 rounded">${item.shop_code}</span>
                    <span class="font-semibold">${escapeHtml(item.shop_name)}</span>
                </div>
                <div class="text-[11px] text-slate-400 flex items-center space-x-2 mt-0.5">
                    <span>${escapeHtml(item.shop_category || 'เหล็ก')}</span>
                    <span>•</span>
                    <span>หน่วย: ${item.shop_unit}</span>
                </div>
            </td>

            <!-- 2S Metal Mapping -->
            <td class="py-3 px-3">
                ${isMapped ? `
                    <div class="flex items-center justify-between">
                        <div>
                            <div class="text-xs font-medium text-blue-900">${escapeHtml(item.supplier_name)}</div>
                            <div class="text-[11px] text-slate-400">${escapeHtml(item.supplier_spec || '')}</div>
                        </div>
                        <button onclick="openMappingModal(${shopId})" class="text-slate-300 hover:text-blue-600 p-1 opacity-0 group-hover:opacity-100 transition" title="เปลี่ยนการจับคู่">
                            <i data-lucide="edit-2" class="w-3.5 h-3.5"></i>
                        </button>
                    </div>
                ` : `
                    <button onclick="openMappingModal(${shopId})" class="inline-flex items-center space-x-1 text-xs text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 px-2 py-1 rounded-lg font-medium transition">
                        <i data-lucide="link" class="w-3 h-3"></i>
                        <span>+ ผูกกับ 2S</span>
                    </button>
                `}
            </td>

            <!-- 2S Cost -->
            <td class="py-3 px-3 text-right bg-slate-50/60 font-mono">
                ${isMapped && effCost > 0 ? `
                    <div class="font-bold text-slate-800 text-sm flex items-center justify-end space-x-1">
                        ${trendIcon}
                        <span>฿${effCost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="text-[10px] text-slate-500 font-sans">
                        ราคาตั้ง ฿${(item.raw_supplier_cost || (item.supplier_cost * (item.multiplier || 1.0))).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                        ${item.include_vat ? `<span class="text-emerald-700 font-medium">(ลด ${item.discount_pct}%+VAT)</span>` : `<span class="text-amber-700 font-medium">(ลด ${item.discount_pct}%)</span>`}
                    </div>
                    ${item.multiplier !== 1 ? `<div class="text-[10px] text-slate-400 font-sans">ตัวคูณ ${item.multiplier}</div>` : ''}
                ` : `
                    <span class="text-xs text-slate-300">-</span>
                `}
            </td>

            <!-- Normal Selling Price -->
            <td class="py-3 px-3 text-right font-mono font-medium text-slate-700">
                ฿${normalPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
            </td>

            <!-- Normal Profit -->
            <td class="py-3 px-3 text-right font-mono">
                ${isMapped ? `
                    <span class="font-semibold ${normalProfit < 0 ? 'text-rose-600 font-bold' : (normalProfit > 0 ? 'text-slate-800' : 'text-slate-400')}">
                        ฿${normalProfit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                    </span>
                ` : `<span class="text-slate-300">-</span>`}
            </td>

            <!-- Normal Margin % Badge -->
            <td class="py-3 px-3 text-center">
                ${normalBadge}
            </td>

            <!-- [ DYNAMIC INPUT: DISCOUNT SELLING PRICE ] -->
            <td class="py-2.5 px-3 bg-amber-50/50 border-l border-r border-amber-200/80">
                <div class="relative flex items-center justify-center">
                    <span class="absolute left-2 text-xs text-slate-400 pointer-events-none">฿</span>
                    <input type="number" step="0.5" 
                           id="discountInput-${shopId}"
                           value="${discountPrice}" 
                           oninput="onDiscountChanged(${shopId}, this.value, ${effCost})"
                           class="discount-input w-28 pl-6 pr-2 py-1 text-right text-sm font-bold font-mono text-slate-900 bg-white border border-amber-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500 shadow-sm"
                           placeholder="${normalPrice}">
                </div>
            </td>

            <!-- New Profit (Real-time) -->
            <td class="py-3 px-3 text-right font-mono bg-amber-50/20" id="discProfitCell-${shopId}">
                ${isMapped ? `
                    <span class="font-bold text-sm ${discProfit < 0 ? 'text-rose-600 animate-pulse' : 'text-slate-900'}">
                        ฿${discProfit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                    </span>
                ` : `<span class="text-slate-300">-</span>`}
            </td>

            <!-- New Margin % (Real-time) -->
            <td class="py-3 px-3 text-center bg-amber-50/20" id="discMarginCell-${shopId}">
                ${renderMarginBadge(discStatus, discMargin, isMapped)}
            </td>

            <!-- Actions -->
            <td class="py-3 px-3 text-center">
                <div class="flex items-center justify-center space-x-1">
                    <button onclick="copyPriceQuote(${shopId}, '${escapeHtml(item.shop_name)}', ${discountPrice})" 
                            class="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition" title="คัดลอกราคาเสนอเพื่อส่งให้ลูกค้า">
                        <i data-lucide="copy" class="w-4 h-4"></i>
                    </button>
                    ${isMapped ? `
                        <button onclick="unlinkMapping(${item.mapping_id})" class="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition" title="ยกเลิกการผูก">
                            <i data-lucide="unlink" class="w-4 h-4"></i>
                        </button>
                    ` : ''}
                    <button onclick="deleteShopProduct(${shopId}, '${escapeHtml(item.shop_name)}')" class="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition" title="ลบสินค้านี้ออกจากร้าน">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
            </td>
        </tr>
        `;
    });

    tbody.innerHTML = html;
    lucide.createIcons();
}

function renderMarginBadge(status, marginPct, isMapped) {
    if (!isMapped) {
        return `<span class="text-[11px] text-slate-300 font-medium">-</span>`;
    }
    const val = marginPct.toFixed(1);
    const tooltip = `title="คิดกำไรจากราคาขาย: (กำไร ÷ ราคาขาย) × 100 = ${val}%"`;
    if (status === 'loss') {
        return `<span ${tooltip} class="text-[11px] font-bold text-white bg-rose-600 px-2.5 py-1 rounded-full shadow-sm animate-bounce cursor-help">ขาดทุน! (${val}%)</span>`;
    } else if (status === 'warning') {
        return `<span ${tooltip} class="text-[11px] font-bold text-amber-900 bg-amber-200 px-2 py-0.5 rounded-full border border-amber-300 cursor-help">${val}% (กำไรต่ำ)</span>`;
    } else if (status === 'good') {
        return `<span ${tooltip} class="text-[11px] font-bold text-emerald-900 bg-emerald-200 px-2 py-0.5 rounded-full border border-emerald-300 cursor-help">${val}% (กำไรดี)</span>`;
    } else {
        return `<span ${tooltip} class="text-[11px] font-semibold text-sky-900 bg-sky-100 px-2 py-0.5 rounded-full border border-sky-200 cursor-help">${val}%</span>`;
    }
}

// ----------------- Mobile Cards View Renderer -----------------
function renderMatrixCards(items) {
    const container = document.getElementById('matrixCardsContainer');
    if (!container) return;

    if (!items || items.length === 0) {
        container.innerHTML = `
            <div class="col-span-full py-12 text-center text-slate-400 bg-white rounded-2xl border border-slate-200/80 p-6">
                <i data-lucide="inbox" class="w-10 h-10 text-slate-300 mx-auto mb-2"></i>
                <span class="text-slate-500 font-medium block">ไม่พบรายการสินค้าที่ตรงกับเงื่อนไข</span>
                <p class="text-xs text-slate-400 mt-1">ลองเปลี่ยนคำค้นหา หรือเลือกหมวดหมู่อื่น</p>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    const lowThresh = parseFloat(appState.settings['low_margin_threshold'] || 8.0);
    const goodThresh = parseFloat(appState.settings['good_margin_threshold'] || 15.0);

    let html = '';
    items.forEach((item) => {
        const shopId = item.shop_id;
        const isMapped = item.is_mapped;
        const effCost = item.effective_cost;
        const normalPrice = item.selling_price;
        const normalProfit = item.normal_profit;
        const normalMargin = item.normal_margin_pct;

        const discountPrice = appState.discounts[shopId] !== undefined ? appState.discounts[shopId] : normalPrice;
        const hasDiscount = appState.discounts[shopId] !== undefined && appState.discounts[shopId] !== normalPrice;

        let discProfit = 0;
        let discMargin = 0;
        let discStatus = 'no_data';
        if (isMapped && effCost > 0 && discountPrice > 0) {
            discProfit = discountPrice - effCost;
            discMargin = (discProfit / discountPrice) * 100.0;
            if (discProfit < 0) discStatus = 'loss';
            else if (discMargin < lowThresh) discStatus = 'warning';
            else if (discMargin >= goodThresh) discStatus = 'good';
            else discStatus = 'normal';
        }

        // Badges for Normal Margin
        let normalBadge = '';
        if (!isMapped) {
            normalBadge = `<span class="text-[11px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full font-medium">ยังไม่ผูก</span>`;
        } else if (item.margin_status === 'loss') {
            normalBadge = `<span class="text-[11px] font-bold text-rose-700 bg-rose-100 px-2.5 py-0.5 rounded-full animate-pulse">ขาดทุน (${normalMargin}%)</span>`;
        } else if (item.margin_status === 'warning') {
            normalBadge = `<span class="text-[11px] font-bold text-amber-800 bg-amber-100 px-2.5 py-0.5 rounded-full">${normalMargin}% (ต่ำ)</span>`;
        } else if (item.margin_status === 'good') {
            normalBadge = `<span class="text-[11px] font-bold text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full">${normalMargin}% (ดี)</span>`;
        } else {
            normalBadge = `<span class="text-[11px] font-semibold text-sky-800 bg-sky-100 px-2.5 py-0.5 rounded-full">${normalMargin}%</span>`;
        }

        const cardBorderClass = discStatus === 'loss' ? 'border-rose-400 bg-rose-50/40 shadow-rose-100' : 'border-slate-200/90 bg-white hover:border-blue-300';

        html += `
        <div class="rounded-2xl border ${cardBorderClass} shadow-sm p-4 space-y-3 transition duration-150 relative" id="card-${shopId}">
            <!-- Card Header -->
            <div class="flex items-start justify-between gap-2">
                <div class="space-y-1 min-w-0 flex-1">
                    <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="text-[11px] font-mono font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">${item.shop_code}</span>
                        <span class="text-[11px] font-medium text-sky-700 bg-sky-50 border border-sky-200/60 px-2 py-0.5 rounded-md">${escapeHtml(item.shop_category || 'เหล็ก')}</span>
                    </div>
                    <h4 class="text-sm font-bold text-slate-900 leading-snug line-clamp-2">${escapeHtml(item.shop_name)}</h4>
                </div>
                <div class="flex-shrink-0 pt-0.5">
                    ${normalBadge}
                </div>
            </div>

            <!-- Price & Cost Comparison Section -->
            <div class="grid grid-cols-2 gap-2 bg-slate-50/90 p-2.5 rounded-xl border border-slate-100">
                <!-- Shop Selling Price -->
                <div>
                    <span class="text-[10px] text-slate-400 font-medium block">ราคาขายหน้าร้าน</span>
                    <span class="text-base font-bold text-slate-900 font-mono">฿${normalPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    <span class="text-[10px] text-slate-400 block">หน่วย: ${escapeHtml(item.shop_unit || 'เส้น')}</span>
                </div>
                <!-- 2S Metal Net Cost -->
                <div class="text-right">
                    <span class="text-[10px] text-slate-400 font-medium block">ต้นทุนสุทธิ 2S (รวมVAT-1%)</span>
                    ${isMapped && effCost > 0 ? `
                        <span class="text-base font-bold text-blue-700 font-mono">฿${effCost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                        <span class="text-[10px] text-slate-500 block truncate" title="${escapeHtml(item.supplier_name)}">${escapeHtml(item.supplier_name)}</span>
                    ` : `
                        <span class="text-xs text-amber-600 font-medium mt-1 inline-block">ยังไม่ผูกสินค้า</span>
                    `}
                </div>
            </div>

            <!-- Normal Profit Summary -->
            ${isMapped && effCost > 0 ? `
            <div class="flex items-center justify-between text-xs px-1 text-slate-600 border-b border-slate-100 pb-2">
                <span>กำไรปกติ: <strong class="text-slate-900 font-mono">฿${normalProfit.toFixed(2)}</strong></span>
                <span>% กำไรปกติ: <strong class="font-mono text-slate-900">${normalMargin}%</strong></span>
            </div>
            ` : ''}

            <!-- [ TOUCH-FRIENDLY SPECIAL OFFER PRICE INPUT ] -->
            <div class="bg-amber-50/70 border border-amber-200/90 rounded-xl p-3 space-y-2">
                <div class="flex items-center justify-between">
                    <label class="text-xs font-bold text-amber-950 flex items-center gap-1.5">
                        <i data-lucide="tag" class="w-3.5 h-3.5 text-amber-600"></i>
                        ราคาขายเสนอพิเศษ (ลดราคา)
                    </label>
                    <button onclick="resetSingleCardDiscount(${shopId}, ${normalPrice}, ${effCost})" 
                            id="cardResetBtn-${shopId}"
                            class="text-[11px] text-amber-700 hover:text-amber-900 underline font-medium ${hasDiscount ? '' : 'hidden'}">
                        คืนค่าเดิม
                    </button>
                </div>
                <div class="relative">
                    <span class="absolute left-3 top-2.5 text-amber-600 font-bold text-sm pointer-events-none">฿</span>
                    <input type="number" 
                           step="0.5" 
                           inputmode="decimal"
                           id="cardDiscountInput-${shopId}"
                           value="${discountPrice}" 
                           oninput="onDiscountChanged(${shopId}, this.value, ${effCost})"
                           placeholder="${normalPrice.toFixed(2)}"
                           class="w-full pl-8 pr-3 py-2 bg-white border border-amber-300 rounded-lg text-base font-bold font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 shadow-sm transition">
                </div>
                
                <!-- Live Recalculated Margin for Card -->
                <div class="flex items-center justify-between text-xs pt-1.5 border-t border-amber-200/60" id="cardDiscSummary-${shopId}">
                    <div>
                        <span class="text-slate-600">กำไรใหม่: </span>
                        <strong class="font-mono text-sm ${discProfit < 0 ? 'text-rose-600 animate-pulse font-bold' : 'text-slate-900'}" id="cardDiscProfit-${shopId}">
                            ${isMapped ? `฿${discProfit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : '-'}
                        </strong>
                    </div>
                    <div id="cardDiscMargin-${shopId}">
                        ${renderMarginBadge(discStatus, discMargin, isMapped)}
                    </div>
                </div>
            </div>

            <!-- Card Bottom Actions -->
            <div class="flex items-center justify-between pt-1 text-xs">
                <div class="flex items-center space-x-1">
                    <button onclick="copyPriceQuote(${shopId}, '${escapeHtml(item.shop_name)}', ${discountPrice})" 
                            class="inline-flex items-center space-x-1 px-2.5 py-1.5 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-700 rounded-lg font-medium transition" title="คัดลอกราคาเสนอ">
                        <i data-lucide="copy" class="w-3.5 h-3.5 text-slate-500"></i>
                        <span>คัดลอกราคา</span>
                    </button>
                </div>
                <div>
                    ${isMapped ? `
                        <button onclick="openMappingModal(${shopId})" class="inline-flex items-center space-x-1 text-blue-600 hover:text-blue-800 font-medium py-1 px-2">
                            <i data-lucide="edit-2" class="w-3 h-3"></i>
                            <span>เปลี่ยนผูก</span>
                        </button>
                    ` : `
                        <button onclick="openMappingModal(${shopId})" class="inline-flex items-center space-x-1 text-amber-700 bg-amber-100 hover:bg-amber-200 px-2.5 py-1 rounded-lg font-bold">
                            <i data-lucide="link" class="w-3 h-3"></i>
                            <span>+ ผูก 2S</span>
                        </button>
                    `}
                </div>
            </div>
        </div>
        `;
    });

    container.innerHTML = html;
    lucide.createIcons();
}

// ----------------- Real-time Discount Price Input Handler (Table & Card Sync) -----------------
function onDiscountChanged(shopId, newPriceStr, effectiveCost) {
    const newPrice = parseFloat(newPriceStr) || 0;
    appState.discounts[shopId] = newPrice;

    // Sync input values between Table and Card
    const tblInput = document.getElementById(`discountInput-${shopId}`);
    const cardInput = document.getElementById(`cardDiscountInput-${shopId}`);
    if (tblInput && tblInput.value !== newPriceStr) tblInput.value = newPriceStr;
    if (cardInput && cardInput.value !== newPriceStr) cardInput.value = newPriceStr;

    // Show/hide card reset button
    const cardResetBtn = document.getElementById(`cardResetBtn-${shopId}`);
    if (cardResetBtn) {
        cardResetBtn.classList.remove('hidden');
    }

    const profitCell = document.getElementById(`discProfitCell-${shopId}`);
    const marginCell = document.getElementById(`discMarginCell-${shopId}`);
    const rowEl = document.getElementById(`row-${shopId}`);

    const cardProfitEl = document.getElementById(`cardDiscProfit-${shopId}`);
    const cardMarginEl = document.getElementById(`cardDiscMargin-${shopId}`);
    const cardEl = document.getElementById(`card-${shopId}`);

    if (!effectiveCost || effectiveCost <= 0) {
        if (profitCell) profitCell.innerHTML = `<span class="text-slate-300">-</span>`;
        if (marginCell) marginCell.innerHTML = `<span class="text-slate-300">-</span>`;
        if (cardProfitEl) cardProfitEl.innerHTML = `-`;
        if (cardMarginEl) cardMarginEl.innerHTML = `<span class="text-[11px] text-slate-300">-</span>`;
        return;
    }

    const profit = newPrice - effectiveCost;
    const marginPct = newPrice > 0 ? (profit / newPrice) * 100.0 : 0.0;

    const lowThresh = parseFloat(appState.settings['low_margin_threshold'] || 8.0);
    const goodThresh = parseFloat(appState.settings['good_margin_threshold'] || 15.0);

    let status = 'normal';
    if (profit < 0) status = 'loss';
    else if (marginPct < lowThresh) status = 'warning';
    else if (marginPct >= goodThresh) status = 'good';

    // Update Table row and cells
    if (rowEl) {
        rowEl.className = status === 'loss' ? 'bg-rose-50 hover:bg-rose-100 transition group' : 'hover:bg-slate-50/80 transition group';
    }
    if (profitCell) {
        profitCell.innerHTML = `
            <span class="font-bold text-sm ${profit < 0 ? 'text-rose-600 animate-pulse' : 'text-slate-900'}">
                ฿${profit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
            </span>
        `;
    }
    if (marginCell) {
        marginCell.innerHTML = renderMarginBadge(status, marginPct, true);
    }

    // Update Card appearance and cells
    if (cardEl) {
        cardEl.className = status === 'loss'
            ? 'rounded-2xl border border-rose-400 bg-rose-50/40 shadow-rose-100 shadow-sm p-4 space-y-3 transition duration-150 relative'
            : 'rounded-2xl border border-slate-200/90 bg-white hover:border-blue-300 shadow-sm p-4 space-y-3 transition duration-150 relative';
    }
    if (cardProfitEl) {
        cardProfitEl.className = `font-mono text-sm ${profit < 0 ? 'text-rose-600 animate-pulse font-bold' : 'text-slate-900'}`;
        cardProfitEl.textContent = `฿${profit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }
    if (cardMarginEl) {
        cardMarginEl.innerHTML = renderMarginBadge(status, marginPct, true);
    }

    // Persist custom prices locally on mobile
    if (appState.isCloudMode) {
        try {
            localStorage.setItem('steel_mobile_discounts', JSON.stringify(appState.discounts));
        } catch(e) {}
    }
}

function resetSingleCardDiscount(shopId, normalPrice, effCost) {
    delete appState.discounts[shopId];
    onDiscountChanged(shopId, normalPrice.toString(), effCost);
    const cardResetBtn = document.getElementById(`cardResetBtn-${shopId}`);
    if (cardResetBtn) cardResetBtn.classList.add('hidden');
    if (appState.isCloudMode) {
        try {
            localStorage.setItem('steel_mobile_discounts', JSON.stringify(appState.discounts));
        } catch(e) {}
    }
}

function resetAllDiscounts() {
    appState.discounts = {};
    if (appState.isCloudMode) {
        try {
            localStorage.removeItem('steel_mobile_discounts');
        } catch(e) {}
    }
    renderMatrixTable(appState.matrix);
    renderMatrixCards(appState.matrix);
    showToast("รีเซ็ตราคาขายเสนอกลับเป็นราคาปกติเรียบร้อย", "info");
}

function copyPriceQuote(shopId, name, price) {
    const text = `เสนอราคาเหล็ก: ${name}\nราคา: ฿${price.toLocaleString()} ต่อหน่วย`;
    navigator.clipboard.writeText(text).then(() => {
        showToast("คัดลอกราคาเสนอเรียบร้อย พร้อมส่งใน LINE", "success");
    }).catch(() => {
        showToast(`ราคา: ฿${price}`, "info");
    });
}

// ----------------- Filter & Search -----------------
function debounceFilter() {
    clearTimeout(appState.filterDebounceTimer);
    appState.filterDebounceTimer = setTimeout(() => {
        fetchMatrix();
    }, 250);
}

function filterMatrix() {
    fetchMatrix();
}

// ----------------- Tab Switching -----------------
function switchTab(tabId) {
    appState.activeTab = tabId;
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

    const tabEl = document.getElementById(`tab-${tabId}`);
    const btnEl = document.getElementById(`tabBtn-${tabId}`);
    if (tabEl) tabEl.classList.remove('hidden');
    if (btnEl) btnEl.classList.add('active');

    if (tabId === 'pricing') {
        fetchMatrix();
    } else if (tabId === 'mapping') {
        loadMappingWorkspace();
    } else if (tabId === 'supplier') {
        fetchSupplierProducts();
    } else if (tabId === 'shop') {
        fetchShopProducts();
    } else if (tabId === 'settings') {
        fetchSettings();
    }

    lucide.createIcons();
}

// ----------------- Mapping Workspace Logic -----------------
async function loadMappingWorkspace() {
    const container = document.getElementById('mappingListContainer');
    container.innerHTML = `<div class="p-8 text-center text-slate-400">กำลังโหลดรายการจับคู่...</div>`;

    try {
        const [resShop, resSupp, resMap] = await Promise.all([
            fetch('/api/shop-products').then(r => r.json()),
            fetch('/api/supplier-products').then(r => r.json()),
            fetch('/api/mappings').then(r => r.json())
        ]);

        appState.shopProducts = resShop;
        appState.supplierProducts = resSupp;
        appState.mappings = resMap;

        renderMappingCategorySlicers();
        filterMappingList();
    } catch (e) {
        console.error(e);
    }
}

function renderMappingCategorySlicers() {
    const container = document.getElementById('mappingCategorySlicerContainer');
    if (!container) return;

    const mapDict = {};
    (appState.mappings || []).forEach(m => { mapDict[m.shop_product_id] = m; });

    // Count unmapped per category
    const catCounts = {};
    (appState.shopProducts || []).forEach(item => {
        const cat = item.category || 'เหล็ก';
        if (!catCounts[cat]) catCounts[cat] = { total: 0, unmapped: 0 };
        catCounts[cat].total++;
        if (!mapDict[item.id]) {
            catCounts[cat].unmapped++;
        }
    });

    const activeCat = appState.mapSelectedCategory || '';
    const isAllActive = !activeCat;
    const totalShop = (appState.shopProducts || []).length;
    const totalUnmapped = (appState.shopProducts || []).filter(it => !mapDict[it.id]).length;

    let html = `
        <button type="button" onclick="selectMappingCategorySlicer('')" 
                class="px-3 py-1.5 rounded-lg text-xs transition flex items-center space-x-1.5 cursor-pointer ${isAllActive ? 'bg-blue-600 text-white font-bold shadow ring-2 ring-blue-300' : 'bg-white hover:bg-slate-200 text-slate-700 border border-slate-200 font-medium'}">
            <span>ทั้งหมด</span>
            <span class="px-1.5 py-0.2 rounded-full text-[10px] ${isAllActive ? 'bg-blue-800 text-white' : 'bg-amber-100 text-amber-800 font-bold'}">${totalUnmapped} / ${totalShop}</span>
        </button>
    `;

    STEEL_CATEGORIES.forEach(cat => {
        const info = catCounts[cat] || { total: 0, unmapped: 0 };
        const isActive = activeCat === cat;
        html += `
            <button type="button" onclick="selectMappingCategorySlicer('${escapeHtml(cat)}')" 
                    class="px-3 py-1.5 rounded-lg text-xs transition flex items-center space-x-1.5 cursor-pointer ${isActive ? 'bg-blue-600 text-white font-bold shadow ring-2 ring-blue-300' : 'bg-white hover:bg-slate-200 text-slate-700 border border-slate-200 font-medium'}">
                <span>${escapeHtml(cat)}</span>
                <span class="px-1.5 py-0.2 rounded-full text-[10px] ${isActive ? 'bg-blue-800 text-white' : (info.unmapped > 0 ? 'bg-amber-100 text-amber-800 font-bold' : 'bg-slate-100 text-slate-500')}">${info.unmapped} / ${info.total}</span>
            </button>
        `;
    });

    container.innerHTML = html;
}

function selectMappingCategorySlicer(cat) {
    appState.mapSelectedCategory = cat;
    const badge = document.getElementById('activeMapSlicerBadge');
    if (badge) {
        badge.textContent = cat ? cat : 'ทั้งหมด';
    }
    renderMappingCategorySlicers();
    filterMappingList();
}

async function clearAllMappingsConfirm() {
    if (!confirm("คุณแน่ใจหรือไม่ว่าต้องการล้างการจับคู่สินค้าทั้งหมด?\n(ข้อมูลสินค้าจะไม่ถูกลบ แต่จะรีเซ็ตสถานะเป็น 'ยังไม่ได้จับคู่' เพื่อให้คุณจับคู่ใหม่เองทั้งหมด)")) {
        return;
    }
    try {
        const res = await fetch('/api/mappings/clear-all', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast("ล้างการจับคู่ทั้งหมดเรียบร้อยแล้ว", "success");
            await Promise.all([fetchMatrix(), loadMappingWorkspace(), fetchStatus()]);
        } else {
            showToast(data.message || "เกิดข้อผิดพลาด", "error");
        }
    } catch (e) {
        console.error(e);
        showToast("เกิดข้อผิดพลาดในการเชื่อมต่อ", "error");
    }
}

function setMapFilterType(type) {
    appState.mappingFilterType = type;
    const btnUnmapped = document.getElementById('btnFilterUnmapped');
    const btnAll = document.getElementById('btnFilterAll');

    if (type === 'unmapped') {
        btnUnmapped.className = 'px-3 py-2 rounded-lg text-sm font-medium bg-amber-100 text-amber-800 border border-amber-300';
        btnAll.className = 'px-3 py-2 rounded-lg text-sm font-medium bg-slate-100 text-slate-700';
    } else {
        btnAll.className = 'px-3 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-800 border border-blue-300';
        btnUnmapped.className = 'px-3 py-2 rounded-lg text-sm font-medium bg-slate-100 text-slate-700';
    }
    filterMappingList();
}

function filterMappingList() {
    const search = document.getElementById('mapSearchInput').value.toLowerCase();
    const container = document.getElementById('mappingListContainer');
    const mapDict = {};
    appState.mappings.forEach(m => { mapDict[m.shop_product_id] = m; });

    let filtered = appState.shopProducts.filter(item => {
        const isMapped = !!mapDict[item.id];
        if (appState.mappingFilterType === 'unmapped' && isMapped) return false;
        if (appState.mapSelectedCategory && item.category !== appState.mapSelectedCategory) return false;
        if (search) {
            const matchName = item.name.toLowerCase().includes(search);
            const matchCode = item.code.toLowerCase().includes(search);
            return matchName || matchCode;
        }
        return true;
    });

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="py-12 text-center text-slate-400">
                <i data-lucide="check-circle-2" class="w-10 h-10 text-emerald-400 mx-auto mb-2"></i>
                <p class="font-medium text-slate-600">ไม่มีรายการที่ต้องจับคู่</p>
                <p class="text-xs text-slate-400">สินค้าทั้งหมดถูกผูกเรียบร้อยแล้ว หรือไม่ตรงกับการค้นหา</p>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    let html = '';
    filtered.forEach(item => {
        const mapping = mapDict[item.id];
        html += `
        <div class="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-50/60 p-2 rounded-xl transition">
            <div class="flex-1">
                <div class="flex items-center space-x-2">
                    <span class="text-xs font-mono bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-semibold">${item.code}</span>
                    <strong class="text-sm text-slate-800 font-semibold">${escapeHtml(item.name)}</strong>
                </div>
                <div class="text-xs text-slate-500 mt-1 flex items-center space-x-3">
                    <span>หมวด: ${escapeHtml(item.category || 'เหล็ก')}</span>
                    <span>ราคาขาย: ฿${item.selling_price.toLocaleString()}</span>
                    <span>หน่วย: ${item.unit}</span>
                </div>
            </div>

            <div class="flex items-center space-x-3">
                ${mapping ? `
                    <div class="text-right">
                        <div class="text-xs font-medium text-blue-900 flex items-center space-x-1 justify-end">
                            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                            <span>ผูกกับ: ${escapeHtml(mapping.supplier_name)}</span>
                        </div>
                        <div class="text-[11px] text-slate-400">ต้นทุน: ฿${mapping.supplier_cost.toLocaleString()} (ตัวคูณ ${mapping.multiplier})</div>
                    </div>
                    <button onclick="openMappingModal(${item.id})" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition">
                        เปลี่ยน
                    </button>
                    <button onclick="unlinkMapping(${mapping.mapping_id})" class="p-1.5 text-slate-400 hover:text-rose-600 transition" title="ยกเลิก">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                ` : `
                    <button onclick="openMappingModal(${item.id})" class="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium shadow flex items-center space-x-1.5 transition">
                        <i data-lucide="link" class="w-3.5 h-3.5"></i>
                        <span>+ จับคู่กับ 2S</span>
                    </button>
                `}
            </div>
        </div>
        `;
    });

    container.innerHTML = html;
    lucide.createIcons();
}

// ----------------- Mapping Modal -----------------
async function openMappingModal(shopId) {
    appState.selectedShopForMapping = shopId;
    appState.modal2sCategory = '';
    const modal = document.getElementById('modalLink');
    const shopItem = appState.matrix.find(it => it.shop_id === shopId) || appState.shopProducts.find(it => it.id === shopId);
    
    if (!shopItem) return;

    document.getElementById('modalShopCode').textContent = shopItem.shop_code || shopItem.code;
    document.getElementById('modalShopName').textContent = shopItem.shop_name || shopItem.name;
    document.getElementById('modalShopPrice').textContent = `฿${(shopItem.selling_price || 0).toLocaleString()}`;
    document.getElementById('modalMultiplier').value = shopItem.multiplier || 1.0;
    document.getElementById('modalNotes').value = shopItem.mapping_notes || '';

    // Reset search input and category pills
    const searchInput = document.getElementById('modal2sSearch');
    if (searchInput) searchInput.value = '';
    
    const pills = document.querySelectorAll('.modal-cat-pill');
    pills.forEach((p, idx) => {
        if (idx === 0) {
            p.className = 'modal-cat-pill active text-[11px] px-2.5 py-0.5 rounded-full bg-blue-600 text-white font-medium';
        } else {
            p.className = 'modal-cat-pill text-[11px] px-2.5 py-0.5 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium';
        }
    });

    // Initial selected 2S item
    const currentSupplierId = shopItem.supplier_id || null;
    document.getElementById('modalSupplierSelect').value = currentSupplierId || '';
    if (currentSupplierId) {
        selectModal2sItem(currentSupplierId, false);
    } else {
        const banner = document.getElementById('modalSelected2sBanner');
        if (banner) banner.classList.add('hidden');
    }

    // Populate all 2S items list
    filterModal2sList();

    // Fetch AI / best match suggestions
    const suggContainer = document.getElementById('modalSuggestions');
    suggContainer.innerHTML = `<div class="text-xs text-slate-400 p-2">กำลังค้นหาสินค้า 2S ที่สเปกใกล้เคียง...</div>`;
    modal.classList.remove('hidden');
    lucide.createIcons();

    try {
        const res = await fetch(`/api/mappings/suggest/${shopId}`);
        const data = await res.json();
        
        if (data.suggestions && data.suggestions.length > 0) {
            suggContainer.innerHTML = data.suggestions.map(s => `
                <div onclick="selectSuggestion(${s.id})" class="p-2.5 rounded-lg border border-slate-200 hover:border-blue-500 hover:bg-blue-50/50 cursor-pointer flex items-center justify-between transition group shadow-xs">
                    <div class="flex-1 min-w-0 pr-2">
                        <div class="text-xs font-semibold text-slate-800 truncate">${escapeHtml(s.name)}</div>
                        <div class="text-[11px] text-slate-500 truncate">${escapeHtml(s.spec || '')} • สต๊อก: ${s.stock_status}</div>
                    </div>
                    <div class="text-right flex items-center space-x-2 flex-shrink-0">
                        <div>
                            <div class="text-xs font-bold text-blue-600 font-mono">฿${s.current_cost.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
                            <span class="text-[10px] bg-emerald-100 text-emerald-800 px-1.5 py-0.2 rounded font-semibold">ตรง ${s.match_score}%</span>
                        </div>
                        <button type="button" onclick="selectAndSaveSuggestion(event, ${s.id})" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-bold shadow transition flex items-center gap-1" title="ผูกสินค้านี้ทันทีและบันทึก">
                            <span>ผูกทันที</span>
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            suggContainer.innerHTML = `<div class="text-xs text-slate-400 p-2 bg-slate-50 rounded-lg border border-slate-100">ไม่พบสเปกที่แนะนำตรงกันชัดเจน สามารถพิมพ์ค้นหาเลือกจากรายการ 2S Metal ด้านล่างได้เลย</div>`;
        }
    } catch (e) {
        console.error(e);
        suggContainer.innerHTML = `<div class="text-xs text-slate-400 p-2">ค้นหาสินค้าจากรายการด้านล่าง</div>`;
    }
}

// Filter and browse ALL 2S Metal items in modal
function filterModal2sList() {
    const q = (document.getElementById('modal2sSearch')?.value || '').toLowerCase().trim();
    const cat = appState.modal2sCategory || '';
    const selectedId = parseInt(document.getElementById('modalSupplierSelect')?.value || '0');

    let items = appState.supplierProducts || [];

    if (cat) {
        items = items.filter(it => it.category === cat);
    }

    if (q) {
        const tokens = q.split(/\s+/).filter(t => t);
        items = items.filter(it => {
            const combined = `${it.supplier_code || ''} ${it.name || ''} ${it.spec || ''} ${it.category || ''}`.toLowerCase();
            return tokens.every(token => combined.includes(token));
        });
    }

    const countText = document.getElementById('modal2sCountText');
    if (countText) {
        countText.textContent = `พบ ${items.length} รายการ (จากทั้งหมด ${appState.supplierProducts.length} รายการ)`;
    }

    renderModal2sList(items, selectedId);
}

function setModal2sCategory(cat) {
    appState.modal2sCategory = cat;
    const pills = document.querySelectorAll('.modal-cat-pill');
    pills.forEach(p => {
        const pText = p.getAttribute('onclick') || '';
        if ((!cat && pText.includes("''")) || (cat && pText.includes(`'${cat}'`))) {
            p.className = 'modal-cat-pill active text-[11px] px-2.5 py-0.5 rounded-full bg-blue-600 text-white font-medium';
        } else {
            p.className = 'modal-cat-pill text-[11px] px-2.5 py-0.5 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium';
        }
    });
    filterModal2sList();
}

function renderModal2sList(items, selectedId) {
    const container = document.getElementById('modal2sItemList');
    if (!container) return;

    if (!items || items.length === 0) {
        container.innerHTML = `
            <div class="py-6 text-center text-xs text-slate-400">
                <i data-lucide="package-x" class="w-6 h-6 mx-auto mb-1 text-slate-300"></i>
                <span>ไม่พบสินค้า 2S Metal ที่ตรงกับคำค้นหา</span>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    container.innerHTML = items.map(it => {
        const isSelected = it.id === selectedId;
        const borderClass = isSelected ? 'border-emerald-500 bg-emerald-50/70' : 'border-slate-200 bg-white hover:border-blue-400 hover:bg-blue-50/30';
        return `
            <div onclick="selectModal2sItem(${it.id})" class="p-2 rounded-lg border ${borderClass} cursor-pointer flex items-center justify-between transition">
                <div class="flex-1 min-w-0 pr-2">
                    <div class="flex items-center space-x-1.5">
                        ${isSelected ? '<span class="w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0"></span>' : ''}
                        <span class="text-[10px] font-mono text-slate-400 bg-slate-100 px-1 py-0.5 rounded flex-shrink-0">${escapeHtml(it.supplier_code || '')}</span>
                        <strong class="text-xs font-semibold text-slate-800 truncate">${escapeHtml(it.name)}</strong>
                    </div>
                    <div class="text-[11px] text-slate-400 flex items-center space-x-2 mt-0.5 truncate">
                        <span>${escapeHtml(it.spec || it.category || 'เหล็ก')}</span>
                        <span>•</span>
                        <span>หน่วย: ${it.unit}</span>
                    </div>
                </div>
                <div class="text-right flex items-center space-x-2 flex-shrink-0">
                    <div>
                        <div class="text-xs font-bold text-blue-700 font-mono">฿${(it.net_cost || (it.current_cost * 1.0593)).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                        <div class="text-[10px] text-slate-400">ตั้ง ฿${it.current_cost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                    </div>
                    <button type="button" onclick="selectAndSave2sItem(event, ${it.id})" class="px-2.5 py-1 rounded text-xs font-bold ${isSelected ? 'bg-emerald-600 text-white' : 'bg-blue-600 hover:bg-blue-700 text-white'} transition shadow-xs">
                        ${isSelected ? '✓ ผูกอยู่แล้ว' : 'ผูกทันที'}
                    </button>
                </div>
            </div>
        `;
    }).join('');
    lucide.createIcons();
}

function selectModal2sItem(suppId, reFilter = true) {
    document.getElementById('modalSupplierSelect').value = suppId;
    const supp = appState.supplierProducts.find(s => s.id === suppId);
    const banner = document.getElementById('modalSelected2sBanner');
    
    if (supp && banner) {
        banner.classList.remove('hidden');
        document.getElementById('modalSelected2sName').textContent = supp.name;
        document.getElementById('modalSelected2sSpec').textContent = `(${supp.spec || supp.category}) | รหัส: ${supp.supplier_code}`;
        const netCost = supp.net_cost || (supp.current_cost * 1.0593);
        document.getElementById('modalSelected2sPrice').innerHTML = `
            <div class="font-bold text-emerald-800">สุทธิ ฿${netCost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
            <div class="text-[10px] text-slate-400">ราคาตั้ง ฿${supp.current_cost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
        `;
    }

    if (reFilter) {
        filterModal2sList();
    }
}

function selectSuggestion(suppId) {
    selectModal2sItem(suppId, true);
}

async function selectAndSaveSuggestion(event, suppId) {
    if (event) event.stopPropagation();
    selectModal2sItem(suppId, false);
    await confirmSaveMapping();
}

async function selectAndSave2sItem(event, suppId) {
    if (event) event.stopPropagation();
    selectModal2sItem(suppId, false);
    await confirmSaveMapping();
}

async function backupMappings() {
    try {
        const res = await fetch('/api/mappings/backup');
        const data = await res.json();
        if (!data || data.length === 0) {
            showToast("ยังไม่มีรายการที่จับคู่เพื่อสำรองข้อมูล", "info");
            return;
        }
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `steel_mappings_backup_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast(`สำรองข้อมูลการจับคู่ ${data.length} รายการเรียบร้อย`, "success");
    } catch (e) {
        console.error(e);
        showToast("เกิดข้อผิดพลาดในการสำรองข้อมูล", "error");
    }
}

async function restoreMappings(input) {
    const file = input.files && input.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const mappings = JSON.parse(e.target.result);
            if (!Array.isArray(mappings)) {
                showToast("รูปแบบไฟล์สำรองไม่ถูกต้อง", "error");
                return;
            }
            const res = await fetch('/api/mappings/restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mappings })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`กู้คืนการจับคู่สำเร็จ ${data.count} รายการ`, "success");
                await Promise.all([fetchMatrix(), loadMappingWorkspace(), fetchStatus()]);
            } else {
                showToast(data.message || "เกิดข้อผิดพลาด", "error");
            }
        } catch (err) {
            console.error(err);
            showToast("ไฟล์ JSON ไม่ถูกต้อง", "error");
        } finally {
            input.value = '';
        }
    };
    reader.readAsText(file);
}

async function confirmSaveMapping() {
    const shopId = appState.selectedShopForMapping;
    const suppId = parseInt(document.getElementById('modalSupplierSelect').value);
    const multiplier = parseFloat(document.getElementById('modalMultiplier').value) || 1.0;
    const notes = document.getElementById('modalNotes').value;

    if (!suppId) {
        showToast("กรุณาเลือกสินค้า 2S Metal ที่ต้องการจับคู่", "error");
        return;
    }

    try {
        const res = await fetch('/api/mappings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                shop_product_id: shopId,
                supplier_product_id: suppId,
                multiplier: multiplier,
                notes: notes
            })
        });
        const data = await res.json();
        if (data.success) {
            closeModal('modalLink');
            showToast("บันทึกการจับคู่สินค้าเรียบร้อย (ระบบจดจำถาวร)", "success");
            fetchStatus();
            await Promise.all([fetchMatrix(), loadMappingWorkspace()]);
        }
    } catch (e) {
        showToast("ข้อผิดพลาดในการบันทึก", "error");
    }
}

async function unlinkMapping(mappingId) {
    if (!confirm("คุณแน่ใจหรือไม่ว่าต้องการยกเลิกการจับคู่สินค้านี้?")) return;
    try {
        const res = await fetch(`/api/mappings/${mappingId}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast("ยกเลิกการจับคู่เรียบร้อย", "info");
            fetchStatus();
            await Promise.all([fetchMatrix(), loadMappingWorkspace()]);
        }
    } catch (e) {
        showToast("เกิดข้อผิดพลาด", "error");
    }
}

async function autoLinkHighConfidence() {
    if (!confirm("ระบบจะจับคู่สินค้าที่ชื่อและสเปกตรงกันแน่นอน (คะแนนความเหมือน 80% ขึ้นไป) ให้โดยอัตโนมัติ ยืนยันหรือไม่?")) return;
    try {
        const res = await fetch('/api/mappings/auto-link-high-confidence', {method: 'POST'});
        const data = await res.json();
        showToast(data.message, "success");
        fetchStatus();
        if (appState.activeTab === 'pricing') fetchMatrix();
        else if (appState.activeTab === 'mapping') loadMappingWorkspace();
    } catch (e) {
        showToast("ข้อผิดพลาด", "error");
    }
}

// ----------------- 2S Metal Sync & Actions -----------------
function openSyncModal() {
    document.getElementById('modalSync').classList.remove('hidden');
    document.getElementById('syncProgressMsg').classList.add('hidden');
    lucide.createIcons();
}

async function executeSyncLive() {
    const user = document.getElementById('syncModalUser').value.trim();
    const pass = document.getElementById('syncModalPass').value.trim();
    const cookie = document.getElementById('syncModalCookie').value.trim();

    const progressMsg = document.getElementById('syncProgressMsg');
    const btn = document.getElementById('btnExecuteSync');

    progressMsg.className = "p-3 rounded-lg text-xs font-medium bg-blue-50 text-blue-700 block border border-blue-200";
    progressMsg.innerHTML = `<div class="flex items-center space-x-2"><div class="w-3.5 h-3.5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div><span>กำลังเชื่อมต่อไปยัง 2S Metal DConnect...</span></div>`;
    btn.disabled = true;

    try {
        const res = await fetch('/api/supplier/sync-live', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                username: user,
                password: pass,
                session_cookie: cookie
            })
        });
        const data = await res.json();
        if (data.success) {
            progressMsg.className = "p-3 rounded-lg text-xs font-medium bg-emerald-50 text-emerald-800 block border border-emerald-200";
            progressMsg.textContent = data.message;
            showToast("อัปเดตราคาต้นทุน 2S Metal สำเร็จ!", "success");
            setTimeout(() => {
                closeModal('modalSync');
                loadInitialData();
            }, 1000);
        } else {
            progressMsg.className = "p-3 rounded-lg text-xs font-medium bg-rose-50 text-rose-800 block border border-rose-200";
            progressMsg.textContent = data.message;
        }
    } catch (e) {
        progressMsg.className = "p-3 rounded-lg text-xs font-medium bg-rose-50 text-rose-800 block border border-rose-200";
        progressMsg.textContent = "การเชื่อมต่อขัดข้อง: " + e.message;
    } finally {
        btn.disabled = false;
    }
}

async function loadSampleCatalogDirect() {
    closeModal('modalSync');
    await loadSampleCatalog();
}

async function loadSampleCatalog() {
    try {
        const res = await fetch('/api/supplier/import-sample', {method: 'POST'});
        const data = await res.json();
        showToast(data.message, "success");
        loadInitialData();
    } catch (e) {
        showToast("เกิดข้อผิดพลาดในการโหลดแค็ตตาล็อกตัวอย่าง", "error");
    }
}

function openPasteModal() {
    document.getElementById('modalPaste').classList.remove('hidden');
    document.getElementById('pasteHtmlText').value = '';
    lucide.createIcons();
}

async function executePastedImport() {
    const text = document.getElementById('pasteHtmlText').value.trim();
    if (!text) {
        showToast("กรุณาวางเนื้อหาตารางจากเว็บ 2S Metal", "error");
        return;
    }
    try {
        const res = await fetch('/api/supplier/import-pasted', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({html_content: text})
        });
        const data = await res.json();
        if (data.success) {
            closeModal('modalPaste');
            showToast(data.message, "success");
            loadInitialData();
        } else {
            showToast(data.message || "ไม่สามารถอ่านตารางได้", "error");
        }
    } catch (e) {
        showToast("ข้อผิดพลาด: " + e.message, "error");
    }
}

// ----------------- Supplier Table Filter & Search -----------------
let suppDebounceTimer = null;
function debounceSupplierSearch() {
    clearTimeout(suppDebounceTimer);
    suppDebounceTimer = setTimeout(() => {
        filterSupplierTable();
    }, 200);
}

function filterSupplierTable() {
    const q = (document.getElementById('suppSearchInput')?.value || '').toLowerCase().trim();
    const cat = document.getElementById('suppCategoryFilter')?.value || '';

    let filtered = appState.supplierProducts || [];

    if (cat) {
        filtered = filtered.filter(it => it.category === cat);
    }

    if (q) {
        const tokens = q.split(/\s+/).filter(t => t);
        filtered = filtered.filter(it => {
            const combined = `${it.supplier_code || ''} ${it.name || ''} ${it.spec || ''} ${it.category || ''}`.toLowerCase();
            return tokens.every(token => combined.includes(token));
        });
    }

    const badge = document.getElementById('suppCountBadge');
    if (badge) {
        badge.textContent = `พบ ${filtered.length} รายการ (จากทั้งหมด ${appState.supplierProducts.length})`;
    }

    renderSupplierTable(filtered);
}

function renderSupplierTable(items) {
    const tbody = document.getElementById('supplierTableBody');
    if (!items || items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="p-8 text-center text-slate-400">ไม่พบรายการสินค้า 2S Metal ที่ค้นหา</td></tr>`;
        return;
    }
    tbody.innerHTML = items.map(it => `
        <tr class="hover:bg-slate-50">
            <td class="py-2.5 px-3 font-mono text-xs text-slate-500">${escapeHtml(it.supplier_code || '')}</td>
            <td class="py-2.5 px-3 font-semibold text-slate-800">${escapeHtml(it.name)}</td>
            <td class="py-2.5 px-3 text-slate-500 text-xs">${escapeHtml(it.spec || '-')}</td>
            <td class="py-2.5 px-3 text-xs"><span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded">${escapeHtml(it.category || 'เหล็ก')}</span></td>
            <td class="py-2.5 px-3 text-slate-600 text-xs">${it.unit}</td>
            <td class="py-2.5 px-3 text-right font-mono text-slate-600">฿${it.current_cost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
            <td class="py-2.5 px-3 text-right font-mono font-bold text-blue-700 bg-blue-50/50">฿${(it.net_cost || (it.current_cost * 1.0593)).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
            <td class="py-2.5 px-3 text-right font-mono text-xs text-slate-400">${(it.prev_net_cost && it.prev_net_cost > 0) ? `฿${it.prev_net_cost.toLocaleString(undefined, {minimumFractionDigits: 2})}` : ((it.prev_cost && it.prev_cost > 0) ? `฿${it.prev_cost.toLocaleString()}` : '-')}</td>
            <td class="py-2.5 px-3 text-center text-xs"><span class="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full font-medium">${it.stock_status || 'พร้อมส่ง'}</span></td>
            <td class="py-2.5 px-3 text-slate-400 text-xs font-mono">${it.updated_at || '-'}</td>
        </tr>
    `).join('');
}

// ----------------- Express & Shop Product Actions -----------------
async function importExpressAuto() {
    showToast("กำลังอ่านฐานข้อมูล Express (STMAS.DBF)...", "info");
    try {
        const res = await fetch('/api/shop-products/import-express', {method: 'POST'});
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            loadInitialData();
        } else {
            showToast("ไม่สามารถนำเข้าจาก Express ได้: " + data.detail, "error");
        }
    } catch (e) {
        showToast("ข้อผิดพลาด: ตรวจสอบว่าไดรฟ์ Z: เชื่อมต่ออยู่", "error");
    }
}

async function uploadCSV(inputEl) {
    const file = inputEl.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/shop-products/import-csv', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            loadInitialData();
        } else {
            showToast(data.detail || "อัปโหลดไม่สำเร็จ", "error");
        }
    } catch (e) {
        showToast("ข้อผิดพลาด: " + e.message, "error");
    } finally {
        inputEl.value = '';
    }
}

// ----------------- Shop Products Management & Deletion -----------------
function filterShopTable() {
    const q = (document.getElementById('shopSearchInput')?.value || '').toLowerCase().trim();
    let filtered = appState.shopProducts || [];
    if (q) {
        filtered = filtered.filter(it => 
            (it.code && it.code.toLowerCase().includes(q)) || 
            (it.name && it.name.toLowerCase().includes(q)) ||
            (it.category && it.category.toLowerCase().includes(q))
        );
    }
    renderShopTable(filtered);
}

function renderShopTable(items) {
    const tbody = document.getElementById('shopTableBody');
    const badge = document.getElementById('shopCountBadge');
    if (badge) {
        badge.textContent = `${items.length} รายการ (จากทั้งหมด ${appState.shopProducts.length})`;
    }

    if (!items || items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="p-8 text-center text-slate-400">ยังไม่มีข้อมูลสินค้าของร้าน กดปุ่ม "ซิงค์จาก Express" หรือ "นำเข้าไฟล์ CSV"</td></tr>`;
        return;
    }

    const mapDict = {};
    appState.mappings.forEach(m => { mapDict[m.shop_product_id] = m; });

    tbody.innerHTML = items.map(it => {
        const isMapped = !!mapDict[it.id];
        return `
            <tr class="hover:bg-slate-50 transition group">
                <td class="py-2.5 px-3 text-center">
                    <input type="checkbox" class="shop-item-checkbox rounded text-blue-600 focus:ring-0 cursor-pointer" value="${it.id}" onchange="updateDeleteSelectedButton()">
                </td>
                <td class="py-2.5 px-3 font-mono text-xs text-slate-500">${escapeHtml(it.code)}</td>
                <td class="py-2.5 px-3 font-semibold text-slate-800">${escapeHtml(it.name)}</td>
                <td class="py-2.5 px-3 text-xs"><span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded">${escapeHtml(it.category || 'เหล็ก')}</span></td>
                <td class="py-2.5 px-3 text-slate-600 text-xs">${it.unit}</td>
                <td class="py-2.5 px-3 text-right font-mono font-bold text-slate-800">฿${it.selling_price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                <td class="py-2.5 px-3 text-right font-mono text-xs text-slate-500">฿${it.standard_cost.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                <td class="py-2.5 px-3 text-center">
                    ${isMapped ? `
                        <span class="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-medium border border-emerald-200">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> ผูกแล้ว
                        </span>
                    ` : `
                        <span class="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">ยังไม่ผูก</span>
                    `}
                </td>
                <td class="py-2.5 px-3 text-center">
                    <div class="flex items-center justify-center space-x-1">
                        <button onclick="openMappingModal(${it.id})" class="p-1 text-blue-600 hover:bg-blue-50 rounded transition" title="ผูกสินค้า">
                            <i data-lucide="link" class="w-4 h-4"></i>
                        </button>
                        <button onclick="deleteShopProduct(${it.id}, '${escapeHtml(it.name)}')" class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition" title="ลบสินค้า">
                            <i data-lucide="trash-2" class="w-4 h-4"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
    lucide.createIcons();
    updateDeleteSelectedButton();
}

// Delete Single Shop Product
async function deleteShopProduct(productId, name) {
    if (!confirm(`คุณแน่ใจหรือไม่ว่าต้องการลบสินค้า "${name}" ออกจากระบบ?\n(การจับคู่กับ 2S จะถูกยกเลิกด้วย)`)) {
        return;
    }
    try {
        const res = await fetch(`/api/shop-products/${productId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast(`ลบสินค้า "${name}" เรียบร้อย`, "success");
            await loadInitialData();
            if (appState.activeTab === 'shop') fetchShopProducts();
        } else {
            showToast(data.message || "ลบไม่สำเร็จ", "error");
        }
    } catch (e) {
        showToast("ข้อผิดพลาดในการลบสินค้า: " + e.message, "error");
    }
}

// Multi-select Shop Products Deletion
function toggleSelectAllShop(masterEl) {
    const cbs = document.querySelectorAll('.shop-item-checkbox');
    cbs.forEach(cb => cb.checked = masterEl.checked);
    updateDeleteSelectedButton();
}

function updateDeleteSelectedButton() {
    const checkedBoxes = document.querySelectorAll('.shop-item-checkbox:checked');
    const btn = document.getElementById('btnDeleteSelectedShop');
    const text = document.getElementById('deleteSelectedText');
    if (!btn || !text) return;

    if (checkedBoxes.length > 0) {
        btn.classList.remove('hidden');
        btn.classList.add('flex');
        text.textContent = `ลบที่เลือก (${checkedBoxes.length})`;
    } else {
        btn.classList.add('hidden');
        btn.classList.remove('flex');
    }
}

async function deleteSelectedShopProducts() {
    const checkedBoxes = document.querySelectorAll('.shop-item-checkbox:checked');
    const ids = Array.from(checkedBoxes).map(cb => parseInt(cb.value)).filter(id => !isNaN(id));
    
    if (ids.length === 0) {
        showToast("กรุณาติ๊กเลือกสินค้าที่ต้องการลบอย่างน้อย 1 รายการ", "error");
        return;
    }

    if (!confirm(`คุณแน่ใจหรือไม่ว่าต้องการลบสินค้าที่เลือกจำนวน ${ids.length} รายการ?`)) {
        return;
    }

    try {
        const res = await fetch('/api/shop-products/delete-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_ids: ids })
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            const masterCheckbox = document.getElementById('selectAllShopCheckbox');
            if (masterCheckbox) masterCheckbox.checked = false;
            await loadInitialData();
            if (appState.activeTab === 'shop') fetchShopProducts();
        } else {
            showToast("ลบไม่สำเร็จ", "error");
        }
    } catch (e) {
        showToast("เกิดข้อผิดพลาด: " + e.message, "error");
    }
}

async function deleteAllShopProducts() {
    if (!confirm("⚠️ คำเตือนสำคัญ:\nคุณต้องการลบสินค้าของร้านทั้งหมดใช่หรือไม่?\n\n(ข้อมูลสินค้าและการจับคู่ทั้งหมดจะถูกล้าง คุณสามารถกด 'ดึงจาก Express' เพื่อนำเข้าใหม่ได้ตลอดเวลา)")) {
        return;
    }

    try {
        const res = await fetch('/api/shop-products/delete-all', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            await loadInitialData();
            if (appState.activeTab === 'shop') fetchShopProducts();
        } else {
            showToast("ไม่สามารถล้างข้อมูลได้", "error");
        }
    } catch (e) {
        showToast("เกิดข้อผิดพลาด: " + e.message, "error");
    }
}

// Add New Product Manually
function openAddProductModal() {
    document.getElementById('newProdCode').value = '';
    document.getElementById('newProdName').value = '';
    document.getElementById('newProdPrice').value = '';
    document.getElementById('newProdCost').value = '';
    document.getElementById('modalAddProduct').classList.remove('hidden');
    lucide.createIcons();
}

async function executeSaveNewProduct() {
    const code = document.getElementById('newProdCode').value.trim();
    const name = document.getElementById('newProdName').value.trim();
    const cat = document.getElementById('newProdCategory').value;
    const unit = document.getElementById('newProdUnit').value.trim() || 'เส้น';
    const price = parseFloat(document.getElementById('newProdPrice').value) || 0.0;
    const cost = parseFloat(document.getElementById('newProdCost').value) || 0.0;

    if (!code || !name) {
        showToast("กรุณากรอกรหัสสินค้าและชื่อสินค้า", "error");
        return;
    }

    try {
        const res = await fetch('/api/shop-products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: code,
                name: name,
                category: cat,
                unit: unit,
                selling_price: price,
                standard_cost: cost
            })
        });
        const data = await res.json();
        if (data.success) {
            closeModal('modalAddProduct');
            showToast(`เพิ่มสินค้า "${name}" เรียบร้อยแล้ว`, "success");
            await loadInitialData();
            if (appState.activeTab === 'shop') fetchShopProducts();
        }
    } catch (e) {
        showToast("ข้อผิดพลาดในการบันทึก: " + e.message, "error");
    }
}

// ----------------- Settings & Export -----------------
async function saveAppSettings() {
    const user = document.getElementById('setting2sUser').value.trim();
    const pass = document.getElementById('setting2sPass').value.trim();
    const cookie = document.getElementById('setting2sCookie').value.trim();
    const expPath = document.getElementById('settingExpressPath').value.trim();
    const lowMargin = document.getElementById('settingLowMargin').value.trim();
    const goodMargin = document.getElementById('settingGoodMargin').value.trim();
    const discPct = document.getElementById('settingSupplierDiscount')?.value.trim() || '1.0';
    const vatPct = document.getElementById('settingSupplierVat')?.value.trim() || '7.0';
    const incVat = document.getElementById('settingIncludeVat')?.checked ? '1' : '0';

    const payload = {
        settings: {
            '2s_username': user,
            '2s_session_cookie': cookie,
            'express_path': expPath,
            'low_margin_threshold': lowMargin,
            'good_margin_threshold': goodMargin,
            'supplier_discount_pct': discPct,
            'supplier_vat_pct': vatPct,
            'include_vat': incVat
        }
    };
    if (pass && pass !== '******') {
        payload.settings['2s_password'] = pass;
    }

    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast("บันทึกการตั้งค่าเรียบร้อยแล้ว (อัปเดตต้นทุนและกำไรใหม่แล้ว)", "success");
            await loadInitialData();
        }
    } catch (e) {
        showToast("เกิดข้อผิดพลาดในการบันทึก", "error");
    }
}

function exportToCSV() {
    const items = appState.matrix || [];
    if (!items.length) {
        showToast("ไม่พบข้อมูลสินค้าสำหรับส่งออก", "warning");
        return;
    }

    const headers = [
        "รหัสสินค้า", "ชื่อสินค้าของร้าน", "หมวดหมู่", "หน่วย",
        "สินค้า 2S Metal ที่ผูกไว้", "สเปก 2S", "ต้นทุนสุทธิ 2S (บาท)",
        "ราคาขายหน้าร้าน (บาท)", "กำไรปกติ (บาท)", "% กำไรปกติ",
        "ราคาขายเสนอพิเศษ (บาท)", "กำไรใหม่ (บาท)", "% กำไรใหม่", "สถานะกำไร"
    ];

    const escapeCsv = (val) => {
        if (val === null || val === undefined) return '""';
        const str = String(val).replace(/"/g, '""');
        return `"${str}"`;
    };

    let csvContent = '\uFEFF'; // UTF-8 BOM so Thai fonts render properly in Excel
    csvContent += headers.map(escapeCsv).join(',') + '\r\n';

    const lowThresh = parseFloat(appState.settings['low_margin_threshold'] || 8.0);
    const goodThresh = parseFloat(appState.settings['good_margin_threshold'] || 15.0);

    items.forEach(it => {
        const shopId = it.shop_id;
        const isMapped = it.is_mapped;
        const effCost = it.effective_cost || 0;
        const normalPrice = it.selling_price || 0;
        const normalProfit = it.normal_profit || 0;
        const normalMargin = it.normal_margin_pct || 0;

        const discountPrice = appState.discounts[shopId] !== undefined ? appState.discounts[shopId] : normalPrice;
        let discProfit = 0;
        let discMargin = 0;
        let statusLabel = it.status_label || (isMapped ? "ปกติ" : "ยังไม่จับคู่");

        if (isMapped && effCost > 0 && discountPrice > 0) {
            discProfit = discountPrice - effCost;
            discMargin = (discProfit / discountPrice) * 100.0;
            if (discProfit < 0) statusLabel = "ขาดทุน";
            else if (discMargin < lowThresh) statusLabel = "กำไรต่ำ";
            else if (discMargin >= goodThresh) statusLabel = "กำไรดี";
            else statusLabel = "ปกติ";
        }

        const row = [
            it.shop_code || '',
            it.shop_name || '',
            it.shop_category || '',
            it.shop_unit || '',
            it.supplier_name || (isMapped ? '' : 'ยังไม่จับคู่'),
            it.supplier_spec || '',
            isMapped ? effCost.toFixed(2) : '0.00',
            normalPrice.toFixed(2),
            normalProfit.toFixed(2),
            `${normalMargin}%`,
            discountPrice.toFixed(2),
            discProfit.toFixed(2),
            `${discMargin.toFixed(1)}%`,
            statusLabel
        ];
        csvContent += row.map(escapeCsv).join(',') + '\r\n';
    });

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const now = new Date();
    const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;
    a.download = `steel_price_export_${dateStr}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("ส่งออกไฟล์ Excel (CSV) เรียบร้อยแล้ว", "success");
}

// ----------------- UI Helpers -----------------
function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('hidden');
}

function showToast(msg, type = "success") {
    const toast = document.getElementById('toast');
    const toastBox = document.getElementById('toastBox');
    const toastMsg = document.getElementById('toastMsg');
    const toastIcon = document.getElementById('toastIcon');

    toastMsg.textContent = msg;

    if (type === 'success') {
        toastBox.className = "flex items-center space-x-3 px-4 py-3 rounded-xl shadow-xl text-white text-sm font-medium bg-emerald-600";
        toastIcon.setAttribute('data-lucide', 'check-circle');
    } else if (type === 'error') {
        toastBox.className = "flex items-center space-x-3 px-4 py-3 rounded-xl shadow-xl text-white text-sm font-medium bg-rose-600";
        toastIcon.setAttribute('data-lucide', 'alert-circle');
    } else {
        toastBox.className = "flex items-center space-x-3 px-4 py-3 rounded-xl shadow-xl text-white text-sm font-medium bg-blue-600";
        toastIcon.setAttribute('data-lucide', 'info');
    }

    lucide.createIcons();
    toast.classList.remove('translate-y-20', 'opacity-0', 'pointer-events-none');

    setTimeout(() => {
        toast.classList.add('translate-y-20', 'opacity-0', 'pointer-events-none');
    }, 3500);
}

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/[&<>"']/g, function(m) {
        return {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        }[m];
    });
}
