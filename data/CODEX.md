# CODEX_TASKS.md — Nhiệm vụ theo giai đoạn cho VietReport

Tài liệu này đi kèm `AGENTS.md`. `AGENTS.md` cho biết **luật chung**; file này cho biết **làm gì, theo thứ tự nào, xong khi nào**.

## Cách dùng

- Giao **một task một lần** (ví dụ: "Làm task T1.2 trong CODEX_TASKS.md"). Không giao cả giai đoạn.
- Mỗi task có 4 phần: **Mục tiêu**, **Kỹ thuật xử lý**, **File**, **Tiêu chí hoàn thành**. Task chỉ xong khi mọi tiêu chí đều đạt và `ruff check .` + `pytest -q -m "not db"` pass.
- Task có phụ thuộc: chỉ làm khi các task phụ thuộc đã xong.
- Mẫu lệnh giao việc:

  > Làm task **T1.2** trong CODEX_TASKS.md. Tuân thủ AGENTS.md. Chỉ sửa các file được liệt kê trong task. Khi xong, báo: đã làm gì, file đổi, cách chạy test, giả định đã đặt.

## Hiện trạng đầu vào

Đã có (không viết lại, chỉ kiểm tra/dùng): `db/schema.sql` (13 bảng, camelCase, comment tiếng Việt) và `db/generate_data.py` (seed cố định, ~3000 khách hàng, 150 sản phẩm, 30000 đơn, insight cài sẵn, lỗi bẩn có kiểm soát). Số liệu thực tế theo repo; nếu lệch với tài liệu này thì theo repo.

---

# GIAI ĐOẠN 0 — Khung dự án và cơ sở dữ liệu chạy được

## T0.1 — Khung repo và công cụ

- **Mục tiêu:** repo có cấu trúc thư mục theo AGENTS.md mục 10, cài đặt và lint/test chạy được từ máy sạch.
- **Kỹ thuật xử lý:**
  - Cấu hình `ruff` (lint + format) và `pytest` (đăng ký marker `db`).
  - `.gitignore` (có `.env`, `eval/cache/`, `__pycache__`), `.env.example` (biến: `GROQ_API_KEY`, `DB_*`, `LANGFUSE_*`), `scripts` cho lệnh thường dùng.
  - Tạo các package rỗng có `__init__.py` kèm một test "smoke" import được.
- **File:** `.gitignore`, `.env.example`, `src/**/__init__.py`, `tests/test_smoke.py`.
- **Tiêu chí hoàn thành:** `pip install -e .[dev]`, `ruff check .`, `pytest -q` đều chạy sạch trên môi trường mới. Không có secret trong repo.

## T0.2 — Docker Compose + Postgres + user chỉ đọc

- **Mục tiêu:** `docker compose up -d db` dựng Postgres, nạp schema, có **hai role**: role ghi (để sinh dữ liệu) và role **chỉ SELECT** (cho agent).
- **Kỹ thuật xử lý:**
  - Compose service `db` với volume, healthcheck (`pg_isready`).
  - Script init (`docker/initdb/`): chạy `schema.sql`, rồi tạo role `vietreport_ro` với `GRANT CONNECT`, `GRANT USAGE ON SCHEMA public`, `GRANT SELECT ON ALL TABLES`, và `ALTER DEFAULT PRIVILEGES ... GRANT SELECT`. Đặt `ALTER ROLE vietreport_ro SET statement_timeout = '10s'` và `default_transaction_read_only = on` làm lớp phòng thủ thứ hai.
  - Mật khẩu lấy từ biến môi trường, không hardcode.
  - Lệnh nạp dữ liệu: `python db/generate_data.py` kết nối bằng role ghi.
- **File:** `docker/docker-compose.yml`, `docker/initdb/*.sql|sh`, `docs`/README ngắn về cách chạy.
- **Tiêu chí hoàn thành:** từ máy sạch chạy compose + generate_data thành công. Test `@pytest.mark.db`: role chỉ đọc `SELECT` được nhưng `INSERT/UPDATE/DELETE/DROP/CREATE` đều bị DB từ chối.

## T0.3 — Kiểm tra tính toàn vẹn dữ liệu sinh ra

