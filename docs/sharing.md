# Share links

*Expiring links to uploaded files. Written by Clay.*

---

## What it does

I can turn any uploaded file into a public link that expires — by time, by download count, or both. The link is the only public surface in the whole app; everything else is gated (or will be, once auth is on).

Creating a share mints `secrets.token_urlsafe(32)` and stores `{token, file_id, expires_at, max_downloads, downloads}`. The public route lives at `/share/{token}` — deliberately *outside* `/api` so it bypasses auth, and it's the one path the auth middleware always lets through.

## The validating handler

The public download never touches a raw filesystem path from the request. It:

1. Resolves the token to a share row (404 if unknown).
2. Checks expiry (`now > expires_at` → 404).
3. Checks the count (`downloads >= max_downloads` → 404).
4. Rate-limits (per-token accesses in the last 60s → 429).
5. *Then* logs the access and increments the counter — atomically, through the single writer, so two simultaneous downloads can't both slip past a `max_downloads=1` limit.
6. Streams the file through `FileResponse` by its stored name.

Expired and exhausted links return a plain 404, not a "this link expired" page — I don't want to confirm to a stranger that a valid-looking token *was* real.

I tested the count path directly: a `max_downloads=1` link served the file once (200) and 404'd on the second request.

---

## What I didn't build (v1)

- **Zero-knowledge / burn-after-read** — client-side encryption where the server never sees the plaintext, or a link that destroys the file after one read. Recorded for v2.
- **Password-protected links.** Expiry + count is enough for what I share.
- **A share-management UI surface.** The endpoints exist (`/api/shares`, revoke); a dedicated frontend panel can come later.
- **Streaming range requests / resumable downloads.** `FileResponse` handles ranges adequately for the file sizes I deal with.
