from .settings import *


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# The production history contains MySQL-specific RunSQL operations. Unit tests
# build current local app models directly so they remain portable on SQLite.
MIGRATION_MODULES = {
    'accounts': None,
    'activities': None,
}