- **Mục tiêu:** có test tự động khẳng định dữ liệu đúng cam kết (đây là nền cho eval về sau).
- **Kỹ thuật xử lý:** `tests/test_data_integrity.py` (marker `db`):
  - Số dòng từng bảng khớp kỳ vọng; chạy generate hai lần với cùng seed cho kết quả giống nhau (so checksum của vài bảng).
  - Giá trị enum hợp lệ (`trangThai`, `loaiGiaoDich`…); riêng `Dang xử lý` không dấu ở `van_chuyen` phải **tồn tại** (lỗi cố ý).
  - `tongTien` lệch công thức derived ở một tỷ lệ nhỏ (~0,5%), không phải 0% và không quá lớn.
  - Mỗi insight trong `ground_truth_insights.md` có query kiểm chứng; test chạy query và xác nhận insight **có thật** trong dữ liệu (ví dụ doanh thu khu vực X giảm đáng kể từ tuần N).
- **Tiêu chí hoàn thành:** toàn bộ test pass; nếu một insight không kiểm chứng được thì **báo lỗi cho người dùng**, không tự sửa generator.

---

# GIAI ĐOẠN 1 — Nền tảng: an toàn, cấu hình, LLM, schema context

## T1.1 — Cấu hình tập trung

- **Mục tiêu:** mọi tham số (model, DB, ngưỡng) đọc từ `configs/` và biến môi trường, có validate.
- **Kỹ thuật xử lý:** `pydantic-settings` + YAML. `configs/models.yaml` gán model **theo từng agent** (ví dụ planner/writer dùng model lớn, sql_agent/verifier model phù hợp, bước đơn giản dùng model nhỏ), `temperature`, `max_tokens`. `configs/safety.yaml`: `statement_timeout_ms`, `max_rows`, blacklist hàm, allowlist schema. `configs/db.yaml`: tham số kết nối (không chứa mật khẩu).
- **File:** `src/config.py`, `configs/*.yaml`, `tests/test_config.py`.
- **Tiêu chí hoàn thành:** thiếu biến bắt buộc → lỗi rõ ràng; test đọc cấu hình mẫu; không còn hằng số model/ngưỡng rải rác trong code.

## T1.2 — SQL Guard (kiểm tra an toàn SQL)

- **Mục tiêu:** hàm `validate_sql(sql, allowed_tables) -> ValidatedSQL` chỉ cho qua đúng một câu truy vấn đọc, an toàn.
- **Kỹ thuật xử lý:** dùng **`sqlglot` với dialect `postgres`**, phân tích AST, **không dựa vào regex**:
  1. `sqlglot.parse(sql, read="postgres")` → phải ra **đúng 1** câu lệnh (chặn `;` nối nhiều lệnh; comment không được giấu lệnh).
  2. Gốc cây là `Select`/`Union` (CTE `WITH ... SELECT` hợp lệ). Duyệt toàn bộ cây: nếu gặp `Insert/Update/Delete/Merge/Create/Drop/Alter/Command/Copy/Set/Call/Into` ở **bất kỳ đâu** (kể cả trong CTE, `SELECT ... INTO`) → từ chối.
  3. Hàm trong blacklist (`pg_sleep`, `pg_read_file`, `lo_import`, `dblink`, `set_config`, `pg_terminate_backend`…) → từ chối; chặn `FOR UPDATE/SHARE`.
  4. Gom tên bảng thật (loại trừ alias CTE); mọi bảng phải nằm trong allowlist; chặn `pg_catalog`, `information_schema`, schema khác `public`.
  5. Trả lỗi có **mã lý do** (enum) để SQL agent dùng làm phản hồi sửa lỗi.
- **File:** `src/safety/sql_guard.py`, `tests/test_sql_guard.py`.
- **Tiêu chí hoàn thành:** ≥15 ca bị chặn (nhiều câu lệnh, DML/DDL, `SELECT INTO`, CTE chứa ghi, hàm nguy hiểm, viết hoa/thường lẫn lộn, chèn comment, tên bảng không tồn tại, schema hệ thống) và ≥10 ca hợp lệ (JOIN, CTE, window function, subquery, `ILIKE`, ép kiểu `::`). Test **không cần DB**.

## T1.3 — Bộ thực thi an toàn

