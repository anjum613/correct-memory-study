# External Flask-CORS evaluators

The functional oracle and defensive security witness import the candidate's
real `flask_cors/core.py` in a subprocess and call its CORS-header procedure
with fixed request dictionaries. Import-only stubs replace unavailable legacy
Flask, Six, and Werkzeug APIs; no snapshot is modified and no network or live
server is used.

These files remain outside the model-visible repository and are bound by the
family package hash.
