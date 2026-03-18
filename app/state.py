import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Iterable, List, Dict

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash TEXT UNIQUE,
  simhash INTEGER,
  author TEXT,
  text TEXT,
  url TEXT,
  created_ts INTEGER,
  status TEXT
);

CREATE TABLE IF NOT EXISTS queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER,
  scheduled_ts INTEGER,
  status TEXT
);

CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER,
  posted_ts INTEGER,
  url TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER,
  action TEXT,
  ts INTEGER
);
"""

@dataclass
class StateDB:
    path: str

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def init(self) -> None:
        with self._connect() as con:
            con.executescript(SCHEMA)

    def add_candidate(self, h: str, simhash: int, author: str, text: str, url: str) -> int | None:
        now = int(time.time())
        with self._connect() as con:
            try:
                cur = con.execute(
                    "INSERT INTO candidates(hash,simhash,author,text,url,created_ts,status) VALUES(?,?,?,?,?,?,?)",
                    (h, simhash, author, text, url, now, "new"),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def list_candidates(self, status: str = "new") -> List[Dict]:
        with self._connect() as con:
            cur = con.execute(
                "SELECT id,author,text,url,created_ts FROM candidates WHERE status=? ORDER BY created_ts DESC",
                (status,),
            )
            return [
                {"id": r[0], "author": r[1], "text": r[2], "url": r[3], "created_ts": r[4]}
                for r in cur.fetchall()
            ]

    def mark_status(self, cid: int, status: str) -> None:
        with self._connect() as con:
            con.execute("UPDATE candidates SET status=? WHERE id=?", (status, cid))

    def enqueue(self, cid: int, scheduled_ts: int) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO queue(candidate_id,scheduled_ts,status) VALUES(?,?,?)",
                (cid, scheduled_ts, "pending"),
            )

    def dequeue_ready(self, now_ts: int) -> List[int]:
        with self._connect() as con:
            cur = con.execute(
                "SELECT id, candidate_id FROM queue WHERE status='pending' AND scheduled_ts<=? ORDER BY scheduled_ts",
                (now_ts,),
            )
            rows = cur.fetchall()
            ids = []
            for qid, cid in rows:
                con.execute("UPDATE queue SET status='done' WHERE id=?", (qid,))
                ids.append(cid)
            return ids

    def record_post(self, cid: int, url: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO posts(candidate_id,posted_ts,url) VALUES(?,?,?)",
                (cid, int(time.time()), url),
            )

    def count_posts_today(self) -> int:
        now = int(time.time())
        start = now - (now % 86400)
        with self._connect() as con:
            cur = con.execute("SELECT COUNT(1) FROM posts WHERE posted_ts>=?", (start,))
            return int(cur.fetchone()[0])


    def count_queue_pending(self) -> int:
        with self._connect() as con:
            cur = con.execute("SELECT COUNT(1) FROM queue WHERE status='pending'")
            return int(cur.fetchone()[0])

    def list_queue_pending(self, limit: int = 10) -> List[Dict]:
        with self._connect() as con:
            cur = con.execute(
                """
                SELECT q.candidate_id, q.scheduled_ts, c.author, c.text, c.url
                FROM queue q
                JOIN candidates c ON c.id = q.candidate_id
                WHERE q.status='pending'
                ORDER BY q.scheduled_ts ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {
                    "candidate_id": r[0],
                    "scheduled_ts": r[1],
                    "author": r[2],
                    "text": r[3],
                    "url": r[4],
                }
                for r in rows
            ]


    def has_post(self, cid: int) -> bool:
        with self._connect() as con:
            cur = con.execute("SELECT COUNT(1) FROM posts WHERE candidate_id=?", (cid,))
            return int(cur.fetchone()[0]) > 0

    def is_in_queue(self, cid: int) -> bool:
        with self._connect() as con:
            cur = con.execute("SELECT COUNT(1) FROM queue WHERE candidate_id=? AND status IN ('pending','processing')", (cid,))
            return int(cur.fetchone()[0]) > 0

    def claim_ready(self, now_ts: int, limit: int = 10) -> List[Dict]:
        with self._connect() as con:
            cur = con.execute(
                "SELECT id, candidate_id FROM queue WHERE status='pending' AND scheduled_ts<=? ORDER BY scheduled_ts LIMIT ?",
                (now_ts, limit),
            )
            rows = cur.fetchall()
            items = []
            for qid, cid in rows:
                con.execute("UPDATE queue SET status='processing' WHERE id=?", (qid,))
                items.append({"queue_id": qid, "candidate_id": cid})
            return items

    def mark_queue_status(self, qid: int, status: str) -> None:
        with self._connect() as con:
            con.execute("UPDATE queue SET status=? WHERE id=?", (status, qid))