- **Mục tiêu:** `execute_readonly(sql) -> QueryResult` chạy SQL đã qua guard với giới hạn thời gian và số dòng.
- **Kỹ thuật xử lý:** engine riêng dùng role `vietreport_ro`; mở transaction `READ ONLY`; `SET LOCAL statement_timeout`; lấy tối đa `max_rows + 1` dòng bằng `fetchmany` để biết có bị cắt không (`truncated`); chuyển `Decimal/date` sang kiểu serialize được; bắt và phân loại lỗi (cú pháp, cột/bảng không tồn tại, timeout) thành mã lỗi + thông báo ngắn gọn cho agent sửa SQL. Mọi đường chạy SQL trong dự án **bắt buộc** đi qua hàm này (guard gọi bên trong, không để chỗ khác gọi trực tiếp DB).
- **File:** `src/safety/executor.py`, `src/schemas.py` (phần `QueryResult`), `tests/test_executor.py` (marker `db`).
- **Tiêu chí hoàn thành:** test timeout (truy vấn chậm bị ngắt), test cắt dòng, test lỗi cột không tồn tại có mã lỗi rõ, test SQL ghi không bao giờ tới được DB.

## T1.4 — Lớp gọi LLM duy nhất

- **Mục tiêu:** mọi agent gọi LLM qua `LLMClient`, có retry, cache, structured output, trace.
- **Kỹ thuật xử lý:**
  - Dùng SDK tương thích OpenAI trỏ tới Groq (base URL và key từ cấu hình).
  - Retry với exponential backoff + jitter khi 429/5xx; timeout; giới hạn token.
  - **Cache trên đĩa** (SQLite hoặc file) khóa theo hash của (model, messages, tham số). Có cờ bật/tắt cache; eval chạy với cache bật.
  - Hàm `complete_structured(model_cls, ...)`: yêu cầu JSON theo schema Pydantic, parse + validate, nếu sai thì retry có giới hạn kèm thông báo lỗi.
  - Ghi nhận token/độ trễ mỗi lần gọi (chuẩn bị cho Langfuse ở T2.4).
  - Giao diện đủ trừu tượng để test dùng `FakeLLMClient` trả lời cố định.
- **File:** `src/llm/client.py`, `src/llm/cache.py`, `src/llm/fake.py`, `tests/test_llm_client.py`.
- **Tiêu chí hoàn thành:** test (không gọi mạng) cho retry, cache hit/miss, parse structured thành công và thất bại; không có API key trong code/log.

## T1.5 — Schema context builder

- **Mục tiêu:** sinh đoạn mô tả schema đưa vào prompt Text-to-SQL, **chính xác và gọn**.
- **Kỹ thuật xử lý:**
  - Đọc từ DB: tên bảng/cột/kiểu/khóa ngoại/comment qua `information_schema` + `pg_description`, **không viết tay** để tránh lệch schema.
  - Render mỗi bảng: cột kèm kiểu, khóa, comment; **luôn in tên định danh trong dấu nháy kép** (`"donHangId"`) và kèm một dòng quy tắc về nháy kép.
  - Thêm ví dụ giá trị cho cột phân loại (liệt kê giá trị DISTINCT của các cột enum như `trangThai`) — lấy từ DB và cache lại.
  - Phần "ghi chú nghiệp vụ" cố định (đơn Đã hủy không tính doanh thu, `thanhTien` generated, COGS từ `phieu_nhap`, `Dang xử lý` không dấu…) đặt ở file riêng `configs/business_notes.md` để dễ chỉnh.
  - Hỗ trợ chọn tập bảng liên quan theo câu hỏi (bước đơn giản: truyền danh sách bảng; bước nâng cao: LLM/embedding chọn bảng — chỉ làm nếu context vượt ngưỡng).
- **File:** `src/agents/schema_context.py`, `configs/business_notes.md`, `tests/test_schema_context.py` (marker `db`).
- **Tiêu chí hoàn thành:** output chứa đủ 13 bảng, mọi cột camelCase đều có nháy kép, enum value hiển thị đúng; test snapshot đối chiếu với schema thật.

## T1.6 — Định dạng bộ câu hỏi, baseline Text-to-SQL, khung eval

