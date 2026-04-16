// Package geoip wraps oschwald/geoip2-golang.
//
// The in-memory .mmdb lookup is ~1-5us — negligible vs the 5ms latency
// budget. If the .mmdb is missing at startup we return a no-op reader
// that answers "XX" (unknown) rather than failing — analytics should
// degrade gracefully (HLA 2.1 footnote).
package geoip

import (
	"errors"
	"fmt"
	"io/fs"
	"net"
	"os"
	"sync"

	"github.com/oschwald/geoip2-golang"
)

// UnknownCountry is the 2-letter fallback when the DB is missing or the IP
// is unresolvable (private range, IPv6 localhost, bogons, etc.).
const UnknownCountry = "XX"

// Reader looks up a country code for an IP.
type Reader interface {
	Lookup(ip string) string
	Close() error
	// Loaded reports whether a real .mmdb is in use.
	Loaded() bool
}

// mmdbReader is the real implementation backed by a loaded .mmdb file.
type mmdbReader struct {
	r  *geoip2.Reader
	mu sync.RWMutex
}

// Open loads a MaxMind .mmdb. If the file does not exist it returns a no-op
// reader and no error — callers should log a warning but continue.
func Open(path string) (Reader, error) {
	r, err := geoip2.Open(path)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) || errors.Is(err, os.ErrNotExist) {
			return NoopReader{}, nil
		}
		return nil, fmt.Errorf("geoip: open %q: %w", path, err)
	}
	return &mmdbReader{r: r}, nil
}

// Lookup returns the ISO-3166 alpha-2 country code for ip, or UnknownCountry.
func (m *mmdbReader) Lookup(ip string) string {
	if m == nil || m.r == nil {
		return UnknownCountry
	}
	parsed := net.ParseIP(ip)
	if parsed == nil {
		return UnknownCountry
	}
	m.mu.RLock()
	rec, err := m.r.Country(parsed)
	m.mu.RUnlock()
	if err != nil || rec == nil || rec.Country.IsoCode == "" {
		return UnknownCountry
	}
	return rec.Country.IsoCode
}

// Close releases the underlying mmap.
func (m *mmdbReader) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.r == nil {
		return nil
	}
	err := m.r.Close()
	m.r = nil
	return err
}

// Loaded reports true when the .mmdb is open.
func (m *mmdbReader) Loaded() bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.r != nil
}

// NoopReader is used when the .mmdb is absent. It always returns UnknownCountry.
type NoopReader struct{}

func (NoopReader) Lookup(string) string { return UnknownCountry }
func (NoopReader) Close() error         { return nil }
func (NoopReader) Loaded() bool         { return false }
