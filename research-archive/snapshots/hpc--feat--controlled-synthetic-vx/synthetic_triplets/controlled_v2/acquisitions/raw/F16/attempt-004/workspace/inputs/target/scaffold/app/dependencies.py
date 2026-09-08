class ChildStore:
    def __init__(self, children):
        self.children = {child.child_id: child for child in children}

    def get(self, child_id):
        return self.children[child_id]
