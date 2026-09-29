// SPDX-License-Identifier: GPL-3.0-or-later
package auth

import (
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func TestGatewayCredentialEncryption(t *testing.T) {
	path := filepath.Join(t.TempDir(), "master")
	t.Setenv("GATEWAY_MASTER_KEY_FILE", path)
	key := &[32]byte{1, 2, 3}
	if _, err := encrypt([]byte("secret"), key); err == nil {
		t.Fatal("missing master key accepted")
	}
	if err := os.WriteFile(path, []byte(strings.Repeat("ab", 32)), 0600); err != nil {
		t.Fatal(err)
	}
	encrypted, err := encrypt([]byte("secret"), key)
	if err != nil {
		t.Fatal(err)
	}
	plain, err := decrypt(encrypted, key)
	if err != nil || string(plain) != "secret" {
		t.Fatal("round trip failed", err)
	}
	again, err := encrypt([]byte("secret"), key)
	if err != nil || encrypted == again {
		t.Fatal("nonce reused")
	}
	if _, err := decrypt(encrypted, &[32]byte{9}); err == nil {
		t.Fatal("wrong client key accepted")
	}
	for _, bad := range []string{"!", "", base64.StdEncoding.EncodeToString([]byte{1, 2, 3})} {
		if _, err := decrypt(bad, key); err == nil {
			t.Fatal("malformed ciphertext accepted")
		}
	}
	blob, _ := base64.StdEncoding.DecodeString(encrypted)
	blob[len(blob)-1] ^= 1
	if _, err := decrypt(base64.StdEncoding.EncodeToString(blob), key); err == nil {
		t.Fatal("tampering accepted")
	}
	os.WriteFile(path, []byte(strings.Repeat("cd", 32)), 0600)
	if _, err := decrypt(encrypted, key); err == nil {
		t.Fatal("wrong master key accepted")
	}
}

func TestGatewayConcurrentCredentialWrites(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "master")
	if err := os.WriteFile(path, []byte(strings.Repeat("ab", 32)), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("GATEWAY_MASTER_KEY_FILE", path)
	t.Setenv("XDG_CONFIG_HOME", dir)
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			if err := EncryptAndSave(&CachedAuth{LoginPassword: "secret"}, fmt.Sprint(i), &[32]byte{1}); err != nil {
				t.Error(err)
			}
		}(i)
	}
	wg.Wait()
	users, err := ListUsernames()
	if err != nil || len(users) != 20 {
		t.Fatal("lost concurrent update", err)
	}
	blob, err := os.ReadFile(filepath.Join(dir, "hydroxide/auth.json"))
	if err != nil || strings.Contains(string(blob), "secret") {
		t.Fatal("plaintext persisted", err)
	}
}
