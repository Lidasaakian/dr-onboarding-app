"""Which links can be shown in the working area (spec learner-workspace, content-in-working-area)."""

import types

import framing
from framing import Checker, allows_framing, embed_url

OURS = "https://app.datarobot.com"


def test_youtube_and_vimeo_become_players():
    assert embed_url("https://www.youtube.com/watch?v=abc123XYZ&t=42s") == "https://www.youtube.com/embed/abc123XYZ?start=42"
    assert embed_url("https://youtu.be/abc123XYZ") == "https://www.youtube.com/embed/abc123XYZ"
    assert embed_url("https://www.youtube.com/shorts/abc123XYZ") == "https://www.youtube.com/embed/abc123XYZ"
    assert embed_url("https://vimeo.com/76979871") == "https://player.vimeo.com/video/76979871"
    assert embed_url("https://docs.python.org/3/") == "https://docs.python.org/3/"


def test_header_rules():
    t = "https://docs.example.com/page"
    assert allows_framing({}, OURS, t) is True
    assert allows_framing({"X-Frame-Options": "DENY"}, OURS, t) is False
    assert allows_framing({"X-Frame-Options": "SAMEORIGIN"}, OURS, t) is False
    assert allows_framing({"X-Frame-Options": "SAMEORIGIN"}, OURS, "https://app.datarobot.com/usecases") is True
    assert allows_framing({"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'"}, OURS, t) is False
    assert allows_framing({"Content-Security-Policy": "frame-ancestors 'self'"}, OURS, t) is False
    assert allows_framing({"Content-Security-Policy": "frame-ancestors *"}, OURS, t) is True
    assert allows_framing({"Content-Security-Policy": "frame-ancestors https://*.datarobot.com"}, OURS, t) is True
    assert allows_framing({"Content-Security-Policy": "frame-ancestors https:"}, OURS, t) is True
    assert allows_framing({"Content-Security-Policy": "frame-ancestors https://other.com"}, OURS, t) is False
    # frame-ancestors wins over X-Frame-Options, as in browsers
    assert allows_framing({"X-Frame-Options": "DENY", "Content-Security-Policy": "frame-ancestors *"}, OURS, t) is True


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, **kw):
        self.asked.append(url)
        status, headers = self.pages[url]
        return types.SimpleNamespace(status_code=status, headers=headers, is_redirect=300 <= status < 400, close=lambda: None)


def test_checker_follows_redirects_and_caches(monkeypatch):
    monkeypatch.setattr(framing, "public_url", lambda u: True)
    http = FakeHttp({"https://a.com/x": (301, {"location": "https://b.com/y"}), "https://b.com/y": (200, {})})
    c = Checker(http)
    assert c.check(["https://a.com/x"], OURS)["https://a.com/x"]["frame"] is True
    c.check(["https://a.com/x"], OURS)
    assert http.asked == ["https://a.com/x", "https://b.com/y"]  # the second check came from the cache


def test_private_addresses_are_never_contacted():
    http = FakeHttp({})
    assert Checker(http).check(["http://10.0.0.5/admin", "http://127.0.0.1:8765/"], OURS) == {
        "http://10.0.0.5/admin": {"frame": False, "embed": "http://10.0.0.5/admin"},
        "http://127.0.0.1:8765/": {"frame": False, "embed": "http://127.0.0.1:8765/"}}
    assert http.asked == []


def test_redirect_to_a_private_address_is_refused(monkeypatch):
    monkeypatch.setattr(framing, "public_url", lambda u: "10.0.0.5" not in u)
    http = FakeHttp({"https://a.com/x": (302, {"location": "http://10.0.0.5/"})})
    assert Checker(http).check(["https://a.com/x"], OURS)["https://a.com/x"]["frame"] is False
    assert http.asked == ["https://a.com/x"]


def test_videos_need_no_request():
    http = FakeHttp({})
    r = Checker(http).check(["https://youtu.be/abc123XYZ"], OURS)
    assert r["https://youtu.be/abc123XYZ"] == {"frame": True, "embed": "https://www.youtube.com/embed/abc123XYZ"}
    assert http.asked == []


def test_api_frameable(client, app_module, monkeypatch):
    monkeypatch.setattr(framing, "public_url", lambda u: True)
    http = FakeHttp({"https://docs.example.com/": (200, {}), "https://academy.example.com/": (200, {"X-Frame-Options": "SAMEORIGIN"})})
    monkeypatch.setattr(app_module, "frame_checker", Checker(http))
    r = client.post("/api/frameable", json={"origin": OURS, "urls": ["https://docs.example.com/", "https://academy.example.com/",
                                                                      "https://youtu.be/abc123XYZ", "mailto:x@y.z"]})
    links = r.json()["links"]
    assert links["https://docs.example.com/"]["frame"] is True
    assert links["https://academy.example.com/"]["frame"] is False
    assert links["https://youtu.be/abc123XYZ"]["embed"] == "https://www.youtube.com/embed/abc123XYZ"
    assert "mailto:x@y.z" not in links
    assert client.post("/api/frameable", json={"origin": "javascript:x", "urls": []}).status_code == 400
