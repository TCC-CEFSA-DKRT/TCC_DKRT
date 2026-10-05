#!/bin/sh
set -eu
KEY_FILE="${BROKER_API_KEY_ENCRYPTION_KEYS_FILE:-/var/lib/auditor-secrets/broker_api_key_encryption_keys}"
if [ ! -s "$KEY_FILE" ]; then
  umask 077
  python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' > "$KEY_FILE.tmp"
  mv "$KEY_FILE.tmp" "$KEY_FILE"
fi
BROKER_API_KEY_ENCRYPTION_KEYS="$(cat "$KEY_FILE")"
export BROKER_API_KEY_ENCRYPTION_KEYS
exec "$@"
