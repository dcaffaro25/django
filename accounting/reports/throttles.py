"""DRF throttles for the AI endpoints.

Light touch for PR 12: per-user rate limit on the four AI endpoints so a
single user can't burn the shared key on a runaway loop. Full quota-with-
reset lives in a later PR once real usage patterns show it's needed.
"""

from rest_framework.throttling import UserRateThrottle


class AIEndpointThrottle(UserRateThrottle):
    """60 AI calls / minute per authenticated user.

    Rate declared here so ops don't need to add it to
    ``REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`` in settings. Override per
    environment with the env var ``AI_RATE_LIMIT`` (e.g. ``30/min``).
    """

    scope = "reports_ai"
    rate = "60/min"

    def __init__(self):
        # Allow an env-var override without touching settings.py. Validate
        # format: "<N>/<period>" where period is sec/min/hour/day.
        import os
        env_rate = os.getenv("AI_RATE_LIMIT")
        if env_rate and "/" in env_rate:
            self.rate = env_rate
        super().__init__()
