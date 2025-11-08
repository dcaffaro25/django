from django.apps import AppConfig


class FeedbackConfig(AppConfig):
    """Configuration class for the feedback app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'feedback'
    verbose_name = 'Feedback'