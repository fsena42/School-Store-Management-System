from django.db import connection


def fetch_one(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))


def fetch_all(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def execute(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


def insert(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.lastrowid
