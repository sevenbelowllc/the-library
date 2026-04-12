"""PluginRegistry — discovers, validates, and manages extractors."""

from __future__ import annotations

from library_server.vault_builder.extractors.base import BaseExtractor


class PluginRegistry:
    """Registry for vault builder extractors."""

    def __init__(self) -> None:
        self._extractors: dict[str, BaseExtractor] = {}

    def register(self, extractor: BaseExtractor) -> None:
        """Register an extractor. Raises ValueError on duplicate name or output_subdir."""
        if extractor.name in self._extractors:
            raise ValueError(f"Extractor '{extractor.name}' already registered")

        for existing in self._extractors.values():
            if existing.output_subdir == extractor.output_subdir:
                raise ValueError(
                    f"Extractor '{extractor.name}' has output_subdir '{extractor.output_subdir}' "
                    f"which conflicts with '{existing.name}'"
                )

        self._extractors[extractor.name] = extractor

    def get(self, name: str) -> BaseExtractor | None:
        """Get an extractor by name."""
        return self._extractors.get(name)

    def list_extractors(self) -> list[str]:
        """List all registered extractor names."""
        return list(self._extractors.keys())

    def get_enabled(self) -> list[BaseExtractor]:
        """Get all enabled extractors."""
        return [e for e in self._extractors.values() if e.is_enabled]

    def get_by_names(self, names: list[str]) -> list[BaseExtractor]:
        """Get extractors by name. Ignores unknown names."""
        return [self._extractors[n] for n in names if n in self._extractors]

    def validate_all(self) -> dict[str, list[str]]:
        """Validate all enabled extractors. Returns {name: [errors]} for extractors with errors."""
        errors: dict[str, list[str]] = {}
        for ext in self.get_enabled():
            ext_errors = ext.validate_config()
            if ext_errors:
                errors[ext.name] = ext_errors
        return errors
