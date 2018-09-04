import os
import struct
import base64
import random

import eventlet

import msgpack
from cryptography import fernet


from simpleutil.log import log as logging
from simpleutil.utils import systemutils
from simpleutil.common.exceptions import InvalidArgument

from goperation.manager import exceptions


# Fernet byte indexes as as computed by pypi/keyless_fernet and defined in
# https://github.com/fernet/spec
TIMESTAMP_START = 1
TIMESTAMP_END = 9

LOG = logging.getLogger(__name__)


def create_key_directory(key_repository, user, group):
    """If the configured key directory does not exist, attempt to create it."""
    # if not os.access(key_repository, os.F_OK):
    if not os.path.exists(key_repository):
        LOG.info('key_repository does not appear to exist; attempting to create it')
        try:
            os.makedirs(key_repository, 0o700)
        except OSError:
            LOG.error('Failed to create [fernet_tokens] key_repository: either it '
                      'already exists or you don\'t have sufficient permissions to '
                      'create it')
        systemutils.chown(key_repository, user, group)
        systemutils.chmod(key_repository, 0700)


def initialize_key_repository(key_repository, max_active_keys,
                              user=None, group=None):
    """Create a key repository and bootstrap it with a key.
    """
    # make sure we have work to do before proceeding
    # if os.access(os.path.join(key_repository, '0'), os.F_OK):

    pkey = os.path.join(key_repository, '0')
    if os.path.exists(pkey) and os.path.isfile(pkey):
        LOG.info('Key repository is already initialized; aborting.')
        return

    # bootstrap an existing key
    create_new_key(key_repository, user, group)

    # ensure that we end up with a primary and secondary key
    rotate_keys(key_repository, max_active_keys, user, group)


def create_new_key(key_repository, user, group):
    """Securely create a new encryption key.

    Create a new key that is readable by the Keystone group and Keystone user.
    """
    key = fernet.Fernet.generate_key()  # key is bytes

    # Determine the file name of the new key
    key_file = os.path.join(key_repository, '0')
    with open(key_file, 'w') as f:
        f.write(key.decode('utf-8'))  # convert key to str for the file.
    if user and group:
        try:
            systemutils.chown(key_file, user, group)
        except:
            os.remove(key_file)
            raise

    LOG.info('Created a new key: %s' % key_file)


def rotate_keys(key_repository, max_active_keys, user=None, group=None):
    """Create a new primary key and revoke excess active keys.
    """
    # read the list of key files
    key_files = dict()
    for filename in os.listdir(key_repository):
        path = os.path.join(key_repository, filename)
        if os.path.isfile(path):
            try:
                key_id = int(filename)
            except ValueError:  # nosec : name isn't a number, ignore the file.
                pass
            else:
                key_files[key_id] = path

    LOG.info('Starting key rotation with %(count)s key files: %(list)s' %
             {'count': len(key_files), 'list': list(key_files.values())})

    # determine the number of the new primary key
    current_primary_key = max(key_files.keys())
    LOG.info('Current primary key is: %s' % current_primary_key)
    new_primary_key = current_primary_key + 1
    LOG.info('Next primary key will be: %s' % new_primary_key)

    # promote the next primary key to be the primary
    os.rename(
        os.path.join(key_repository, '0'),
        os.path.join(key_repository, str(new_primary_key)))
    key_files.pop(0)
    key_files[new_primary_key] = os.path.join(key_repository, str(new_primary_key))
    LOG.info('Promoted key 0 to be the primary: %s' % new_primary_key)

    # add a new key to the rotation, which will be the *next* primary
    create_new_key(key_repository, user, group)

    max_active_keys = max_active_keys
    # check for bad configuration
    if max_active_keys < 1:
        LOG.warning('max_active_keys must be at least 1 to maintain a primary key.')
        max_active_keys = 1

    # purge excess keys
    # Note that key_files doesn't contain the new active key that was created,
    # only the old active keys.
    keys = sorted(key_files.keys(), reverse=True)
    while len(keys) > (max_active_keys - 1):
        index_to_purge = keys.pop()
        key_to_purge = key_files[index_to_purge]
        LOG.info('Excess key to purge: %s' % key_to_purge)
        os.remove(key_to_purge)


