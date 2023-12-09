import sqlite3
import os
from hashlib import md5, sha256
import random

from optimx.utils.file_utils import data_dir


DB_FILE = os.path.join(data_dir(), "account.db")


def create_connection(db_file):
    """create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Exception as e:
        print("error connecting to db")

    return conn


def create_table(db_name=DB_FILE):
    conn = create_connection(db_name)
    mycur = conn.cursor()
    mycur.execute(
        """CREATE TABLE IF NOT EXISTS "Account" (
            "fullName"	TEXT,
            "Email"	TEXT,
            "Password"	TEXT,
            "SessionObject"	TEXT
        );"""
    )


create_table()


class DB:
    code = """Return Code:
            [0][0] : Full Name
            [0][1] : Email
            [0][2] : Password
        """
    conn = create_connection(db_file=DB_FILE)
    cursor = conn.cursor()

    def create(fullName, Email, Password):
        """CREATE TABLE "Account" (
            "fullName"	TEXT,
            "Email"	TEXT,
            "Password"	TEXT,
            "SessionObject"	TEXT
        );"""
        Password = md5(Password.encode()).hexdigest()
        UID = sha256(f"{fullName}-{Email}-{Password}".encode("utf-8")).hexdigest()
        PID = "1000" + str(random.randint(1111, 9999))
        Session_code = str(random.randint(1111, 9999))
        Session_Obj = f"{UID}-{PID}-{Email}-{Session_code}"
        checkAccount = DB.cursor.execute(
            f"SELECT * FROM Account WHERE Email = '{Email}'"
        ).fetchall()
        if len(checkAccount) == 0:
            DB.cursor.execute(
                f"INSERT INTO Account VALUES('{fullName}', '{Email}', '{Password}','{Session_Obj}')"
            )
            DB.conn.commit()
            return 201
        elif checkAccount[0][1] == Email:
            return 302

    def read(Email):
        values = DB.cursor.execute(
            f"SELECT * FROM Account WHERE Email = '{Email}'"
        ).fetchall()
        if len(values) == 0:
            return "User not found"
        else:
            return values

    def get_session(Email):
        """Return code
        [0] = UID
        [1] = PID
        [2] = Email
        [3] = Session Code
        """
        session_obj = (
            DB.cursor.execute(
                f"SELECT SessionObject FROM Account WHERE Email = '{Email}'"
            )
            .fetchall()[0][0]
            .split("-")
        )
        return session_obj
