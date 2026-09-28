// SPDX-License-Identifier: GPL-3.0-or-later
// Gateway replacement for Proton Bridge's Linux keychain selection.
package keychain

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/docker/docker-credential-helpers/credentials"
)

const (
	Pass              = "pass-app"
	SecretService     = "secret-service"
	SecretServiceDBus = "secret-service-dbus"
)

type encryptedHelper struct{}

func listHelpers() (Helpers, string) {
	return Helpers{"gateway-aes-gcm": func(string) (credentials.Helper, error) { return &encryptedHelper{}, nil }}, "gateway-aes-gcm"
}

func (h *encryptedHelper) transaction(update bool, fn func(map[string]credentials.Credentials) error) error {
	keyPath := os.Getenv("GATEWAY_MASTER_KEY_FILE")
	if keyPath == "" {
		return errors.New("master key file required")
	}
	raw, err := os.ReadFile(keyPath)
	if err != nil {
		return errors.New("cannot read master key")
	}
	key, err := hex.DecodeString(strings.TrimSpace(string(raw)))
	if err != nil || len(key) != 32 {
		return errors.New("master key must be 32 bytes in hex")
	}
	defer func() {
		for i := range key {
			key[i] = 0
		}
		for i := range raw {
			raw[i] = 0
		}
	}()
	block, err := aes.NewCipher(key)
	if err != nil {
		return err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return err
	}
	dir := os.Getenv("GATEWAY_KEYCHAIN_DIR")
	if dir == "" {
		return errors.New("keychain directory required")
	}
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	lock, err := os.OpenFile(filepath.Join(dir, "keychain.lock"), os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	defer lock.Close()
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); err != nil {
		return err
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	path := filepath.Join(dir, "keychain.enc")
	data := make(map[string]credentials.Credentials)
	sealed, err := os.ReadFile(path)
	if err == nil {
		n := aead.NonceSize()
		if len(sealed) < n {
			return errors.New("invalid encrypted keychain")
		}
		plain, err := aead.Open(nil, sealed[:n], sealed[n:], []byte("gateway-keychain-v1"))
		if err != nil {
			return errors.New("keychain authentication failed")
		}
		defer func() {
			for i := range plain {
				plain[i] = 0
			}
		}()
		if err := json.Unmarshal(plain, &data); err != nil {
			return errors.New("invalid keychain data")
		}
		if data == nil {
			return errors.New("invalid keychain data")
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := fn(data); err != nil {
		return err
	}
	if !update {
		return nil
	}
	plain, err := json.Marshal(data)
	if err != nil {
		return err
	}
	defer func() {
		for i := range plain {
			plain[i] = 0
		}
	}()
	nonce := make([]byte, aead.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return err
	}
	sealed = aead.Seal(nonce, nonce, plain, []byte("gateway-keychain-v1"))
	tmp, err := os.CreateTemp(dir, ".keychain-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err = tmp.Write(sealed); err != nil {
		tmp.Close()
		return err
	}
	if err = tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err = tmp.Close(); err != nil {
		return err
	}
	if err = os.Rename(tmp.Name(), path); err != nil {
		return err
	}
	d, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}

func (h *encryptedHelper) Add(c *credentials.Credentials) error {
	return h.transaction(true, func(m map[string]credentials.Credentials) error { m[c.ServerURL] = *c; return nil })
}
func (h *encryptedHelper) Delete(url string) error {
	return h.transaction(true, func(m map[string]credentials.Credentials) error { delete(m, url); return nil })
}
func (h *encryptedHelper) Get(url string) (string, string, error) {
	var c credentials.Credentials
	err := h.transaction(false, func(m map[string]credentials.Credentials) error {
		var ok bool
		c, ok = m[url]
		if !ok {
			return credentials.NewErrCredentialsNotFound()
		}
		return nil
	})
	return c.Username, c.Secret, err
}
func (h *encryptedHelper) List() (map[string]string, error) {
	out := make(map[string]string)
	err := h.transaction(false, func(m map[string]credentials.Credentials) error {
		for k, v := range m {
			out[k] = v.Username
		}
		return nil
	})
	return out, err
}
