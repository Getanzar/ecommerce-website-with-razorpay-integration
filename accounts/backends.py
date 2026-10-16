from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Case, Q, When
from django.db.models.functions import Lower, Trim


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identity = (username or kwargs.get("email") or "").strip()
        if not identity or password is None:
            return None
        # A legacy username may itself look like another user's email. Test
        # both matching accounts rather than silently selecting the wrong one.
        matches = User.objects.annotate(login_email=Lower(Trim("email")), login_username=Lower(Trim("username"))).filter(Q(login_email=identity.lower()) | Q(login_username=identity.lower())).order_by(Case(When(login_email=identity.lower(), then=0), default=1), "pk")
        for user in matches:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        if not matches:
            User().set_password(password)
        return None