- **Mục tiêu:** chốt `questions.jsonl`, có baseline một-lần-gọi và `run_eval.py` đo execution accuracy lần đầu.
- **Kỹ thuật xử lý:**
  - Định dạng mỗi dòng: `id`, `question_vi`, `difficulty` (`easy|medium|hard|unanswerable`), `gold_sql` (null nếu không trả lời được), `split` (`dev|heldout`), `tags`, `order_matters` (bool).
  - **Baseline**: một lần gọi LLM (schema context + câu hỏi → SQL), chưa tự sửa lỗi; qua guard + executor.
  - **Comparator** (`src/eval/compare.py`): chạy gold SQL và SQL của agent, chuẩn hóa (Decimal→float làm tròn 4 chữ số, ngày→chuỗi ISO, NULL giữ nguyên), so sánh **multiset các dòng**; nếu `order_matters=false` thì bỏ qua thứ tự dòng; tùy chọn bỏ qua thứ tự cột. Câu `unanswerable` đúng khi agent trả về từ chối có cấu trúc.
  - `run_eval.py`: tham số `--split`, `--config`, `--runs`; **mặc định chỉ chạy `dev`**, chạy `heldout` cần `--split heldout --confirm-final`. Ghi kết quả JSON (config, seed, thời điểm, từng câu đúng/sai + lỗi) vào `eval/results/`.
  - Viết 30 câu đầu kèm gold SQL **do người dùng cung cấp hoặc duyệt**; Codex chỉ dựng khung và có thể đề xuất, không tự coi đề xuất là chuẩn.
- **File:** `eval/questions.jsonl`, `eval/run_eval.py`, `src/eval/compare.py`, `src/agents/baseline_sql.py`, `tests/test_compare.py`.
- **Tiêu chí hoàn thành:** test comparator (thứ tự dòng, làm tròn số, NULL, Decimal), `run_eval.py --split dev` chạy hết và in bảng accuracy theo mức độ; chạy `heldout` không có cờ xác nhận → bị từ chối.

**Mốc cuối giai đoạn 1:** DB một lệnh, guard + executor có test, có số đo baseline đầu tiên.

---

# GIAI ĐOẠN 2 — SQL agent hoàn chỉnh và bộ đánh giá SQL

## T2.1 — SQL agent với vòng tự sửa

- **Mục tiêu:** `SQLAgent.answer(question) -> QueryResult` tự sửa lỗi tối đa N lần (cấu hình 2–3).
- **Kỹ thuật xử lý:** vòng lặp: sinh SQL → `validate_sql` → `execute_readonly` → nếu lỗi, đưa **SQL cũ + mã lỗi + thông báo** vào prompt sửa. Mỗi lần thử lưu vào `attempts` (SQL, lỗi). Dừng khi thành công hoặc hết lượt (trả `error`, **không bịa kết quả**). Có thể cài bằng LangGraph subgraph hoặc vòng lặp thuần — chọn cách đơn giản, test được. Cấp `query_id` ổn định (hash của SQL chuẩn hóa + chỉ số lần chạy) khi thành công.
- **File:** `src/agents/sql_agent.py`, `tests/test_sql_agent.py` (dùng `FakeLLMClient`).
- **Tiêu chí hoàn thành:** test với LLM giả: sửa thành công ở lần 2, thất bại sau hết lượt, guard chặn SQL ghi và agent phản ứng đúng; số lần thử không vượt cấu hình.

## T2.2 — Kết quả rỗng bất thường và câu không trả lời được

- **Mục tiêu:** agent không im lặng chấp nhận kết quả vô lý và biết từ chối.
- **Kỹ thuật xử lý:**
  - Heuristic kết quả rỗng/đáng ngờ: 0 dòng cho câu hỏi dạng thống kê, toàn NULL, một giá trị `0` bất thường → kích hoạt **một lượt** sửa có prompt riêng ("kết quả rỗng, kiểm tra lại điều kiện lọc, giá trị enum, khoảng thời gian"), rồi chấp nhận nếu vẫn rỗng.
  - Phân loại câu hỏi: bước "answerability" (hoặc nằm trong cùng lệnh gọi sinh SQL) trả về cấu trúc `{answerable: bool, reason, sql}`; câu hỏi về cột/bảng không tồn tại → `answerable=false` kèm lý do tiếng Việt, **không sinh SQL**.
- **File:** `src/agents/sql_agent.py`, `configs/prompts/sql_*.md`, `tests/test_sql_agent_edge.py`.
- **Tiêu chí hoàn thành:** test mẫu cho từng nhánh; prompt nằm trong file riêng, không nhúng chuỗi dài trong code.

## T2.3 — Bộ đánh giá SQL đầy đủ

