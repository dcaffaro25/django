# NORD/multitenancy/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from django.forms.models import model_to_dict

User = get_user_model()

@receiver(post_save, sender=User)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)




# A simple global dictionary to store changes
CHANGES_TRACKER = {
    "created": [],
    "updated": [],
    "deleted": []
}

@receiver(post_save)
def track_save(sender, instance, created, **kwargs):
    """
    Whenever any model instance is saved, log it to CHANGES_TRACKER
    if you want to track it. If you only care about certain models,
    you can check `sender` here.
    """
    # For example, if you only want to track changes for certain models:
    # if sender.__name__ not in ("Transaction", "JournalEntry", "Account"):
    #     return

    # Build a simple record of what was changed
    data = {
        "model": sender.__name__,
        "id": instance.pk,
        "created": created,
        "fields": model_to_dict(instance),
    }

    if created:
        CHANGES_TRACKER["created"].append(data)
    else:
        CHANGES_TRACKER["updated"].append(data)

@receiver(post_delete)
def track_delete(sender, instance, **kwargs):
    """
    Whenever a model instance is deleted, log it.
    """
    data = {
        "model": sender.__name__,
        "id": instance.pk,
        "fields": model_to_dict(instance),
    }
    CHANGES_TRACKER["deleted"].append(data)

def clear_changes():
    """
    Reset the CHANGES_TRACKER global dictionary.
    """
    CHANGES_TRACKER["created"].clear()
    CHANGES_TRACKER["updated"].clear()
    CHANGES_TRACKER["deleted"].clear()

def get_changes():
    """
    Return the current changes and then clear them out, or
    you can return a copy if you prefer to keep them.
    """
    # Make a shallow copy if you want to keep them
    changes_copy = {
        "created": list(CHANGES_TRACKER["created"]),
        "updated": list(CHANGES_TRACKER["updated"]),
        "deleted": list(CHANGES_TRACKER["deleted"]),
    }
    clear_changes()
    return changes_copy