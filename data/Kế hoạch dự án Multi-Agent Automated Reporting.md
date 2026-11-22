# Kế hoạch dự án Multi-Agent Automated Reporting (1 tháng)

Tên tạm: **VietReport** (có thể đổi). Mục tiêu: một hệ thống nhiều agent nhận yêu cầu báo cáo bằng tiếng Việt, truy vấn PostgreSQL an toàn, phân tích, viết báo cáo và tự kiểm tra số liệu trước khi xuất.

## 1. Mục tiêu và tiêu chí hoàn thành

**Mục tiêu** có sản phẩm chạy được, có số liệu đánh giá thật, và trả lời được câu hỏi "vì sao cần nhiều agent".

**Dự án được coi là xong khi:**

- Chạy được bằng một lệnh `docker compose up` (Postgres + API + UI).
- Sinh được ít nhất 3 loại báo cáo từ yêu cầu tiếng Việt, xuất HTML hoặc PDF.
- Có bộ đánh giá với số liệu cụ thể (độ chính xác SQL, độ chính xác số liệu trong báo cáo, so sánh với baseline một agent).
- Có CI xanh (ruff + pytest), README đầy đủ, ảnh hoặc video demo ngắn.

**Phạm vi khóa (không mở rộng trước khi xong lõi):** một database, ba loại báo cáo, một định dạng đầu ra, năm vai agent. Không làm: tìm kiếm web, ngôn ngữ, đửi email, đa năng nhập nhiều người dùng.

## 2. Kiến trúc

Luồng xử lý:

1. **Planner** nhận yêu cầu, xác định các mục cần có trong báo cáo (ví dụ: tổng quan doanh thu, theo khu vực, top sản phẩm, so sánh kỳ trước) và danh sách câu hỏi dữ liệu cần trả lời.
2. **SQL agent** với mỗi câu hỏi dữ liệu: lấy ngữ cảnh schema, sinh SQL, kiểm tra an toàn, chạy, nếu lỗi thì tự sửa tối đa 2-3 lần. Mỗi kết quả được lưu kèm một `query_id`.
3. **Analyst** tính toán từ kết quả (pandas): tăng giảm so với kỳ trước, tỷ trọng, phát hiện bất thường; vẽ biểu đồ.
4. **Writer** viết nhận xét tiếng Việt. Bắt buộc xuất dạng có cấu trúc: mỗi nhận định có danh sách số liệu kèm `query_id` nguồn.
5. **Verifier** đối chiếu từng con số trong nhận định với kết quả truy vấn (so sánh có dung sai làm tròn). Số không khớp hoặc không có nguồn thì trả về Writer sửa, tối đa 2 vòng.
6. **Bước duyệt của người dùng** trước khi xuất bản chính thức, rồi **Renderer** xuất HTML/PDF.

Triển khai bằng LangGraph (đồ thị trạng thái, vòng lặp sửa lỗi, điểm dừng chờ duyệt), FastAPI làm API, UI đơn giản bằng Streamlit, tracing bằng Langfuse (hoặc LangSmith), Docker Compose, GitHub Actions.

**Bảo vệ cần có từ đầu:** kết nối DB bằng user chỉ có quyền SELECT; chặn mọi câu lệnh không phải SELECT (kiểm tra bằng bộ phân tích SQL, không chỉ regex); giới hạn thời gian chạy (statement timeout) và số dòng trả về.

## 3. Thiết kế database mô phỏng

thương mại điện tử Việt Nam. Schema gồm 11 bảng chia 4 nhóm: dimension `(khu_vuc, danh_muc)`, `master data (san_pham, khach_hang, khuyen_mai)`, `transaction (don_hang, don_hang_khuyen_mai, chi_tiet_don_hang, thanh_toan, van_chuyen, danh_gia)`, `và tồn kho/nhập hàng (ton_kho, phieu_nhap)`.

**Sinh dữ liệu bằng script có seed cố định** (Python + Faker + numpy), để chạy lại ra đúng dữ liệu cũ:

- 12–18 tháng dữ liệu, kết thúc gần ngày hiện tại (để báo cáo "tuần này so với tuần trước" có nghĩa).

- Quy mô: khoảng 1 nghìn khách hàng, 150 sản phẩm, 20 nghìn đơn hàng. Đủ lớn để truy vấn có ý nghĩa, đủ nhỏ để chạy nhanh trên laptop.

- Có tính mùa vụ và xu hướng (Tết, 11/11, 12/12, cuối tuần), khác biệt theo khu_vuc và danh_muc.

**Ràng buộc phải tôn trọng khi sinh dữ liệu (để không vi phạm schema)**:

- chi_tiet_don_hang.thanhTien là generated column — không insert tay, DB tự tính từ soLuong \* donGia.

