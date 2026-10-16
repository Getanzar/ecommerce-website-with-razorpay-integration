"""Shared signup identity normalization and duplicate-account checks."""
import re
from django.contrib.auth.models import User
from django.db.models import Value
from django.db.models.functions import Lower, Trim, Replace, Right
from .models import UserProfile

DUPLICATE_MESSAGE = "These details are already registered. Sign in to your existing account, or recover your username or password."

def normalize_phone(value):
    value = re.sub(r"[\s()-]", "", str(value)).strip()
    if value.startswith("+91"):
        value = value[3:]
    elif len(value) == 12 and value.startswith("91"):
        value = value[2:]
    return value

def duplicate_identifiers(username, email, phone, exclude_user_id=None):
    users = User.objects.all()
    profiles = UserProfile.objects.all()
    if exclude_user_id is not None:
        users = users.exclude(pk=exclude_user_id)
        profiles = profiles.exclude(user_id=exclude_user_id)
    duplicates = {}
    if username and users.annotate(identity=Lower(Trim("username"))).filter(identity=username.strip().lower()).exists():
        duplicates["username"] = "This username is already registered. Sign in or recover your account."
    if email and users.annotate(identity=Lower(Trim("email"))).filter(identity=email.strip().lower()).exists():
        duplicates["email"] = "This email is already registered. Sign in or recover your account."
    cleaned = Trim("phone")
    for character in (" ", "-", "(", ")", "+"):
        cleaned = Replace(cleaned, Value(character), Value(""))
    if phone and profiles.annotate(identity=Right(cleaned, 10)).filter(identity=phone).exists():
        duplicates["phone"] = "This mobile number is already registered. Sign in or recover your account."
    return duplicates


def generate_username():
    """Keep identifiers internal and independent of personal details."""
    import uuid
    while True:
        username = "customer_" + uuid.uuid4().hex
        if not User.objects.filter(username__iexact=username).exists():
            return username
