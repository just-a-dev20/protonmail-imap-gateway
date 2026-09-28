"""Apply small, reviewable patches to the pinned GPL upstream source."""

import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1])
for name in ("go.mod", "go.sum"):
    shutil.copyfile(pathlib.Path("upstream") / name, root / name)
for name in ("helper_linux.go", "helper_linux_test.go"):
    shutil.copyfile(pathlib.Path("upstream") / name, root / "pkg/keychain" / name)
path = root / "internal/logging/logging.go"
text = path.read_text()
start = text.index("\tlogrus.SetFormatter(", text.index("func Init("))
end = text.index("\n}\n", start)
text = (
    text[:start]
    + """\t// Gateway: upstream logs may contain human-verification tokens.
\tlogrus.SetOutput(io.Discard)
\tlogrus.StandardLogger().ReplaceHooks(logrus.LevelHooks{})
\tlogrus.SetLevel(logrus.PanicLevel)
\treturn nil, nil"""
    + text[end:]
)
path.write_text(text)

# Fail closed instead of using the desktop application's insecure fallback.
path = root / "internal/app/vault.go"
text = path.read_text()
marker = "if key, helper, err := loadVaultKey(vaultDir, keychains, featureFlags); err != nil {"
start = text.index(marker) + len(marker)
end = text.index("\n\t} else {", start)
text = (
    text[:start]
    + '\n\t\treturn nil, false, nil, fmt.Errorf("secure keychain unavailable: %w", err)'
    + text[end:]
)
path.write_text(text)

path = root / "internal/vault/types_settings.go"
text = path.read_text()
for old, new in (
    ("IMAPSSL:  false", "IMAPSSL:  true"),
    ("SMTPSSL:  false", "SMTPSSL:  true"),
    ("AutoUpdate:        true", "AutoUpdate:        false"),
):
    if text.count(old) != 1:
        raise RuntimeError("upstream defaults changed; review patch")
    text = text.replace(old, new)
path.write_text(text)