- **Mục tiêu:** ~70 câu (20 dễ, 25 vừa, 15 khó, 10 không trả lời được), tách 20 câu held-out; chạy so sánh có/không vòng tự sửa.
- **Kỹ thuật xử lý:** mở rộng `questions.jsonl`; cờ `--no-repair` cho ablation; `--runs N` lặp nhiều lần và báo trung bình ± độ lệch; bảng kết quả theo mức độ, theo cấu hình (baseline / agent có sửa / agent không sửa). Script `eval/report_table.py` sinh bảng markdown từ `eval/results/`. Kiểm tra tự động: câu held-out **không** xuất hiện trong prompt/few-shot (test so khớp văn bản).
- **File:** `eval/questions.jsonl`, `eval/run_eval.py`, `eval/report_table.py`, `tests/test_eval_guard.py`.
- **Tiêu chí hoàn thành:** bảng accuracy dễ/vừa/khó/từ chối cho 3 cấu hình trên tập dev; chạy held-out chỉ khi có cờ xác nhận. **Không tự chỉnh prompt dựa trên held-out.**

## T2.4 — Tracing và CI

- **Mục tiêu:** mỗi lần gọi LLM/agent có trace; CI chạy lint + test.
- **Kỹ thuật xử lý:** tích hợp Langfuse trong `LLMClient` (token, độ trễ, tên agent, `query_id`), bật/tắt bằng cấu hình để test không cần Langfuse. GitHub Actions: cài dependency, `ruff check`, `ruff format --check`, `pytest -m "not db"`; job riêng (tùy chọn) dựng Postgres service để chạy test `db`. Cache pip.
- **File:** `src/llm/tracing.py`, `.github/workflows/ci.yml`.
- **Tiêu chí hoàn thành:** CI xanh trên nhánh chính; tắt Langfuse thì mọi thứ vẫn chạy.

**Mốc cuối giai đoạn 2:** bảng accuracy SQL theo mức độ + so sánh có/không tự sửa; CI xanh.

---

# GIAI ĐOẠN 3 — Các agent còn lại và đồ thị

## T3.1 — Hợp đồng dữ liệu và mẫu báo cáo

- **Mục tiêu:** hoàn thiện `src/schemas.py` theo AGENTS.md mục 6 và định nghĩa 3 loại báo cáo.
- **Kỹ thuật xử lý:** Pydantic v2 cho `DataQuestion`, `QueryResult`, `Figure`, `Claim`, `ReportSection`, `ReportDraft`, `VerificationReport`, `ReportState`. Ba mẫu báo cáo trong `configs/report_templates/*.yaml`: (1) doanh thu theo tuần so với kỳ trước, (2) hiệu quả theo khu vực, (3) sản phẩm và hoàn hàng. Mỗi mẫu liệt kê mục cần có, loại phân tích gợi ý, câu hỏi dữ liệu mẫu.
- **Tiêu chí hoàn thành:** test serialize/validate; mẫu báo cáo load và validate được; đổi hợp đồng nào cũng phải cập nhật test.

## T3.2 — Planner

- **Mục tiêu:** từ yêu cầu tiếng Việt → `ReportPlan` (mục + danh sách `DataQuestion`).
- **Kỹ thuật xử lý:** chọn mẫu báo cáo phù hợp (hoặc kết hợp), điền tham số thời gian ("tuần này so với tuần trước", "tháng 11") — **ngày tham chiếu lấy từ `max(ngayDat)` của DB hoặc tham số, không dùng giờ hệ thống** để báo cáo tái lập được. Structured output; giới hạn số câu hỏi dữ liệu tối đa (cấu hình). Yêu cầu nằm ngoài phạm vi (ví dụ cần dữ liệu không có) → plan có cờ `unsupported` kèm lý do.
- **File:** `src/agents/planner.py`, `configs/prompts/planner.md`, `tests/test_planner.py` (LLM giả).
- **Tiêu chí hoàn thành:** test cho 3 loại yêu cầu và 1 yêu cầu không hỗ trợ; ngày tham chiếu luôn được cố định trong plan.

## T3.3 — Điều phối truy vấn

