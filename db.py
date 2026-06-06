import sqlite3
import os
import uuid

DB_PATH = os.path.join(os.path.dirname(__file__), "platform.db")


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS child_bots (
                id              TEXT PRIMARY KEY,
                owner_id        INTEGER NOT NULL,
                token           TEXT UNIQUE NOT NULL,
                username        TEXT,
                display_name    TEXT,
                active          INTEGER DEFAULT 1,
                registered_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS links (
                id              TEXT PRIMARY KEY,
                child_bot_id    TEXT NOT NULL,
                owner_id        INTEGER NOT NULL,
                amount          INTEGER NOT NULL,
                label           TEXT NOT NULL,
                message         TEXT,
                invoice_url     TEXT,
                active          INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (child_bot_id) REFERENCES child_bots(id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id         TEXT NOT NULL,
                child_bot_id    TEXT NOT NULL,
                owner_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                username        TEXT,
                stars           INTEGER NOT NULL,
                fee_stars       INTEGER NOT NULL,
                fee_paid        INTEGER DEFAULT 0,
                paid_at         TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (link_id) REFERENCES links(id)
            );

            CREATE TABLE IF NOT EXISTS fee_invoices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id      INTEGER NOT NULL,
                owner_id        INTEGER NOT NULL,
                fee_stars       INTEGER NOT NULL,
                invoice_url     TEXT,
                paid            INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            );
        """)
        self.conn.commit()

    # ── Child bots ────────────────────────────────────────────────────────────

    def register_bot(self, owner_id: int, token: str, username: str, display_name: str) -> str:
        bot_id = str(uuid.uuid4())[:8].upper()
        self.conn.execute(
            "INSERT INTO child_bots (id, owner_id, token, username, display_name) VALUES (?,?,?,?,?)",
            (bot_id, owner_id, token, username, display_name)
        )
        self.conn.commit()
        return bot_id

    def update_bot_info(self, bot_id: str, username: str, display_name: str):
        self.conn.execute(
            "UPDATE child_bots SET username = ?, display_name = ? WHERE id = ?",
            (username, display_name, bot_id)
        )
        self.conn.commit()

    def get_bot_by_token(self, token: str):
        row = self.conn.execute(
            "SELECT * FROM child_bots WHERE token = ? AND active = 1", (token,)
        ).fetchone()
        return dict(row) if row else None

    def get_bot_by_id(self, bot_id: str):
        row = self.conn.execute(
            "SELECT * FROM child_bots WHERE id = ? AND active = 1", (bot_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_owner_bots(self, owner_id: int):
        rows = self.conn.execute(
            "SELECT * FROM child_bots WHERE owner_id = ? AND active = 1 ORDER BY registered_at DESC",
            (owner_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_active_bots(self):
        rows = self.conn.execute(
            "SELECT * FROM child_bots WHERE active = 1"
        ).fetchall()
        return [dict(r) for r in rows]

    def deactivate_bot(self, bot_id: str, owner_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE child_bots SET active = 0 WHERE id = ? AND owner_id = ?",
            (bot_id, owner_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def token_exists(self, token: str) -> bool:
        row = self.conn.execute(
            "SELECT id FROM child_bots WHERE token = ?", (token,)
        ).fetchone()
        return row is not None

    # ── Links ─────────────────────────────────────────────────────────────────

    def create_link(self, child_bot_id: str, owner_id: int, amount: int, label: str) -> str:
        link_id = str(uuid.uuid4())[:8].upper()
        self.conn.execute(
            "INSERT INTO links (id, child_bot_id, owner_id, amount, label) VALUES (?,?,?,?,?)",
            (link_id, child_bot_id, owner_id, amount, label)
        )
        self.conn.commit()
        return link_id

    def save_invoice_url(self, link_id: str, url: str):
        self.conn.execute("UPDATE links SET invoice_url = ? WHERE id = ?", (url, link_id))
        self.conn.commit()

    def get_link(self, link_id: str):
        row = self.conn.execute(
            "SELECT * FROM links WHERE id = ? AND active = 1", (link_id,)
        ).fetchone()
        return dict(row) if row else None

    def set_custom_message(self, link_id: str, owner_id: int, message: str) -> bool:
        cur = self.conn.execute(
            "UPDATE links SET message = ? WHERE id = ? AND owner_id = ? AND active = 1",
            (message, link_id, owner_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_bot_links(self, child_bot_id: str, owner_id: int):
        rows = self.conn.execute("""
            SELECT l.*, COUNT(p.id) as payment_count
            FROM links l
            LEFT JOIN payments p ON p.link_id = l.id
            WHERE l.child_bot_id = ? AND l.owner_id = ? AND l.active = 1
            GROUP BY l.id
            ORDER BY l.created_at DESC
        """, (child_bot_id, owner_id)).fetchall()
        return [dict(r) for r in rows]

    def delete_link(self, link_id: str, owner_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE links SET active = 0 WHERE id = ? AND owner_id = ?",
            (link_id, owner_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ── Payments ──────────────────────────────────────────────────────────────

    def record_payment(self, link_id: str, child_bot_id: str, owner_id: int,
                       user_id: int, username: str, stars: int, fee_stars: int) -> int:
        cur = self.conn.execute(
            """INSERT INTO payments
               (link_id, child_bot_id, owner_id, user_id, username, stars, fee_stars)
               VALUES (?,?,?,?,?,?,?)""",
            (link_id, child_bot_id, owner_id, user_id, username, stars, fee_stars)
        )
        self.conn.commit()
        return cur.lastrowid

    def record_fee_invoice(self, payment_id: int, owner_id: int, fee_stars: int, invoice_url: str):
        self.conn.execute(
            "INSERT INTO fee_invoices (payment_id, owner_id, fee_stars, invoice_url) VALUES (?,?,?,?)",
            (payment_id, owner_id, fee_stars, invoice_url)
        )
        self.conn.commit()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_owner_stats(self, owner_id: int) -> dict:
        row = self.conn.execute("""
            SELECT
                COUNT(DISTINCT l.id) as total_links,
                COUNT(p.id) as total_payments,
                COALESCE(SUM(p.stars), 0) as total_stars,
                COALESCE(SUM(p.fee_stars), 0) as total_fees
            FROM links l
            LEFT JOIN payments p ON p.link_id = l.id
            WHERE l.owner_id = ?
        """, (owner_id,)).fetchone()
        return dict(row) if row else {}

    def get_platform_stats(self) -> dict:
        row = self.conn.execute("""
            SELECT
                COUNT(DISTINCT cb.id) as total_bots,
                COUNT(DISTINCT p.id) as total_payments,
                COALESCE(SUM(p.stars), 0) as total_stars,
                COALESCE(SUM(p.fee_stars), 0) as total_fees
            FROM child_bots cb
            LEFT JOIN payments p ON p.child_bot_id = cb.id
        """).fetchone()
        return dict(row) if row else {}


db = Database()
