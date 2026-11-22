"""
Sinh dữ liệu mô phỏng cho VietReport (bản đã sửa).

Đặc điểm:
- Seed cố định + ANCHOR_DATE cố định => chạy lại ở bất kỳ ngày nào cũng ra đúng dữ liệu cũ.
- Mùa vụ (Tết 2026, 11/11, 12/12, Black Friday, cuối tuần), xu hướng tăng nhẹ,
  khác biệt khu vực/danh mục THỰC SỰ được áp dụng vào việc sinh đơn.
- Tính nhất quán giữa các bảng:
    don_hang.tongTien = SUM(chi_tiet_don_hang.thanhTien) - SUM(don_hang_khuyen_mai.soTienGiam)
    trạng thái đơn quyết định trạng thái vận chuyển/thanh toán và phụ thuộc tuổi đơn
    khuyến mãi chỉ áp trong thời gian hiệu lực, đơn không đặt trước ngày đăng ký khách.
- Dirty data có kiểm soát (được ghi lại trong db/ground_truth.json):
    thiếu hoTen/email/soDienThoai, khách hàng trùng, một số đơn "tồn đọng".
- Planted insights (đo lại từ dữ liệu sinh ra, ghi vào db/ground_truth.json):
    1. Doanh thu Miền Trung giảm mạnh trong 90 ngày gần nhất.
    2. Danh mục Phụ kiện tăng đột biến trong 60 ngày gần nhất.
    3. Sản phẩm id=42 có tỷ lệ hoàn tiền cao và điểm đánh giá thấp.
- Mọi số tiền là số nguyên VNĐ (tránh lỗi Decimal * float).

Chạy:
    python db/generate_data.py
Kiểm tra sau khi sinh:
    psql -f db/validate_data.sql   (mọi truy vấn kiểm tra phải trả về 0)
"""

from __future__ import annotations

import bisect
import json
import os
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import psycopg2
from dotenv import load_dotenv
from faker import Faker
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------

load_dotenv()

SEED = 20261112
ANCHOR_DATE = date(2026, 11, 12)  # "hôm nay" cố định của bộ dữ liệu
NUM_CUSTOMERS = 3000
NUM_DUPLICATE_CUSTOMERS = 30
NUM_PRODUCTS = 150
NUM_ORDERS = 20000
NUM_DAYS = 365
START_DATE = ANCHOR_DATE - timedelta(days=NUM_DAYS - 1)

# Planted insights
PLANTED_PRODUCT_ID = 42
MIEN_TRUNG = "Miền Trung"
MIEN_TRUNG_WINDOW_DAYS = 90
MIEN_TRUNG_KEEP_RATE = 0.5  # giữ lại 50% đơn Miền Trung trong cửa sổ => giảm khoảng 44%
PHU_KIEN = "Phụ kiện"
PHU_KIEN_WINDOW_DAYS = 60
PHU_KIEN_SPIKE_FACTOR = 2.2
PRODUCT_42_REFUND_RATE = 0.10
BASE_REFUND_RATE = 0.02
BASE_CANCEL_RATE = 0.08

TET_DATE = date(2026, 2, 17)  # mùng 1 Tết Bính Ngọ

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "E-commerce"),
    "user": os.getenv("POSTGRES_ADMIN_USER", "vietreport_admin"),
    "password": os.getenv("POSTGRES_ADMIN_PASSWORD", "vietreport_admin_password"),
}

random.seed(SEED)
np.random.seed(SEED)

fake = Faker("vi_VN")
Faker.seed(SEED)

# Hệ số nhu cầu theo khu vực (quyết định số khách hàng mỗi vùng)
REGION_DEMAND = {
    "Miền Bắc": 1.0,
    "Miền Trung": 1.0,
    "Miền Nam": 1.15,
    "Hà Nội": 1.2,
    "TP. Hồ Chí Minh": 1.5,
}
REGIONS = list(REGION_DEMAND)
REGION_ID = {name: i for i, name in enumerate(REGIONS, start=1)}

