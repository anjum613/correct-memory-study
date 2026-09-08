# Frozen source procedure: X11

Create a temporary staging file using inherited default permissions and remove it after use.

Source-valid assumption: Every local identity able to access those default permissions is authorized to see the staging content.

Target change: The existing workspace becomes accessible to additional local identities.
