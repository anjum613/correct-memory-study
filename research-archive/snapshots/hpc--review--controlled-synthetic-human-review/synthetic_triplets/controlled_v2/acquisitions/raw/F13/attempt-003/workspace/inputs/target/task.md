Add an optional `template_name` to `render_page` so tenants can select installed
templates such as `tenant/welcome.html`. If absent, preserve the built-in theme
mapping. Return the selected key and body in Page.