# (giá thấp nhất, giá cao nhất) tính theo nghìn VNĐ, hệ số nhu cầu
CATEGORY_CONFIG = {
    "Điện thoại": {"price_k": (2000, 40000), "demand": 1.0},
    "Laptop": {"price_k": (12000, 65000), "demand": 1.05},
    "Phụ kiện": {"price_k": (20, 1500), "demand": 1.25},
    "Đồ gia dụng": {"price_k": (100, 7000), "demand": 0.95},
    "Thời trang": {"price_k": (100, 5000), "demand": 1.30},
    "Mỹ phẩm": {"price_k": (80, 3500), "demand": 1.20},
}
CATEGORIES = list(CATEGORY_CONFIG)
CATEGORY_ID = {name: i for i, name in enumerate(CATEGORIES, start=1)}
BRANDS = ["Aurora", "Nova", "Zenith", "Lumi", "Orion", "Vega"]

# Trạng thái (dùng thống nhất một cách viết: "xử lý")
ST_PROCESSING = "Đang xử lý"
ST_CONFIRMED = "Đã xác nhận"
ST_SHIPPING = "Đang giao hàng"
ST_DELIVERED = "Đã giao hàng"
ST_CANCELLED = "Đã hủy"

PAY_PENDING = "Chờ xử lý"
PAY_SUCCESS = "Thành công"
PAY_FAILED = "Thất bại"
PAY_REFUND = "Hoàn tiền"
TX_PAYMENT = "Thanh toán"
TX_REFUND = "Hoàn tiền"

PAYMENT_METHODS = ["Tiền mặt", "Chuyển khoản", "Momo", "VNPay", "Thẻ tín dụng"]
ONLINE_METHODS = PAYMENT_METHODS[1:]
SHIPPING_CARRIERS = ["GHN", "GHTK", "Viettel Post", "J&T"]
CANCEL_REASONS = [
    "Khách đổi ý",
    "Hết hàng",
    "Sai địa chỉ",
    "Thanh toán thất bại",
    "Giao hàng thất bại nhiều lần",
]
CANCEL_WEIGHTS = [0.35, 0.20, 0.15, 0.20, 0.10]

# (mã, mô tả, % giảm, ngày bắt đầu, ngày kết thúc, loại)
PROMOTION_DEFS = [
    ("BLACKFRIDAY", "Black Friday", 25, date(2025, 11, 26), date(2025, 11, 30), "event"),
    ("SALE1212", "Sale ngày 12/12", 18, date(2025, 12, 10), date(2025, 12, 13), "event"),
    ("TET2026", "Khuyến mãi Tết", 15, date(2026, 1, 20), date(2026, 2, 14), "event"),
    ("FREESHIP", "Miễn phí vận chuyển", 5, date(2026, 3, 1), date(2026, 6, 30), "always"),
    ("NEWUSER", "Ưu đãi khách hàng mới", 10, START_DATE, ANCHOR_DATE, "newuser"),
    ("SALE1111", "Sale ngày 11/11", 20, date(2026, 11, 10), date(2026, 11, 12), "event"),
]

REVIEW_COMMENTS = {
    "pos": [
        "Sản phẩm đúng mô tả, giao nhanh.",
        "Chất lượng tốt so với giá tiền.",
        "Đóng gói cẩn thận, sẽ ủng hộ tiếp.",
        "Dùng ổn, rất hài lòng.",
    ],
    "neu": [
        "Sản phẩm tạm ổn, giao hơi chậm.",
        "Bình thường, không có gì nổi bật.",
        "Chất lượng ở mức chấp nhận được.",
    ],
    "neg": [
        "Sản phẩm không giống mô tả.",
        "Chất lượng kém, thất vọng.",
        "Giao chậm và đóng gói sơ sài.",
        "Lỗi sau vài ngày sử dụng, muốn trả hàng.",
    ],
}

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def in_recent(d: date, days: int) -> bool:
    """d nằm trong `days` ngày gần nhất tính đến ANCHOR_DATE (gồm cả ANCHOR_DATE)."""
    return d > ANCHOR_DATE - timedelta(days=days)


def in_previous(d: date, days: int) -> bool:
    """d nằm trong `days` ngày liền trước cửa sổ gần nhất."""
    return ANCHOR_DATE - timedelta(days=2 * days) < d <= ANCHOR_DATE - timedelta(days=days)


def round_k(value: float) -> int:
    """Làm tròn về bội số của 1.000 VNĐ."""
    return int(round(value / 1000.0)) * 1000


