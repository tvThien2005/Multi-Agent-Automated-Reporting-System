-- =============================================================================
-- E-commerce DATABASE SCHEMA
-- Mục đích: Giả lập dữ liệu cho dự án Multi-agent Automated Reporting
-- CSDL: PostgreSQL 16
-- Encoding: UTF-8
-- Quy ước đặt tên:
--   - Bảng/cột: camelCase (theo yêu cầu nghiệp vụ VN)
--   - Index: idx_<bảng>_<cột>
--   - View:  v_<mô_tả>
-- Ngày tạo: 2026-11-12
-- =============================================================================


-- =============================================================================
-- NHÓM 1: BẢNG DANH MỤC (DIMENSION) — dữ liệu ít thay đổi, dùng để join
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Bảng: khu_vuc
-- Mục đích: Danh mục vùng/khu vực địa lý (Bắc/Trung/Nam, hoặc theo tỉnh/thành).
--           Dùng để phân tích doanh thu, khách hàng, đơn hàng theo khu vực.
-- Lưu ý: tenKhuVuc là UNIQUE — không cho phép 2 khu vực trùng tên.
-- -----------------------------------------------------------------------------
CREATE TABLE khu_vuc (
    id SERIAL PRIMARY KEY,       
    tenKhuVuc VARCHAR(100) NOT NULL UNIQUE -- Tên khu vực (VD: 'Miền Bắc', 'Hà Nội', ...)
);

COMMENT ON TABLE khu_vuc IS 'Danh mục khu vực địa lý. Dùng làm dimension cho báo cáo doanh thu/khách hàng theo vùng.';
COMMENT ON COLUMN khu_vuc.id IS 'Khóa chính, tự tăng.';
COMMENT ON COLUMN khu_vuc.tenKhuVuc IS 'Tên khu vực, duy nhất (UNIQUE). VD: Miền Bắc, Miền Trung, Miền Nam, Hà Nội, TP.HCM...';


-- -----------------------------------------------------------------------------
-- Bảng: danh_muc
-- Mục đích: Danh mục ngành hàng của sản phẩm (VD: Điện tử, Thời trang, Gia dụng).
--           Dùng để nhóm sản phẩm trong báo cáo top danh mục / doanh thu theo ngành hàng.
-- -----------------------------------------------------------------------------
CREATE TABLE danh_muc (
    id SERIAL PRIMARY KEY, 
    tenDanhMuc VARCHAR(100) NOT NULL UNIQUE -- Tên danh mục, duy nhất
);

COMMENT ON TABLE  danh_muc             IS 'Danh mục ngành hàng của sản phẩm. Dimension cho báo cáo doanh thu theo ngành.';
COMMENT ON COLUMN danh_muc.id          IS 'Khóa chính, tự tăng.';
COMMENT ON COLUMN danh_muc.tenDanhMuc  IS 'Tên danh mục, duy nhất. VD: Điện tử, Thời trang, Gia dụng, Mỹ phẩm...';

-- =============================================================================
-- NHÓM 2: BẢNG THỰC THỂ CHÍNH (MASTER DATA)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Bảng: san_pham
-- Mục đích: Danh mục sản phẩm đang kinh doanh.
-- Lưu ý quan trọng:
--   - giaBan  = giá bán hiện tại (có thể thay đổi theo thời gian)
--   - giaNhap = giá nhập hiện tại (có thể thay đổi theo thời gian)
--   => KHÔNG dùng giaNhap/giaBan để tính COGS/doanh thu LỊCH SỬ.
--      Dùng chi_tiet_don_hang.donGia (snapshot giá lúc bán) thay thế.
-- -----------------------------------------------------------------------------
CREATE TABLE san_pham (
    id SERIAL PRIMARY KEY,                          
    tenSanPham  VARCHAR(200)  NOT NULL, 
    danhMucId INT NOT NULL REFERENCES danh_muc(id),     -- FK → danh_muc
    giaBan NUMERIC(12,2) NOT NULL CHECK (giaBan  >= 0),  -- Giá bán hiện tại (VNĐ)
    giaNhap NUMERIC(12,2) NOT NULL CHECK (giaNhap >= 0), -- Giá nhập hiện tại (VNĐ)
    trangThai VARCHAR(20) NOT NULL DEFAULT 'active'  -- Trạng thái kinh doanh
);

