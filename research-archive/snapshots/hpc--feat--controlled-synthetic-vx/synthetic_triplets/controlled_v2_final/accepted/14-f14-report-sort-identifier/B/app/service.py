def list_reports(database, sort_column=None):
    column = "created_at"
    return database.execute(f"SELECT id, name FROM reports ORDER BY {column}")
