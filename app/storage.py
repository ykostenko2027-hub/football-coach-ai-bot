import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from app.models import RequestRecord


class BaseStorage(ABC):
    @abstractmethod
    def init_schema(self) -> None:
        pass

    @abstractmethod
    def save_record(self, record: RequestRecord) -> None:
        pass

    @abstractmethod
    def get_record(self, request_id: str) -> RequestRecord | None:
        pass

    @abstractmethod
    def list_records(self, limit: int = 20) -> list[RequestRecord]:
        pass

    @abstractmethod
    def ping(self) -> bool:
        pass


class SQLiteStorage(BaseStorage):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._mem_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            path = Path(db_path)
            if path.parent:
                path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> tuple[sqlite3.Connection, bool]:
        if self._mem_conn is not None:
            return self._mem_conn, False
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return conn, True

    def init_schema(self) -> None:
        conn, close_conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS coach_requests (
                    request_id TEXT PRIMARY KEY,
                    user_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    result_json TEXT,
                    error_kind TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            if close_conn:
                conn.close()

    def save_record(self, record: RequestRecord) -> None:
        conn, close_conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO coach_requests (
                    request_id, user_text, status, provider, model,
                    latency_ms, result_json, error_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.request_id,
                    record.user_text,
                    record.status,
                    record.provider,
                    record.model,
                    record.latency_ms,
                    record.result_json,
                    record.error_kind,
                    record.created_at,
                ),
            )
            conn.commit()
        finally:
            if close_conn:
                conn.close()

    def get_record(self, request_id: str) -> RequestRecord | None:
        conn, close_conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT request_id, user_text, status, provider, model,
                       latency_ms, result_json, error_kind, created_at
                FROM coach_requests WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            return RequestRecord(
                request_id=row[0],
                user_text=row[1],
                status=row[2],
                provider=row[3],
                model=row[4],
                latency_ms=row[5],
                result_json=row[6],
                error_kind=row[7],
                created_at=row[8],
            )
        finally:
            if close_conn:
                conn.close()

    def list_records(self, limit: int = 20) -> list[RequestRecord]:
        conn, close_conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT request_id, user_text, status, provider, model,
                       latency_ms, result_json, error_kind, created_at
                FROM coach_requests ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                RequestRecord(
                    request_id=row[0],
                    user_text=row[1],
                    status=row[2],
                    provider=row[3],
                    model=row[4],
                    latency_ms=row[5],
                    result_json=row[6],
                    error_kind=row[7],
                    created_at=row[8],
                )
                for row in rows
            ]
        finally:
            if close_conn:
                conn.close()

    def ping(self) -> bool:
        conn, close_conn = self._connect()
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False
        finally:
            if close_conn:
                conn.close()
