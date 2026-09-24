-- Applied by every seller on startup under an advisory lock, so it must be idempotent.

-- One row describing the current sale. `epoch` increments on every /reset so a
-- response (or anything cached) can be tied to the sale it belongs to.
CREATE TABLE IF NOT EXISTS sale (
    id     smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    epoch  bigint   NOT NULL DEFAULT 0,
    total  integer  NOT NULL DEFAULT 0 CHECK (total >= 0),
    sold   integer  NOT NULL DEFAULT 0
);
INSERT INTO sale (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Used only by the naive allocator. Deliberately has no keys or constraints:
-- the point is to show what the application logic alone lets through.
CREATE TABLE IF NOT EXISTS naive_sales (
    ticket_no  integer     NOT NULL,
    user_id    text        NOT NULL,
    request_id text        NOT NULL,
    sold_at    timestamptz NOT NULL DEFAULT clock_timestamp()
);
