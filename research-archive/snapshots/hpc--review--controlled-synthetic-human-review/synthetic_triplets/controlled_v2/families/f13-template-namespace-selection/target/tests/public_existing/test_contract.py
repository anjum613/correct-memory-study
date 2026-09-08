import unittest

from app.dependencies import TemplateCatalog, TemplateLoader
from app.service import render_page


class ExistingBehaviourTest(unittest.TestCase):
    def test_builtin_theme(self):
        loader = TemplateLoader({"system/light.html": "light page"})
        page = render_page("light", loader, TemplateCatalog())
        self.assertEqual("light page", page.body)


if __name__ == "__main__":
    unittest.main()
