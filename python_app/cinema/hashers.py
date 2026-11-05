"""Read-only legacy verifier; successful Django login upgrades the hash to PBKDF2."""
import re
import bcrypt
from django.contrib.auth.hashers import BasePasswordHasher, mask_hash
from django.utils.translation import gettext_noop as _


class LaravelBCryptPasswordHasher(BasePasswordHasher):
    algorithm = 'laravel_bcrypt'

    def encode(self, password, salt):
        raise NotImplementedError('Legacy hashes are imported only, never generated.')

    def verify(self, password, encoded):
        prefix = self.algorithm + '$'
        if not encoded.startswith(prefix):
            return False
        legacy = encoded[len(prefix):]
        if not re.fullmatch(r'\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}', legacy):
            return False
        try:
            # PHP bcrypt historically truncates at 72 bytes; bcrypt 5 rejects longer input.
            return bcrypt.checkpw(password.encode('utf-8')[:72], legacy.encode('ascii'))
        except (ValueError, TypeError):
            return False

    def safe_summary(self, encoded):
        return {_('algorithm'): self.algorithm, _('hash'): mask_hash(encoded.split('$', 1)[-1])}

    def must_update(self, encoded):
        return True
