from serial_writer.config import Settings, ModelSpec
from serial_writer.doctor import resolve_models_from_list


def test_model_name_resolution():
    models = {
        "gemini-3.5-flash": ModelSpec(match=["3.5", "flash"], exclude=["lite"], rpm=5, tpm=250000, rpd=20),
        "gemini-3.5-flash-lite": ModelSpec(match=["3.5", "flash", "lite"], exclude=[], rpm=15, tpm=250000, rpd=500),
        "gemma-4-31b": ModelSpec(match=["gemma", "4", "31b"], exclude=[], rpm=30, tpm=16000, rpd=14400),
    }

    available_api_models = [
        "models/gemini-3.5-flash-preview",
        "models/gemini-3.5-flash-001",
        "models/gemini-3.5-flash-lite-preview",
        "models/gemma-4-31b-it",
    ]

    resolved = resolve_models_from_list(models, available_api_models)

    assert resolved["gemini-3.5-flash"] == "gemini-3.5-flash-001"
    assert resolved["gemini-3.5-flash-lite"] == "gemini-3.5-flash-lite-preview"
    assert resolved["gemma-4-31b"] == "gemma-4-31b-it"


def test_resolution_drops_missing_and_handles_empty():
    models = {
        "nonexistent-model": ModelSpec(match=["nonexistent"], exclude=[], rpm=5, tpm=250000, rpd=20)
    }
    available_api_models = ["models/gemini-1.5-flash"]
    resolved = resolve_models_from_list(models, available_api_models)
    assert "nonexistent-model" not in resolved
