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
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-development-placeholder-key-for-local-testing')

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1' if DEBUG else '').split(',')
    if host.strip()
]

if not DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    if not os.getenv('DJANGO_SECRET_KEY') or SECRET_KEY.startswith(('django-insecure', 'insecure', 'change-me')):
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be configured with a secure key in production.")

    wildcard_host = chr(42)
    if not ALLOWED_HOSTS or any(host == wildcard_host for host in ALLOWED_HOSTS):
        raise ImproperlyConfigured("ALLOWED_HOSTS must be explicitly defined without wildcards in production.")

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


def _get_env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.lower() in ('true', '1', 'yes')


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
    'DEFAULT_THROTTLING_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
    },
}

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
}
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    # Nginx handles TLS termination; enable HSTS for browsers only
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = _get_env_bool('SECURE_SSL_REDIRECT', False)

# Real-Time WebSocket Channel Layer (Using Redis topology with opt-in InMemory for local testing)
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/1')
USE_IN_MEMORY_CHANNEL_LAYER = (
    os.getenv('USE_IN_MEMORY_CHANNEL_LAYER', 'False').lower() in ('true', '1', 'yes')
)

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

if DEBUG and USE_IN_MEMORY_CHANNEL_LAYER:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
                'capacity': 1500,
                'expiry': 60,
            },
        }
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
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = os.getenv('TIME_ZONE', 'UTC')
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_SOFT_TIME_LIMIT = 90
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Configure Periodic Tasks Schedules mapping matrices
CELERY_BEAT_SCHEDULE = {
    'orchestrate-scraping-every-four-hours': {
        'task': 'trackers.tasks.orchestrate_scraping_pipeline',
        'schedule': 14400.0,
    },
    'recover-undelivered-alerts-every-two-minutes': {
        'task': 'trackers.tasks.recover_undelivered_alerts',
        'schedule': 120.0,
    },
}

# Structured Console Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'trackers': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
