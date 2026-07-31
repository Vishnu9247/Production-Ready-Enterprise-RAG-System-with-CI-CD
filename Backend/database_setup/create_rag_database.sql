-- Run this script while connected to the built-in `postgres` database as the
-- Azure PostgreSQL administrator. Execute each numbered section separately in
-- DBeaver with auto-commit enabled. Never commit a real password to this file.

-- 1. Create a dedicated application login. Replace the placeholder locally.
CREATE ROLE rag_app
    WITH LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    PASSWORD 'REPLACE_WITH_A_NEW_RANDOM_PASSWORD';

-- 2. Create the application database. CREATE DATABASE cannot run inside a
-- transaction block, so execute this statement by itself.
CREATE DATABASE rag_db
    WITH ENCODING = 'UTF8'
    TEMPLATE = template0;

-- 3. Restrict database access to the application role and database owner.
REVOKE ALL ON DATABASE rag_db FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE rag_db TO rag_app;

-- 4. In DBeaver, reconnect or change the active database from `postgres` to
-- `rag_db`, then execute the remaining statements.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO rag_app;

-- Application tables are intentionally not created here. The backend runs
-- SQLAlchemy Base.metadata.create_all() when AUTO_INIT_DB=true, ensuring the
-- schema matches the deployed application code.
