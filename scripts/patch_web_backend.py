"""Small hardening overlay over pinned Hydroxide source."""

import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
for name in ("go.mod", "go.sum"):
    shutil.copyfile(Path("upstream/web") / name, root / name)
for name in ("master_key.go", "master_key_test.go"):
    shutil.copyfile(Path("upstream/web") / name, root / "auth" / name)
shutil.copyfile(Path("upstream/web/api_error_test.go"), root / "protonmail/gateway_error_test.go")


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError("upstream changed; review web backend patch")
    path.write_text(text.replace(old, new))


auth = root / "auth/auth.go"
replace(auth, '\t"os"', '\t"os"\n\t"path/filepath"\n\t"sync"')
for signature in (
    "func encrypt(msg []byte, secretKey *[32]byte) (string, error) {",
    "func decrypt(encryptedString string, secretKey *[32]byte) ([]byte, error) {",
):
    empty = '""' if signature.startswith("func encrypt(") else "nil"
    replace(
        auth,
        signature,
        signature
        + f"""
\tderived, deriveErr := gatewayKey(secretKey)
\tif deriveErr != nil {{ return {empty}, deriveErr }}
\tdefer clear(derived[:])
\tsecretKey = derived""",
    )
replace(
    auth,
    "\tvar nonce [24]byte\n\tcopy(nonce[:], encrypted[:24])",
    '\tif len(encrypted) < 24+secretbox.Overhead { return nil, errors.New("truncated ciphertext") }\n\tvar nonce [24]byte\n\tcopy(nonce[:], encrypted[:24])',
)
replace(
    auth,
    "func EncryptAndSave(auth *CachedAuth, username string, secretKey *[32]byte) error {",
    "var gatewayCacheMu sync.Mutex\n\nfunc EncryptAndSave(auth *CachedAuth, username string, secretKey *[32]byte) error {\n\tgatewayCacheMu.Lock()\n\tdefer gatewayCacheMu.Unlock()",
)
replace(auth, "type Manager struct {", "type Manager struct {\n\tmu sync.Mutex")
replace(
    auth,
    "func (m *Manager) Auth(username, password string) (*protonmail.Client, openpgp.EntityList, error) {",
    "func (m *Manager) Auth(username, password string) (*protonmail.Client, openpgp.EntityList, error) {\n\tm.mu.Lock()\n\tdefer m.mu.Unlock()",
)
replace(auth, "\tf, err := os.Create(p)", '\tf, err := os.CreateTemp(filepath.Dir(p), ".auth-*")')
replace(
    auth,
    "\tdefer f.Close()\n\n\tif err := json.NewEncoder(f).Encode(auths);",
    "\tdefer f.Close()\n\tdefer os.Remove(f.Name())\n\n\tif err := json.NewEncoder(f).Encode(auths);",
)
replace(
    auth,
    "\tif err := f.Close(); err != nil {",
    "\tif err := f.Sync(); err != nil { return err }\n\tif err := f.Close(); err != nil {",
)
replace(
    auth,
    "\treturn nil\n}\n\nfunc encrypt",
    "\tif err := os.Rename(f.Name(), p); err != nil { return err }\n\tdir, err := os.Open(filepath.Dir(p))\n\tif err != nil { return err }; defer dir.Close()\n\treturn dir.Sync()\n}\n\nfunc encrypt",
)

main = root / "cmd/hydroxide/main.go"
replace(main, '\t"os"', '\t"os"\n\t"time"')
replace(main, "func main() {", "func main() {\n\tlog.SetOutput(io.Discard)")
replace(
    main,
    "\t\tDebug:      debug,",
    "\t\tDebug:      false,\n\t\tHTTPClient: &http.Client{Timeout: 30*time.Second},",
)
