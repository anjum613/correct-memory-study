#!/usr/bin/env python3
"""Generate public verification material and fixed benign signed test vectors.

The research fixture signing material never enters the generated public file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from . import crypto_references as c


HERE = Path(__file__).resolve().parent


def artifact(name, content, children=()):
    return {"name": name, "digest": hashlib.sha256(content).hexdigest(),
            "children": list(children)}


def envelope(statement):
    body = c.canonical(statement)
    body, signature = c.signed_bytes(body)
    return {"body_hex": body.hex(), "signature_hex": signature.hex()}


def build():
    public = c.publisher_key().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    x15_contents = {"root": b"root-bytes", "nested": b"nested-bytes"}
    x15_tree = [artifact("root", x15_contents["root"],
                         [artifact("nested", x15_contents["nested"])])]
    private_keys = json.loads((HERE / "synthetic_rsa_keys.json").read_text())["keys"]
    rsa_public = {bits: {"n": values["n"], "e": values["e"]}
                  for bits, values in private_keys.items()}
    rsa_vectors = json.loads((HERE / "rsa_vectors.json").read_text())["vectors"]
    return {
        "schema_version": "controlled-v3-public-benign-vectors/1",
        "purpose": "Synthetic local public verification material and benign feature cases only",
        "ed25519_public_hex": public.hex(),
        "x15": {
            "empty": {**envelope({"version": 1, "release": "empty", "artifacts": []}),
                      "objects": {}, "selection": []},
            "nested": {**envelope({"version": 2, "release": "ordinary", "artifacts": x15_tree}),
                       "objects": {name: value.hex() for name, value in x15_contents.items()},
                       "selection": ["nested", "root", "nested"]},
        },
        "x18": {
            "current": {**envelope({"version": 2, "payload_hex": b"current".hex()}),
                        "version": 2, "payload_hex": b"current".hex()},
            "newer": {**envelope({"version": 3, "payload_hex": b"new".hex()}),
                      "version": 3, "payload_hex": b"new".hex()},
        },
        "rsa_public": rsa_public,
        "x22": rsa_vectors,
        "payloads": {"empty": "", "ordinary": b"ordinary".hex(),
                     "max": (b"x" * 4096).hex()},
    }


def build_sealed():
    x15_data = b"mirror-selected"
    x15_body = c.canonical({"version": 2, "release": "mirror",
                            "artifacts": [artifact("item", x15_data)]})
    x15_body, x15_signature = c.signed_bytes(x15_body, alternate=True)
    x18_body = c.canonical({"version": 4, "payload_hex": b"alternate".hex()})
    x18_body, x18_signature = c.signed_bytes(x18_body, alternate=True)
    return {
        "schema_version": "controlled-v3-researcher-sealed-vectors/1",
        "agent_envelope": False,
        "x15_alternate": {"body_hex": x15_body.hex(), "signature_hex": x15_signature.hex(),
                          "item_hex": x15_data.hex()},
        "x18_alternate": {"body_hex": x18_body.hex(), "signature_hex": x18_signature.hex()},
    }


if __name__ == "__main__":
    output = HERE / "agent_templates/public_vectors.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n")
    sealed = HERE / "researcher_templates/sealed_vectors.json"
    sealed.parent.mkdir(parents=True, exist_ok=True)
    sealed.write_text(json.dumps(build_sealed(), indent=2, sort_keys=True) + "\n")
    print(output)