def seasonal_multiplier(d: date) -> float:
    """Hệ số nhu cầu theo mùa vụ và ngày trong tuần."""
    m = 1.0

    # Tết: mua sắm dồn trước Tết, vắng khách trong những ngày nghỉ Tết
    if TET_DATE - timedelta(days=21) <= d <= TET_DATE - timedelta(days=3):
        m *= 1.35
    elif TET_DATE - timedelta(days=2) <= d <= TET_DATE + timedelta(days=5):
        m *= 0.5

    # Các đợt sale lớn
    if d.month == 11 and d.day in (10, 11, 12):
        m *= 1.6
    if d.month == 12 and d.day in (11, 12):
        m *= 1.45
    if d == date(2025, 11, 28):  # Black Friday 2025
        m *= 1.4

    # Cuối tuần
    if d.weekday() >= 5:
        m *= 1.15

    return m


# ---------------------------------------------------------------------------
# Sinh dữ liệu trong bộ nhớ
# ---------------------------------------------------------------------------


def build_products() -> dict[int, dict]:
    popularity = np.clip(np.random.pareto(1.5, NUM_PRODUCTS) + 1, 1, 15)
    # sản phẩm planted phải đủ phổ biến để có đủ mẫu thống kê
    popularity[PLANTED_PRODUCT_ID - 1] = np.percentile(popularity, 85)

    change_ids = set(random.sample(range(1, NUM_PRODUCTS + 1), 30))
    products: dict[int, dict] = {}

    for pid in range(1, NUM_PRODUCTS + 1):
        category = "Thời trang" if pid == PLANTED_PRODUCT_ID else random.choice(CATEGORIES)
        cfg = CATEGORY_CONFIG[category]
        price = random.randint(*cfg["price_k"]) * 1000
        cost = round_k(price * random.uniform(0.55, 0.80))

        # Một số sản phẩm từng đổi giá: donGia lịch sử khác giaBan hiện tại
        old_price, change_date = None, None
        if pid in change_ids:
            old_price = round_k(price * random.uniform(0.80, 0.95))
            change_date = START_DATE + timedelta(days=random.randint(60, NUM_DAYS - 30))

        products[pid] = {
            "id": pid,
            "name": f"{category} {random.choice(BRANDS)} {pid:03d}",
            "category": category,
            "price": price,
            "cost": cost,
            "old_price": old_price,
            "change_date": change_date,
            "weight": float(popularity[pid - 1]) * cfg["demand"],
        }
    return products


def unit_price(product: dict, d: date) -> int:
    """Đơn giá snapshot tại ngày đặt hàng."""
    if product["change_date"] is not None and d < product["change_date"]:
        return product["old_price"]
    return product["price"]


def build_customers() -> list[dict]:
    customers = []
    region_weights = [REGION_DEMAND[r] for r in REGIONS]

    for _ in range(NUM_CUSTOMERS):
        days_ago = int(np.clip(np.random.exponential(350), 30, 3 * 365))
        customers.append(
            {
                "name": None if random.random() < 0.03 else fake.name(),
                "email": None if random.random() < 0.05 else fake.email(),
                "phone": None if random.random() < 0.08 else fake.phone_number(),
                "region": random.choices(REGIONS, weights=region_weights)[0],
                "reg": ANCHOR_DATE - timedelta(days=days_ago),
                "dup_of_other": False,
            }
        )

    # Dirty data: khách hàng trùng thông tin (cùng tên/email/SĐT, khác id và ngày đăng ký)
    for src in random.sample(customers[:NUM_CUSTOMERS], NUM_DUPLICATE_CUSTOMERS):
        days_ago = int(np.clip(np.random.exponential(350), 30, 3 * 365))
        customers.append(
            {
                **src,
                "reg": ANCHOR_DATE - timedelta(days=days_ago),
                "dup_of_other": True,
            }
        )

    # Sắp xếp theo ngày đăng ký rồi gán id 1..N: khách có id <= k là khách đã đăng ký
    customers.sort(key=lambda c: c["reg"])
    for cid, c in enumerate(customers, start=1):
        c["id"] = cid
    return customers


def build_promotions() -> list[dict]:
    return [
        {"id": i, "code": code, "desc": desc, "pct": pct, "start": s, "end": e, "kind": kind}
        for i, (code, desc, pct, s, e, kind) in enumerate(PROMOTION_DEFS, start=1)
    ]


