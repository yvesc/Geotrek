from .default import *

#
#  Django Tests
#..........................

TEST = True

TEST_EXCLUDE = ('django',)

LOGGING['handlers']['console']['level'] = 'CRITICAL'

LANGUAGE_CODE = 'en'

SOUTH_TESTS_MIGRATE = False # XXX Django 1.6 transactioni crash
