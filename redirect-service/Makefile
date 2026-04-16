.PHONY: help build run test test-race cover lint fmt tidy vet docker-build up down logs clean

BINARY := redirect
PKG    := ./...
IMAGE  := urlshortener/redirect-service:latest

help:
	@echo "Targets:"
	@echo "  build         compile the binary into ./bin/$(BINARY)"
	@echo "  run           go run ./cmd/server"
	@echo "  test          go test $(PKG)"
	@echo "  test-race     go test -race -count=1 $(PKG)"
	@echo "  cover         go test -coverprofile=coverage.out $(PKG)"
	@echo "  lint          golangci-lint run"
	@echo "  fmt           gofmt -s -w . && goimports -w ."
	@echo "  tidy          go mod tidy"
	@echo "  vet           go vet $(PKG)"
	@echo "  docker-build  build docker image $(IMAGE)"
	@echo "  up            docker compose up -d"
	@echo "  down          docker compose down"
	@echo "  logs          docker compose logs -f redirect-service"
	@echo "  clean         remove bin/ and coverage artifacts"

build:
	CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o bin/$(BINARY) ./cmd/server

run:
	go run ./cmd/server

test:
	go test -count=1 $(PKG)

test-race:
	go test -race -count=1 $(PKG)

cover:
	go test -coverprofile=coverage.out -covermode=atomic $(PKG)
	go tool cover -html=coverage.out -o coverage.html

lint:
	golangci-lint run

fmt:
	gofmt -s -w .
	@command -v goimports >/dev/null 2>&1 && goimports -w . || true

tidy:
	go mod tidy

vet:
	go vet $(PKG)

docker-build:
	docker build -t $(IMAGE) .

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f redirect-service

clean:
	rm -rf bin coverage.out coverage.html