COMMENT ON TABLE  san_pham            IS 'Danh mục sản phẩm. Dimension cho báo cáo top sản phẩm, doanh thu theo sản phẩm.';
COMMENT ON COLUMN san_pham.tenSanPham IS 'Tên sản phẩm hiển thị.';
COMMENT ON COLUMN san_pham.danhMucId  IS 'FK → danh_muc.id. Danh mục ngành hàng của sản phẩm.';
COMMENT ON COLUMN san_pham.giaBan     IS 'Giá bán HIỆN TẠI (VNĐ). KHÔNG dùng để tính doanh thu lịch sử — dùng chi_tiet_don_hang.donGia.';
COMMENT ON COLUMN san_pham.giaNhap    IS 'Giá nhập HIỆN TẠI (VNĐ). KHÔNG dùng để tính COGS lịch sử — xem phieu_nhap để lấy giá vốn đúng thời điểm.';
COMMENT ON COLUMN san_pham.trangThai  IS 'Trạng thái kinh doanh. Giá trị hợp lệ: active | inactive | discontinued (ngừng bán).';


-- -----------------------------------------------------------------------------
-- Bảng: khach_hang
-- Mục đích: Thông tin khách hàng (master data).
-- phanKhuc = phân khúc khách (Silver/Gold/Platinum...) do hệ thống CRM gán.
-- Dùng cho báo cáo RFM, phân tích theo hạng khách.
-- -----------------------------------------------------------------------------
CREATE TABLE khach_hang (
    id SERIAL PRIMARY KEY,  
    hoTen VARCHAR(200),                              -- Họ tên (có thể NULL nếu đăng ký bằng SĐT)
    email VARCHAR(200),                              -- Email liên hệ
    soDienThoai VARCHAR(20),                         -- Số điện thoại liên hệ
    khuVucId INT REFERENCES khu_vuc(id),             -- FK → khu_vuc (địa chỉ khách)
    ngayDangKy DATE NOT NULL,                        -- Ngày đăng ký tài khoản
    phanKhuc VARCHAR(30)                             -- Phân khúc khách hàng VD: Silver | Gold | Platinum | VIP | New | Inactive.
);


-- -----------------------------------------------------------------------------
-- Bảng: khuyen_mai
-- Mục đích: Chương trình khuyến mãi (promotion).
-- Lưu ý:
--   - ngayBatDau <= ngayKetThuc (ràng buộc check).
--   - Liên kết với đơn hàng qua bảng don_hang_khuyen_mai.
-- -----------------------------------------------------------------------------
CREATE TABLE khuyen_mai (
    id SERIAL PRIMARY KEY, -- Khóa chính
    maKhuyenMai VARCHAR(50)  NOT NULL UNIQUE,               -- Mã khuyến mãi (VD: TET2026, BLACKFRIDAY)
    moTa TEXT,                                              -- Mô tả chi tiết chương trình
    phanTramGiam  NUMERIC(5,2) NOT NULL CHECK (phanTramGiam BETWEEN 0 AND 100),  -- % giảm giá
    ngayBatDau DATE  NOT NULL,                             -- Ngày bắt đầu hiệu lực
    ngayKetThuc DATE NOT NULL,                             -- Ngày kết thúc hiệu lực
    CONSTRAINT chk_khuyen_mai_ngay CHECK (ngayKetThuc >= ngayBatDau)
);


