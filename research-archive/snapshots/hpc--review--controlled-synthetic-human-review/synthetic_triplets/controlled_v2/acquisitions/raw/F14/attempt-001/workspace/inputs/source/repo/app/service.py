def list_recent(database):
    column = "created_at"
    return database.execute(f"SELECT id, name FROM reports ORDER BY {column}")
