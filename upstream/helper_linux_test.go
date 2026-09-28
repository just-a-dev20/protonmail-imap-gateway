// SPDX-License-Identifier: GPL-3.0-or-later
package keychain

import (
	"bytes"
	"github.com/docker/docker-credential-helpers/credentials"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestGatewayKeychain(t *testing.T) {
	dir := t.TempDir()
	key := filepath.Join(dir, "master")
	if err := os.WriteFile(key, []byte(strings.Repeat("ab", 32)), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("GATEWAY_MASTER_KEY_FILE", key)
	t.Setenv("GATEWAY_KEYCHAIN_DIR", dir)
	h := &encryptedHelper{}
	c := &credentials.Credentials{ServerURL: "test", Username: "alice", Secret: "never-store-plaintext"}
	if err := h.Add(c); err != nil {
		t.Fatal(err)
	}
	u, s, err := h.Get("test")
	if err != nil || u != c.Username || s != c.Secret {
		t.Fatal("round trip failed", err)
	}
	path := filepath.Join(dir, "keychain.enc")
	blob, _ := os.ReadFile(path)
	if bytes.Contains(blob, []byte(c.Secret)) {
		t.Fatal("plaintext on disk")
	}
	first := append([]byte(nil), blob...)
	if err := h.Add(c); err != nil {
		t.Fatal(err)
	}
	blob, _ = os.ReadFile(path)
	if bytes.Equal(first, blob) {
		t.Fatal("nonce reused")
	}
	listed, err := h.List()
	if err != nil || listed["test"] != "alice" {
		t.Fatal("list failed")
	}
	blob[len(blob)-1] ^= 1
	os.WriteFile(path, blob, 0600)
	if _, _, err := h.Get("test"); err == nil {
		t.Fatal("tampering accepted")
	}
	os.WriteFile(path, first, 0600)
	os.WriteFile(key, []byte(strings.Repeat("cd", 32)), 0600)
	if _, _, err := h.Get("test"); err == nil {
		t.Fatal("wrong key accepted")
	}
	os.WriteFile(key, []byte(strings.Repeat("ab", 32)), 0600)
	if err := h.Delete("test"); err != nil {
		t.Fatal(err)
	}
	if _, _, err := h.Get("test"); err == nil {
		t.Fatal("deleted entry survived")
	}
}