def load_keys(key_repository, max_active_keys):
    """Load keys from disk into a list.

    The first key in the list is the primary key used for encryption. All
    other keys are active secondary keys that can be used for decrypting
    tokens.

    """

    # build a dictionary of key_number:encryption_key pairs
    keys = dict()
    for filename in os.listdir(key_repository):
        path = os.path.join(key_repository, str(filename))
        if os.path.isfile(path):
            with open(path, 'r') as key_file:
                try:
                    key_id = int(filename)
                except ValueError:  # nosec : filename isn't a number, ignore
                    # this file since it's not a key.
                    pass
                else:
                    keys[key_id] = key_file.read()

    if len(keys) != max_active_keys:
        # If there haven't been enough key rotations to reach max_active_keys,
        # or if the configured value of max_active_keys has changed since the
        # last rotation, then reporting the discrepancy might be useful. Once
        # the number of keys matches max_active_keys, this log entry is too
        # repetitive to be useful.
        LOG.info('Loaded %(count)d encryption keys (max_active_keys=%(max)d) '
                 'from: %(dir)s') % {'count': len(keys),
                                     'max': max_active_keys,
                                     'dir': key_repository}

    # return the encryption_keys, sorted by key number, descending
    return [keys[x] for x in sorted(keys.keys(), reverse=True)]


class FernetTokenFormatter(object):

    CONF = None


    def __init__(self, path, days):

        if not path:
            raise exceptions.FernetKeysNotFound()

        self.key_repository = path
        self.max_active_keys = days + 2

        self._fernet = self._crypto()
        if not self._fernet:
            raise exceptions.FernetKeysNotFound()
        eventlet.spawn_after(3600 + random.randint(-10, 10), self._reload)

        # FernetTokenFormatter.Fernet = self

    @staticmethod
    def restore_padding(token):
        mod_returned = len(token) % 4
        if mod_returned:
            missing_padding = 4 - mod_returned
            token += '=' * missing_padding
        return token

    @staticmethod
    def creation_time(restored_fernet_token):
        fernet_token = restored_fernet_token
        token_bytes = base64.urlsafe_b64decode(fernet_token.encode('utf-8'))

        # slice into the byte array to get just the timestamp
        timestamp_bytes = token_bytes[TIMESTAMP_START:TIMESTAMP_END]
        return struct.unpack(">Q", timestamp_bytes)[0]

    def _reload(self):
        try:
            self._fernet = self._crypto()
        except exceptions.FernetKeysNotFound:
            eventlet.spawn_after(60, self._reload)
        except Exception as e:
            if LOG.isEnabledFor(logging.DEBUG):
                LOG.exception('Reload fernet key error')
            else:
                LOG.error('Reload fernet key catch except excption %s' % e.__class__.__name__)
            eventlet.spawn_after(60, self._reload)
        else:
            eventlet.spawn_after(3600 + random.randint(-10, 10), self._reload)

    def _crypto(self):
        keys = load_keys(self.key_repository, self.max_active_keys)

        if not keys:
            raise exceptions.FernetKeysNotFound()

        fernet_instances = [fernet.Fernet(key) for key in keys]
        return fernet.MultiFernet(fernet_instances)

    @property
    def crypto(self):
        return self._fernet

    def pack(self, payload):
        serialized_payload = msgpack.packb(payload)
        return self.crypto.encrypt(serialized_payload).rstrip(b'=').decode('utf-8')

    def unpack(self, token):
        token = self.restore_padding(token)
        try:
            serialized_payload = self.crypto.decrypt(token.encode('utf-8'))
            payload = msgpack.unpackb(serialized_payload)
            payload['ctime'] = self.creation_time(token)
        except fernet.InvalidToken:
            raise InvalidArgument('This is not a recognized Fernet token')
        except struct.error:
            raise InvalidArgument('Get create time from Fernet token error')
        return  payload