-- =============================================================================
-- NHÓM 3: BẢNG GIAO DỊCH (TRANSACTION) — dữ liệu phát sinh, dùng để phân tích
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Bảng: don_hang
-- Mục đích: Đơn hàng — bảng trung tâm (fact table) của hệ thống.
-- Lưu ý quan trọng:
--   - tongTien là DERIVED từ SUM(chi_tiet_don_hang.thanhTien) - SUM(don_hang_khuyen_mai.soTienGiam).
--   - Đơn bị HỦY (trangThai = 'Đã hủy') phải được LOẠI TRỪ khỏi báo cáo doanh thu.
--   - lyDoHuy dùng cho báo cáo top lý do hủy đơn.
-- -----------------------------------------------------------------------------
CREATE TABLE don_hang (
    id SERIAL PRIMARY KEY,                          
    khachHangId INT NOT NULL REFERENCES khach_hang(id),  -- FK → khach_hang
    ngayDat DATE NOT NULL, -- Ngày đặt hàng
    trangThai VARCHAR(30) NOT NULL,    -- Trạng thái đơn
    tongTien NUMERIC(14,2) NOT NULL DEFAULT 0, -- Tổng tiền sau Khuyến Mãi (VNĐ)
    khuVucId INT REFERENCES khu_vuc(id),       -- FK → khu_vuc (địa chỉ giao hàng)
    lyDoHuy VARCHAR(200)                       -- Lý do hủy (chỉ có giá trị nếu trangThai='Đã hủy')
);


COMMENT ON COLUMN don_hang.trangThai    IS 'Trạng thái đơn. Giá trị hợp lệ: Đang xử lý | Đã xác nhận | Đang giao hàng | Đã giao hàng | Đã hủy. KHÔNG tính doanh thu cho đơn Đã hủy.';
COMMENT ON COLUMN don_hang.tongTien     IS 'Tổng tiền cuối cùng sau khuyến mãi (VNĐ). Là derived column — cần đảm bảo sync với chi_tiet_don_hang và don_hang_khuyen_mai.';
COMMENT ON COLUMN don_hang.khuVucId     IS 'FK → khu_vuc.id. Khu vực nhận hàng — dùng cho báo cáo doanh thu theo vùng.';
COMMENT ON COLUMN don_hang.lyDoHuy      IS 'Lý do hủy đơn (NULL nếu đơn không bị hủy). Dùng cho báo cáo top lý do hủy.';


-- -----------------------------------------------------------------------------
-- Bảng: don_hang_khuyen_mai
-- Mục đích: Liên kết N-N giữa đơn hàng và khuyến mãi (1 đơn có thể áp nhiều KM).
-- Lưu ý: soTienGiam là snapshot số tiền giảm THỰC TẾ của KM đó trên đơn này
--        (không phải luôn = tongTien * phanTramGiam vì có thể có giới hạn/stacking).
-- -----------------------------------------------------------------------------
CREATE TABLE don_hang_khuyen_mai (
    donHangId INT NOT NULL REFERENCES don_hang(id)   ON DELETE CASCADE,
    khuyenMaiId INT NOT NULL REFERENCES khuyen_mai(id),
    soTienGiam NUMERIC(14,2) NOT NULL CHECK (soTienGiam >= 0), -- Số tiền giảm thực tế của KM này trên đơn
    PRIMARY KEY (donHangId, khuyenMaiId)                       -- Composite PK, chống trùng lặp
);

COMMENT ON TABLE  don_hang_khuyen_mai              IS 'Liên kết đơn hàng ↔ khuyến mãi (N-N). Dùng cho báo cáo hiệu quả KM, ROI từng chương trình.';
COMMENT ON COLUMN don_hang_khuyen_mai.donHangId    IS 'FK → don_hang.id. Xóa đơn → tự động xóa liên kết (CASCADE).';
COMMENT ON COLUMN don_hang_khuyen_mai.khuyenMaiId  IS 'FK → khuyen_mai.id.';
COMMENT ON COLUMN don_hang_khuyen_mai.soTienGiam   IS 'Số tiền giảm THỰC TẾ của KM này áp lên đơn (VNĐ). Có thể khác phanTramGiam * tongTien nếu có stacking/giới hạn.';


