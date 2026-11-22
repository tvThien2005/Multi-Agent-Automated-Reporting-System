# Hướng Dẫn Cài Đặt và Khởi Chạy Dự Án (VietReport)

Dự án **Multi-Agent Automated Reporting System** sử dụng kiến trúc Multi-Agent để tự động tạo báo cáo từ cơ sở dữ liệu thương mại điện tử PostgreSQL.

Tài liệu này hướng dẫn chi tiết các bước thiết lập môi trường và khởi chạy cơ sở dữ liệu trên máy cá nhân sau khi clone source code về.

---

## 1. Yêu Cầu Tiên Quyết (Prerequisites)

Trước khi bắt đầu, hãy đảm bảo máy tính đã cài đặt:

* **[Docker](https://www.docker.com/)** & **Docker Compose** (Docker Desktop đang chạy).
* **[Python 3.10+](https://www.python.org/)** và công cụ quản lý gói `pip`.
* **Git**.

---

## 2. Quy Trình Khởi Chạy Từng Bước

### Bước 1: Clone repository và mở thư mục dự án

```bash
git clone <URL_REPO_CUA_BAN>
cd "Multi-Agent Automated Reporting System"
```

---

### Bước 2: Thiết lập file môi trường `.env`

Dự án sử dụng file `.env` để cấu hình kết nối database và các API key cho Agent. File `.env` chứa thông tin nhạy cảm nên không được commit lên GitHub.

Hãy sao chép file cấu hình mẫu `.env.example` thành `.env`:

* **Trên Windows PowerShell:**
  ```powershell
  Copy-Item .env.example .env
  ```
* **Trên Linux / macOS / Git Bash:**
  ```bash
  cp .env.example .env
  ```

> ⚠️ **Lưu ý:** Mở file `.env` vừa tạo để kiểm tra các thông số kết nối Database (đã được cấu hình mặc định khớp với Docker) và điền các API Key của LLMs (nếu chạy phần Agent).

---

### Bước 3: Khởi động Database PostgreSQL qua Docker

Chạy lệnh sau tại thư mục gốc của dự án:

```bash
docker compose up -d
```

#### 🔍 Quá trình khởi tạo tự động của Docker:
Thư mục `db/init/` được ánh xạ trực tiếp vào thư mục khởi tạo của container (`/docker-entrypoint-initdb.d/`). Khi container khởi động lần đầu tiên, PostgreSQL sẽ tự động chạy:
1. `01_schema.sql`: Khởi tạo toàn bộ 11 bảng, khóa chính, khóa ngoại, view và index.
2. `02_roles.sql`: Tạo tài khoản phân quyền `vietreport_reader` với quyền **Read-Only** và giới hạn timeout (10s) dành riêng cho SQL Agent.

Kiểm tra trạng thái container:
```bash
docker ps
```
Khi container `vietreport_postgres` có trạng thái **`Up`** (hoặc `healthy`), Database đã sẵn sàng đón kết nối.

---

### Bước 4: Cài đặt thư viện Python & Sinh dữ liệu mô phỏng (Data Seeding)

Dữ liệu mô phỏng được sinh thông qua script Python với **seed cố định** (`SEED = 20261112`), đảm bảo dữ liệu sinh ra trên tất cả các máy đều đồng nhất 100%.

1. **Khởi tạo và kích hoạt môi trường ảo (Khuyến nghị):**
   * **Windows:**
     ```powershell
     python -m venv .venv
     .venv\Scripts\activate
     ```
   * **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

2. **Cài đặt các thư viện cần thiết:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Chạy script sinh dữ liệu vào Database:**
   ```bash
   python db/generate_data.py
   ```
   *Quá trình này sẽ nạp 3.000 khách hàng, 150 sản phẩm, 20.000 đơn hàng kèm chi tiết vận chuyển, thanh toán, đánh giá và các case dữ liệu đặc biệt phục vụ phân tích.*

---

### Bước 5: Kiểm tra và xác thực dữ liệu (Validation)

Sau khi script sinh dữ liệu chạy xong, hãy chạy script xác thực để đảm bảo dữ liệu đã nạp không có lỗi vi phạm ràng buộc nghiệp vụ:

```bash
docker exec -i vietreport_postgres psql -U vietreport_admin -d E-commerce -f /docker-entrypoint-initdb.d/03_validate_data.sql
```

> ✅ **Kết quả mong đợi:** Tất cả các dòng truy vấn kiểm tra đều trả về cột `so_loi` là **`0`**.

---

## 3. Thông Tin Kết Nối Database

Dưới đây là thông tin tài khoản được thiết lập trong hệ thống:

| Thông số | Quản trị viên (Admin / Seeding) | SQL Agent (Read-only) |
| :--- | :--- | :--- |
| **Host** | `localhost` (hoặc `postgres` trong Docker network) | `localhost` (hoặc `postgres`) |
| **Port** | `5432` | `5432` |
| **Database** | `E-commerce` | `E-commerce` |
| **Username** | `vietreport_admin` | `vietreport_reader` |
| **Password** | `vietreport_admin_password` | `vietreport_reader_password` |
| **Quyền hạn** | Toàn quyền (DDL / DML) | Chỉ SELECT, Read-only transaction, timeout 10s |

---

## 4. Các Lệnh Tiện Ích Khác

* **Dừng database:**
  ```bash
  docker compose down
  ```
* **Xóa sạch dữ liệu và khởi động lại từ đầu (Reset Data):**
  ```bash
  docker compose down -v
  docker compose up -d
  python db/generate_data.py
  ```
* **Truy cập trực tiếp vào giao diện dòng lệnh của Postgres:**
  ```bash
  docker exec -it vietreport_postgres psql -U vietreport_admin -d E-commerce
  ```
