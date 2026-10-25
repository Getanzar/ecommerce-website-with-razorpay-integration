from django.conf import settings
from django.core.management import call_command
from django.db import migrations


def create_cache(apps, schema_editor):
    config = settings.CACHES["default"]
    tables = {"ziyamart_cache"}
    if config["BACKEND"].endswith("DatabaseCache"):
        tables.add(config["LOCATION"])
    for table in tables:
        call_command("createcachetable", table, database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0017_sellerprofile_aadhaar_image")]
    operations = [migrations.RunPython(create_cache, migrations.RunPython.noop)]