-- -----------------------------------------------------------------------------
-- Bảng: chi_tiet_don_hang
-- Mục đích: Chi tiết từng dòng sản phẩm trong đơn (line items).
-- Lưu ý quan trọng:
--   - donGia là SNAPSHOT giá bán tại thời điểm đặt — KHÔNG đổi khi san_pham.giaBan thay đổi.
--   - thanhTien là GENERATED COLUMN (= soLuong * donGia), DB tự tính — không thể insert sai.
--   - Đây là nguồn dữ liệu CHÍNH XÁC NHẤT cho doanh thu theo sản phẩm.
-- -----------------------------------------------------------------------------
CREATE TABLE chi_tiet_don_hang (
    id BIGSERIAL PRIMARY KEY,                           
    donHangId INT NOT NULL REFERENCES don_hang(id) ON DELETE CASCADE,
    sanPhamId INT NOT NULL REFERENCES san_pham(id),
    soLuong INT NOT NULL CHECK (soLuong > 0),          -- Số lượng mua (phải > 0)
    donGia NUMERIC(12,2) NOT NULL CHECK (donGia >= 0), -- Đơn giá SNAPSHOT tại thời điểm đặt
    thanhTien NUMERIC(14,2) GENERATED ALWAYS AS (soLuong * donGia) STORED
);

COMMENT ON TABLE  chi_tiet_don_hang            IS 'Chi tiết dòng sản phẩm trong đơn. Nguồn dữ liệu CHÍNH XÁC cho doanh thu theo sản phẩm.';
COMMENT ON COLUMN chi_tiet_don_hang.donHangId  IS 'FK → don_hang.id. Xóa đơn → tự động xóa dòng chi tiết (CASCADE).';
COMMENT ON COLUMN chi_tiet_don_hang.sanPhamId  IS 'FK → san_pham.id.';
COMMENT ON COLUMN chi_tiet_don_hang.soLuong    IS 'Số lượng sản phẩm mua. Phải > 0.';
COMMENT ON COLUMN chi_tiet_don_hang.donGia     IS 'Đơn giá SNAPSHOT tại thời điểm đặt hàng (VNĐ). KHÔNG phải giá hiện tại của san_pham.';
COMMENT ON COLUMN chi_tiet_don_hang.thanhTien  IS 'Thành tiền = soLuong * donGia. GENERATED ALWAYS — DB tự tính, không insert tay.';


-- -----------------------------------------------------------------------------
-- Bảng: thanh_toan
-- Mục đích: Giao dịch thanh toán / hoàn tiền của đơn hàng.
-- Lưu ý:
--   - 1 đơn có thể có NHIỀU giao dịch (trả trước, trả sau, hoàn tiền...).
--   - loaiGiaoDich phân biệt 'Thanh toán' vs 'Hoàn tiền'.
--   - Muốn tính "đã thanh toán đủ chưa": SUM(soTien WHERE loaiGiaoDich='Thanh toán' AND trangThai='Thành công').
-- -----------------------------------------------------------------------------
CREATE TABLE thanh_toan (
    id             BIGSERIAL     PRIMARY KEY,                       -- Khóa chính
    donHangId      INT           NOT NULL REFERENCES don_hang(id) ON DELETE CASCADE,
    phuongThuc     VARCHAR(30)   NOT NULL,                          -- Phương thức thanh toán
    soTien         NUMERIC(14,2) NOT NULL,                          -- Số tiền giao dịch (VNĐ)
    trangThai      VARCHAR(30)   NOT NULL,                          -- Trạng thái giao dịch
    ngayThanhToan  DATE,                                            -- Ngày giao dịch (NULL nếu chưa hoàn tất)
    loaiGiaoDich   VARCHAR(20)   NOT NULL DEFAULT 'Thanh toán'      -- Loại giao dịch
);

