# 0008: WhatsApp enrollment with a one-time code bound to the registered number

**Status:** Accepted (2026-10-22)

## Context
PDD Journey A: a phone-number match alone must not be enough. Residents should not need
an app or a password.

## Decision
- A manager registers the resident's phone, then generates a code in the dashboard
  (8 characters from an unambiguous alphabet, shown once, valid 7 days).
- Enrollment requires **both** an inbound message from that exact number (as asserted by
  WhatsApp) **and** the code. Only an HMAC of `phone_id:code` (keyed by `SECRET_KEY`) is
  stored. Five wrong attempts lock the code, and a new code revokes the previous one.
- Success sets `resident_phones.verified_at`, moves the resident from `invited` to
  `active`, links the conversation, and writes a `resident.enrolled` audit event with the
  resident as actor.
- Until enrolled, the sender gets fixed system replies only. The model is never called
  for unverified numbers. Suspended or revoked residents are told to contact the
  administration.
- Each additional phone enrolls on its own. Removing a phone removes its verification.

## Consequences
- Managers must hand the code over out of band (printed, in person, email), which is
  the trust anchor.
- Sensitive future operations (visitor authorizations) can additionally require a
  confirmation step, but enrollment is the identity baseline.
