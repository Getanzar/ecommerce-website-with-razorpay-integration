from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateIdentityStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=Path(settings.PRIVATE_MEDIA_ROOT) / "seller_identity")

    def url(self, name):
        raise ValueError("Identity images require authenticated admin access.")


def identity_upload_path(instance, filename):
    return f"{uuid4().hex}{Path(filename).suffix.lower()}"
