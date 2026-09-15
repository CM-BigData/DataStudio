from __future__ import annotations

import os
from pathlib import Path

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator
from parse_engine.utilities.document.ocrflux_client import OcrFluxError, parse_document_to_markdown as parse_with_ocrflux
from parse_engine.utilities.document.openai_vision_client import parse_document_to_markdown as parse_with_openai_vision


class DocumentParseOperator(BaseOperator):
    operator_name = "document_parse"  # Operator name: registry name for provider-routed PDF/image document parsing.

    def process(self, item: DataItem) -> DataItem:
        """Parse a PDF or image into a Markdown artifact through the configured provider.

        Business logic:
            1. Pass samples outside pdf/image modalities through unchanged.
            2. Route to `openai_compatible` by default or `ocrflux` when configured.
            3. Store the resulting Markdown as both intermediate state and a markdown artifact.

        Args:
            item (DataItem): Current pdf/image sample.

        Returns:
            DataItem: Updated sample with provider-routed Markdown output or explicit issues.

        Examples:
            >>> DocumentParseOperator({}).operator_name
            'document_parse'
        """
        if item.modality not in {"pdf", "image"}:
            return item

        path = Path(item.payload["path"])
        provider = str(self.config.get("provider", "openai_compatible") or "openai_compatible").strip().lower()
        try:
            if provider == "ocrflux":
                markdown = parse_with_ocrflux(
                    path,
                    model=str(self.config.get("model", "OCRFlux-3B")),
                    url=str(self.config.get("url", "http://localhost")),
                    port=int(self.config.get("port", 8005)),
                    skip_cross_page_merge=bool(self.config.get("skip_cross_page_merge", False)),
                    max_page_retries=int(self.config.get("max_page_retries", 1)),
                )
            elif provider == "openai_compatible":
                markdown = parse_with_openai_vision(
                    path,
                    model=str(self.config.get("model", "gpt-4.1")),
                    api_key=self._resolve_secret("api_key", "api_key_env"),
                    api_base=self._resolve_optional_secret("api_base", "api_base_env"),
                    prompt=str(self.config.get("prompt", "") or "") or None,
                    max_pages=int(self.config.get("max_pages", 32)),
                )
            else:
                raise OcrFluxError(f"Unsupported document parse provider: {provider}")
        except OcrFluxError as exc:
            item.issues.append({"type": "document_parse_error", "provider": provider, "message": str(exc)})
            item.action = "failed"
            return item

        markdown = markdown.strip()
        if not markdown:
            item.issues.append({"type": "document_parse_empty", "provider": provider, "message": "Document parser returned empty markdown"})
            item.action = "failed"
            return item

        item.intermediate["markdown"] = markdown
        item.artifacts.append(
            Artifact(
                id=f"{item.id}_markdown",
                type="markdown",
                text=markdown,
                data={"artifact_count": len(item.artifacts), "provider": provider},
                source_trace=SourceTrace(file=str(path), operator=self.operator_name),
            )
        )
        item.metrics["document_parse_provider"] = provider
        item.metrics["document_parse_text_length"] = len(markdown)
        item.action = "parsed"
        return item

    def _resolve_secret(self, direct_key: str, env_key: str) -> str:
        """Resolve a required direct or environment-backed secret from workflow config.

        业务逻辑：
            1. Prefer an explicit direct value when the workflow provides one.
            2. Otherwise read the environment variable named by the workflow.
            3. Raise an OcrFluxError when no value can be resolved.

        Args:
            direct_key (str): Direct-value field name.
            env_key (str): Environment-variable-name field.

        Returns:
            str: Resolved secret value.

        Examples:
            >>> DocumentParseOperator({'api_key': 'x'})._resolve_secret('api_key', 'api_key_env')
            'x'
        """
        if self.config.get(direct_key):
            return str(self.config[direct_key])
        if self.config.get(env_key):
            env_name = str(self.config[env_key])
            value = os.getenv(env_name)
            if value:
                return value
            raise OcrFluxError(f"Required environment variable is missing: {env_name}")
        raise OcrFluxError(f"Workflow must provide `{direct_key}` or `{env_key}`")

    def _resolve_optional_secret(self, direct_key: str, env_key: str) -> str | None:
        """Resolve an optional direct or environment-backed setting from workflow config.

        业务逻辑：
            1. Prefer an explicit direct value when provided.
            2. Otherwise read the environment variable named by the workflow.
            3. Return None when neither source is configured.

        Args:
            direct_key (str): Direct-value field name.
            env_key (str): Environment-variable-name field.

        Returns:
            str | None: Resolved optional value or None.

        Examples:
            >>> DocumentParseOperator({})._resolve_optional_secret('api_base', 'api_base_env') is None
            True
        """
        if self.config.get(direct_key):
            return str(self.config[direct_key])
        if self.config.get(env_key):
            env_name = str(self.config[env_key])
            value = os.getenv(env_name)
            if value:
                return value
            raise OcrFluxError(f"Required environment variable is missing: {env_name}")
        return None
