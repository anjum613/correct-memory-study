import unittest

from app.dependencies import TemplateCatalog, TemplateLoader
from app.service import render_page


class RequestedFeatureTest(unittest.TestCase):
    def test_tenant_template(self):
        loader = TemplateLoader({
            "system/light.html": "light page",
            "tenant/welcome.html": "welcome",
        })
        page = render_page(
            "light", loader, TemplateCatalog(), template_name="tenant/welcome.html"
        )
        self.assertEqual(("tenant/welcome.html", "welcome"), (page.template, page.body))


if __name__ == "__main__":
    unittest.main()
