// Package store is the Postgres fallback for short-code lookups.
package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ErrNotFound is returned when no row matches the given short code.
var ErrNotFound = errors.New("store: code not found")

// URL is the projection of the `urls` table that redirect-service needs.
type URL struct {
	LongURL      string
	ExpiresAt    *time.Time // nullable
	IsActive     bool
	PasswordHash *string // nullable; nil => no password
}

// Expired reports whether the URL has an ExpiresAt in the past.
func (u URL) Expired(now time.Time) bool {
	return u.ExpiresAt != nil && !u.ExpiresAt.IsZero() && now.After(*u.ExpiresAt)
}

// Restricted reports whether the URL is inactive or password-protected.
func (u URL) Restricted() bool {
	if !u.IsActive {
		return true
	}
	if u.PasswordHash != nil && *u.PasswordHash != "" {
		return true
	}
	return false
}

// Querier is the minimal interface we need from pgxpool.Pool. It is also
// satisfied by pgxmock, which we use in tests.
type Querier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Ping(ctx context.Context) error
	Close()
}

// Store wraps a pgx connection pool and exposes URLLookup.
type Store struct {
	q            Querier
	queryTimeout time.Duration
}

// New builds a pgxpool-backed Store.
func New(ctx context.Context, dsn string, minConns, maxConns int32, queryTimeout time.Duration) (*Store, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("store: parse dsn: %w", err)
	}
	cfg.MinConns = minConns
	cfg.MaxConns = maxConns
	cfg.MaxConnLifetime = time.Hour
	cfg.MaxConnLifetimeJitter = 5 * time.Minute
	cfg.MaxConnIdleTime = 15 * time.Minute
	cfg.HealthCheckPeriod = time.Minute
	cfg.ConnConfig.ConnectTimeout = 3 * time.Second
	// Cache prepared statement descriptions — low-overhead single-param SELECT.
	cfg.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeCacheDescribe

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("store: new pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("store: ping: %w", err)
	}
	return &Store{q: &poolAdapter{pool: pool}, queryTimeout: queryTimeout}, nil
}

// NewWithQuerier is an injection point for tests (pgxmock).
func NewWithQuerier(q Querier, queryTimeout time.Duration) *Store {
	return &Store{q: q, queryTimeout: queryTimeout}
}

// URLLookup returns the URL row for the given short code, or ErrNotFound.
//
// Query matches HLA 2.1: SELECT long_url, expires_at, is_active, password_hash
// FROM urls WHERE short_code=$1.
func (s *Store) URLLookup(ctx context.Context, code string) (URL, error) {
	const q = `SELECT long_url, expires_at, is_active, password_hash
	           FROM urls WHERE short_code = $1`

	if s.queryTimeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, s.queryTimeout)
		defer cancel()
	}

	var u URL
	err := s.q.QueryRow(ctx, q, code).Scan(&u.LongURL, &u.ExpiresAt, &u.IsActive, &u.PasswordHash)
	if errors.Is(err, pgx.ErrNoRows) {
		return URL{}, ErrNotFound
	}
	if err != nil {
		return URL{}, fmt.Errorf("store: url lookup: %w", err)
	}
	return u, nil
}

// Ping checks the pool is reachable.
func (s *Store) Ping(ctx context.Context) error {
	if s.queryTimeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, s.queryTimeout)
		defer cancel()
	}
	return s.q.Ping(ctx)
}

// Close releases pool resources.
func (s *Store) Close() { s.q.Close() }

// poolAdapter bridges *pgxpool.Pool to the Querier interface by exposing
// a QueryRow that returns pgx.Row.
type poolAdapter struct{ pool *pgxpool.Pool }

func (p *poolAdapter) QueryRow(ctx context.Context, sql string, args ...any) pgx.Row {
	return p.pool.QueryRow(ctx, sql, args...)
}
func (p *poolAdapter) Ping(ctx context.Context) error { return p.pool.Ping(ctx) }
func (p *poolAdapter) Close()                         { p.pool.Close() }
