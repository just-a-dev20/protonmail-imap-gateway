#!/bin/sh
# Generate development localhost TLS material and an independent volume key.
set -eu
umask 077
if [ -e secrets ]; then
  echo 'secrets already exists; refusing to overwrite keys' >&2
  exit 1
fi
mkdir -m 700 secrets
openssl rand -hex 32 > secrets/master_key
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
  -keyout secrets/tls_key.pem -out secrets/tls_cert.pem \
  -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1'
# Compose bind-mounted secrets retain host permissions. Protect the enclosing
# directory (0700) but permit the unprivileged container UID to read each file.
chmod 444 secrets/master_key secrets/tls_key.pem secrets/tls_cert.pem
if [ ! -e config.toml ]; then cp config.example.toml config.toml; fi
echo 'Store secrets/master_key separately from backups of the Docker volume.'
echo 'Trust secrets/tls_cert.pem in clients, or replace TLS files with your own certificate.'
