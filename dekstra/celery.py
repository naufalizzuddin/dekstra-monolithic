import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dekstra.settings')

app = Celery('dekstra')

# ambil config dari Django settings (prefix CELERY_)
app.config_from_object('django.conf:settings', namespace='CELERY')

# auto detect tasks.py di semua app
app.autodiscover_tasks()