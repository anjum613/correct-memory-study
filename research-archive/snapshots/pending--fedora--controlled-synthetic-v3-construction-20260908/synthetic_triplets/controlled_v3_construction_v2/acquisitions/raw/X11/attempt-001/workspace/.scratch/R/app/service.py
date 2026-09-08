"""Stage privately and grant access to the designated consumer."""


def run(workspace, content_bytes, fault=None):
    identity = None
    try:
        if fault == "create":
            raise OSError("controlled create failure")
        identity = workspace.create({"producer"}, content_bytes)
        if fault == "write":
            raise OSError("controlled write failure")
        if fault == "handoff":
            raise OSError("controlled handoff failure")
        workspace.permissions(identity, {"producer", "consumer"})
        content = workspace.read(identity, "consumer", fault=fault)
        if content is None:
            raise OSError("consumer access denied")
        return ("ok", content)
    except OSError:
        return ("error", None)
    finally:
        if identity is not None:
            workspace.remove(identity)
