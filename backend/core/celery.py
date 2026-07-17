import os
from celery import Celery

# Set default Django settings module environment mapping
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Initialize system app interface with unique engine namespace
app = Celery('ecommerce_analytics_engine')

# Load structural variables directly from existing settings using CELERY namespace prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Automatically scan all local apps directories for asynchronous worker definitions (tasks.py)
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request Context Vector: {self.request!r}')