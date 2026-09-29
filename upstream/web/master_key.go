// SPDX-License-Identifier: GPL-3.0-or-later
// Bind Hydroxide's credential encryption to the external gateway master secret.
package auth

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"strings"

	"golang.org/x/crypto/hkdf"
)

func gatewayKey(clientKey *[32]byte) (*[32]byte, error) {
	raw, err := os.ReadFile(os.Getenv("GATEWAY_MASTER_KEY_FILE"))
	if err != nil {
		return nil, errors.New("gateway master key unavailable")
	}
	master, err := hex.DecodeString(strings.TrimSpace(string(raw)))
	if err != nil || len(master) != 32 {
		return nil, errors.New("invalid gateway master key")
	}
	defer func() { clear(raw); clear(master) }()
	var key [32]byte
	reader := hkdf.New(sha256.New, clientKey[:], master, []byte("gateway-web-credentials-v1"))
	if _, err := io.ReadFull(reader, key[:]); err != nil {
		return nil, err
	}
	return &key, nil
}
