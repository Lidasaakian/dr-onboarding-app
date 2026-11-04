# Design

## Context

See proposal.md. The working area (`embedded-datarobot-panel`) is a sandboxed `<iframe>` panel in
`static/assets/common.js`, used today only for DataRobot pages on the same site. Browsers refuse to show a page in a
frame when it sends `X-Frame-Options` (DENY or SAMEORIGIN) or a `Content-Security-Policy` `frame-ancestors` list that
doesn't include the embedding site; a refused frame just shows an error page, and the embedding page can't detect it
for another site. So the decision has to be made before opening the link.

## Decisions

1. **The server decides, the page asks ahead.** `framing.py` has pure functions: `embed_url(url)` (YouTube watch,
   youtu.be and shorts → `youtube.com/embed/<id>`, Vimeo → `player.vimeo.com/video/<id>`, else unchanged) and
   `allows_framing(headers, our_origin)`. `Checker.check(urls)` fetches the headers with redirects followed by hand
   (each hop must pass `sources.public_url`), 8-second timeout, eight at a time, and caches each answer for 24 hours
   (2,000 entries). `POST api/frameable {"urls": [...]}` (signed-in users, up to 300 links) returns
   `{url: {"frame": bool, "embed": url}}`.
2. **No delay at click time.** Browsers block pop-ups opened after waiting on a request, so path pages send the links
   in their content to `api/frameable` right after loading (and again when content is rebuilt), and keep the answers.
   A click on a link with a known "yes" opens the working area; anything else opens a new tab immediately.
3. **One panel for everything.** `openPanel(url, kind)` where kind is `datarobot` (same site: back, forward, failure
   detection as today) or `web` (another site: the toolbar shows its host; back and forward are hidden because another
   site's history can't be reached). The frame keeps the sandbox without top navigation, and adds
   `allow="fullscreen; autoplay; encrypted-media; picture-in-picture"` for players. The saved state keeps the last
   URL and kind.
4. **Which links:** links inside the page's content (`#main`, the steps) that point to another site or are
   DataRobot links; not the app's own pages, `mailto:`, in-page anchors, links inside the panel, or anything while
   editing. Under 900 px wide, nothing changes.
5. **The refusal note** is a small toast ("This site can't be shown inside the path, so it opened in a new tab.")
   shown once per site per page view.

## Risks / Trade-offs

- [A site's headers differ between the checked URL and pages it later navigates to, or it refuses only after
  sign-in] → the toolbar always has Open in new window; the cache expires daily.
- [The server makes outbound requests on learners' behalf] → only public addresses (each redirect checked), only
  headers are used, short timeouts, cached, signed-in users only.
