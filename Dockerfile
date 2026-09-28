# syntax=docker/dockerfile:1
FROM golang:1.26.7-bookworm AS bridge-build
RUN apt-get update && apt-get install -y --no-install-recommends git python3 libsecret-1-dev libfido2-dev libcbor-dev pkg-config && rm -rf /var/lib/apt/lists/*
WORKDIR /source
ARG BRIDGE_REVISION=87b5832e4fdaf30638c91a3b19f84c96e3f6a466
RUN git init bridge && cd bridge && git remote add origin https://github.com/ProtonMail/proton-bridge.git && git fetch --depth 1 origin "$BRIDGE_REVISION" && git checkout --detach FETCH_HEAD && test "$(git rev-parse HEAD)" = "$BRIDGE_REVISION"
COPY upstream/ /source/upstream/
COPY scripts/patch_upstream.py /source/scripts/patch_upstream.py
RUN python3 scripts/patch_upstream.py /source/bridge
WORKDIR /source/bridge
RUN go test ./pkg/keychain -run TestGatewayKeychain -count=1
RUN CGO_ENABLED=1 go build -trimpath -ldflags="-X github.com/ProtonMail/proton-bridge/v3/internal/constants.Version=3.27.0+gateway -X github.com/ProtonMail/proton-bridge/v3/internal/constants.Revision=${BRIDGE_REVISION}" -o /out/proton-bridge ./cmd/Desktop-Bridge
# Include the exact corresponding modified source, modules and their licenses.
RUN go mod vendor && tar --exclude=.git -czf /out/bridge-corresponding-source.tar.gz .

FROM python:3.13-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libsecret-1-0 libfido2-1 libcbor0.8 tini && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home gateway && mkdir /data && chown gateway:gateway /data
COPY --from=bridge-build /out/proton-bridge /usr/local/bin/proton-bridge
COPY --from=bridge-build /out/bridge-corresponding-source.tar.gz /usr/share/gateway/bridge-corresponding-source.tar.gz
WORKDIR /app
COPY gateway/ gateway/
COPY config.example.toml config.toml
COPY LICENSE /usr/share/gateway/LICENSE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GATEWAY_MASTER_KEY_FILE=/run/secrets/master_key
USER 10001:10001
EXPOSE 1993 1465
HEALTHCHECK --interval=30s --timeout=25s --start-period=60s --retries=3 CMD ["python", "-m", "gateway", "healthcheck"]
ENTRYPOINT ["/usr/bin/tini", "--", "python", "-m", "gateway"]
CMD ["serve"]

FROM runtime AS test
USER root
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
COPY tests/ tests/
USER 10001:10001
ENTRYPOINT ["python", "-m", "unittest", "discover", "-v"]

FROM runtime AS final
