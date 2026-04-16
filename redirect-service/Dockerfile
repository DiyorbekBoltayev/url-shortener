# syntax=docker/dockerfile:1.7

########################
# Stage 1 — builder
########################
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache ca-certificates tzdata git

WORKDIR /src

# Pre-cache modules (layer invalidated only when go.mod/go.sum change)
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

# Source
COPY . .

# Static, stripped, reproducible binary
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux \
    go build -trimpath -ldflags="-s -w -buildid=" \
    -o /app/redirect ./cmd/server

########################
# Stage 2 — runtime (distroless static, nonroot)
########################
FROM gcr.io/distroless/static-debian12:nonroot

# CA certs + tzdata already present in distroless/static.
COPY --from=builder /app/redirect /app/redirect

USER nonroot:nonroot
EXPOSE 8080

# Healthcheck uses the binary itself (`redirect healthcheck`) since distroless
# has no wget/curl. See docker-compose.yml for HEALTHCHECK wiring.
ENTRYPOINT ["/app/redirect"]
