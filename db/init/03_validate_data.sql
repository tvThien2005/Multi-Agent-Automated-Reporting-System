-- =============================================================================
-- Kiểm tra tính nhất quán của dữ liệu sau khi sinh.
-- Chạy: psql -f db/validate_data.sql
-- Mọi dòng có cột `so_loi` phải bằng 0.
-- =============================================================================

SELECT 'tongTien khong khop chi tiet/khuyen mai' AS kiem_tra, COUNT(*) AS so_loi
FROM don_hang dh
LEFT JOIN (SELECT donHangId, SUM(thanhTien) s FROM chi_tiet_don_hang GROUP BY donHangId) i ON i.donHangId = dh.id
LEFT JOIN (SELECT donHangId, SUM(soTienGiam) d FROM don_hang_khuyen_mai GROUP BY donHangId) p ON p.donHangId = dh.id
WHERE dh.tongTien <> COALESCE(i.s, 0) - COALESCE(p.d, 0)

UNION ALL
SELECT 'don khong co chi tiet', COUNT(*)
FROM don_hang dh
WHERE NOT EXISTS (SELECT 1 FROM chi_tiet_don_hang c WHERE c.donHangId = dh.id)

UNION ALL
SELECT 'khuyen mai ap ngoai thoi gian hieu luc', COUNT(*)
FROM don_hang_khuyen_mai x
JOIN don_hang dh ON dh.id = x.donHangId
JOIN khuyen_mai km ON km.id = x.khuyenMaiId
WHERE dh.ngayDat NOT BETWEEN km.ngayBatDau AND km.ngayKetThuc

UNION ALL
SELECT 'don dat truoc ngay dang ky cua khach', COUNT(*)
FROM don_hang dh JOIN khach_hang kh ON kh.id = dh.khachHangId
WHERE dh.ngayDat < kh.ngayDangKy

UNION ALL
SELECT 'ngay giao/thanh toan o tuong lai (so voi 2026-11-12)', COUNT(*)
FROM (
    SELECT ngayGiaoThucTe AS d FROM van_chuyen
    UNION ALL SELECT ngayThanhToan FROM thanh_toan
    UNION ALL SELECT ngayDanhGia FROM danh_gia
) t
WHERE d > DATE '2026-11-12'

UNION ALL
SELECT 'trang thai van chuyen khac trang thai don', COUNT(*)
FROM don_hang dh JOIN van_chuyen vc ON vc.donHangId = dh.id
WHERE dh.trangThai <> vc.trangThai

UNION ALL
SELECT 'don da giao thieu ngay giao thuc te, hoac don chua giao co ngay giao', COUNT(*)
FROM don_hang dh JOIN van_chuyen vc ON vc.donHangId = dh.id
WHERE (dh.trangThai = 'Đã giao hàng' AND vc.ngayGiaoThucTe IS NULL)
   OR (dh.trangThai <> 'Đã giao hàng' AND vc.ngayGiaoThucTe IS NOT NULL)

UNION ALL
SELECT 'don huy thieu ly do, hoac don khac huy co ly do', COUNT(*)
FROM don_hang
WHERE (trangThai = 'Đã hủy' AND lyDoHuy IS NULL)
   OR (trangThai <> 'Đã hủy' AND lyDoHuy IS NOT NULL)

UNION ALL
SELECT 'don huy nhung co thanh toan thanh cong', COUNT(*)
FROM don_hang dh JOIN thanh_toan tt ON tt.donHangId = dh.id
WHERE dh.trangThai = 'Đã hủy' AND tt.trangThai = 'Thành công'

UNION ALL
SELECT 'hoan tien lon hon so tien da tra', COUNT(*)
FROM thanh_toan r
JOIN thanh_toan p ON p.donHangId = r.donHangId AND p.loaiGiaoDich = 'Thanh toán'
WHERE r.loaiGiaoDich = 'Hoàn tiền' AND r.soTien > p.soTien

