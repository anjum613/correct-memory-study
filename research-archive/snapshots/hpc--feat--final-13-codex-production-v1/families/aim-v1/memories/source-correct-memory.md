# Source-correct procedural memory

Source repository: `aimhubio/aim`
Source task: `Move the Flask server to main repo to support 'docker'less UI`
Source revision: `dfd8368c7eb01142af69ed27cfebde0697110876`

## Procedure from the frozen source solution

Use the exact source implementation artifacts below as the procedure. Their bytes were verified against the frozen source snapshot.

### `aim/web/app/views.py`

Selection basis: complete static-file route module registered by the source-visible Flask application

````python
import os

from flask import Blueprint, send_from_directory
from flask_restful import Api, Resource


general_bp = Blueprint('general', __name__)
general_api = Api(general_bp)


def serve_wrong_urls(e):
    from aim.web.run import application
    static_dir = os.path.join(os.path.dirname(application.root_path), 'ui', 'build')
    return send_from_directory(static_dir, 'index.html'), 200


@general_api.resource('/')
class ServeMainPage(Resource):
    def get(self, path=None):
        from aim.web.run import application
        static_dir = os.path.join(os.path.dirname(application.root_path), 'ui', 'build')
        return send_from_directory(static_dir, 'index.html')


@general_api.resource('/static-files/<path:path>')
class ServeStaticFiles(Resource):
    def get(self, path):
        from aim.web.run import application
        static_dir = os.path.join(os.path.dirname(application.root_path), 'ui', 'build')
        return send_from_directory(static_dir, path)


@general_api.resource('/static/<exp_name>/<commit_hash>/media/images/<path>')
class ServeImages(Resource):
    def get(self, exp_name, commit_hash, path):
        images_dir = os.path.join(os.getcwd(), '.aim',
                                  exp_name, commit_hash,
                                  'objects', 'media', 'images')
        return send_from_directory(images_dir, path)
````

## Source-visible validation

The frozen source validation passed: 1 passed, 0 failed, 0 skipped.
