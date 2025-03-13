from pathlib import Path
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'your-default-secret-key')

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'daphne',  # WebSocket desteği için en üstte olmalı
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party apps
    'rest_framework',
    'corsheaders',
    'channels',
    # Local apps
    'users',
    'profiles',
    'cvs',
    'social_django',
    'social_auth',
    'contact',
    'storages',
    'subscriptions',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cv_builder.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),  # Ana template dizini
        ],
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

WSGI_APPLICATION = 'cv_builder.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DEV_DATABASE_ENGINE'),
        'NAME': os.getenv('DEV_DATABASE_NAME'),
        'USER': os.getenv('DEV_DATABASE_USER'),
        'PASSWORD': os.getenv('DEV_DATABASE_PASSWORD'),
        'HOST': os.getenv('DEV_DATABASE_HOST'),
        'PORT': os.getenv('DEV_DATABASE_PORT'),
        'OPTIONS': {
            'sslmode': 'require',  # SSL gereklilik durumu
        },
    }
}


ALLOWED_DOCUMENT_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/png'
]




AUTH_USER_MODEL = 'users.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# CORS ayarları
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://cvbuilder.tech",
    "https://www.cvbuilder.tech",
]

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# WebSocket için CORS ayarları
CORS_ALLOWED_ORIGINS_WEBSOCKET = [
    "ws://localhost:3000",
    "ws://127.0.0.1:3000",
    "wss://localhost:3000",
    "wss://127.0.0.1:3000",
    "ws://localhost:8000",
    "ws://127.0.0.1:8000",
    "wss://cvbuilder.tech",
    "wss://www.cvbuilder.tech",
    "wss://web-production-9f41e.up.railway.app",
]

CSRF_COOKIE_SECURE = True  # HTTPS üzerinden
SESSION_COOKIE_SECURE = True  # HTTPS üzerinden
CSRF_COOKIE_SAMESITE = 'Lax'  # veya 'None' (HTTPS gerektirir)
SESSION_COOKIE_SAMESITE = 'Lax'  # veya 'None' (HTTPS gerektirir)


if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Storage ayarları
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": os.getenv('AWS_STORAGE_BUCKET_NAME'),
            "region_name": os.getenv('AWS_S3_REGION_NAME'),
            "endpoint_url": os.getenv('AWS_S3_ENDPOINT_URL'),
            "custom_domain": f"{os.getenv('AWS_STORAGE_BUCKET_NAME')}.{os.getenv('AWS_S3_REGION_NAME')}.cdn.digitaloceanspaces.com",
            "file_overwrite": False,
            "default_acl": "public-read",
            "querystring_auth": False,
            "location": "media",
        }
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
        "OPTIONS": {
            "bucket_name": os.getenv('AWS_STORAGE_BUCKET_NAME'),
            "region_name": os.getenv('AWS_S3_REGION_NAME'),
            "endpoint_url": os.getenv('AWS_S3_ENDPOINT_URL'),
            "custom_domain": f"{os.getenv('AWS_STORAGE_BUCKET_NAME')}.{os.getenv('AWS_S3_REGION_NAME')}.cdn.digitaloceanspaces.com",
            "file_overwrite": False,
            "default_acl": "public-read",
            "querystring_auth": False,
            "location": "static",
        }
    }
}

# AWS/DigitalOcean Spaces ayarları
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL')
AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.{AWS_S3_REGION_NAME}.cdn.digitaloceanspaces.com"

# Static ve Media dosya ayarları
STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Social Auth ayarları
AUTHENTICATION_BACKENDS = (
    'users.auth.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
    'social_core.backends.google.GoogleOAuth2',
    'social_core.backends.linkedin.LinkedinOAuth2',
)

# Google OAuth2 ayarları
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.getenv('GOOGLE_CLIENT_ID')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]

# LinkedIn OAuth2 ayarları
SOCIAL_AUTH_LINKEDIN_OAUTH2_KEY = os.getenv('LINKEDIN_CLIENT_ID')
SOCIAL_AUTH_LINKEDIN_OAUTH2_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
SOCIAL_AUTH_LINKEDIN_OAUTH2_SCOPE = ['r_liteprofile', 'r_emailaddress']
SOCIAL_AUTH_LINKEDIN_OAUTH2_FIELD_SELECTORS = ['email-address', 'formatted-name', 'public-profile-url', 'picture-url']

# Social Auth pipeline
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.social_auth.associate_by_email',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
)

# Social Auth ayarları
SOCIAL_AUTH_JSONFIELD_ENABLED = True
SOCIAL_AUTH_URL_NAMESPACE = 'social'
SOCIAL_AUTH_LOGIN_REDIRECT_URL = 'http://localhost:3000/dashboard'
SOCIAL_AUTH_LOGIN_ERROR_URL = 'http://localhost:3000/login'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
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
            'level': 'INFO',
            'propagate': False,
        },
        'users': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'storages': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# URL sonuna otomatik slash eklemek için
APPEND_SLASH = True

# URL patterns'da trailing slash kullanımını zorunlu kıl
TRAILING_SLASH = True 


OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Channels ve ASGI ayarları
ASGI_APPLICATION = 'cv_builder.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}

# WebSocket için authentication ayarları
CHANNEL_AUTHENTICATION = {
    'DEFAULT': 'channels.auth.SessionAuthentication',
}

CHANNEL_SETTINGS = {
    'PING_INTERVAL': 30,  # saniye
    'PING_TIMEOUT': 20,   # saniye
}

# WebSocket için güvenlik ayarları
CHANNEL_SECURITY = {
    'ALLOWED_HOSTS': [
        'localhost',
        '127.0.0.1',
        'cvbuilder.tech',
        'www.cvbuilder.tech',
        'web-production-9f41e.up.railway.app',
    ],
    'ALLOWED_ORIGINS': [
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'https://cvbuilder.tech',
        'https://www.cvbuilder.tech',
        'https://web-production-9f41e.up.railway.app',
        'ws://localhost:3000',
        'ws://127.0.0.1:3000',
        'wss://localhost:3000',
        'wss://127.0.0.1:3000',
        'ws://localhost:8000',
        'ws://127.0.0.1:8000',
        'wss://cvbuilder.tech',
        'wss://www.cvbuilder.tech',
        'wss://web-production-9f41e.up.railway.app',
    ],
}



SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    
    'JTI_CLAIM': 'jti',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}



# SMTP2GO Configuration
SMTP2GO_API_KEY = os.getenv('SMTP2GO_API_KEY')
SMTP2GO_FROM_EMAIL = os.getenv('SMTP2GO_FROM_EMAIL')

# Frontend URL for email verification links
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Iyzico Settings
IYZICO_API_KEY = os.environ.get('IYZICO_API_KEY', 'your_api_key')
IYZICO_SECRET_KEY = os.environ.get('IYZICO_SECRET_KEY', 'your_secret_key')
IYZICO_BASE_URL = os.environ.get('IYZICO_BASE_URL', 'https://sandbox-api.iyzipay.com')

# IYZIPAY Settings dict for easy access
IYZIPAY_SETTINGS = {
    'api_key': IYZICO_API_KEY,
    'secret_key': IYZICO_SECRET_KEY,
    'base_url': IYZICO_BASE_URL
}