UNION ALL
SELECT 'danh gia cho don chua giao', COUNT(*)
FROM danh_gia g JOIN don_hang dh ON dh.id = g.donHangId
WHERE dh.trangThai <> 'Đã giao hàng'

UNION ALL
SELECT 'danh gia truoc ngay giao hang', COUNT(*)
FROM danh_gia g JOIN van_chuyen vc ON vc.donHangId = g.donHangId
WHERE g.ngayDanhGia <= vc.ngayGiaoThucTe

UNION ALL
SELECT 'san pham trong chi tiet khong thuoc don (trung dong san pham trong 1 don)', COUNT(*)
FROM (SELECT donHangId, sanPhamId FROM chi_tiet_don_hang GROUP BY 1, 2 HAVING COUNT(*) > 1) t;

-- -----------------------------------------------------------------------------
-- Kiểm chứng planted insights (so sánh với db/ground_truth.json)
-- -----------------------------------------------------------------------------

-- 1. Doanh thu Miền Trung: 90 ngày gần nhất so với 90 ngày trước đó
SELECT
    SUM(CASE WHEN dh.ngayDat >  DATE '2026-11-12' - 90  THEN dh.tongTien END) AS gan_nhat_90_ngay,
    SUM(CASE WHEN dh.ngayDat >  DATE '2026-11-12' - 180
              AND dh.ngayDat <= DATE '2026-11-12' - 90  THEN dh.tongTien END) AS truoc_do_90_ngay
FROM don_hang dh JOIN khu_vuc kv ON kv.id = dh.khuVucId
WHERE kv.tenKhuVuc = 'Miền Trung' AND dh.trangThai <> 'Đã hủy';

-- 2. Doanh thu dòng sản phẩm Phụ kiện: 60 ngày gần nhất so với 60 ngày trước đó
SELECT
    SUM(CASE WHEN dh.ngayDat >  DATE '2026-11-12' - 60  THEN c.thanhTien END) AS gan_nhat_60_ngay,
    SUM(CASE WHEN dh.ngayDat >  DATE '2026-11-12' - 120
              AND dh.ngayDat <= DATE '2026-11-12' - 60  THEN c.thanhTien END) AS truoc_do_60_ngay
FROM chi_tiet_don_hang c
JOIN don_hang dh ON dh.id = c.donHangId
JOIN san_pham sp ON sp.id = c.sanPhamId
JOIN danh_muc dm ON dm.id = sp.danhMucId
WHERE dm.tenDanhMuc = 'Phụ kiện' AND dh.trangThai <> 'Đã hủy';

-- 3. Tỷ lệ hoàn tiền đúng sản phẩm 42 so với hoàn tiền của các đơn còn lại.
WITH delivered AS (
    SELECT
        dh.id,
        EXISTS (
            SELECT 1 FROM chi_tiet_don_hang c
            WHERE c.donHangId = dh.id AND c.sanPhamId = 42
        ) AS co_sp_42
    FROM don_hang dh
    WHERE dh.trangThai = 'Đã giao hàng'
)
SELECT
    COUNT(*) FILTER (WHERE co_sp_42) AS so_don_da_giao_co_sp_42,
    ROUND(AVG((EXISTS (
        SELECT 1 FROM thanh_toan t
        WHERE t.donHangId = d.id
          AND t.loaiGiaoDich = 'Hoàn tiền'
          AND t.sanPhamId = 42
    ))::int) FILTER (WHERE co_sp_42), 3) AS ty_le_hoan_sp_42,
    ROUND(AVG((EXISTS (
        SELECT 1 FROM thanh_toan t
        WHERE t.donHangId = d.id AND t.loaiGiaoDich = 'Hoàn tiền'
    ))::int) FILTER (WHERE NOT co_sp_42), 3) AS ty_le_hoan_cac_don_con_lai
FROM delivered d;