- **Mục tiêu:** chạy SQL agent cho mọi câu hỏi trong plan, lưu kết quả vào kho theo `query_id`.
- **Kỹ thuật xử lý:** `QueryStore` (dict trong state hoặc SQLite) lưu `QueryResult`; chạy song song có giới hạn (`asyncio` + semaphore, tôn trọng rate limit); một câu thất bại không làm sập cả báo cáo — đánh dấu thiếu dữ liệu để Writer nêu rõ.
- **File:** `src/graph/query_stage.py`, `tests/test_query_stage.py`.
- **Tiêu chí hoàn thành:** test song song, test một câu lỗi, `query_id` duy nhất và ổn định.

## T3.4 — Analyst

- **Mục tiêu:** từ kết quả truy vấn → các **số liệu suy ra có công thức** và biểu đồ.
- **Kỹ thuật xử lý:** phần tính toán **xác định (pandas), không để LLM tính**: tăng/giảm % so với kỳ trước, tỷ trọng, top-N, z-score/ngưỡng để đánh dấu bất thường. Mỗi số suy ra được ghi thành `Figure(kind="derived")` kèm `formula` và các `query_id` nguồn để Verifier tái tính. Biểu đồ bằng matplotlib/plotly xuất ảnh (PNG/base64) hoặc SVG; chỉ vẽ từ dữ liệu có `query_id`. LLM (nếu dùng) chỉ để chọn loại phân tích/biểu đồ, không để sinh số.
- **File:** `src/agents/analyst.py`, `src/analysis/*.py`, `tests/test_analyst.py`.
- **Tiêu chí hoàn thành:** test với DataFrame cố định cho từng phép tính (kể cả chia cho 0, NULL, kỳ trước rỗng); mọi số suy ra đều có công thức truy vết được.

## T3.5 — Writer (đầu ra có cấu trúc)

- **Mục tiêu:** viết nhận định tiếng Việt, mỗi nhận định kèm danh sách `Figure` có nguồn.
- **Kỹ thuật xử lý:** Writer nhận **chỉ** các số đã có `query_id`/công thức (bảng "số được phép dùng"); prompt cấm nêu số ngoài danh sách; đầu ra là `ReportDraft` (JSON) chứ không phải văn bản tự do; câu chữ có số phải dùng placeholder hoặc cặp (`text`, `figures`) để Verifier ánh xạ. Định dạng số kiểu Việt (dấu chấm ngàn, phẩy thập phân, "triệu/tỷ") do **một hàm định dạng chung** (`src/format_vi.py`), không để LLM tự định dạng. Nhận phản hồi từ Verifier để sửa (vòng tối đa 2).
- **File:** `src/agents/writer.py`, `src/format_vi.py`, `configs/prompts/writer.md`, `tests/test_writer.py`, `tests/test_format_vi.py`.
- **Tiêu chí hoàn thành:** test định dạng số (ví dụ 1234567.8 → "1.234.567,8", 12.5% → "12,5%"); test Writer với LLM giả; mọi `Claim` có ít nhất một nguồn hoặc được đánh dấu là nhận định định tính.

## T3.6 — Verifier

- **Mục tiêu:** chặn mọi con số sai hoặc không có nguồn trước khi xuất bản.
- **Kỹ thuật xử lý:** làm **hai lớp, ưu tiên xác định (không LLM)**:
  1. **Đối chiếu theo cấu trúc:** với mỗi `Figure`, lấy giá trị thật từ `QueryStore` (hoặc tái tính từ công thức) và so sánh với dung sai: sai số tương đối nhỏ **hoặc** khớp sau khi làm tròn đúng số chữ số hiển thị. Chuẩn hóa đơn vị (triệu/tỷ, %).
  2. **Quét số "mồ côi":** trích mọi số trong văn bản nhận định (regex hiểu định dạng Việt `1.234,5`, `12,5%`, `1,2 triệu`) và đối chiếu với `figures` của chính nhận định đó; số có trong văn bản mà không có nguồn → từ chối.
  3. (Tùy chọn, LLM) kiểm tra **khẳng định định tính** ("tăng mạnh", "cao nhất") có khớp số liệu không; chỉ gắn cờ cảnh báo, không tự động sửa.
  - Kết quả: `VerificationReport` liệt kê claim bị từ chối + lý do cụ thể (số kỳ vọng vs số báo cáo) để Writer sửa; tối đa 2 vòng, hết vòng mà còn lỗi → báo cáo đánh dấu rõ phần chưa xác minh, **không im lặng xuất bản**.
