# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for local UCN branding and the supplied icon, encoded losslessly."""
from hashlib import sha256
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from app import __version__

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
FAVICON_SHA256 = "29320b9b0a2d17a8daaab7dd02e419574d73c1354b20310b664daf0a82dd6d22"


@pytest.mark.parametrize("url,status", [
    ("/", 200), ("/apply", 200), ("/status", 200),
    ("/admin/login", 200), ("/privacy", 200), ("/about", 200),
    ("/does-not-exist", 404),
])
def test_shared_branding_on_public_pages(client, url, status):
    response = client.get(url)
    assert response.status_code == status
    assert "ProxPortal" in response.text
    assert f'/static/ucn-logo.svg?v={__version__}' in response.text
    assert f'/favicon.ico?v={__version__}' in response.text
    assert 'alt="UCN — Professionshøjskolen"' in response.text
    assert 'name="theme-color" content="#004250"' in response.text
    assert 'class="brand-mark"' not in response.text


def test_favicon_matches_verified_lossless_asset(client):
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/x-icon"
    assert sha256(response.content).hexdigest() == FAVICON_SHA256
    assert response.content == (STATIC / "favicon.ico").read_bytes()
    assert response.content[:4] == b"\x00\x00\x01\x00"
    assert response.content[4:6] == b"\x03\x00"  # Three icon sizes.


def test_favicon_does_not_create_sessions(client, db):
    response = client.get("/favicon.ico")
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert response.headers["x-content-type-options"] == "nosniff"
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 0


def test_favicon_rejects_post_without_session(client, db):
    assert client.post("/favicon.ico", data={}).status_code == 405
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 0


def test_static_favicon_matches_canonical_route(client):
    assert client.get("/static/favicon.ico").content == client.get("/favicon.ico").content


def test_logo_is_local_vector_without_external_dependencies(client):
    response = client.get("/static/ucn-logo.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    svg = ET.fromstring(response.content)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert len(svg.attrib["viewBox"].split()) == 4
    assert svg.find("svg:title", ns).text == "UCN — Professionshøjskolen"
    assert svg.findall("svg:path", ns)
    for node in svg.iter():
        assert node.tag.rsplit("}", 1)[-1] not in {"script", "image", "foreignObject"}
        assert not any(key.rsplit("}", 1)[-1] == "href" for key in node.attrib)
    assert "set-cookie" not in response.headers


def test_theme_contains_the_ucn_template_palette(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    for colour in ("#004250", "#00646e", "#0096a0", "#a5dccd", "#bed6db",
                   "#ffe673", "#ffc87d", "#ffa591"):
        assert colour in response.text
    assert "@import" not in response.text


def test_brand_asset_license_is_not_misrepresented(client):
    response = client.get("/about")
    assert "ikke omfattet af kildekodens Apache-licens" in response.text
    assert "ingen automatisk VM-oprettelse" in response.text
