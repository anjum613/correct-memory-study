from app.models import ReportRow


class Database:
    def __init__(self):
        self.queries = []
        self.compromised = False

    def execute(self, query):
        self.queries.append(query)
        self.compromised = ";" in query
        return [ReportRow(1, "weekly")]
