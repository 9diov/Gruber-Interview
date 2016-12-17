import sqlite3
conn = None


def get_conn():
    global conn
    if (conn is None):
        conn = create_conn()
    return conn


def fetchone(cursor, query):
    cursor.execute(query)
    return cursor.fetchone()


def init(conn):
    cursor = conn.cursor()
    query = "SELECT name FROM sqlite_master \
               WHERE type='table' and name='passenger'"
    has_table = fetchone(cursor, query)
    if (has_table is None):
        query = "CREATE TABLE passenger(id INTEGER PRIMARY KEY,name TEXT)"
        cursor.execute(query)

    query = "SELECT name FROM sqlite_master \
               WHERE type='table' and name='driver'"
    has_table = fetchone(cursor, query)
    if (has_table is None):
        query = "CREATE TABLE driver(id INTEGER PRIMARY KEY, name TEXT)"
        cursor.execute(query)

    conn.commit()


def create_conn():
    conn = sqlite3.connect('gruber.db')
    init(conn)
    return conn


def insert_and_get_id(query, params):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(query, params)

    query = "SELECT last_insert_rowid()"
    cursor.execute(query)
    result = cursor.fetchone()
    id = None
    if (result is not None):
        id = result[0]
        conn.commit()
    else:
        conn.rollback()
    return id


def new_passenger(name):
    query = "INSERT INTO passenger(name) VALUES(?)"
    return insert_and_get_id(query, (name, ))


def new_driver(name):
    query = "INSERT INTO driver(name) VALUES(?)"
    return insert_and_get_id(query, (name, ))
