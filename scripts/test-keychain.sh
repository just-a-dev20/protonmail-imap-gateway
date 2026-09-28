#!/bin/sh
# Test the exact Go adapter without needing the rest of Bridge's C toolchain.
set -eu
repo=$(pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp upstream/helper_linux.go upstream/helper_linux_test.go "$tmp/"
cat > "$tmp/types_test.go" <<'GO'
package keychain
import "github.com/docker/docker-credential-helpers/credentials"
type Helpers map[string]func(string) (credentials.Helper, error)
GO
cd "$tmp"
go mod init gateway-keychain-tests
go get github.com/docker/docker-credential-helpers@v0.9.5
go test -v ./...
cd "$repo"
