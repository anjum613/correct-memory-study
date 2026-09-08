class TemplateLoader:
    def __init__(self, templates):
        self.templates = dict(templates)
        self.loaded = []

    def load(self, name):
        self.loaded.append(name)
        return self.templates[name]


class TemplateCatalog:
    BUILTINS = {"light": "system/light.html", "dark": "system/dark.html"}

    def builtin(self, theme):
        return self.BUILTINS[theme]
