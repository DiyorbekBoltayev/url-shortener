package store_test

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
	"github.com/stretchr/testify/require"

	"github.com/urlshortener/redirect-service/internal/store"
)

// mockQuerier adapts pgxmock.PgxPoolIface to store.Querier.
type mockQuerier struct {
	mock pgxmock.PgxPoolIface
}

func (m *mockQuerier) QueryRow(ctx context.Context, sql string, args ...any) pgx.Row {
	return m.mock.QueryRow(ctx, sql, args...)
}
func (m *mockQuerier) Ping(ctx context.Context) error { return m.mock.Ping(ctx) }
func (m *mockQuerier) Close()                         { m.mock.Close() }

func TestURLLookup_Found(t *testing.T) {
	t.Parallel()
	mock, err := pgxmock.NewPool()
	require.NoError(t, err)
	defer mock.Close()

	expires := time.Now().Add(24 * time.Hour)
	rows := pgxmock.NewRows([]string{"long_url", "expires_at", "is_active", "password_hash"}).
		AddRow("https://example.com", &expires, true, (*string)(nil))
	mock.ExpectQuery("SELECT long_url").
		WithArgs("abc").
		WillReturnRows(rows)

	s := store.NewWithQuerier(&mockQuerier{mock: mock}, 200*time.Millisecond)
	u, err := s.URLLookup(context.Background(), "abc")
	require.NoError(t, err)
	require.Equal(t, "https://example.com", u.LongURL)
	require.True(t, u.IsActive)
	require.False(t, u.Restricted())
	require.False(t, u.Expired(time.Now()))
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestURLLookup_NotFound(t *testing.T) {
	t.Parallel()
	mock, err := pgxmock.NewPool()
	require.NoError(t, err)
	defer mock.Close()

	mock.ExpectQuery("SELECT long_url").
		WithArgs("ghost").
		WillReturnError(pgx.ErrNoRows)

	s := store.NewWithQuerier(&mockQuerier{mock: mock}, 0)
	_, err = s.URLLookup(context.Background(), "ghost")
	require.ErrorIs(t, err, store.ErrNotFound)
}

func TestURLLookup_Restricted(t *testing.T) {
	t.Parallel()
	mock, err := pgxmock.NewPool()
	require.NoError(t, err)
	defer mock.Close()

	pw := "argon2id$..."
	rows := pgxmock.NewRows([]string{"long_url", "expires_at", "is_active", "password_hash"}).
		AddRow("https://x", (*time.Time)(nil), true, &pw)
	mock.ExpectQuery("SELECT long_url").
		WithArgs("pw").
		WillReturnRows(rows)

	s := store.NewWithQuerier(&mockQuerier{mock: mock}, 0)
	u, err := s.URLLookup(context.Background(), "pw")
	require.NoError(t, err)
	require.True(t, u.Restricted())
}

func TestURL_Expired(t *testing.T) {
	t.Parallel()
	past := time.Now().Add(-time.Hour)
	u := store.URL{ExpiresAt: &past, IsActive: true}
	require.True(t, u.Expired(time.Now()))

	var nilURL store.URL
	require.False(t, nilURL.Expired(time.Now()))
}
