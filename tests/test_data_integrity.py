"""Database assertions for deterministic VietReport seed data."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.db

ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_PATH = ROOT / "eval" / "ground_truth.json"

EXPECTED_ROW_COUNTS = {
    "chi_tiet_don_hang": 34_081,
    "danh_gia": 10_214,
    "danh_muc": 6,
    "don_hang": 20_000,
    "don_hang_khuyen_mai": 3_033,
    "khach_hang": 3_030,
    "khuyen_mai": 6,
    "khu_vuc": 5,
    "phieu_nhap": 545,
    "san_pham": 150,
    "thanh_toan": 20_380,
    "ton_kho": 150,
    "van_chuyen": 20_000,
}


def _scalar(connection, sql: str, params: tuple = ()):  # noqa: ANN001
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def _row(connection, sql: str, params: tuple = ()):  # noqa: ANN001
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def _ground_truth() -> dict:
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def test_seed_row_counts_match_fixed_dataset(admin_connection) -> None:
    for table, expected_count in EXPECTED_ROW_COUNTS.items():
        assert _scalar(admin_connection, f"SELECT COUNT(*) FROM {table}") == expected_count


def test_seed_status_values_and_order_total_integrity(admin_connection) -> None:
    allowed_order_statuses = {
        "Đang xử lý",
        "Đã xác nhận",
        "Đang giao hàng",
        "Đã giao hàng",
        "Đã hủy",
    }
    statuses = _scalar(
        admin_connection,
        "SELECT ARRAY_AGG(DISTINCT trangthai ORDER BY trangthai) FROM don_hang",
    )
    assert set(statuses) == allowed_order_statuses

    mismatched_totals = _scalar(
        admin_connection,
        """
        SELECT COUNT(*)
        FROM don_hang d
        LEFT JOIN (
            SELECT donhangid, SUM(thanhtien) AS line_total
            FROM chi_tiet_don_hang
            GROUP BY donhangid
        ) lines ON lines.donhangid = d.id
        LEFT JOIN (
            SELECT donhangid, SUM(sotiengiam) AS discount_total
            FROM don_hang_khuyen_mai
            GROUP BY donhangid
        ) discounts ON discounts.donhangid = d.id
        WHERE d.tongtien <> COALESCE(lines.line_total, 0) - COALESCE(discounts.discount_total, 0)
        """,
    )
    assert mismatched_totals == 0


def test_documented_dirty_data_counts_match_database(admin_connection) -> None:
    expected = _ground_truth()["dirty_data"]
    actual = {
        "khach_hang_thieu_hoTen": _scalar(admin_connection, "SELECT COUNT(*) FROM khach_hang WHERE hoten IS NULL"),
        "khach_hang_thieu_email": _scalar(admin_connection, "SELECT COUNT(*) FROM khach_hang WHERE email IS NULL"),
        "khach_hang_thieu_soDienThoai": _scalar(
            admin_connection, "SELECT COUNT(*) FROM khach_hang WHERE sodienthoai IS NULL"
        ),
        "don_ton_dong_cu_hon_4_ngay": _scalar(
            admin_connection,
            """
            SELECT COUNT(*) FROM don_hang
            WHERE trangthai IN ('Đang xử lý', 'Đang giao hàng')
              AND DATE '2026-11-12' - ngaydat > 4
            """,
        ),
        "don_da_huy": _scalar(admin_connection, "SELECT COUNT(*) FROM don_hang WHERE trangthai = 'Đã hủy'"),
    }
    for key, value in actual.items():
        assert value == expected[key]
    assert expected["khach_hang_trung_thong_tin"] == 30


def test_revenue_insights_match_ground_truth(admin_connection) -> None:
    expected = _ground_truth()["insights"]
    mien_trung = _row(
        admin_connection,
        """
        WITH revenue AS (
            SELECT
                SUM(tongtien) FILTER (WHERE ngaydat > DATE '2026-11-12' - 90) AS recent,
                SUM(tongtien) FILTER (
                    WHERE ngaydat > DATE '2026-11-12' - 180
                      AND ngaydat <= DATE '2026-11-12' - 90
                ) AS previous
            FROM don_hang d
            JOIN khu_vuc k ON k.id = d.khuvucid
            WHERE k.tenkhuvuc = 'Miền Trung' AND d.trangthai <> 'Đã hủy'
        )
        SELECT recent, previous, ROUND(100.0 * (recent - previous) / previous, 1) FROM revenue
        """,
    )
    assert [float(value) for value in mien_trung] == [
        expected["mien_trung_doanh_thu_giam"]["gan_nhat_90_ngay"],
        expected["mien_trung_doanh_thu_giam"]["90_ngay_truoc_do"],
        expected["mien_trung_doanh_thu_giam"]["phan_tram_thay_doi"],
    ]

    phu_kien = _row(
        admin_connection,
        """
        WITH revenue AS (
            SELECT
                SUM(c.thanhtien) FILTER (WHERE d.ngaydat > DATE '2026-11-12' - 60) AS recent,
                SUM(c.thanhtien) FILTER (
                    WHERE d.ngaydat > DATE '2026-11-12' - 120
                      AND d.ngaydat <= DATE '2026-11-12' - 60
                ) AS previous
            FROM chi_tiet_don_hang c
            JOIN don_hang d ON d.id = c.donhangid
            JOIN san_pham s ON s.id = c.sanphamid
            JOIN danh_muc m ON m.id = s.danhmucid
            WHERE m.tendanhmuc = 'Phụ kiện' AND d.trangthai <> 'Đã hủy'
        )
        SELECT recent, previous, ROUND(100.0 * (recent - previous) / previous, 1) FROM revenue
        """,
    )
    assert [float(value) for value in phu_kien] == [
        expected["phu_kien_tang_dot_bien"]["gan_nhat_60_ngay"],
        expected["phu_kien_tang_dot_bien"]["60_ngay_truoc_do"],
        expected["phu_kien_tang_dot_bien"]["phan_tram_thay_doi"],
    ]


def test_product_42_insight_is_present(admin_connection) -> None:
    """Verify the observable portion of the product-42 anomaly from DB facts."""
    expected = _ground_truth()["insights"]["san_pham_42_hoan_tien_cao"]
    delivered_with_42 = _scalar(
        admin_connection,
        """
        SELECT COUNT(*)
        FROM don_hang d
        WHERE d.trangthai = 'Đã giao hàng'
          AND EXISTS (
              SELECT 1 FROM chi_tiet_don_hang c
              WHERE c.donhangid = d.id AND c.sanphamid = %s
          )
        """,
        (expected["san_pham_id"],),
    )
    assert delivered_with_42 == expected["so_don_da_giao_co_sp_42"]

    ratings = _row(
        admin_connection,
        """
        SELECT
            ROUND(AVG(diem) FILTER (WHERE sanphamid = %s), 2),
            ROUND(AVG(diem) FILTER (WHERE sanphamid <> %s), 2)
        FROM danh_gia
        """,
        (expected["san_pham_id"], expected["san_pham_id"]),
    )
    assert [float(value) for value in ratings] == [
        expected["diem_danh_gia_tb_sp_42"],
        expected["diem_danh_gia_tb_cac_sp_khac"],
    ]

    refund_rates = _row(
        admin_connection,
        """
        SELECT
            ROUND(AVG((EXISTS (
                SELECT 1 FROM thanh_toan t
                WHERE t.donhangid = d.id
                  AND t.loaigiaodich = 'Hoàn tiền'
                  AND t.sanphamid = %s
            ))::int) FILTER (WHERE EXISTS (
                SELECT 1 FROM chi_tiet_don_hang c
                WHERE c.donhangid = d.id AND c.sanphamid = %s
            )), 3),
            ROUND(AVG((EXISTS (
                SELECT 1 FROM thanh_toan t
                WHERE t.donhangid = d.id AND t.loaigiaodich = 'Hoàn tiền'
            ))::int) FILTER (WHERE NOT EXISTS (
                SELECT 1 FROM chi_tiet_don_hang c
                WHERE c.donhangid = d.id AND c.sanphamid = %s
            )), 3)
        FROM don_hang d
        WHERE d.trangthai = 'Đã giao hàng'
        """,
        (expected["san_pham_id"], expected["san_pham_id"], expected["san_pham_id"]),
    )
    assert [float(value) for value in refund_rates] == [
        expected["ty_le_hoan_sp_42"],
        expected["ty_le_hoan_cac_don_con_lai"],
    ]


@pytest.mark.skipif(
    os.getenv("VIETREPORT_RUN_RESEED_TEST") != "1",
    reason="Set VIETREPORT_RUN_RESEED_TEST=1 to run this slow, destructive reproducibility check.",
)
def test_reseeding_twice_preserves_ground_truth() -> None:
    """Opt-in: generator truncates and reseeds the local database twice."""
    before = GROUND_TRUTH_PATH.read_bytes()
    for _ in range(2):
        subprocess.run([sys.executable, "db/generate_data.py"], cwd=ROOT, check=True)
    assert GROUND_TRUTH_PATH.read_bytes() == before