- don_hang.tongTien là derived = SUM(chi_tiet_don_hang.thanhTien) − SUM(don_hang_khuyen_mai.soTienGiam); phải sync sau khi sinh chi tiết + khuyến mãi.

- don_hang.trangThai chỉ nhận: Đang xử lý | Đã xác nhận | Đang giao hàng | Đã giao hàng | Đã hủy. Đơn Đã hủy không được tính doanh thu.

- thanh_toan.loaiGiaoDich ∈ {Thanh toán, Hoàn tiền, Điều chỉnh}; trangThai ∈ {Chờ xử lý, Thành công, Thất bại, Hoàn tiền}. 1 đơn có thể có nhiều giao dịch.

- van_chuyen.trangThai ∈ {Dang xử lý, Đã xác nhận, Đang giao hàng, Đã giao hàng, Đã hủy} (lưu ý giá trị Dang xử lý viết không dấu là cố ý trong schema — đây là một trong các lỗi bẩn có kiểm soát).

- danh_gia có UNIQUE (donHangId, sanPhamId) — 1 khách/1 đơn/1 sản phẩm chỉ đánh giá 1 lần.

- khuyen_mai.phanTramGiam ∈ [0, 100] và ngayKetThuc >= ngayBatDau; soTienGiam snapshot thực tế (có thể khác phanTramGiam \* tongTien nếu stacking/giới hạn).

- ton_kho chỉ 1 dòng/sản phẩm (PK = sanPhamId), soLuongTon >= 0.

- phieu_nhap.donGiaNhap là snapshot giá nhập — dùng để tính COGS lịch sử (không dùng san_pham.giaNhap).

**Lỗi bẩn có kiểm soát (ghi rõ trong tài liệu data_issues.md)**:

- Một ít khach_hang.hoTen/email/soDienThoai/khuVucId/phanKhuc NULL (schema cho phép).

- Đơn Đã hủy kèm lyDoHuy (một số NULL dù đã hủy — lỗi cố ý), đơn hoàn tiền có thanh_toan.loaiGiaoDich = 'Hoàn tiền'.

- van_chuyen.trangThai = 'Dang xử lý' (không dấu) lẫn với 'Đang xử lý' (có dấu) — viết không thống nhất.

- Một số danh_gia.diem = 1 hoặc 5 kèm binhLuan NULL.

- Bản ghi trùng ở khach_hang (cùng SĐT, khác id) — không đặt UNIQUE trên soDienThoai nên chèn được, dùng để test dedup.

- don_hang.tongTien lệch nhẹ so với công thức derived ở ~0.5% đơn (mô phỏng sync trễ) — dùng để test validation.

**Cài sẵn "insight có đáp án" (ghi trong ground_truth_insights.md, kèm query kiểm chứng)**:

- Doanh thu khu_vuc X giảm ~20% từ tuần N (gắn với một đợt tăng Đã hủy hoặc giảm đơn).

- Một danh_muc tăng đột biến trong 2 tuần quanh 11/11 hoặc 12/12.

- Một san_pham có tỷ lệ hoàn (thanh_toan.loaiGiaoDich='Hoàn tiền' / đơn Đã giao hàng) cao bất thường.

- Một khuyen_mai có soTienGiam thực tế thấp hơn kỳ vọng (phanTramGiam \* tongTien) — test báo cáo hiệu quả KM.

- Một nhaVanChuyen có on-time rate (ngayGiaoThucTe <= ngayGiaoDuKien) thấp hơn hẳn các đơn vị khác.

- Danh sách này để đo xem báo cáo có tìm ra các insight đó không.

Lưu ý trong README: đây là dữ liệu mô phỏng sinh bằng script, không phải dữ liệu nghiệp vụ thật — nên không đo được "độ hữu ích với nghiệp vụ thật", chỉ đo được khả năng phát hiện insight đã cài sẵn và xử lý lỗi bẩn có kiểm soát.

## 4. Thiết kế đánh giá (làm song song, không để cuối)

**Bộ SQL (khoảng 70 câu, tiếng Việt, kèm gold SQL):**

- 20 câu dễ (một bảng), 25 câu vừa (JOIN 2-3 bảng, GROUP BY), 15 câu khó (CTE, window function, so sánh theo kỳ).
- 10 câu không trả lời được hoặc mơ hồ (hỏi cột không tồn tại) để đo việc agent từ chối thay vì bịa.
- **Tách 20 câu giữ riêng (held-out)** từ đầu, chỉ chạy khi chốt kết quả cuối, giống cách khóa test set ở dự án Credit-Fraud.
- Cách chấm: chạy cả SQL của agent và gold SQL, so sánh tập kết quả (execution accuracy).

**Đánh giá cấp báo cáo (10-15\*\*** yêu cầu báo cáo):\*\*

