from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class UserProfile(models.Model):

    GENDER_CHOICES = [
        ("Male", "Male"),
        ("Female", "Female"),
        ("Other", "Other"),
        ("Prefer not to say", "Prefer not to say"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
    )

    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        blank=True,
    )

    date_of_birth = models.DateField(
        blank=True,
        null=True,
    )

    profile_picture = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True,
    )
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username
    
class EmailOTP(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="email_otp",
    )

    otp = models.CharField(
        max_length=6,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    expires_at = models.DateTimeField()

    attempts = models.PositiveIntegerField(
        default=0,
    )

    is_verified = models.BooleanField(
        default=False,
    )

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.email} OTP"