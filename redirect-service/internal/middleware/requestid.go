// Package middleware holds small Fiber middlewares specific to redirect-service.
//
// We use Fiber built-ins (recover, logger via zerolog adapter, prometheus)
// elsewhere; this file is for custom ones.
package middleware

import (
	"crypto/rand"
	"encoding/hex"

	"github.com/gofiber/fiber/v2"
)

// RequestIDHeader is the canonical header name used and echoed.
const RequestIDHeader = "X-Request-ID"

// LocalsKeyRequestID is the key under which the request id is stored
// in fiber.Ctx.Locals.
const LocalsKeyRequestID = "request_id"

// RequestID is a small middleware: trust inbound X-Request-ID if present
// (single hop from nginx), otherwise mint one. Store on c.Locals for logging.
func RequestID() fiber.Handler {
	return func(c *fiber.Ctx) error {
		rid := c.Get(RequestIDHeader)
		if rid == "" {
			rid = newID()
		}
		c.Locals(LocalsKeyRequestID, rid)
		c.Set(RequestIDHeader, rid)
		return c.Next()
	}
}

func newID() string {
	var b [12]byte
	if _, err := rand.Read(b[:]); err != nil {
		// Random source failure is extraordinarily rare; return empty and
		// let nginx's rid (if any) dominate upstream logs.
		return "00000000000000000000000000000000"
	}
	return hex.EncodeToString(b[:])
}
