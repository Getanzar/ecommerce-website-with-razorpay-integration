from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateEvidenceStorage(FileSystemStorage):
    """Never expose delivery evidence under the public MEDIA_URL."""
    def __init__(self):
        super().__init__(location=getattr(settings, "PRIVATE_MEDIA_ROOT", Path(settings.BASE_DIR) / "private_media"))

    def url(self, name):
        raise ValueError("Delivery evidence requires an authenticated operations download.")
