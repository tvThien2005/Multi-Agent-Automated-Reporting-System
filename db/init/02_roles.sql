-- User mà SQL Agent sẽ dùng để truy vấn
CREATE ROLE vietreport_reader WITH LOGIN PASSWORD 'vietreport_reader_password';

GRANT CONNECT ON DATABASE E-commerce TO vietreport_reader;

GRANT USAGE ON SCHEMA public TO vietreport_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO vietreport_reader;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO vietreport_reader;

ALTER ROLE vietreport_reader SET default_transaction_read_only = on;
ALTER ROLE vietreport_reader SET statement_timeout = '10s';
ALTER ROLE vietreport_reader SET idle_in_transaction_session_timeout = '30s';