from django.db import transaction
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import UserProfile, SellerProfile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):

    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):

    UserProfile.objects.get_or_create(user=instance)

    instance.profile.save()

# Remove replaced/deleted identity documents after the database change commits.


@receiver(pre_save, sender=SellerProfile)
def remove_replaced_identity_image(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).values_list("aadhaar_image", flat=True).first()
    if previous and previous != instance.aadhaar_image.name:
        storage = sender._meta.get_field("aadhaar_image").storage
        transaction.on_commit(lambda: storage.delete(previous))


@receiver(post_delete, sender=SellerProfile)
def remove_deleted_identity_image(sender, instance, **kwargs):
    if instance.aadhaar_image:
        storage, name = instance.aadhaar_image.storage, instance.aadhaar_image.name
        transaction.on_commit(lambda: storage.delete(name))
