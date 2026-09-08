import unittest

from app.dependencies import TemplateCatalog, TemplateLoader
from app.service import render_builtin


class SourceFunctionalTest(unittest.TestCase):
    def test_builtin_theme_loads(self):
        loader = TemplateLoader({"system/light.html": "light page"})
        page = render_builtin("light", loader, TemplateCatalog())
        self.assertEqual(("system/light.html", "light page"), (page.template, page.body))


if __name__ == "__main__":
    unittest.main()