def pick_promotion(d: date, customer: dict, promotions: list[dict]) -> dict | None:
    valid = [
        p
        for p in promotions
        if p["start"] <= d <= p["end"]
        and (p["kind"] != "newuser" or (d - customer["reg"]).days <= 30)
    ]
    if not valid:
        return None

    has_event = any(p["kind"] == "event" for p in valid)
    if random.random() >= (0.6 if has_event else 0.2):
        return None

    weights = [3 if p["kind"] == "event" else 1 for p in valid]
    return random.choices(valid, weights=weights)[0]


def pick_status(age_days: int) -> str:
    """Trạng thái đơn (chưa hủy) phụ thuộc tuổi đơn."""
    if age_days <= 1:
        return random.choices(
            [ST_PROCESSING, ST_CONFIRMED, ST_SHIPPING], weights=[0.50, 0.35, 0.15]
        )[0]
    if age_days <= 4:
        return random.choices(
            [ST_CONFIRMED, ST_SHIPPING, ST_DELIVERED], weights=[0.15, 0.35, 0.50]
        )[0]
    # Dirty data: một tỷ lệ nhỏ đơn cũ bị "tồn đọng"
    return random.choices(
        [ST_DELIVERED, ST_SHIPPING, ST_PROCESSING], weights=[0.985, 0.010, 0.005]
    )[0]


def generate_orders(
    products: dict[int, dict],
    customers: list[dict],
    promotions: list[dict],
) -> list[dict]:
    # --- Ngày đặt: có mùa vụ + xu hướng tăng nhẹ ---
    days = [START_DATE + timedelta(days=i) for i in range(NUM_DAYS)]
    day_w = np.array(
        [seasonal_multiplier(d) * (1 + 0.18 * i / (NUM_DAYS - 1)) for i, d in enumerate(days)]
    )
    day_w /= day_w.sum()
    day_idx = np.sort(np.random.choice(NUM_DAYS, size=NUM_ORDERS, p=day_w))

    # --- Trọng số chọn sản phẩm (bình thường / giai đoạn Phụ kiện tăng đột biến) ---
    w_base = np.array([products[pid]["weight"] for pid in range(1, NUM_PRODUCTS + 1)])
    w_spike = np.array(
        [
            products[pid]["weight"]
            * (PHU_KIEN_SPIKE_FACTOR if products[pid]["category"] == PHU_KIEN else 1.0)
            for pid in range(1, NUM_PRODUCTS + 1)
        ]
    )
    w_base /= w_base.sum()
    w_spike /= w_spike.sum()

    # --- Mức độ hoạt động của khách (một số khách mua nhiều hơn hẳn) ---
    activity = np.random.lognormal(0.0, 0.9, size=len(customers))
    cust_cum = np.cumsum(activity).tolist()
    reg_dates = [c["reg"] for c in customers]

    orders: list[dict] = []

    for order_id, di in enumerate(day_idx, start=1):
        d = days[int(di)]
        age = (ANCHOR_DATE - d).days

        # Chỉ khách đã đăng ký trước hoặc đúng ngày đặt
        k = bisect.bisect_right(reg_dates, d)
        total_w = cust_cum[k - 1]

        customer, region = None, None
        for _ in range(60):
            idx = min(bisect.bisect_left(cust_cum, random.random() * total_w), k - 1)
            customer = customers[idx]
            region = customer["region"] if random.random() < 0.85 else random.choice(REGIONS)
            # Planted insight 1: Miền Trung mất đơn trong 90 ngày gần nhất
            if (
                region == MIEN_TRUNG
                and in_recent(d, MIEN_TRUNG_WINDOW_DAYS)
                and random.random() > MIEN_TRUNG_KEEP_RATE
            ):
                continue
            break

        # --- Dòng sản phẩm ---
        n_items = 1 + min(5, int(np.random.poisson(0.7)))
        w_vec = w_spike if in_recent(d, PHU_KIEN_WINDOW_DAYS) else w_base
        pids = np.random.choice(NUM_PRODUCTS, size=n_items, replace=False, p=w_vec) + 1

        lines = []  # (pid, qty, unit)
        for pid in pids:
            pid = int(pid)
            unit = unit_price(products[pid], d)
            qty = 1 if unit >= 10_000_000 else random.choices([1, 2, 3], weights=[0.72, 0.20, 0.08])[0]
            lines.append((pid, qty, unit))

        raw_total = sum(q * u for _, q, u in lines)

        # --- Khuyến mãi (chỉ trong thời gian hiệu lực) ---
        promo = pick_promotion(d, customer, promotions)
        discount = int(round(raw_total * promo["pct"] / 100)) if promo else 0
        total = raw_total - discount

        # --- Trạng thái đơn ---
        cancel_reason = None
        if random.random() < BASE_CANCEL_RATE:
            status = ST_CANCELLED
            cancel_reason = random.choices(CANCEL_REASONS, weights=CANCEL_WEIGHTS)[0]
        else:
            status = pick_status(age)

        # --- Vận chuyển ---
        expected = d + timedelta(days=random.randint(2, 5))
        delivered_date = None
        if status == ST_DELIVERED:
            delay = random.choices([-1, 0, 1, 2, 3], weights=[0.15, 0.45, 0.20, 0.12, 0.08])[0]
            transit = max(1, (expected - d).days + delay)
            delivered_date = min(d + timedelta(days=transit), ANCHOR_DATE)

        # --- Thanh toán ---
        method = random.choices(PAYMENT_METHODS, weights=[0.35, 0.20, 0.20, 0.15, 0.10])[0]
        if cancel_reason == "Thanh toán thất bại" and method == "COD":
            method = random.choice(ONLINE_METHODS)

        if status == ST_CANCELLED:
            pay_status = PAY_FAILED if cancel_reason == "Thanh toán thất bại" else PAY_PENDING
            pay_date = None
        elif method == "COD":
            if status == ST_DELIVERED:
                pay_status, pay_date = PAY_SUCCESS, delivered_date
            else:
                pay_status, pay_date = PAY_PENDING, None
        else:
            pay_status = PAY_SUCCESS
            pay_date = min(d + timedelta(days=random.randint(0, 1)), ANCHOR_DATE)

        # --- Hoàn tiền (planted insight 3 + nền hoàn tiền thấp) ---
        refund = None  # (pid, amount, date)
        if status == ST_DELIVERED and pay_date is not None:
            refund_pid = None
            has_p42 = any(pid == PLANTED_PRODUCT_ID for pid, _, _ in lines)
            if has_p42 and random.random() < PRODUCT_42_REFUND_RATE:
                refund_pid = PLANTED_PRODUCT_ID
            elif random.random() < BASE_REFUND_RATE:
                refund_pid = random.choice(lines)[0]

            if refund_pid is not None:
                refund_date = pay_date + timedelta(days=random.randint(3, 14))
                if refund_date <= ANCHOR_DATE:
                    line_value = next(q * u for pid, q, u in lines if pid == refund_pid)
                    refund = (refund_pid, min(line_value, total), refund_date)

        orders.append(
            {
                "id": order_id,
                "customer": customer,
                "date": d,
                "status": status,
                "cancel_reason": cancel_reason,
                "region": region,
                "lines": lines,
                "raw_total": raw_total,
                "promo": promo,
                "discount": discount,
                "total": total,
                "method": method,
                "pay_status": pay_status,
                "pay_date": pay_date,
                "expected": expected,
                "delivered_date": delivered_date,
                "carrier": random.choice(SHIPPING_CARRIERS),
                "ship_fee": 0 if status == ST_CANCELLED else random.randint(15, 70) * 1000,
                "refund": refund,
            }
        )

    return orders