COMMENT ON TABLE  thanh_toan                IS 'Giao dịch thanh toán/hoàn tiền. 1 đơn có thể có nhiều giao dịch.';
COMMENT ON COLUMN thanh_toan.id             IS 'Khóa chính, BIGSERIAL.';
COMMENT ON COLUMN thanh_toan.donHangId      IS 'FK → don_hang.id. Xóa đơn → tự động xóa giao dịch (CASCADE).';
COMMENT ON COLUMN thanh_toan.phuongThuc     IS 'Phương thức thanh toán. VD: COD | Chuyển khoản | Momo | VNPay | Thẻ tín dụng.';
COMMENT ON COLUMN thanh_toan.soTien         IS 'Số tiền giao dịch (VNĐ).';
COMMENT ON COLUMN thanh_toan.trangThai      IS 'Trạng thái giao dịch. Giá trị hợp lệ: Chờ xử lý | Thành công | Thất bại | Hoàn tiền.';
COMMENT ON COLUMN thanh_toan.ngayThanhToan  IS 'Ngày giao dịch hoàn tất. NULL nếu giao dịch chưa hoàn tất.';
COMMENT ON COLUMN thanh_toan.loaiGiaoDich   IS 'Loại giao dịch. Giá trị hợp lệ: Thanh toán | Hoàn tiền | Điều chỉnh.';


-- -----------------------------------------------------------------------------
-- Bảng: van_chuyen
-- Mục đích: Thông tin vận chuyển của đơn — dùng tính SLA, lead time, phí ship.
-- Lưu ý: on-time delivery = ngayGiaoThucTe <= ngayGiaoDuKien.
-- -----------------------------------------------------------------------------
CREATE TABLE van_chuyen (
    id              BIGSERIAL     PRIMARY KEY,                      -- Khóa chính
    donHangId       INT           NOT NULL REFERENCES don_hang(id) ON DELETE CASCADE,
    nhaVanChuyen    VARCHAR(50),                                    -- Đơn vị vận chuyển
    phiVanChuyen    NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (phiVanChuyen >= 0),
    ngayGiaoDuKien  DATE,                                           -- Ngày giao dự kiến
    ngayGiaoThucTe  DATE,                                           -- Ngày giao thực tế
    trangThai       VARCHAR(30)   NOT NULL                          -- Trạng thái vận chuyển
);

COMMENT ON TABLE  van_chuyen                  IS 'Thông tin vận chuyển. Dùng tính SLA, on-time rate, lead time, chi phí ship theo đơn vị.';
COMMENT ON COLUMN van_chuyen.id               IS 'Khóa chính, BIGSERIAL.';
COMMENT ON COLUMN van_chuyen.donHangId        IS 'FK → don_hang.id. Xóa đơn → tự động xóa vận chuyển (CASCADE).';
COMMENT ON COLUMN van_chuyen.nhaVanChuyen     IS 'Đơn vị vận chuyển. VD: GHN | GHTK | Viettel Post | J&T.';
COMMENT ON COLUMN van_chuyen.phiVanChuyen     IS 'Phí vận chuyển (VNĐ).';
COMMENT ON COLUMN van_chuyen.ngayGiaoDuKien   IS 'Ngày giao hàng dự kiến.';
COMMENT ON COLUMN van_chuyen.ngayGiaoThucTe   IS 'Ngày giao hàng thực tế (NULL nếu chưa giao).';
COMMENT ON COLUMN van_chuyen.trangThai        IS 'Trạng thái vận chuyển. Giá trị hợp lệ: Dang xử lý | Đã xác nhận | Đang giao hàng | Đã giao hàng | Đã hủy.';


-- -----------------------------------------------------------------------------
-- Bảng: danh_gia
-- Mục đích: Đánh giá sản phẩm của khách sau khi mua.
-- Lưu ý: 1 khách / 1 đơn / 1 sản phẩm thường chỉ đánh giá 1 lần — nên có UNIQUE.
-- -----------------------------------------------------------------------------
CREATE TABLE danh_gia (
    id           BIGSERIAL   PRIMARY KEY,                     
    donHangId    INT         NOT NULL REFERENCES don_hang(id) ON DELETE CASCADE,
    sanPhamId    INT         NOT NULL REFERENCES san_pham(id),
    diem         INT         NOT NULL CHECK (diem BETWEEN 1 AND 5), -- Điểm 1-5 sao
    binhLuan     TEXT,                                              -- Nội dung bình luận
    ngayDanhGia  DATE        NOT NULL                               -- Ngày đánh giá
);

