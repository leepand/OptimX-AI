import hirlite
import os

from .sfdb import Database


class FileStore:
    def __init__(self, db_file, db_type="rlite", return_type="dbobj"):
        self.db_file = db_file
        self.db_type = db_type
        self.return_type = return_type

    def build_cache_store(self):
        VALID_DB_TYPES = ("rlite", "redis", "diskcache", "sfdb")
        assert (
            self.db_type in VALID_DB_TYPES
        ), f"DB cache type {self.db_type} not supported. Valid db types are {VALID_DB_TYPES}"
        VALID_RETURN_TYPES = ("dblink", "dbobj")
        assert (
            self.return_type in VALID_RETURN_TYPES
        ), f"Return type {self.return_type} not supported. Valid return types are {VALID_RETURN_TYPES}"

        if self.db_type == "rlite":
            db_store = hirlite.Rlite(self.db_file, encoding="utf8")
        elif self.db_type == "diskcache":
            import diskcache as dc

            db_store = dc.Cache(self.db_file)
        elif self.db_type == "sfdb":
            db_store = Database(filename=self.db_file)

        else:
            db_store = None
        if self.return_type == "dblink":
            return self.db_file
        else:
            return db_store
