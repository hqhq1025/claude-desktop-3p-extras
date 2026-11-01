#!/usr/bin/env bash
# Create a private CA and a server certificate for one hostname alias.
#
# Usage: scripts/gen-certs.sh [ALIAS] [OUT_DIR]
#   ALIAS   hostname in the gateway URL (default: local-gw)
#   OUT_DIR where to write the files (default: ./certs)
#
# Re-running keeps an existing CA and only re-issues the server certificate,
# so clients that already trust the CA keep working.
set -euo pipefail

alias_name="${1:-local-gw}"
out="${2:-./certs}"
mkdir -p "$out"
cd "$out"

if [[ ! -f ca.pem ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.pem -days 3650 \
    -subj "/CN=${alias_name} local CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
  chmod 600 ca.key
fi

cat > leaf.ext <<EOF
subjectAltName=DNS:${alias_name}
extendedKeyUsage=serverAuth
keyUsage=critical,digitalSignature,keyEncipherment
basicConstraints=CA:FALSE
EOF

openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=${alias_name}"
# macOS rejects server certificates valid for more than 825 days.
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out server.pem -days 800 -extfile leaf.ext
chmod 600 server.key
rm -f server.csr

openssl verify -CAfile ca.pem server.pem
echo "Wrote $(pwd)/{ca.pem,ca.key,server.pem,server.key}. Keep ca.key private."
