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

-- The safe allocators' inventory: exactly `total` rows are created by /reset
-- and buys only ever UPDATE an unsold row, so the table itself enforces:
--   I1 no oversell            -> there is no row N+1 to sell
--   I2 no duplicate number    -> ticket_no is the primary key
--   I3 idempotent request_id  -> UNIQUE (request_id)
--   D3 one ticket per user    -> UNIQUE (user_id)
-- even if application code is wrong. NULLs are distinct, so unsold rows coexist.
CREATE TABLE IF NOT EXISTS tickets (
    ticket_no  integer PRIMARY KEY CHECK (ticket_no > 0),
    user_id    text UNIQUE,
    request_id text UNIQUE,
    sold_at    timestamptz,
    CHECK ((user_id IS NULL) = (request_id IS NULL)),
    CHECK ((user_id IS NULL) = (sold_at IS NULL))
);
-- Finding "the lowest unsold ticket" must not scan past every sold one.
CREATE INDEX IF NOT EXISTS tickets_unsold ON tickets (ticket_no) WHERE user_id IS NULL;

-- Used only by the naive allocator. Deliberately has no keys or constraints:
-- the point is to show what the application logic alone lets through.
CREATE TABLE IF NOT EXISTS naive_sales (
    ticket_no  integer     NOT NULL,
    user_id    text        NOT NULL,
    request_id text        NOT NULL,
    sold_at    timestamptz NOT NULL DEFAULT clock_timestamp()
);
