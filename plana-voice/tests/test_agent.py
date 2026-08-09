from types import SimpleNamespace
from unittest.mock import sentinel

import pytest

import agent


def test_gemini_live_model_uses_the_google_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Gemini credential stays in the agent process, not the browser."""
    captured: dict[str, object] = {}

    def fake_realtime_model(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel.realtime_model

    monkeypatch.setenv("GOOGLE_API_KEY", "google-api-key")
    monkeypatch.setenv("GEMINI_LIVE_MODEL", "custom-live-model")
    monkeypatch.setenv("GEMINI_LIVE_VOICE", "Aoede")
    monkeypatch.setattr(
        agent.google.realtime,
        "RealtimeModel",
        fake_realtime_model,
    )

    assert agent.create_gemini_live_model() is sentinel.realtime_model
    assert captured == {
        "api_key": "google-api-key",
        "instructions": agent.VOICE_INSTRUCTIONS,
        "model": "custom-live-model",
        "temperature": 0.8,
        "voice": "Aoede",
    }


def test_gemini_live_model_requires_a_google_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        agent.create_gemini_live_model()


def test_voice_input_uses_the_quail_voice_focus_small_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_enhancement: dict[str, object] = {}
    captured_options: dict[str, object] = {}

    def fake_audio_enhancement(**kwargs: object) -> object:
        captured_enhancement.update(kwargs)
        return sentinel.noise_cancellation

    def fake_audio_input_options(**kwargs: object) -> object:
        captured_options.update(kwargs)
        return sentinel.audio_input_options

    monkeypatch.setattr(
        agent,
        "ai_coustics",
        SimpleNamespace(
            EnhancerModel=SimpleNamespace(QUAIL_VF_S=sentinel.quail_vf_s),
            audio_enhancement=fake_audio_enhancement,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        agent,
        "room_io",
        SimpleNamespace(AudioInputOptions=fake_audio_input_options),
        raising=False,
    )

    assert agent.create_audio_input_options() is sentinel.audio_input_options
    assert captured_enhancement == {"model": sentinel.quail_vf_s}
    assert captured_options == {"noise_cancellation": sentinel.noise_cancellation}


def test_plan_a_voice_instructions_are_short_and_conversational() -> None:
    assert "Plan A" in agent.VOICE_INSTRUCTIONS
    assert "one question at a time" in agent.VOICE_INSTRUCTIONS
