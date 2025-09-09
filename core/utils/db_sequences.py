# utils/db_sequences.py
from django.db import connection
from django.core.management.color import no_style

def reset_pk_sequences(models):
    """
    Reset auto-increment sequences so the next ID = MAX(id) (or 1 if empty).
    Works on Postgres/MySQL/SQLite using Django's vendor-aware SQL.
    """
    sql_list = connection.ops.sequence_reset_sql(no_style(), models)
    if not sql_list:
        return
    with connection.cursor() as cursor:
        for sql in sql_list:
            cursor.execute(sql)