- **File:** `src/agents/verifier.py`, `src/verify/numbers.py`, `tests/test_verifier.py`, `tests/test_numbers_vi.py`.
- **Tiêu chí hoàn thành:** test cho số khớp, lệch làm tròn hợp lệ, số sai, số không nguồn, số trong chữ "1,2 triệu"; đây là phần **không được cắt**.

## T3.7 — Ghép đồ thị LangGraph và bước duyệt

- **Mục tiêu:** pipeline đầu-cuối: plan → query → analyze → write → verify (vòng) → chờ duyệt → render.
- **Kỹ thuật xử lý:** `StateGraph` với state là Pydantic/TypedDict; cạnh điều kiện cho vòng Writer↔Verifier (đếm vòng); `interrupt` trước bước xuất bản và checkpointer (MemorySaver cho dev, Postgres/SQLite checkpointer cho API) để tiếp tục sau khi người dùng duyệt/từ chối/yêu cầu sửa. Graph chỉ điều phối; không chứa logic nghiệp vụ.
- **File:** `src/graph/build.py`, `src/graph/state.py`, `tests/test_graph.py` (LLM giả, DB giả hoặc nhỏ).
- **Tiêu chí hoàn thành:** test chạy đủ đường vui, đường Verifier trả về sửa 1 và 2 lần, đường hết vòng, đường người dùng từ chối.

## T3.8 — Renderer HTML/PDF

- **Mục tiêu:** xuất báo cáo từ `ReportDraft` đã duyệt.
- **Kỹ thuật xử lý:** Jinja2 với **autoescape bật**; template HTML tự chứa (CSS nội tuyến, ảnh biểu đồ base64); chú thích nguồn (`query_id`) và phần "phương pháp/giới hạn" (dữ liệu mô phỏng). PDF: chuyển HTML → PDF bằng một công cụ duy nhất (WeasyPrint hoặc Playwright) — **hỏi người dùng chọn** trước khi thêm dependency nặng; kiểm tra font tiếng Việt hiển thị đúng dấu. Bước 1 xong HTML trước, PDF làm sau (có thể cắt).
- **File:** `src/render/html.py`, `src/render/pdf.py`, `src/render/templates/*.html`, `tests/test_render.py`.
- **Tiêu chí hoàn thành:** test escape (nội dung có `<script>` không chạy), HTML mở được độc lập, PDF (nếu làm) có tiếng Việt đúng dấu.

**Mốc cuối giai đoạn 3:** từ một yêu cầu tiếng Việt ra được báo cáo HTML hoàn chỉnh, dù còn thô.

---

# GIAI ĐOẠN 4 — Đánh giá cuối, đóng gói, trình bày

## T4.1 — Đánh giá cấp báo cáo, baseline single-agent, ablation

- **Mục tiêu:** có số liệu thật cho 3 cấu hình: single-agent, multi-agent đầy đủ, multi-agent bỏ Verifier/bỏ tự sửa SQL.
- **Kỹ thuật xử lý:**
  - Tạo 15–20 yêu cầu báo cáo (`eval/report_requests.jsonl`), mỗi yêu cầu gắn danh sách insight cài sẵn kỳ vọng.
  - **Single-agent baseline**: một agent có đủ công cụ (SQL + pandas) làm toàn bộ, không Planner/Verifier riêng — cùng model, cùng ngân sách token để công bằng.
  - Chỉ số tự động: **độ chính xác số liệu** (dùng module quét số của Verifier nhưng chạy **độc lập** trên bản trước và sau Verifier), **thu hồi insight** (so khớp với `ground_truth_insights.md`; có thể dùng LLM-judge và ghi rõ giới hạn), **chi phí/độ trễ** từ trace.
  - Rubric 1–5 (đúng, đủ, dễ hiểu): xuất file chấm tay (CSV) để **người dùng tự chấm**; Codex không tự chấm thay.
  - Chạy mỗi cấu hình nhiều lần, báo trung bình ± độ lệch; chạy held-out SQL **một lần cuối**.
- **File:** `eval/report_requests.jsonl`, `eval/run_report_eval.py`, `src/agents/single_agent.py`, `eval/results/`.
- **Tiêu chí hoàn thành:** bảng so sánh 3 cấu hình trên mọi chỉ số; kết quả lưu kèm config/seed; nếu multi-agent không hơn baseline ở chỉ số nào đó, ghi nguyên trạng — **không làm đẹp số liệu**.