| Chỉ số               | Cách đo                                                                                  |
| -------------------- | ---------------------------------------------------------------------------------------- |
| Độ chính xác số liệu | Tỷ lệ con số trong báo cáo khớp với kết quả truy vấn gốc (trước và sau Verifier)         |
| Thu hồi insight      | Tỷ lệ insight cài sẵn được báo cáo nêu đúng                                              |
| Chất lượng tổng thể  | Rubric 1-5 (đúng, đủ, dễ hiểu), chấm tay, nên nhờ thêm một người chấm một nửa số báo cáo |
| Chi phí và độ trễ    | Token và thời gian mỗi báo cáo (lấy từ tracing)                                          |

**So sánh bắt buộc:**

1. Baseline: một agent duy nhất có đủ công cụ, làm toàn bộ.
2. Multi-agent đầy đủ.
3. Multi-agent bỏ Verifier, và bỏ vòng tự sửa SQL (ablation).

Nếu multi-agent không hơn baseline ở chỉ số nào đó, vẫn ghi lại và phân tích nguyên nhân. Nếu dùng LLM làm giám khảo thì ghi rõ giới hạn (thiên lệch, không thay được người chấm).

### Định dạng `eval/questions.jsonl`

Mỗi dòng là một test case JSON độc lập; không đặt dấu phẩy giữa các dòng. Các trường tối thiểu gồm `id`, `question_vi`, `difficulty`, `answerable`, và `gold_sql`. Khuyến nghị thêm `expected_columns` và `tags` để phân tích lỗi theo loại truy vấn.

Ví dụ câu trả lời được:

```json
{
  "id": "Q001",
  "question_vi": "Tổng doanh thu đơn hàng đã giao trong tháng 10 năm 2026 là bao nhiêu?",
  "difficulty": "easy",
  "answerable": true,
  "gold_sql": "SELECT COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_doanh_thu\nFROM don_hang dh\nJOIN chi_tiet_don_hang ct ON ct.don_hang_id = dh.id\nWHERE dh.trang_thai = 'da_giao'\n  AND dh.ngay_dat >= DATE '2026-10-01'\n  AND dh.ngay_dat < DATE '2026-11-01';",
  "expected_columns": ["tong_doanh_thu"],
  "tags": ["aggregation", "date_filter"]
}
```

Ví dụ câu phải từ chối vì schema không hỗ trợ:

```json
{
  "id": "Q002",
  "question_vi": "Doanh thu theo kênh TikTok Shop trong quý 3 là bao nhiêu?",
  "difficulty": "reject",
  "answerable": false,
  "gold_sql": null,
  "expected_columns": [],
  "tags": ["unsupported_dimension"],
  "expected_refusal_reason": "Schema không có dữ liệu về kênh bán hàng hoặc TikTok Shop."
}
```

`gold_sql` là truy vấn chuẩn do người viết benchmark xác nhận chạy đúng trên dữ liệu seed. Khi chấm, chạy SQL của agent và `gold_sql`, rồi so sánh tập kết quả thay vì so sánh chuỗi SQL.

## 5. Cấu trúc repo

```
vietreport/
  configs/        cấu hình model, DB, ngưỡng
  db/             schema.sql, generate_data.py, injected_issues.md
  src/
    agents/       planner, sql_agent, analyst, writer, verifier
    graph/        định nghĩa đồ thị LangGraph
    safety/       kiểm tra SQL, giới hạn thực thi
    render/       template HTML, xuất PDF
  api/            FastAPI
  ui/             Streamlit
  eval/           questions.jsonl, gold_sql, run_eval.py, results/
  tests/
  docker/         Dockerfile, docker-compose.yml
  .github/workflows/ci.yml
```

## 6. Kế hoạch theo tuần

Giả định làm đều khoảng 2-3 giờ mỗi ngày trong tuần và nhiều hơn vào cuối tuần. Mỗi cuối tuần có một **mốc kiểm tra**: nếu chưa đạt, cắt phạm vi chứ đừng dồn sang tuần sau.

### Tuần 1: Nền tảng, dữ liệu, baseline

- Ngày 1-2: dựng repo, Docker Compose với PostgreSQL, thiết kế schema, tạo user chỉ đọc.
- Ngày 3-4: viết `generate_data.py` (seed cố định), cài lỗi bẩn và insight có đáp án, ghi tài liệu.
- Ngày 5: bộ kiểm tra SQL an toàn (chỉ SELECT, timeout, giới hạn dòng) kèm test.
- Ngày 6-7: viết 30 câu hỏi đầu tiên kèm gold SQL; làm baseline Text-to-SQL đơn giản (một lần gọi LLM, chưa tự sửa lỗi) và đo lần đầu.

**Mốc cuối tuần 1:** DB chạy được bằng một lệnh, có số đo baseline đầu tiên.

