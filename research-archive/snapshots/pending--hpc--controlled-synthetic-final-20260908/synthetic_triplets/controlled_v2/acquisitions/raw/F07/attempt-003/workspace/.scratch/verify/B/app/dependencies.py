class Response:
    def __init__(self):
        self.headers = {}

    def set_header(self, name, value):
        lines = value.split("\r\n")
        self.headers[name] = lines[0]
        for line in lines[1:]:
            if ":" in line:
                extra_name, extra_value = line.split(":", 1)
                self.headers[extra_name.strip()] = extra_value.strip()