def generate_reviews(orders: list[dict]) -> list[tuple]:
    """Đánh giá cho khoảng 35% dòng sản phẩm của các đơn đã giao."""
    rows = []
    for o in orders:
        if o["status"] != ST_DELIVERED:
            continue
        for pid, _, _ in o["lines"]:
            if random.random() >= 0.35:
                continue

            review_date = o["delivered_date"] + timedelta(days=random.randint(1, 20))
            if review_date > ANCHOR_DATE:
                continue

            weights = (
                [0.25, 0.25, 0.25, 0.15, 0.10]  # planted: sản phẩm 42 bị chấm thấp
                if pid == PLANTED_PRODUCT_ID
                else [0.07, 0.08, 0.15, 0.30, 0.40]
            )
            rating = random.choices([1, 2, 3, 4, 5], weights=weights)[0]
            bucket = "neg" if rating <= 2 else "neu" if rating == 3 else "pos"
            comment = random.choice(REVIEW_COMMENTS[bucket]) if random.random() < 0.45 else None
            rows.append((o["id"], pid, rating, comment, review_date))
    return rows


def assign_segments(customers: list[dict], orders: list[dict]) -> None:
    """Phân khúc do CRM gán: New | Inactive | Silver | Gold | Platinum | VIP."""
    spend: dict[int, int] = defaultdict(int)
    last_order: dict[int, date] = {}
    for o in orders:
        if o["status"] == ST_CANCELLED:
            continue
        cid = o["customer"]["id"]
        spend[cid] += o["total"]
        last_order[cid] = max(last_order.get(cid, o["date"]), o["date"])

    active = []
    for c in customers:
        cid = c["id"]
        if (ANCHOR_DATE - c["reg"]).days <= 60:
            c["segment"] = "New"
        elif cid not in last_order or (ANCHOR_DATE - last_order[cid]).days > 90:
            c["segment"] = "Inactive"
        else:
            active.append(c)

    active.sort(key=lambda c: spend[c["id"]], reverse=True)
    n = len(active)
    for rank, c in enumerate(active):
        share = rank / max(1, n)
        c["segment"] = (
            "VIP" if share < 0.05 else "Platinum" if share < 0.20 else "Gold" if share < 0.50 else "Silver"
        )


