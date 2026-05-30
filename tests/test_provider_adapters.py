from types import SimpleNamespace

from prototype.jimsai.provider_adapters import ProductionRuntime, ProductionSettings, ProviderStatus


def test_production_does_not_enable_local_multimodal_by_default(monkeypatch):
    monkeypatch.setenv("JIMS_STORAGE_BACKEND", "production")
    monkeypatch.delenv("JIMS_ENABLE_MULTIMODAL_ENCODERS", raising=False)
    monkeypatch.delenv("JIMS_MULTIMODAL_ENCODER_MODE", raising=False)
    monkeypatch.delenv("JIMS_MULTIMODAL_ENCODER_URL", raising=False)

    settings = ProductionSettings.from_env()

    assert settings.effective_multimodal_encoder_mode == "disabled"
    assert settings.enable_multimodal_encoders is False


def test_external_multimodal_url_selects_external_encoder(monkeypatch):
    monkeypatch.setenv("JIMS_STORAGE_BACKEND", "production")
    monkeypatch.delenv("JIMS_ENABLE_MULTIMODAL_ENCODERS", raising=False)
    monkeypatch.delenv("JIMS_MULTIMODAL_ENCODER_MODE", raising=False)
    monkeypatch.setenv("JIMS_MULTIMODAL_ENCODER_URL", "https://encoder.example.com")

    settings = ProductionSettings.from_env()

    assert settings.effective_multimodal_encoder_mode == "external"
    assert settings.enable_multimodal_encoders is True


def test_multimodal_can_be_explicitly_disabled_with_url(monkeypatch):
    monkeypatch.setenv("JIMS_STORAGE_BACKEND", "production")
    monkeypatch.setenv("JIMS_ENABLE_MULTIMODAL_ENCODERS", "false")
    monkeypatch.setenv("JIMS_MULTIMODAL_ENCODER_URL", "https://encoder.example.com")

    settings = ProductionSettings.from_env()

    assert settings.effective_multimodal_encoder_mode == "external"
    assert settings.enable_multimodal_encoders is False


def test_local_multimodal_mode_is_not_supported(monkeypatch):
    monkeypatch.setenv("JIMS_STORAGE_BACKEND", "production")
    monkeypatch.setenv("JIMS_MULTIMODAL_ENCODER_MODE", "local")

    settings = ProductionSettings.from_env()

    assert settings.effective_multimodal_encoder_mode == "disabled"
    assert settings.enable_multimodal_encoders is False


def test_runtime_provider_attempt_degrades_without_raising():
    runtime = ProductionRuntime.__new__(ProductionRuntime)
    runtime.settings = SimpleNamespace(strict_provider_startup=True)
    runtime.statuses = {
        "vectorize": ProviderStatus(name="vectorize", configured=True, available=True, detail="ready")
    }

    result = runtime._attempt("vectorize", lambda: (_ for _ in ()).throw(TimeoutError("provider timeout")))

    assert result is None
    assert runtime.statuses["vectorize"].available is False
    assert "provider timeout" in runtime.statuses["vectorize"].detail
