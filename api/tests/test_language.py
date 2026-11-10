"""The visitor's language (D-027) with the scripted fake model and the real database: Spanish and
French reach the model, English leaves the prompts as they were, and anything else is refused
before a model call."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from api import chat, report
from api.agent import Settings
from api.db import connect
from api.tests.fake_model import FakeClient, message, text
from api.tests.test_api import REPORT, gather, write_report

SETTINGS = Settings(api_key="test-key", model="claude-sonnet-5-5", allow_no_spend_cap=True)
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
RULES = {"es": "in Spanish", "fr": "in French"}


@pytest.fixture
def use_model():
    def install(client):
        app_module.app.dependency_overrides[app_module.get_settings] = lambda: SETTINGS
        app_module.app.dependency_overrides[app_module.get_client] = lambda: client
        return client

    yield install
    app_module.app.dependency_overrides.clear()


@pytest.fixture
def http():
    return TestClient(app_module.app)


def first_prompt(model):
    return model.requests[0]["messages"][0]["content"]


def system_text(model):
    return json.dumps(model.requests[0]["system"])


@pytest.mark.parametrize("language", ["es", "fr"])
def test_the_report_is_written_in_the_chosen_language(http, use_model, language):
    model = use_model(FakeClient([gather, write_report()]))
    response = http.post("/report", json={**REPORT, "language": language})
    assert response.status_code == 200 and response.json()["status"] == "verified"
    prompt = first_prompt(model)
    assert RULES[language] in prompt
    assert all(rule not in prompt for code, rule in RULES.items() if code != language)


def test_an_english_report_has_no_language_rule(http, use_model):
    model = use_model(FakeClient([gather, write_report()]))
    assert http.post("/report", json={**REPORT, "language": "en"}).status_code == 200
    unset = use_model(FakeClient([gather, write_report()]))
    assert http.post("/report", json=REPORT).status_code == 200
    assert first_prompt(model) == first_prompt(unset)
    assert not any(rule in first_prompt(model) for rule in RULES.values())


@pytest.mark.parametrize("language", ["es", "fr"])
def test_the_chat_answers_in_the_chosen_language(http, use_model, language):
    model = use_model(FakeClient([message(text("ok"))]))
    response = http.post("/chat", json={"messages": [{"role": "user", "content": "hola"}], "language": language})
    assert response.status_code == 200
    assert f"Answer {RULES[language]}" in system_text(model)


@pytest.mark.parametrize(
    "path, body",
    [
        ("/report/stream", {**REPORT, "language": "de"}),
        ("/report", {**REPORT, "language": "ES"}),
        ("/chat", {"messages": [{"role": "user", "content": "hi"}], "language": "pt"}),
        ("/chat", {"messages": [{"role": "user", "content": "hi"}], "language": None}),
    ],
)
def test_another_language_is_refused_before_any_model_call(http, use_model, path, body):
    model = use_model(FakeClient([]))
    assert http.post(path, json=body).status_code == 422
    assert model.requests == []


def test_english_prompts_are_the_ones_the_evals_use():
    """The evals call chat_system_prompt(conn) and the report's English prompt has no extra rule."""
    p, o = {"player": {"player_id": 1, "name": "A"}}, {"player": {"player_id": 2, "name": "B"}}
    english = report.report_prompt(p, o, "Clay", "2024-10-26", "2026-10-26")
    assert report.report_prompt(p, o, "Clay", "2024-10-26", "2026-10-26", "en") == english
    for language, rule in RULES.items():
        assert report.report_prompt(p, o, "Clay", "2024-10-26", "2026-10-26", language) == english + report.REPORT_LANGUAGE_RULES[language]
        assert rule in report.REPORT_LANGUAGE_RULES[language]
    with connect() as conn:
        assert chat.chat_system_prompt(conn, "en") == chat.chat_system_prompt(conn)
