# Public demonstration: security and availability

Reviewed 21 October 2026. These are application safeguards, not a guarantee that
the site cannot be compromised or interrupted. This is an anonymous simulation,
not a controller connected to physical equipment.

## Protections in this release

- A signed, expiring HttpOnly / SameSite=Lax browser cookie owns each public
  simulation. Public cookies are Secure; plain HTTP cookies are allowed only
  on localhost/127.0.0.1 for development and container tests. Signing keys are
  generated in memory at startup and never committed or sent to visitors.
- Refreshing reuses that browser's scene. A browser cannot use another browser's
  session ID to operate or export its model. The free instance retains at most
  two visitor scenes and reclaims inactive scenes after three minutes when a
  new layout is requested. Tabs in the same public browser share its model.
- Commands reject cross-site browser requests, unknown callbacks, unexpected
  input/output targets, non-finite or oversized numeric values, unsupported
  settings, oversized JSON and deeply nested browser values. Request bodies
  are limited to 64 KiB. No proxy/IP header is accepted as a visitor identity.
- Bounded in-process token buckets limit callbacks (30/s per browser, burst 50;
  60/s globally, burst 90), layouts (6/min per browser, burst 2; 12/min globally,
  burst 4), forced weather refreshes and exports. Bucket storage is capped.
- Work admission permits two concurrent callbacks and one native renderer
  operation. Excess work receives 429/503 and Retry-After instead of an
  unbounded queue. A browser's overlapping model commands are also bounded.
  The health endpoint does not allocate a scene or require these permits.
- Public scene PNG exports are limited to 1920×1080, one image per 15 seconds
  globally; JSON exports have a five-second browser cooldown. Local exports
  retain QHD/4K. On-screen rendering and local fan animation are unchanged.
- A hash-based script Content Security Policy, same-origin resource policy,
  frame denial, MIME-sniffing protection, referrer/permission policies and
  public-host HSTS provide browser protections. Inline styles remain necessary
  for Dash; arbitrary inline scripts are not allowed. Flask validates hosts,
  and Gunicorn limits request-line/header sizes and its connection backlog.
- The Docker process remains non-root. The public image omits unused Streamlit
  dependencies and pins Pillow 13.0.0, which resolves the image-library
  advisories reported for the local environment's Pillow 12.3.0. The local
  Streamlit release currently requires Pillow <13; this dashboard only uses
  Pillow to write internally generated PNGs, not to decode uploaded images/PDFs.
  CI uses the official PyPA pip-audit action for the cloud dependency tree.

Security policy and resource admission run only on the public cloud entry point;
the local Streamlit iframe continues to use its loopback viewer. Render account
credentials and owner Suspend/Resume controls are never exposed by the website.

## Practical limits

Render already includes platform-level
[DDoS protection](https://render.com/docs/ddos-protection). Application limits
help with malformed requests, accidental overload and some abuse; they cannot
prevent every attack, malicious use of legitimately issued browser cookies,
session-slot occupation, bandwidth exhaustion or a hosting-provider failure.
Do not treat a passing advisory lookup or regression suite as a penetration test
or a proof that every dependency/browser bundle is vulnerability-free.

The [free Render plan](https://render.com/docs/free) sleeps after 15 minutes
without incoming traffic, has cold-start delays and resource/usage limits, and
may restart. It cannot provide guaranteed continuous availability. This free
configuration admits two active visitor browsers; additional visitors see a
capacity message. Larger audiences or dependable production availability require
appropriately sized hosting and further operational work. No paid resources,
external monitoring, account-permission changes or keep-alive workaround are
created by this release.
