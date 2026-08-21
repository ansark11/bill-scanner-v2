"""
In-memory fake of the subset of the supabase-py client used by this backend.

This exists so authorization/IDOR tests can assert on real data isolation
(e.g. "querying as user A never returns user B's rows") instead of just
mocking return values, which would hide a missing `.eq("user_id", ...)`
filter rather than catching it.

Only implements the query shapes actually used in routers/ and services/.
"""
import copy
import uuid
from types import SimpleNamespace


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeAuth:
    def __init__(self, valid_tokens: dict[str, str]):
        # token -> user_id
        self.valid_tokens = valid_tokens

    def get_user(self, token: str):
        user_id = self.valid_tokens.get(token)
        if user_id is None:
            return FakeResponse(None) if False else SimpleNamespace(user=None)
        return SimpleNamespace(user=SimpleNamespace(id=user_id))


class _NotProxy:
    """Supports the `.not_.is_(col, val)` chain used for IS NOT NULL."""

    def __init__(self, query):
        self._query = query

    def is_(self, col, val):
        self._query._filters.append(("not_is", col, val))
        return self._query


class FakeQuery:
    def __init__(self, db: dict, table_name: str):
        self._db = db
        self._table_name = table_name
        self._op = None
        self._payload = None
        self._filters: list[tuple] = []
        self._single = False
        self._order = None

    # -- verb methods --
    def select(self, cols="*"):
        self._op = "select"
        self._cols = cols
        return self

    def insert(self, payload: dict):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    # -- filter methods --
    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, vals))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    @property
    def not_(self):
        return _NotProxy(self)

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def single(self):
        self._single = True
        return self

    # -- execution --
    def _rows(self):
        return self._db.setdefault(self._table_name, [])

    def _matches(self, row):
        for kind, col, val in self._filters:
            if kind == "eq":
                if row.get(col) != val:
                    return False
            elif kind == "gte":
                if row.get(col) is None or row.get(col) < val:
                    return False
            elif kind == "lte":
                if row.get(col) is None or row.get(col) > val:
                    return False
            elif kind == "in":
                if row.get(col) not in val:
                    return False
            elif kind == "is":
                target = None if val in (None, "null") else val
                if row.get(col) != target:
                    return False
            elif kind == "not_is":
                target = None if val in (None, "null") else val
                if row.get(col) == target:
                    return False
        return True

    def _joined(self, row: dict) -> dict:
        """Handle the one embedded-relation shape this codebase uses:
        bills.select('*, billers(name, account_number)')."""
        if self._table_name == "bills" and "billers(" in getattr(self, "_cols", ""):
            row = copy.deepcopy(row)
            biller = next(
                (b for b in self._db.get("billers", []) if b["id"] == row.get("biller_id")),
                None,
            )
            row["billers"] = (
                {"name": biller["name"], "account_number": biller.get("account_number")}
                if biller
                else None
            )
        return row

    def execute(self):
        if self._op == "select":
            matched = [self._joined(r) for r in self._rows() if self._matches(r)]
            if self._order:
                col, desc = self._order
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._single:
                if len(matched) != 1:
                    raise Exception(
                        f"single() expected exactly 1 row for {self._table_name}, got {len(matched)}"
                    )
                return FakeResponse(matched[0])
            return FakeResponse(matched)

        if self._op == "insert":
            rows = self._rows()
            payload = self._payload
            payloads = payload if isinstance(payload, list) else [payload]
            created = []
            for p in payloads:
                new_row = dict(p)
                new_row.setdefault("id", str(uuid.uuid4()))
                rows.append(new_row)
                created.append(copy.deepcopy(new_row))
            return FakeResponse(created)

        if self._op == "update":
            updated = []
            for row in self._rows():
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(copy.deepcopy(row))
            return FakeResponse(updated)

        if self._op == "delete":
            rows = self._rows()
            remaining = [r for r in rows if not self._matches(r)]
            removed = [r for r in rows if self._matches(r)]
            rows[:] = remaining
            return FakeResponse(removed)

        raise RuntimeError("No operation set before execute()")


class FakeSupabase:
    def __init__(self, db: dict | None = None, valid_tokens: dict[str, str] | None = None):
        self.db = db if db is not None else {}
        self.auth = FakeAuth(valid_tokens or {})

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.db, name)
