package handler_test

import (
	"context"
	"io"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gofiber/fiber/v2"
	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"

	"github.com/urlshortener/redirect-service/internal/cache"
	"github.com/urlshortener/redirect-service/internal/events"
	"github.com/urlshortener/redirect-service/internal/geoip"
	"github.com/urlshortener/redirect-service/internal/handler"
	"github.com/urlshortener/redirect-service/internal/middleware"
	"github.com/urlshortener/redirect-service/internal/store"
)

// mockQuerier adapts pgxmock.PgxPoolIface to store.Querier.
type mockQuerier struct{ mock pgxmock.PgxPoolIface }

func (m *mockQuerier) QueryRow(ctx context.Context, sql string, args ...any) pgx.Row {
	return m.mock.QueryRow(ctx, sql, args...)
}
func (m *mockQuerier) Ping(ctx context.Context) error { return m.mock.Ping(ctx) }
func (m *mockQuerier) Close()                         { m.mock.Close() }

func buildApp(t *testing.T, mr *miniredis.Miniredis, mockPool pgxmock.PgxPoolIface) *fiber.App {
	t.Helper()

	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })

	ch := cache.New(rdb, time.Hour, 5*time.Minute)

	var s *store.Store
	if mockPool != nil {
		s = store.NewWithQuerier(&mockQuerier{mock: mockPool}, 0)
	}

	pub := events.New(rdb, events.Config{
		Stream: "stream:clicks", MaxLen: 1000, Workers: 1, Buffer: 16,
	}, zerolog.New(io.Discard))
	pub.Start(context.Background())
	t.Cleanup(func() { _ = pub.Close(time.Second) })

	app := fiber.New(fiber.Config{
		DisableStartupMessage: true,
		ReadTimeout:           time.Second,
		WriteTimeout:          time.Second,
	})
	app.Use(middleware.RequestID())
	app.Get("/:code", handler.Redirect(handler.RedirectDeps{
		Cache:               ch,
		Store:               s,
		Publisher:           pub,
		GeoIP:               geoip.NoopReader{},
		Log:                 zerolog.New(io.Discard),
		RoutingEnabled:      true,
		InterstitialDelayMS: 50,
	}))
	return app
}

func TestRedirect_CacheHit_302(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:abc", "https://example.com"))

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/abc", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusFound, resp.StatusCode)
	require.Equal(t, "https://example.com", resp.Header.Get("Location"))
	require.Equal(t, "no-store", resp.Header.Get("Cache-Control"))
}

func TestRedirect_InvalidCode_404(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	app := buildApp(t, mr, nil)
	// >10 chars => invalid.
	req := httptest.NewRequest(fiber.MethodGet, "/this_is_way_too_long", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusNotFound, resp.StatusCode)
}

func TestRedirect_NegativeCache_404(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:ghost", cache.SentinelMiss))
	app := buildApp(t, mr, nil)

	req := httptest.NewRequest(fiber.MethodGet, "/ghost", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusNotFound, resp.StatusCode)
}

func TestRedirect_CacheMiss_DBHit_302(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)

	mock, err := pgxmock.NewPool()
	require.NoError(t, err)
	defer mock.Close()
	rows := pgxmock.NewRows([]string{"long_url", "expires_at", "is_active", "password_hash"}).
		AddRow("https://real.example.com", (*time.Time)(nil), true, (*string)(nil))
	mock.ExpectQuery("SELECT long_url").WithArgs("xyz").WillReturnRows(rows)

	app := buildApp(t, mr, mock)

	req := httptest.NewRequest(fiber.MethodGet, "/xyz", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusFound, resp.StatusCode)
	require.Equal(t, "https://real.example.com", resp.Header.Get("Location"))

	v, _ := mr.Get("url:xyz")
	require.Equal(t, "https://real.example.com", v)
}

func TestRedirect_Expired_410(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)

	mock, err := pgxmock.NewPool()
	require.NoError(t, err)
	defer mock.Close()
	past := time.Now().Add(-time.Hour)
	rows := pgxmock.NewRows([]string{"long_url", "expires_at", "is_active", "password_hash"}).
		AddRow("https://expired.example.com", &past, true, (*string)(nil))
	mock.ExpectQuery("SELECT long_url").WithArgs("old1").WillReturnRows(rows)

	app := buildApp(t, mr, mock)
	req := httptest.NewRequest(fiber.MethodGet, "/old1", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusGone, resp.StatusCode)
}

func TestRedirect_Restricted_451(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)

	mock, err := pgxmock.NewPool()
	require.NoError(t, err)
	defer mock.Close()
	pw := "argon2id$..."
	rows := pgxmock.NewRows([]string{"long_url", "expires_at", "is_active", "password_hash"}).
		AddRow("https://private.example.com", (*time.Time)(nil), true, &pw)
	mock.ExpectQuery("SELECT long_url").WithArgs("pwd1").WillReturnRows(rows)

	app := buildApp(t, mr, mock)
	req := httptest.NewRequest(fiber.MethodGet, "/pwd1", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusUnavailableForLegalReasons, resp.StatusCode)
}

// --- S2: routing rules + pixel interstitial -------------------------------