## T4.2 — FastAPI

- **Mục tiêu:** API tạo báo cáo, duyệt, tải về.
- **Kỹ thuật xử lý:** `POST /reports` (nhận yêu cầu, chạy graph tới điểm dừng, trả `report_id` + bản nháp), `GET /reports/{id}`, `POST /reports/{id}/approve` (và `reject` kèm phản hồi), `GET /reports/{id}/download?format=html|pdf`. Chạy nền (BackgroundTasks hoặc hàng đợi đơn giản) vì báo cáo mất thời gian; trạng thái lưu theo checkpointer. Validate đầu vào bằng Pydantic; không trả stack trace ra ngoài.
- **File:** `api/main.py`, `api/routes/*.py`, `tests/test_api.py`.
- **Tiêu chí hoàn thành:** test API với graph giả; luồng tạo → duyệt → tải chạy được.

## T4.3 — Streamlit UI tối giản

- **Mục tiêu:** nhập yêu cầu, xem bản nháp + trạng thái xác minh, duyệt/từ chối, tải file.
- **Kỹ thuật xử lý:** gọi FastAPI (không import trực tiếp graph); hiển thị claim bị Verifier gắn cờ; không logic nghiệp vụ trong UI. (Có thể cắt đầu tiên nếu trễ.)
- **File:** `ui/app.py`.
- **Tiêu chí hoàn thành:** chạy được trong compose, thao tác trọn luồng bằng chuột.

## T4.4 — Hoàn thiện Docker Compose và CI

- **Mục tiêu:** `docker compose up` chạy Postgres + API + UI từ máy sạch.
- **Kỹ thuật xử lý:** Dockerfile nhiều tầng (image nhỏ, chạy bằng user không phải root), healthcheck và `depends_on: condition: service_healthy`, tự động nạp schema + dữ liệu lần đầu (idempotent), biến môi trường qua `.env`. CI thêm bước build image.
- **File:** `docker/Dockerfile`, `docker/docker-compose.yml`, `.github/workflows/ci.yml`.
- **Tiêu chí hoàn thành:** làm theo README trên máy sạch ra hệ thống chạy được; CI xanh.

## T4.5 — README, demo, đoạn CV

- **Mục tiêu:** tài liệu hoàn chỉnh dựa trên **số liệu đã đo thật**.
- **Kỹ thuật xử lý:** README gồm tổng quan, sơ đồ kiến trúc, cách chạy, kết quả đánh giá (copy từ `eval/results/`), **giới hạn** (dữ liệu mô phỏng, chỉ đo khả năng tìm insight cài sẵn, thiên lệch khi dùng LLM-judge, kích thước bộ test nhỏ), cấu trúc repo. Đoạn CV theo khung trong kế hoạch: **chỉ điền số có trong `eval/results/`**; chỗ chưa đo giữ dấu `[ ]`, không ước lượng.
- **File:** `README.md`, `docs/`, ảnh/video demo do người dùng quay.
- **Tiêu chí hoàn thành:** mọi con số trong README/CV truy được về một file kết quả cụ thể.

---

## Bảng tóm tắt thứ tự và phụ thuộc

| Giai đoạn | Task                                                  | Phụ thuộc                          |
| --------- | ----------------------------------------------------- | ---------------------------------- |
| 0         | T0.1 → T0.2 → T0.3                                    | —                                  |
| 1         | T1.1 → T1.2 → T1.3 → T1.4 → T1.5 → T1.6               | T0.2 (T1.3, T1.5, T1.6 cần DB)     |
| 2         | T2.1 → T2.2 → T2.3 → T2.4                             | Giai đoạn 1                        |
| 3         | T3.1 → T3.2 → T3.3 → T3.4 → T3.5 → T3.6 → T3.7 → T3.8 | T2.1; T3.5 cần T3.4; T3.6 cần T3.5 |
| 4         | T4.1 → T4.2 → T4.3 → T4.4 → T4.5                      | Giai đoạn 3                        |

**Nếu trễ, cắt theo thứ tự:** T4.3 (UI) → bớt 1 loại báo cáo ở T3.1 → giảm bộ câu hỏi ở T2.3 xuống 50 (giữ held-out) → PDF ở T3.8. **Không được cắt:** T1.2/T1.3 (an toàn), T3.6 (Verifier), T2.3/T4.1 (đánh giá và so sánh baseline).
