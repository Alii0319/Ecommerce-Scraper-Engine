import os
from pathlib import Path
from dotenv import load_dotenv
from django.template import context as template_context

# Base directory allocation
BASE_DIR = Path(__file__).resolve().parent.parent


def _patch_django_template_context_for_python314() -> None:
    """Work around Django 5.0 template context copying on Python 3.14."""

    def _safe_copy(self):
        duplicate = object.__new__(self.__class__)
        duplicate.__dict__ = self.__dict__.copy()
        duplicate.dicts = self.dicts[:]
        return duplicate

    template_context.BaseContext.__copy__ = _safe_copy


_patch_django_template_context_for_python314()

# Load environment variables explicitly from the root .env file
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Core Security Settings decoupled via environment states
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', '*').split(',')
    if host.strip()
]

DEFAULT_FRONTEND_ORIGINS = [
    'http://localhost',
    'http://127.0.0.1',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5174',
    'http://127.0.0.1:5174',
    'http://localhost:80',
    'http://127.0.0.1:80',
]


def _get_env_list(name: str, default_values: list[str]) -> list[str]:
    return [
        value.strip()
        for value in os.getenv(name, ','.join(default_values)).split(',')
        if value.strip()
    ]


CORS_ALLOWED_ORIGINS = _get_env_list('CORS_ALLOWED_ORIGINS', DEFAULT_FRONTEND_ORIGINS)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^http://localhost:\d+$',
    r'^http://127\.0\.0\.1:\d+$',
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = _get_env_list('CSRF_TRUSTED_ORIGINS', DEFAULT_FRONTEND_ORIGINS)

# Application Orchestration
INSTALLED_APPS = [
    # Daphne must override standard WSGI management layer
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-Party Infrastructure Frameworks
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_spectacular',
    'channels',
    
    # Granular Business Logic Layer Apps
    'authentication',
    'trackers',
    'analytics',
]

# Pipeline Processing Middleware Matrix
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Intercepts cross-origin calls early
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Root Routing Maps
ROOT_URLCONF = 'core.urls'

# Server Interface Gateways (Dual-Layer Configuration)
WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# UI Engines for Administration Interfaces
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Complete Relational Datastore Mapping using environment isolation
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

# Framework Extension Settings (DRF & Authentication Strategy)
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

# Real-Time WebSocket Channel Layer (Using decoupled Redis topology with InMemory fallback for local dev)
import redis

REDIS_URL = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1')

try:
    _r = redis.Redis.from_url(REDIS_URL, socket_timeout=1)
    _r.ping()
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
except Exception:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Swagger UI Documentation Meta Configurations
SPECTACULAR_SETTINGS = {
    'TITLE': 'E-Commerce Scraping & Analytics Engine API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Override Application Core Identity to utilize Custom User Model
AUTH_USER_MODEL = 'authentication.User'

# Standard Localization and Asset Handling Configuration
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles') 

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Celery Asynchronous Engine Cluster Operations Definitions
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = os.getenv('TIME_ZONE', 'UTC')

# Configure Periodic Tasks Schedules mapping matrices
CELERY_BEAT_SCHEDULE = {
    'dispatch-scraping-orchestration-every-4-hours': {
        'task': 'trackers.tasks.orchestrate_scraping_pipeline',
        'schedule': 14400.0,  # Corresponds exactly to 4 Hours standard interval sequence execution
    },
}