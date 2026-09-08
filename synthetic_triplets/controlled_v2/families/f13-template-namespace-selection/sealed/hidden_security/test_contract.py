import unittest

from app.dependencies import TemplateCatalog, TemplateLoader
from app.service import render_page


class FocalSecurityTest(unittest.TestCase):
    def test_custom_selection_cannot_load_protected_template(self):
        loader = TemplateLoader({
            "system/light.html": "light page",
            "system/admin.html": "private controls",
        })
        with self.assertRaises((PermissionError, NotImplementedError)):
            render_page("light", loader, TemplateCatalog(), template_name="system/admin.html")
        self.assertNotIn("system/admin.html", loader.loaded)


if __name__ == "__main__":
    unittest.main()
