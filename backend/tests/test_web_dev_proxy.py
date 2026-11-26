import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import api_path_sections, create_app, is_page_request

from tests.test_backend_hygiene_security import TEST_FERNET_KEY
VITE_CONFIG = Path(__file__).resolve().parents[2] / "web" / "vite.config.js"
BROWSER = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


def test_vite_proxies_every_api_section():
    if not VITE_CONFIG.is_file():
        pytest.skip("web app is not checked out next to the backend")
    block = re.search(r"apiPrefixes = \[(.*?)\];", VITE_CONFIG.read_text(encoding="utf-8"), re.S).group(1)
    proxied = {prefix.strip("/") for prefix in re.findall(r"'([^']+)'", block)}
    app = create_app(Settings(_env_file=None, encryption_key=TEST_FERNET_KEY))
    assert api_path_sections(app) - proxied == set()


@pytest.mark.parametrize(("method", "path", "accept", "expected"), [
    ("GET", "/insights", BROWSER["accept"], True),
    ("GET", "/warehouse/items", BROWSER["accept"], True),
    ("GET", "/insights", "*/*", False),
    ("GET", "/insights", "application/json", False),
    ("POST", "/insights", BROWSER["accept"], False),
    ("GET", "/docs", BROWSER["accept"], False),
    ("GET", "/assets/index.js", BROWSER["accept"], False),
    ("GET", "/favicon.ico", BROWSER["accept"], False),
])
def test_page_requests_are_recognised(method, path, accept, expected):
    assert is_page_request(method, path, accept) is expected


def test_refreshing_a_page_that_shares_an_api_path_loads_the_app(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>ERP</title>", encoding="utf-8")
    client = TestClient(create_app(Settings(_env_file=None, encryption_key=TEST_FERNET_KEY, frontend_dir=str(tmp_path))))
    page = client.get("/insights", headers=BROWSER)
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert client.get("/insights").status_code == 401
    assert client.get("/stock/unknown").status_code == 404
