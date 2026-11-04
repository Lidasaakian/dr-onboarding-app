# Tasks

## 1. Server

- [x] 1.1 Add `framing.py` (`embed_url`, `allows_framing`, `Checker` with redirect-by-hand, public-address check and 24-hour cache); verify unit tests for YouTube/Vimeo conversion, every header case (none, DENY, SAMEORIGIN, frame-ancestors none/self/*/our origin) and a private address refused without a request
- [x] 1.2 Add `POST api/frameable`; verify an app test with the network stubbed

## 2. Pages

- [x] 2.1 Generalize the panel in `static/assets/common.js` to any frameable link (kinds, toolbar label, back/forward only for DataRobot, player permissions, saved state), ask `api/frameable` for the content's links after load, route clicks, and show the note for refused sites; verify locally with a docs link, a YouTube link, a refusing site and a modifier click
- [x] 2.2 Update README; rebuild `static/`; verify the full test suite passes
