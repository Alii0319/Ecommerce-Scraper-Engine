from .celery import app as celery_app

# Enforce explicit distribution module boundaries across runtime cycles
__all__ = ('celery_app',)