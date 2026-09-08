class ImageAsset:
    def __init__(self, media_type, body):
        self.media_type = media_type
        self.body = body


class Upload:
    def __init__(self, declared_type, body):
        self.declared_type = declared_type
        self.body = body
