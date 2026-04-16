package routing_test

import (
	"strings"
	"testing"

	"github.com/urlshortener/redirect-service/internal/routing"
)

const (
	uaIPhone  = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
	uaIPad    = "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/605.1.15"
	uaAndroid = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36"
	uaOperaM  = "Opera/9.80 (Android; Opera Mini/36.2/174.142; U; en)"
	uaDesktop = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
)

func TestDetectDevice(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		ua   string
		want string
	}{
		{"iphone", uaIPhone, "ios"},
		{"ipad", uaIPad, "ios"},
		{"ipod", "Mozilla/5.0 (iPod touch; CPU iPhone OS 16_0)", "ios"},
		{"android_chrome", uaAndroid, "android"},
		{"opera_mini_android", uaOperaM, "desktop"}, // Opera Mini exclusion
		{"desktop", uaDesktop, "desktop"},
		{"empty", "", "desktop"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := routing.DetectDevice(tc.ua)
			if got != tc.want {
				t.Fatalf("DetectDevice(%q) = %q, want %q", tc.ua, got, tc.want)
			}
		})
	}
}

func TestResolve_NilRules_Fallback(t *testing.T) {
	t.Parallel()
	u, b := routing.Resolve(nil, "US", uaIPhone, "https://fb.example")
	if u != "https://fb.example" || b != routing.BranchDirect {
		t.Fatalf("got (%q,%q); want fallback/direct", u, b)
	}
}

func TestResolve_EmptyRules_Fallback(t *testing.T) {
	t.Parallel()
	u, b := routing.Resolve(&routing.RoutingRules{}, "US", uaIPhone, "https://fb.example")
	if u != "https://fb.example" || b != routing.BranchDirect {
		t.Fatalf("got (%q,%q); want fallback/direct", u, b)
	}
}

func TestResolve_Geo_ExactMatch(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		Geo:    map[string]string{"US": "https://us.example", "default": "https://ww.example"},
		Device: map[string]string{"ios": "https://ios.example"},
	}
	u, b := routing.Resolve(rules, "US", uaIPhone, "https://fb.example")
	if u != "https://us.example" || b != routing.BranchGeo {
		t.Fatalf("got (%q,%q); want us/geo", u, b)
	}
}

func TestResolve_Geo_DefaultWhenCountryMissing(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		Geo: map[string]string{"US": "https://us.example", "default": "https://ww.example"},
	}
	u, b := routing.Resolve(rules, "ZZ", uaDesktop, "https://fb.example")
	if u != "https://ww.example" || b != routing.BranchGeo {
		t.Fatalf("got (%q,%q); want ww/geo", u, b)
	}
}

func TestResolve_Geo_SkipsWhenCountryUnknownAndNoDefault(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		Geo:    map[string]string{"US": "https://us.example"}, // no default
		Device: map[string]string{"ios": "https://ios.example"},
	}
	u, b := routing.Resolve(rules, "ZZ", uaIPhone, "https://fb.example")
	if u != "https://ios.example" || b != routing.BranchDevice {
		t.Fatalf("got (%q,%q); want ios/device", u, b)
	}
}

func TestResolve_Device_iOS(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		Device: map[string]string{
			"ios":     "https://ios.example",
			"android": "https://and.example",
			"desktop": "https://dk.example",
		},
	}
	u, b := routing.Resolve(rules, "XX", uaIPhone, "https://fb.example")
	if u != "https://ios.example" || b != routing.BranchDevice {
		t.Fatalf("got (%q,%q); want ios/device", u, b)
	}
}

func TestResolve_Device_Desktop(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		Device: map[string]string{"ios": "https://ios.example", "desktop": "https://dk.example"},
	}
	u, b := routing.Resolve(rules, "", uaDesktop, "https://fb.example")
	if u != "https://dk.example" || b != routing.BranchDevice {
		t.Fatalf("got (%q,%q); want dk/device", u, b)
	}
}

func TestResolve_Device_FallsThroughWhenNoMatchingKey(t *testing.T) {
	t.Parallel()
	// Device map only has "ios"; request is Android -> should continue to AB/fallback.
	rules := &routing.RoutingRules{
		Device: map[string]string{"ios": "https://ios.example"},
		AB:     []routing.ABVariant{{URL: "https://a.example", Weight: 1}},
	}
	u, b := routing.Resolve(rules, "XX", uaAndroid, "https://fb.example")
	if u != "https://a.example" || !strings.HasPrefix(b, routing.BranchABFmt) {
		t.Fatalf("got (%q,%q); want AB pick", u, b)
	}
}

func TestResolve_AB_Split_Deterministic_WhenSingleVariant(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		AB: []routing.ABVariant{{URL: "https://a.example", Weight: 100}},
	}
	u, b := routing.Resolve(rules, "", "", "https://fb.example")
	if u != "https://a.example" || b != routing.BranchABFmt+"0" {
		t.Fatalf("got (%q,%q); want a/ab_0", u, b)
	}
}

func TestResolve_AB_WeightedDistribution(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		AB: []routing.ABVariant{
			{URL: "https://a.example", Weight: 10},
			{URL: "https://b.example", Weight: 90},
		},
	}
	const iters = 4000
	counts := map[string]int{}
	for i := 0; i < iters; i++ {
		u, _ := routing.Resolve(rules, "", "", "https://fb.example")
		counts[u]++
	}
	// Expect B to dominate. Allow wide tolerance since we use math/rand.
	if counts["https://b.example"] < counts["https://a.example"]*3 {
		t.Fatalf("expected B >> A; counts=%v", counts)
	}
}

func TestResolve_AB_IgnoresZeroWeight(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		AB: []routing.ABVariant{
			{URL: "https://a.example", Weight: 0},
			{URL: "https://b.example", Weight: 1},
		},
	}
	// Must always pick b
	for i := 0; i < 50; i++ {
		u, _ := routing.Resolve(rules, "", "", "https://fb.example")
		if u != "https://b.example" {
			t.Fatalf("iter %d: got %q, want b", i, u)
		}
	}
}

func TestResolve_AB_AllZero_FallsThrough(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		AB: []routing.ABVariant{
			{URL: "https://a.example", Weight: 0},
			{URL: "https://b.example", Weight: 0},
		},
	}
	u, b := routing.Resolve(rules, "", "", "https://fb.example")
	if u != "https://fb.example" || b != routing.BranchDirect {
		t.Fatalf("got (%q,%q); want fallback/direct", u, b)
	}
}

func TestResolve_OrderGeoBeforeDevice(t *testing.T) {
	t.Parallel()
	// Both geo and device would match; geo must win.
	rules := &routing.RoutingRules{
		Geo:    map[string]string{"US": "https://us.example"},
		Device: map[string]string{"ios": "https://ios.example"},
	}
	u, b := routing.Resolve(rules, "US", uaIPhone, "https://fb.example")
	if u != "https://us.example" || b != routing.BranchGeo {
		t.Fatalf("got (%q,%q); want us/geo (geo wins)", u, b)
	}
}

func TestResolve_OrderDeviceBeforeAB(t *testing.T) {
	t.Parallel()
	rules := &routing.RoutingRules{
		Device: map[string]string{"ios": "https://ios.example"},
		AB:     []routing.ABVariant{{URL: "https://a.example", Weight: 100}},
	}
	u, b := routing.Resolve(rules, "", uaIPhone, "https://fb.example")
	if u != "https://ios.example" || b != routing.BranchDevice {
		t.Fatalf("got (%q,%q); want ios/device (device wins over AB)", u, b)
	}
}
