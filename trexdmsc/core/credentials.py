"""
Credentials file: the webhooks, the email account, the Google Sheet service account
and the SSH access to the DAQ PC.

The file (config/credentials.toml, relative to the working directory) is not tracked
by git: copy config/credentials.example.toml and fill it in. Every section is
optional: without it, that feature is disabled (no Slack/Mattermost/email alerts, no
Google Sheet run list, no DAQ metrics).
"""
import os
import threading

import toml

CREDENTIALS_FILE = "config/credentials.toml"
CREDENTIALS_EXAMPLE_FILE = "config/credentials.example.toml"
# email settings file used before the credentials file (its [email] section moved there)
OLD_EMAIL_CONFIG_FILE = "email_config.toml"

_lock = threading.Lock()
_cache = {}


def load_credentials(filename=CREDENTIALS_FILE) -> dict:
    """
    The sections of the credentials file, {} if it is missing or invalid. The file
    is read once per process (every logger and device asks for it).
    """
    with _lock:
        if filename not in _cache:
            _cache[filename] = _read(filename)
        return _cache[filename]


def _read(filename):
    if not os.path.isfile(filename):
        print(f"No credentials file '{filename}' (copy {CREDENTIALS_EXAMPLE_FILE} and fill"
              f" it in): Slack/Mattermost/email alerts, Google Sheet and DAQ metrics disabled")
        sections = {}
    else:
        try:
            sections = toml.load(filename)
        except Exception as e:
            print(f"Error reading the credentials file '{filename}': {e}. Credentials disabled")
            sections = {}
    if "email" not in sections and os.path.isfile(OLD_EMAIL_CONFIG_FILE):
        print(f"'{OLD_EMAIL_CONFIG_FILE}' is no longer read: move its [email] section to"
              f" '{filename}' to receive the emails")
    return sections


def credentials_section(name, filename=CREDENTIALS_FILE) -> dict:
    """A section of the credentials file, {} if it is missing."""
    section = load_credentials(filename).get(name, {})
    return section if isinstance(section, dict) else {}