func TestRedirect_Rules_GeoBranch_302(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:geo1", "https://default.example"))
	mr.HSet("url:meta:geo1", "has_rules", "1")
	require.NoError(t, mr.Set("url:rules:geo1",
		`{"geo":{"US":"https://us.example","default":"https://ww.example"}}`))

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/geo1", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusFound, resp.StatusCode)
	// GeoIP is NoopReader => country=="XX" => falls back to the "default" geo entry.
	require.Equal(t, "https://ww.example", resp.Header.Get("Location"))
}

func TestRedirect_Rules_DeviceBranch_302(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:dev1", "https://default.example"))
	mr.HSet("url:meta:dev1", "has_rules", "1")
	require.NoError(t, mr.Set("url:rules:dev1",
		`{"device":{"ios":"https://ios.example","desktop":"https://dk.example"}}`))

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/dev1", nil)
	req.Header.Set("User-Agent",
		"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15")
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusFound, resp.StatusCode)
	require.Equal(t, "https://ios.example", resp.Header.Get("Location"))
}

func TestRedirect_Rules_NoMatch_FallsBackToDirect(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:fb1", "https://fallback.example"))
	mr.HSet("url:meta:fb1", "has_rules", "1")
	// Geo only has entries that won't match XX, no default, no device, no ab.
	require.NoError(t, mr.Set("url:rules:fb1",
		`{"geo":{"US":"https://us.example"}}`))

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/fb1", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusFound, resp.StatusCode)
	require.Equal(t, "https://fallback.example", resp.Header.Get("Location"))
}

func TestRedirect_NoMeta_DirectBranch_302(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:plain", "https://plain.example"))
	// No url:meta:plain hash at all.

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/plain", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusFound, resp.StatusCode)
	require.Equal(t, "https://plain.example", resp.Header.Get("Location"))
}

func TestRedirect_Pixels_Interstitial_200HTML(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:px1", "https://dest.example"))
	mr.HSet("url:meta:px1", "has_pixels", "1")
	require.NoError(t, mr.Set("url:pixels:px1",
		`[{"kind":"fb","pixel_id":"111222333","name":"main"},{"kind":"ga4","pixel_id":"G-ABC123"}]`))

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/px1", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusOK, resp.StatusCode)
	require.Contains(t, resp.Header.Get("Content-Type"), "html")
	body, _ := io.ReadAll(resp.Body)
	defer resp.Body.Close()
	s := string(body)
	require.Contains(t, s, "https://dest.example", "destination should appear in meta refresh + JS")
	require.Contains(t, s, "111222333", "fb pixel id should be inlined")
	require.Contains(t, s, "G-ABC123", "ga4 measurement id should be inlined")
	require.Contains(t, s, "fbq('init'", "fb pixel init snippet")
	require.Contains(t, s, "gtag(", "ga4 gtag snippet")
	require.Contains(t, s, "setTimeout", "delayed replace present")
	require.True(t, len(body) < 4096, "interstitial should stay under 4KB, got %d", len(body))
}

func TestRedirect_Pixels_RulesRoutesDestInInterstitial(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	require.NoError(t, mr.Set("url:rp1", "https://default.example"))
	mr.HSet("url:meta:rp1", "has_rules", "1")
	mr.HSet("url:meta:rp1", "has_pixels", "1")
	require.NoError(t, mr.Set("url:rules:rp1",
		`{"device":{"ios":"https://ios.example","desktop":"https://dk.example"}}`))
	require.NoError(t, mr.Set("url:pixels:rp1",
		`[{"kind":"fb","pixel_id":"999"}]`))

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/rp1", nil)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusOK, resp.StatusCode)
	body, _ := io.ReadAll(resp.Body)
	defer resp.Body.Close()
	// Desktop UA -> dk.example, injected into interstitial.
	require.Contains(t, string(body), "https://dk.example")
	require.Contains(t, string(body), "999")
}

func TestRedirect_Pixels_XSSSafe(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	// Malicious destination with a script-breaker.
	require.NoError(t, mr.Set("url:xss1", "https://x.example/?a=</script><script>alert(1)</script>"))
	mr.HSet("url:meta:xss1", "has_pixels", "1")
	require.NoError(t, mr.Set("url:pixels:xss1", `[{"kind":"fb","pixel_id":"1"}]`))

	app := buildApp(t, mr, nil)
	req := httptest.NewRequest(fiber.MethodGet, "/xss1", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusOK, resp.StatusCode)
	body, _ := io.ReadAll(resp.Body)
	defer resp.Body.Close()
	s := string(body)
	// html/template must have escaped the closing </script> so the injected
	// script cannot break out of the JS string or the surrounding <script>.
	require.NotContains(t, s, "</script><script>alert(1)")
	require.False(t, strings.Contains(s, "alert(1)</script>"), "raw injected tag must not appear verbatim")
}

func TestRedirect_NotFoundInDB_404(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)

	mock, err := pgxmock.NewPool()
	require.NoError(t, err)
	defer mock.Close()
	mock.ExpectQuery("SELECT long_url").WithArgs("nope1").WillReturnError(pgx.ErrNoRows)

	app := buildApp(t, mr, mock)
	req := httptest.NewRequest(fiber.MethodGet, "/nope1", nil)
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	require.Equal(t, fiber.StatusNotFound, resp.StatusCode)

	v, _ := mr.Get("url:nope1")
	require.Equal(t, cache.SentinelMiss, v)
}
