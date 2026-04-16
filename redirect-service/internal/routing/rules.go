// Package routing implements the rule resolver for the redirect-service.
//
// Per FEATURES_PLAN.md, a short link may carry routing rules in the shape:
//
//	{
//	  "ab":     [{"url":"...","weight":50}, ...],
//	  "device": {"ios":"...","android":"...","desktop":"..."},
//	  "geo":    {"US":"...","DE":"...","default":"..."}
//	}
//
// Evaluation order is geo → device → ab → fallback (the urls.long_url).
// Resolve returns both the chosen destination and a short branch label which
// is attached to the click event and emitted as a Prometheus label.
package routing

import (
	"math/rand"
	"strings"
	"sync"
	"time"
)

// Branch label constants. They double as Prometheus labels, so they are kept
// low-cardinality ("ab_<index>" is bounded by len(rules.AB)).
const (
	BranchDirect = "direct"
	BranchGeo    = "geo"
	BranchDevice = "device"
	BranchABFmt  = "ab_" // suffix is the variant index
)

// Device strings.
const (
	DeviceIOS     = "ios"
	DeviceAndroid = "android"
	DeviceDesktop = "desktop"
)

// ABVariant is a single weighted destination for split testing.
type ABVariant struct {
	URL    string `json:"url"`
	Weight int    `json:"weight"`
}

// RoutingRules is the decoded JSON cached at `url:rules:{code}`.
type RoutingRules struct {
	AB     []ABVariant       `json:"ab,omitempty"`
	Device map[string]string `json:"device,omitempty"`
	Geo    map[string]string `json:"geo,omitempty"`
}

// picker is the RNG used for A/B weighted selection. A dedicated source keeps
// us independent of callers that may seed math/rand globally.
//
// TODO(stickiness): swap for a hash(code+ip)%total lookup backed by a short
// Redis sticky key (rr:stick:{code}:{ipHash}, EX 600) so a given IP always
// lands on the same variant for ~10 minutes.
var (
	pickerMu sync.Mutex
	picker   = rand.New(rand.NewSource(time.Now().UnixNano()))
)

// DetectDevice returns "ios" | "android" | "desktop" from a User-Agent string.
// Matches the rules documented in FEATURES_PLAN.md:
//   - iPhone|iPad|iPod → ios
//   - Android (but not Opera Mini) → android
//   - else → desktop
func DetectDevice(ua string) string {
	if ua == "" {
		return DeviceDesktop
	}
	// Fast path — case-sensitive substring matches. These tokens are all
	// capitalized in real UAs from Apple/Google.
	if strings.Contains(ua, "iPhone") || strings.Contains(ua, "iPad") || strings.Contains(ua, "iPod") {
		return DeviceIOS
	}
	if strings.Contains(ua, "Android") && !strings.Contains(ua, "Opera Mini") {
		return DeviceAndroid
	}
	return DeviceDesktop
}

// Resolve picks a destination for the given request, honoring the documented
// evaluation order: geo → device → ab → fallback.
//
// Returns (destination_url, branch_label). When `rules` is nil or empty the
// fallback is returned with branch="direct".
func Resolve(rules *RoutingRules, countryCode, userAgent, fallback string) (string, string) {
	if rules == nil {
		return fallback, BranchDirect
	}

	// 1. Geo — by exact country match, then "default" in the geo map.
	if len(rules.Geo) > 0 {
		if countryCode != "" {
			if u, ok := rules.Geo[strings.ToUpper(countryCode)]; ok && u != "" {
				return u, BranchGeo
			}
		}
		if u, ok := rules.Geo["default"]; ok && u != "" {
			return u, BranchGeo
		}
	}

	// 2. Device — ios / android / desktop.
	if len(rules.Device) > 0 {
		dev := DetectDevice(userAgent)
		if u, ok := rules.Device[dev]; ok && u != "" {
			return u, BranchDevice
		}
	}

	// 3. A/B split — weighted random over positive weights.
	if len(rules.AB) > 0 {
		if u, idx, ok := pickAB(rules.AB); ok {
			return u, branchAB(idx)
		}
	}

	return fallback, BranchDirect
}

// pickAB performs a weighted random pick over rules.AB. Variants with
// Weight<=0 or empty URL are ignored. Returns (url, index, true) on success.
func pickAB(variants []ABVariant) (string, int, bool) {
	total := 0
	for _, v := range variants {
		if v.Weight > 0 && v.URL != "" {
			total += v.Weight
		}
	}
	if total <= 0 {
		return "", 0, false
	}

	pickerMu.Lock()
	r := picker.Intn(total)
	pickerMu.Unlock()

	acc := 0
	for i, v := range variants {
		if v.Weight <= 0 || v.URL == "" {
			continue
		}
		acc += v.Weight
		if r < acc {
			return v.URL, i, true
		}
	}
	// Unreachable given total > 0, but keep a deterministic fallback.
	return variants[len(variants)-1].URL, len(variants) - 1, true
}

// branchAB formats the Prometheus/event branch label for A/B variants.
func branchAB(idx int) string {
	// Hand-rolled to avoid an fmt.Sprintf allocation in the hot path.
	switch idx {
	case 0:
		return BranchABFmt + "0"
	case 1:
		return BranchABFmt + "1"
	case 2:
		return BranchABFmt + "2"
	case 3:
		return BranchABFmt + "3"
	case 4:
		return BranchABFmt + "4"
	default:
		// Rare — up to the caller to keep AB arrays short.
		return BranchABFmt + itoa(idx)
	}
}

// itoa is a tiny strconv.Itoa replacement for non-negative ints. Handles
// the cold path in branchAB.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}