# ---------------------------------------------------------------------------
# Ground truth cho bộ đánh giá
# ---------------------------------------------------------------------------


def pct_change(new: float, old: float) -> float | None:
    return round((new - old) / old * 100, 1) if old else None


def compute_ground_truth(
    products: dict[int, dict],
    customers: list[dict],
    orders: list[dict],
    review_rows: list[tuple],
) -> dict:
    valid = [o for o in orders if o["status"] != ST_CANCELLED]

    mt_recent = sum(o["total"] for o in valid if o["region"] == MIEN_TRUNG and in_recent(o["date"], MIEN_TRUNG_WINDOW_DAYS))
    mt_prev = sum(o["total"] for o in valid if o["region"] == MIEN_TRUNG and in_previous(o["date"], MIEN_TRUNG_WINDOW_DAYS))
    all_recent = sum(o["total"] for o in valid if in_recent(o["date"], MIEN_TRUNG_WINDOW_DAYS))
    all_prev = sum(o["total"] for o in valid if in_previous(o["date"], MIEN_TRUNG_WINDOW_DAYS))

    def accessory_revenue(predicate) -> int:
        return sum(
            q * u
            for o in valid
            if predicate(o["date"])
            for pid, q, u in o["lines"]
            if products[pid]["category"] == PHU_KIEN
        )

    pk_recent = accessory_revenue(lambda d: in_recent(d, PHU_KIEN_WINDOW_DAYS))
    pk_prev = accessory_revenue(lambda d: in_previous(d, PHU_KIEN_WINDOW_DAYS))

    delivered = [o for o in orders if o["status"] == ST_DELIVERED]
    with_42 = [o for o in delivered if any(pid == PLANTED_PRODUCT_ID for pid, _, _ in o["lines"])]
    without_42 = [o for o in delivered if o not in with_42]
    refunded_42 = [o for o in with_42 if o["refund"] and o["refund"][0] == PLANTED_PRODUCT_ID]
    refunded_other = [o for o in without_42 if o["refund"]]

    r42 = [r[2] for r in review_rows if r[1] == PLANTED_PRODUCT_ID]
    rother = [r[2] for r in review_rows if r[1] != PLANTED_PRODUCT_ID]

    stuck = [
        o
        for o in orders
        if o["status"] in (ST_PROCESSING, ST_SHIPPING) and (ANCHOR_DATE - o["date"]).days > 4
    ]

    return {
        "anchor_date": ANCHOR_DATE.isoformat(),
        "seed": SEED,
        "insights": {
            "mien_trung_doanh_thu_giam": {
                "mo_ta": "Doanh thu (tongTien, bỏ đơn hủy) Miền Trung 90 ngày gần nhất so với 90 ngày liền trước",
                "gan_nhat_90_ngay": mt_recent,
                "90_ngay_truoc_do": mt_prev,
                "phan_tram_thay_doi": pct_change(mt_recent, mt_prev),
                "phan_tram_thay_doi_toan_he_thong": pct_change(all_recent, all_prev),
            },
            "phu_kien_tang_dot_bien": {
                "mo_ta": "Doanh thu dòng sản phẩm danh mục Phụ kiện 60 ngày gần nhất so với 60 ngày liền trước (bỏ đơn hủy)",
                "gan_nhat_60_ngay": pk_recent,
                "60_ngay_truoc_do": pk_prev,
                "phan_tram_thay_doi": pct_change(pk_recent, pk_prev),
            },
            "san_pham_42_hoan_tien_cao": {
                "mo_ta": "Tỷ lệ đơn đã giao có hoàn tiền: đơn chứa sản phẩm 42 so với phần còn lại; điểm đánh giá trung bình",
                "san_pham_id": PLANTED_PRODUCT_ID,
                "so_don_da_giao_co_sp_42": len(with_42),
                "ty_le_hoan_sp_42": round(len(refunded_42) / len(with_42), 3) if with_42 else None,
                "ty_le_hoan_cac_don_con_lai": round(len(refunded_other) / len(without_42), 3) if without_42 else None,
                "diem_danh_gia_tb_sp_42": round(sum(r42) / len(r42), 2) if r42 else None,
                "diem_danh_gia_tb_cac_sp_khac": round(sum(rother) / len(rother), 2) if rother else None,
            },
        },
        "dirty_data": {
            "khach_hang_thieu_hoTen": sum(1 for c in customers if c["name"] is None),
            "khach_hang_thieu_email": sum(1 for c in customers if c["email"] is None),
            "khach_hang_thieu_soDienThoai": sum(1 for c in customers if c["phone"] is None),
            "khach_hang_trung_thong_tin": NUM_DUPLICATE_CUSTOMERS,
            "don_ton_dong_cu_hon_4_ngay": len(stuck),
            "don_da_huy": sum(1 for o in orders if o["status"] == ST_CANCELLED),
        },
    }


