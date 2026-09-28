# Security dependency overlay

`go.mod` and `go.sum` start from Bridge commit
`87b5832e4fdaf30638c91a3b19f84c96e3f6a466` and apply the following
security updates, including their module resolver changes:

* `golang.org/x/crypto v0.53.0` → `v0.55.0`:
  [GO-2026-6303 / CVE-2026-56854](https://pkg.go.dev/vuln/GO-2026-6303).
* `google.golang.org/grpc v1.82.1` → `v1.83.2`:
  [HTTP/2 memory exhaustion](https://github.com/grpc/grpc-go/security/advisories/GHSA-vp52-pcj8-j9qc)
  and [malformed xDS request crash](https://github.com/grpc/grpc-go/security/advisories/GHSA-2v4p-qf9q-27wj).

* `github.com/quic-go/quic-go v0.59.0` → `v0.59.1`:
  [HTTP/3 QPACK trailer expansion](https://github.com/quic-go/quic-go/security/advisories/GHSA-vvgj-x9jq-8cj9),
  additionally reported by GitHub Dependabot.

These were found by the project's actual image scan. Modules are updated even
where exploitability may depend on unused upstream features. No scanner
exceptions were added. The exact updated source and vendored module licenses
are retained in the image's corresponding-source archive.

The runtime uses Debian's maintained Python 3 package without pip or third-party
Python packages. The earlier Python base included scanner findings in bundled
Python package metadata; those packaging tools are unnecessary for this
standard-library-only application.
