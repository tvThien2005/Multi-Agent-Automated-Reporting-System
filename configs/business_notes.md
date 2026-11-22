# Quy tắc nghiệp vụ

- Không tính đơn có `trangthai = 'Đã hủy'` vào doanh thu.
- `thanhtien` của `chi_tiet_don_hang` là giá trị dòng hàng trước khuyến mãi.
- `tongtien` của `don_hang` là tổng sau khuyến mãi.
- Mọi hoàn tiền nằm ở `thanh_toan` với `loaigiaodich = 'Hoàn tiền'`; `sanphamid` xác định sản phẩm được hoàn.
- Tên cột vật lý trong PostgreSQL là chữ thường vì schema DDL không dùng dấu nháy kép.