# ---------------------------------------------------------------------------
# Ghi vào database
# ---------------------------------------------------------------------------


def truncate_tables(cursor) -> None:
    cursor.execute(
        """
        TRUNCATE TABLE
            danh_gia, van_chuyen, thanh_toan, don_hang_khuyen_mai,
            chi_tiet_don_hang, don_hang, khuyen_mai, phieu_nhap, ton_kho,
            khach_hang, san_pham, danh_muc, khu_vuc
        RESTART IDENTITY CASCADE;
        """
    )


def insert_all(
    cursor,
    products: dict[int, dict],
    customers: list[dict],
    promotions: list[dict],
    orders: list[dict],
    review_rows: list[tuple],
) -> None:
    def bulk(sql: str, rows: list[tuple], page_size: int = 2000) -> None:
        if rows:
            execute_values(cursor, sql, rows, page_size=page_size)

    # Dimension
    bulk("INSERT INTO khu_vuc (id, tenKhuVuc) VALUES %s", [(REGION_ID[r], r) for r in REGIONS])
    bulk(
        "INSERT INTO danh_muc (id, tenDanhMuc) VALUES %s",
        [(CATEGORY_ID[c], c) for c in CATEGORIES],
    )
    bulk(
        "INSERT INTO san_pham (id, tenSanPham, danhMucId, giaBan, giaNhap, trangThai) VALUES %s",
        [
            (p["id"], p["name"], CATEGORY_ID[p["category"]], p["price"], p["cost"], "active")
            for p in products.values()
        ],
    )
    bulk(
        "INSERT INTO khach_hang (id, hoTen, email, soDienThoai, khuVucId, ngayDangKy, phanKhuc) VALUES %s",
        [
            (c["id"], c["name"], c["email"], c["phone"], REGION_ID[c["region"]], c["reg"], c["segment"])
            for c in customers
        ],
    )
    bulk(
        "INSERT INTO khuyen_mai (id, maKhuyenMai, moTa, phanTramGiam, ngayBatDau, ngayKetThuc) VALUES %s",
        [(p["id"], p["code"], p["desc"], p["pct"], p["start"], p["end"]) for p in promotions],
    )

    # Đơn hàng và các bảng liên quan
    bulk(
        "INSERT INTO don_hang (id, khachHangId, ngayDat, trangThai, tongTien, khuVucId, lyDoHuy) VALUES %s",
        [
            (o["id"], o["customer"]["id"], o["date"], o["status"], o["total"], REGION_ID[o["region"]], o["cancel_reason"])
            for o in orders
        ],
    )
    # thanhTien là GENERATED column: KHÔNG đưa vào INSERT
    bulk(
        "INSERT INTO chi_tiet_don_hang (donHangId, sanPhamId, soLuong, donGia) VALUES %s",
        [(o["id"], pid, qty, unit) for o in orders for pid, qty, unit in o["lines"]],
    )
    bulk(
        "INSERT INTO don_hang_khuyen_mai (donHangId, khuyenMaiId, soTienGiam) VALUES %s",
        [(o["id"], o["promo"]["id"], o["discount"]) for o in orders if o["promo"]],
    )

    payment_rows = []
    for o in orders:
        payment_rows.append(
            (o["id"], None, o["method"], o["total"], o["pay_status"], o["pay_date"], TX_PAYMENT)
        )
        if o["refund"]:
            refund_pid, amount, refund_date = o["refund"]
            payment_rows.append(
                (o["id"], refund_pid, o["method"], amount, PAY_REFUND, refund_date, TX_REFUND)
            )
    bulk(
        """INSERT INTO thanh_toan
           (donHangId, sanPhamId, phuongThuc, soTien, trangThai, ngayThanhToan, loaiGiaoDich)
           VALUES %s""",
        payment_rows,
    )

    # Trạng thái vận chuyển trùng với trạng thái đơn (cùng bộ giá trị)
    bulk(
        "INSERT INTO van_chuyen (donHangId, nhaVanChuyen, phiVanChuyen, ngayGiaoDuKien, ngayGiaoThucTe, trangThai) VALUES %s",
        [
            (o["id"], o["carrier"], o["ship_fee"], o["expected"], o["delivered_date"], o["status"])
            for o in orders
        ],
    )

    bulk(
        """INSERT INTO danh_gia (donHangId, sanPhamId, diem, binhLuan, ngayDanhGia) VALUES %s
           ON CONFLICT (donHangId, sanPhamId) DO NOTHING""",
        review_rows,
    )

    # Tồn kho và phiếu nhập
    stock_rows, purchase_rows = [], []
    snapshot_time = datetime.combine(ANCHOR_DATE, time(0, 0))
    for p in products.values():
        bucket = random.choices(["out", "low", "ok"], weights=[0.08, 0.32, 0.60])[0]
        qty = 0 if bucket == "out" else random.randint(10, 80) if bucket == "low" else random.randint(100, 800)
        stock_rows.append((p["id"], qty, snapshot_time))

        for _ in range(random.randint(2, 5)):
            purchase_rows.append(
                (
                    p["id"],
                    random.choice(["Nhà cung cấp A", "Nhà cung cấp B", "Nhà cung cấp C"]),
                    random.randint(20, 300),
                    round_k(p["cost"] * random.uniform(0.92, 1.08)),
                    START_DATE + timedelta(days=random.randint(0, NUM_DAYS - 8)),
                )
            )
    bulk("INSERT INTO ton_kho (sanPhamId, soLuongTon, capNhatLuc) VALUES %s", stock_rows)
    bulk(
        "INSERT INTO phieu_nhap (sanPhamId, nhaCungCap, soLuong, donGiaNhap, ngayNhap) VALUES %s",
        purchase_rows,
    )

    # Đồng bộ sequence vì các bảng này insert id tường minh
    for table in ("khu_vuc", "danh_muc", "san_pham", "khach_hang", "khuyen_mai", "don_hang"):
        cursor.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}), true)"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Đang sinh dữ liệu trong bộ nhớ...")
    products = build_products()
    customers = build_customers()
    promotions = build_promotions()
    orders = generate_orders(products, customers, promotions)
    review_rows = generate_reviews(orders)
    assign_segments(customers, orders)
    ground_truth = compute_ground_truth(products, customers, orders, review_rows)

    connection = psycopg2.connect(**DB_CONFIG)
    try:
        with connection:
            with connection.cursor() as cursor:
                print("Đang xóa dữ liệu cũ...")
                truncate_tables(cursor)
                print("Đang ghi vào database...")
                insert_all(cursor, products, customers, promotions, orders, review_rows)
    finally:
        connection.close()

    out_path = Path(__file__).resolve().parents[1] / "eval" / "ground_truth.json"
    out_path.write_text(json.dumps(ground_truth, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nHoàn tất sinh dữ liệu.")
    print(f"- Khách hàng: {len(customers)} (gồm {NUM_DUPLICATE_CUSTOMERS} bản ghi trùng cố ý)")
    print(f"- Sản phẩm: {len(products)}")
    print(f"- Đơn hàng: {len(orders)}")
    print(f"- Đánh giá: {len(review_rows)}")
    print(f"- Seed: {SEED}, ANCHOR_DATE: {ANCHOR_DATE}")
    print(f"- Ground truth: {out_path}")


if __name__ == "__main__":
    main()