COMMENT ON TABLE  danh_gia              IS 'Đánh giá sản phẩm sau mua. Dùng báo cáo CSAT, NPS, sentiment, top sản phẩm rating cao/thấp.';
COMMENT ON COLUMN danh_gia.id           IS 'Khóa chính, BIGSERIAL.';
COMMENT ON COLUMN danh_gia.donHangId    IS 'FK → don_hang.id. Xóa đơn → tự động xóa đánh giá (CASCADE).';
COMMENT ON COLUMN danh_gia.sanPhamId    IS 'FK → san_pham.id. Sản phẩm được đánh giá.';
COMMENT ON COLUMN danh_gia.diem         IS 'Điểm đánh giá 1-5 sao.';
COMMENT ON COLUMN danh_gia.binhLuan     IS 'Nội dung bình luận (text tự do).';
COMMENT ON COLUMN danh_gia.ngayDanhGia  IS 'Ngày đánh giá.';


-- =============================================================================
-- NHÓM 4: BẢNG TỒN KHO / NHẬP HÀNG
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Bảng: ton_kho
-- Mục đích: Số lượng tồn kho HIỆN TẠI của từng sản phẩm (snapshot).
-- Lưu ý: Bảng này chỉ lưu trạng thái hiện tại — muốn xem lịch sử tồn kho
--        phải dùng phieu_nhap + chi_tiet_don_hang để dựng lại.
-- -----------------------------------------------------------------------------
CREATE TABLE ton_kho (
    sanPhamId    INT         PRIMARY KEY REFERENCES san_pham(id) ON DELETE CASCADE,
    soLuongTon   INT         NOT NULL DEFAULT 0 CHECK (soLuongTon >= 0),
    capNhatLuc   TIMESTAMP   NOT NULL DEFAULT NOW()                 -- Thời điểm cập nhật gần nhất
);

COMMENT ON TABLE  ton_kho              IS 'Tồn kho HIỆN TẠI của từng sản phẩm. Dùng báo cáo sắp hết hàng, giá trị tồn kho.';
COMMENT ON COLUMN ton_kho.sanPhamId    IS 'Khóa chính = FK → san_pham.id. Mỗi sản phẩm có tối đa 1 dòng tồn kho.';
COMMENT ON COLUMN ton_kho.soLuongTon   IS 'Số lượng tồn hiện tại. Phải >= 0.';
COMMENT ON COLUMN ton_kho.capNhatLuc   IS 'Thời điểm cập nhật số lượng tồn gần nhất.';


-- -----------------------------------------------------------------------------
-- Bảng: phieu_nhap
-- Mục đích: Lịch sử nhập hàng — nguồn dữ liệu để tính giá vốn (COGS) lịch sử chính xác.
-- Lưu ý: donGiaNhap ở đây là SNAPSHOT giá nhập tại thời điểm nhập,
--        khác với san_pham.giaNhap (giá hiện tại).
-- -----------------------------------------------------------------------------
CREATE TABLE phieu_nhap (
    id            BIGSERIAL     PRIMARY KEY,                        -- Khóa chính
    sanPhamId     INT           NOT NULL REFERENCES san_pham(id),
    nhaCungCap    VARCHAR(100),                                     -- Nhà cung cấp
    soLuong       INT           NOT NULL CHECK (soLuong > 0),       -- Số lượng nhập
    donGiaNhap    NUMERIC(12,2) NOT NULL CHECK (donGiaNhap >= 0),   -- Đơn giá nhập SNAPSHOT
    ngayNhap      DATE          NOT NULL                            -- Ngày nhập hàng
);