### Tuần 2: SQL agent hoàn chỉnh và bộ đánh giá SQL

- Ngày 8-9: xử lý ngữ cảnh schema (mô tả bảng, cột, ví dụ giá trị; chỉ đưa bảng liên quan vào prompt nếu schema lớn).
- Ngày 10-11: vòng tự sửa SQL dựa trên thông báo lỗi và kết quả rỗng bất thường; xử lý câu hỏi không trả lời được.
- Ngày 12-13: hoàn tất 70 câu, tách 20 câu held-out, viết `run_eval.py`, chạy và ghi kết quả theo mức độ.
- Ngày 14: thêm tracing (Langfuse), GitHub Actions chạy ruff và pytest.

**Mốc cuối tuần 2:** có bảng độ chính xác SQL theo mức dễ/vừa/khó, có so sánh với và không có vòng tự sửa.

### Tuần 3: Các agent còn lại và đồ thị

- Ngày 15-16: Planner và mẫu ba loại báo cáo (ví dụ: doanh thu theo tuần, hiệu quả theo khu vực, sản phẩm và hoàn hàng).
- Ngày 17-18: Analyst (pandas, biểu đồ) và Writer với đầu ra có cấu trúc kèm `query_id`.
- Ngày 19-20: Verifier đối chiếu số liệu, vòng sửa tối đa 2 lần, bước người dùng duyệt; ghép toàn bộ thành đồ thị LangGraph.
- Ngày 21: Renderer xuất HTML/PDF; chạy thử đầu-cuối và sửa lỗi.

**Mốc cuối tuần 3:** từ một yêu cầu tiếng Việt ra được một báo cáo hoàn chỉnh, dù còn thô.

### Tuần 4: Đánh giá cuối, đóng gói, trình bày

- Ngày 22-24: chạy đánh giá cấp báo cáo trên 15-20 yêu cầu; baseline một agent; ablation; chấm rubric; chạy held-out một lần cuối.
- Ngày 25: FastAPI (endpoint tạo báo cáo, duyệt, tải về) và UI Streamlit tối giản.
- Ngày 26-27: hoàn thiện Docker Compose, CI, test, dọn code.
- Ngày 28-30: viết README (kiến trúc, cách chạy, kết quả đánh giá, giới hạn), ghi ảnh hoặc video demo ngắn, viết đoạn CV bằng số liệu đã đo, đăng GitHub. Dành 1-2 ngày đệm cho phần trễ.

## 7. Nếu bị trễ, cắt theo thứ tự này

1. Bỏ Streamlit, giữ API và báo cáo xuất từ dòng lệnh.
2. Giảm từ ba loại báo cáo xuống hai.
3. Giảm bộ SQL từ 70 xuống 50 câu (giữ nguyên tách held-out).
4. Bỏ xuất PDF, chỉ xuất HTML.

**Không được cắt:** kiểm tra SQL an toàn, Verifier, bộ đánh giá và so sánh với baseline. Đây là phần tạo sức nặng cho dự án.

## 8. Rủi ro chính

- **Giới hạn và chi phí LLM:** gói miễn phí thường có giới hạn tốc độ và hạn mức hằng ngày, và chúng thay đổi theo thời gian, nên hãy kiểm tra trang giá hiện tại của nhà cung cấp bạn dùng. Giảm rủi ro bằng cách lưu đệm (cache) kết quả gọi model khi chạy đánh giá, đặt giới hạn token, và dùng model nhỏ cho bước đơn giản.
- **Kết quả không ổn định giữa các lần chạy:** đặt temperature thấp, chạy mỗi cấu hình đánh giá nhiều lần và báo cáo trung bình.
- **Phình phạm vi:** giữ nguyên danh sách "không làm" ở mục 1.
- **Tự đánh giá thiên lệch:** viết gold SQL và insight cài sẵn trước khi chỉnh prompt, giữ tập held-out nguyên vẹn.

## 9. Khung viết CV (chỉ điền số sau khi đo xong)

- Built a multi-agent reporting system (planner, SQL, analyst, writer, verifier) on LangGraph that turns Vietnamese requests into verified reports from a PostgreSQL database with a read-only, SELECT-only safety layer.
- Designed a \[N\]-question Vietnamese Text-to-SQL benchmark with a locked held-out set; execution accuracy reached \[X\]% overall and \[Y\]% on hard queries, and self-repair raised it from \[A\]% to \[B\]%.
- Added a verifier that checks every number against query results; numeric accuracy in reports rose from \[P\]% to \[Q\]%, and the system recovered \[R\]% of planted insights.
- Compared against a single-agent baseline on accuracy, cost, and latency using Langfuse traces; containerized with Docker Compose and tested in GitHub Actions CI.
