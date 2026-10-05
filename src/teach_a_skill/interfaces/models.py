"""Model provider and runtime inference interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class IModelProvider(ABC):
    """Abstract model provider contract for managing local model runtimes."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier of the backend provider (e.g. 'llama_cpp', 'onnx', 'mlx')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider backend runtime dependencies are installed and operational."""
        pass

    @abstractmethod
    def load_model(self, model_id: str, device: str = "cpu") -> Any:
        """Load model weights into memory. In Phase 1, raises NotImplementedError."""
        pass

    @abstractmethod
    def unload_model(self, model_id: str) -> None:
        """Release model weights and reclaim memory."""
        pass

    @abstractmethod
    def get_loaded_models(self) -> list[str]:
        """List currently loaded model IDs."""
        pass


class IModelRegistry(ABC):
    """Registry interface for model descriptors and capability matching."""

    @abstractmethod
    def register(self, descriptor: Any) -> None:
        """Register a model descriptor."""
        pass

    @abstractmethod
    def get(self, model_id: str) -> Optional[Any]:
        """Retrieve model descriptor by ID."""
        pass

    @abstractmethod
    def list_models(self) -> list[Any]:
        """List all registered model descriptors."""
        pass

    @abstractmethod
    def find_compatible_models(self, budget: Any) -> list[Any]:
        """Filter models that can operate safely within the provided resource budget."""
        pass
