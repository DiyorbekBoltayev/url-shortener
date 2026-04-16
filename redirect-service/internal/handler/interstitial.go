package handler

import (
	"bytes"
	"encoding/json"
	"html/template"
	"sync"
)

// Pixel is a single retarget tag loaded from `url:pixels:{code}`.
//
// Shape matches the JSON array api-service writes:
//
//	[{"kind":"fb","pixel_id":"123","name":"main"}, ...]
type Pixel struct {
	Kind    string `json:"kind"`
	PixelID string `json:"pixel_id"`
	Name    string `json:"name,omitempty"`
}

// interstitialData is the template model.
type interstitialData struct {
	// Dest is the final redirect URL. Used both in the <meta refresh> and in
	// the JavaScript replace call. html/template escapes it contextually.
	Dest     string
	DelayMS  int
	Pixels   []Pixel
	HasFB    bool
	HasGA4   bool
	HasGTM   bool
	HasLI    bool
	HasTikT  bool
	HasPin   bool
	HasTwtr  bool
}

// interstitialTemplate renders a tiny HTML page that:
//   - fires every configured pixel snippet,
//   - meta-refreshes immediately as a JS-disabled fallback,
//   - after DelayMS ms, window.location.replace(Dest) to let beacons fire.
//
// The template uses html/template so {{.Dest}} is escaped per context:
// attribute in the <meta> tag, and JS-string in the final replace call.
// We deliberately keep the page under 4KB and inline every vendor snippet
// with the real pixel IDs from the per-link config (no hardcoded test IDs).
const interstitialTemplateSrc = `<!doctype html>
<html><head><meta charset="utf-8"><title>Redirecting…</title>
<meta http-equiv="refresh" content="0; url={{.Dest}}">
<noscript><meta http-equiv="refresh" content="0; url={{.Dest}}"></noscript>
{{if .HasGA4}}{{range .Pixels}}{{if eq .Kind "ga4"}}<script async src="https://www.googletagmanager.com/gtag/js?id={{.PixelID}}"></script>{{end}}{{end}}{{end}}
<script>
{{if .HasFB}}
!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
{{range .Pixels}}{{if eq .Kind "fb"}}fbq('init','{{.PixelID}}');fbq('track','PageView');
{{end}}{{end}}{{end}}
{{if .HasGA4}}window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());
{{range .Pixels}}{{if eq .Kind "ga4"}}gtag('config','{{.PixelID}}');
{{end}}{{end}}{{end}}
{{if .HasGTM}}window.dataLayer=window.dataLayer||[];
{{range .Pixels}}{{if eq .Kind "gtm"}}(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','{{.PixelID}}');
{{end}}{{end}}{{end}}
{{if .HasLI}}
{{range .Pixels}}{{if eq .Kind "linkedin"}}_linkedin_partner_id='{{.PixelID}}';window._linkedin_data_partner_ids=window._linkedin_data_partner_ids||[];window._linkedin_data_partner_ids.push(_linkedin_partner_id);(function(l){if(!l){window.lintrk=function(a,b){window.lintrk.q.push([a,b])};window.lintrk.q=[]}var s=document.getElementsByTagName('script')[0];var b=document.createElement('script');b.type='text/javascript';b.async=true;b.src='https://snap.licdn.com/li.lms-analytics/insight.min.js';s.parentNode.insertBefore(b,s);})(window.lintrk);
{{end}}{{end}}{{end}}
{{if .HasTikT}}
{{range .Pixels}}{{if eq .Kind "tiktok"}}!function(w,d,t){w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=["page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie"];ttq.setAndDefer=function(t,e){t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}};for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);ttq.instance=function(t){for(var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e};ttq.load=function(e,n){var i='https://analytics.tiktok.com/i18n/pixel/events.js';ttq._i=ttq._i||{};ttq._i[e]=[];ttq._i[e]._u=i;ttq._t=ttq._t||{};ttq._t[e]=+new Date;ttq._o=ttq._o||{};ttq._o[e]=n||{};var o=document.createElement('script');o.type='text/javascript';o.async=!0;o.src=i+'?sdkid='+e+'&lib='+t;var a=document.getElementsByTagName('script')[0];a.parentNode.insertBefore(o,a)};ttq.load('{{.PixelID}}');ttq.page();
{{end}}{{end}}{{end}}
{{if .HasPin}}
{{range .Pixels}}{{if eq .Kind "pinterest"}}!function(e){if(!window.pintrk){window.pintrk=function(){window.pintrk.queue.push(Array.prototype.slice.call(arguments))};var n=window.pintrk;n.queue=[],n.version="3.0";var t=document.createElement("script");t.async=!0,t.src=e;var r=document.getElementsByTagName("script")[0];r.parentNode.insertBefore(t,r)}}("https://s.pinimg.com/ct/core.js");pintrk('load','{{.PixelID}}');pintrk('page');
{{end}}{{end}}{{end}}
{{if .HasTwtr}}
{{range .Pixels}}{{if eq .Kind "twitter"}}!function(e,t,n,s,u,a){e.twq||(s=e.twq=function(){s.exe?s.exe.apply(s,arguments):s.queue.push(arguments)},s.version='1.1',s.queue=[],u=t.createElement(n),u.async=!0,u.src='https://static.ads-twitter.com/uwt.js',a=t.getElementsByTagName(n)[0],a.parentNode.insertBefore(u,a))}(window,document,'script');twq('config','{{.PixelID}}');
{{end}}{{end}}{{end}}
setTimeout(function(){window.location.replace({{.Dest}});},{{.DelayMS}});
</script>
</head><body></body></html>`

var (
	interstitialTplOnce sync.Once
	interstitialTpl     *template.Template
	interstitialTplErr  error
)

func tpl() (*template.Template, error) {
	interstitialTplOnce.Do(func() {
		interstitialTpl, interstitialTplErr = template.New("interstitial").Parse(interstitialTemplateSrc)
	})
	return interstitialTpl, interstitialTplErr
}

// renderInterstitial renders the pixel interstitial page for `dest` with the
// given pixels and a JS redirect delay. Returns the full HTML bytes.
//
// The function is safe for concurrent use.
func renderInterstitial(dest string, pixels []Pixel, delayMS int) ([]byte, error) {
	t, err := tpl()
	if err != nil {
		return nil, err
	}
	data := interstitialData{
		Dest:    dest,
		DelayMS: delayMS,
		Pixels:  pixels,
	}
	for _, p := range pixels {
		switch p.Kind {
		case "fb":
			data.HasFB = true
		case "ga4":
			data.HasGA4 = true
		case "gtm":
			data.HasGTM = true
		case "linkedin":
			data.HasLI = true
		case "tiktok":
			data.HasTikT = true
		case "pinterest":
			data.HasPin = true
		case "twitter":
			data.HasTwtr = true
		}
	}
	var buf bytes.Buffer
	buf.Grow(2048)
	if err := t.Execute(&buf, data); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// decodePixels parses the JSON array cached at `url:pixels:{code}`. Only
// pixels with a known `kind` and non-empty `pixel_id` are retained.
func decodePixels(raw string) []Pixel {
	if raw == "" {
		return nil
	}
	var all []Pixel
	if err := json.Unmarshal([]byte(raw), &all); err != nil {
		return nil
	}
	out := all[:0]
	for _, p := range all {
		if p.PixelID == "" {
			continue
		}
		switch p.Kind {
		case "fb", "ga4", "gtm", "linkedin", "tiktok", "pinterest", "twitter":
			out = append(out, p)
		}
	}
	return out
}

