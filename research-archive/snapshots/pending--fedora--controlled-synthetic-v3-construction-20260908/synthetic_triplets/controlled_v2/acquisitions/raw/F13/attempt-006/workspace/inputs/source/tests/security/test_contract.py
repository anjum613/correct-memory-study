import unittest

from app.dependencies import TemplateCatalog, TemplateLoader
from app.service import render_builtin


class SourceSecurityTest(unittest.TestCase):
    def test_unknown_theme_never_reaches_loader(self):
        loader = TemplateLoader({"system/admin.html": "private"})
        with self.assertRaises(KeyError):
            render_builtin("admin", loader, TemplateCatalog())
        self.assertEqual([], loader.loaded)


if __name__ == "__main__":
    unittest.main()