COMMENT ON TABLE  phieu_nhap              IS 'Lịch sử nhập hàng. Dùng tính giá vốn (COGS) lịch sử, báo cáo nhập hàng theo NCC/tháng.';
COMMENT ON COLUMN phieu_nhap.id           IS 'Khóa chính, BIGSERIAL.';
COMMENT ON COLUMN phieu_nhap.sanPhamId    IS 'FK → san_pham.id. Sản phẩm được nhập.';
COMMENT ON COLUMN phieu_nhap.nhaCungCap   IS 'Tên nhà cung cấp.';
COMMENT ON COLUMN phieu_nhap.soLuong      IS 'Số lượng nhập. Phải > 0.';
COMMENT ON COLUMN phieu_nhap.donGiaNhap   IS 'Đơn giá nhập SNAPSHOT tại thời điểm nhập (VNĐ).';
COMMENT ON COLUMN phieu_nhap.ngayNhap     IS 'Ngày nhập hàng.';


-- =============================================================================
-- NHÓM 5: INDEX — tăng tốc truy vấn cho báo cáo
-- =============================================================================
-- Nguyên tắc:
--   - Mọi cột FK nên có index (Postgres KHÔNG tự tạo) → tránh full-scan khi CASCADE.
--   - Cột thường dùng trong WHERE/JOIN/ORDER BY của báo cáo.
--   - Composite index cho các query phổ biến (báo cáo theo thời gian + chiều khác).

-- Index cho bảng khu_vuc / danh_muc: không cần thêm vì bảng nhỏ, đã có UNIQUE.

-- Index cho san_pham
CREATE INDEX idx_san_pham_danh_muc   ON san_pham(danhMucId);

-- Index cho khach_hang
CREATE INDEX idx_khach_hang_khu_vuc  ON khach_hang(khuVucId);

-- Index cho don_hang
CREATE INDEX idx_don_hang_ngay_dat      ON don_hang(ngayDat);
CREATE INDEX idx_don_hang_khach_hang    ON don_hang(khachHangId);
CREATE INDEX idx_don_hang_khu_vuc       ON don_hang(khuVucId);
-- Composite index phục vụ báo cáo RFM / retention (khách + ngày)
CREATE INDEX idx_don_hang_kh_ngay       ON don_hang(khachHangId, ngayDat DESC);
-- Composite index phục vụ báo cáo doanh thu theo ngày + trạng thái
CREATE INDEX idx_don_hang_ngay_trangthai ON don_hang(ngayDat, trangThai);

-- Index cho don_hang_khuyen_mai
CREATE INDEX idx_dhkm_km                ON don_hang_khuyen_mai(khuyenMaiId);

-- Index cho chi_tiet_don_hang
CREATE INDEX idx_chi_tiet_don_hang_san_pham  ON chi_tiet_don_hang(sanPhamId);
CREATE INDEX idx_chi_tiet_don_hang_don_hang  ON chi_tiet_don_hang(donHangId);

-- Index cho thanh_toan
CREATE INDEX idx_thanh_toan_don_hang    ON thanh_toan(donHangId);
CREATE INDEX idx_thanh_toan_ngay        ON thanh_toan(ngayThanhToan);

-- Index cho van_chuyen
CREATE INDEX idx_van_chuyen_don_hang    ON van_chuyen(donHangId);
CREATE INDEX idx_van_chuyen_ngay_giao   ON van_chuyen(ngayGiaoThucTe);

-- Index cho danh_gia
CREATE INDEX idx_danh_gia_don_hang      ON danh_gia(donHangId);
CREATE INDEX idx_danh_gia_san_pham      ON danh_gia(sanPhamId);
CREATE INDEX idx_danh_gia_ngay          ON danh_gia(ngayDanhGia);
-- Chống 1 khách đánh giá trùng 1 sản phẩm trong cùng 1 đơn
CREATE UNIQUE INDEX uq_danh_gia_don_sp  ON danh_gia(donHangId, sanPhamId);

-- Index cho phieu_nhap
CREATE INDEX idx_phieu_nhap_san_pham    ON phieu_nhap(sanPhamId);
CREATE INDEX idx_phieu_nhap_ngay        ON phieu_nhap(ngayNhap);
CREATE INDEX idx_phieu_nhap_ncc         ON phieu_nhap(nhaCungCap);

