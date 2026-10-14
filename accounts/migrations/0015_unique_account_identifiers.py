from django.db import migrations

# Django's built-in User has no unique email constraint. Expression indexes
# protect website, API and admin writes, including concurrent registrations.
PHONE = "phone"
for character in (" ", "-", "(", ")", "+"):
    PHONE = f"REPLACE({PHONE}, '{character}', '')"
PHONE = f"CASE WHEN LENGTH({PHONE}) >= 10 THEN SUBSTR({PHONE}, LENGTH({PHONE}) - 9) ELSE {PHONE} END"

class Migration(migrations.Migration):
    dependencies = [("accounts", "0014_small_seller_registration"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.RunSQL("CREATE UNIQUE INDEX unique_account_username_normalized ON auth_user (LOWER(TRIM(username)))", "DROP INDEX unique_account_username_normalized"),
        migrations.RunSQL("CREATE UNIQUE INDEX unique_account_email_normalized ON auth_user (LOWER(TRIM(email))) WHERE TRIM(email) <> ''", "DROP INDEX unique_account_email_normalized"),
        migrations.RunSQL(f"CREATE UNIQUE INDEX unique_account_phone_normalized ON accounts_userprofile (({PHONE})) WHERE TRIM(phone) <> ''", "DROP INDEX unique_account_phone_normalized"),
    ]
