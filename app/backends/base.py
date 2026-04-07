"""Abstract base class for reasoning backends."""

from __future__ import annotations

import abc
import json
import logging
import re

from pydantic import BaseModel, ValidationError

from app.backends.models import BackendDescriptor, BackendRequest, BackendResponse, TaskName

logger = logging.getLogger(__name__)


class ReasoningBackend(abc.ABC):
    """Protocol that all execution backends must implement."""

    @abc.abstractmethod
    async def generate(self, request: BackendRequest) -> BackendResponse:
        """Generate a text completion for the given request."""

    @abc.abstractmethod
    def is_available(self, task: TaskName | None = None) -> bool:
        """Return True if this backend is configured and reachable for the given task."""

    @abc.abstractmethod
    def describe(self, task: TaskName | None = None) -> BackendDescriptor:
        """Return metadata about this backend's configuration for a task."""

    async def generate_structured(
        self,
        request: BackendRequest,
        schema_class: type[BaseModel] | None = None,
    ) -> BackendResponse:
        """Generate text and parse as JSON, optionally validating with Pydantic.

        Calls generate() then strips fences / validates.
        Subclasses may override for native structured-output support.
        """
        response = await self.generate(request)
        if not response.success:
            return response

        cleaned = _extract_json(response.text)
        if cleaned is None:
            response.error = "Backend response did not contain valid JSON"
            response.success = False
            return response

        if schema_class is not None:
            try:
                if isinstance(cleaned, str):
                    schema_class.model_validate_json(cleaned)
                else:
                    schema_class.model_validate(cleaned)
            except ValidationError as exc:
                logger.warning("Schema validation failed for %s: %s", request.task, exc)
                response.error = f"Schema validation failed: {exc}"
                response.success = False
                return response

        response.text = cleaned if isinstance(cleaned, str) else json.dumps(cleaned)
        return response


def _extract_json(text: str) -> str | None:
    """Best-effort extraction of a JSON object or array from free-form text."""
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n", 1)
        body = lines[1] if len(lines) > 1 else ""
        if body.endswith("```"):
            body = body[: -3]
        text = body.strip()

    for attempt in (text,):
        try:
            json.loads(attempt)
            return attempt
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        candidate = match.group(1)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return None
