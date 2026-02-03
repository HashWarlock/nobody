"""Model manager for loading and switching between LLM models."""

import yaml
from pathlib import Path
from typing import Any

import config


class ModelManager:
    """Manages model loading and switching."""

    def __init__(self, models_file: Path | None = None):
        """Load models from YAML file.

        Args:
            models_file: Path to models YAML. Defaults to config.MODELS_FILE.
        """
        self.models_file = models_file or config.MODELS_FILE
        self.override_file = config.MODEL_OVERRIDE_FILE
        self._load_models()

    def _load_models(self) -> None:
        """Load models from YAML file."""
        with open(self.models_file) as f:
            data = yaml.safe_load(f)

        self.default_model = data.get("default_model", "deepseek/deepseek-v3.2")
        self.models = {m["id"]: m for m in data.get("models", [])}

    def get_current_model(self) -> str:
        """Get the currently selected model ID.

        Returns model override if set, otherwise default model.
        """
        if self.override_file.exists():
            model_id = self.override_file.read_text().strip()
            if model_id and model_id in self.models:
                return model_id
        return self.default_model

    def set_model(self, model_id: str) -> dict[str, Any]:
        """Set the current model override.

        Args:
            model_id: Model ID to switch to.

        Returns:
            The model configuration dict.

        Raises:
            ValueError: If model_id is not found.
        """
        if model_id not in self.models:
            raise ValueError(f"Unknown model: {model_id}")

        self.override_file.write_text(model_id)
        return self.models[model_id]

    def clear_override(self) -> None:
        """Clear model override, returning to default."""
        if self.override_file.exists():
            self.override_file.unlink()

    def get_model_info(self, model_id: str) -> dict[str, Any] | None:
        """Get model info by ID."""
        return self.models.get(model_id)

    def list_models(self) -> list[dict[str, Any]]:
        """List all available models.

        Returns:
            List of model configuration dicts.
        """
        return list(self.models.values())

    def list_models_formatted(self) -> str:
        """List models in a formatted string for display."""
        current = self.get_current_model()
        lines = []

        # Group by provider
        by_provider: dict[str, list] = {}
        for model in self.models.values():
            provider = model.get("provider", "unknown")
            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append(model)

        for provider, models in by_provider.items():
            lines.append(f"\n{provider.upper()}:")
            for m in models:
                marker = " *" if m["id"] == current else ""
                features = ", ".join(m.get("features", []))
                lines.append(f"  {m['id']}{marker}")
                lines.append(f"    {m['name']} [{features}]")

        lines.append(f"\n* = current model")
        return "\n".join(lines)
