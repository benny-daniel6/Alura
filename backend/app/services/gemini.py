"""
Minimal async client for the Gemini REST API (generateContent).

Used for:
- structured JSON generation (AI stylist, garment tagging) via responseSchema
- image editing (garment -> white-background product shot) via the image model

Plain httpx keeps the dependency surface small; pass `transport` in tests to mock the API.
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    pass


class GeminiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        text_model: Optional[str] = None,
        image_model: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = settings.GEMINI_API_KEY if api_key is None else api_key
        self.base_url = (base_url or settings.GEMINI_API_BASE_URL).rstrip("/")
        self.text_model = text_model or settings.GEMINI_TEXT_MODEL
        self.image_model = image_model or settings.GEMINI_IMAGE_MODEL
        self.timeout = timeout or settings.GEMINI_TIMEOUT_SECONDS
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _generate(self, model: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            raise GeminiError("GEMINI_API_KEY is not configured")
        url = f"{self.base_url}/models/{model}:generateContent"
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            resp = await client.post(url, json=body, headers={"x-goog-api-key": self.api_key})
        if resp.status_code != 200:
            # Error bodies never contain the key; keep them short in logs
            raise GeminiError(f"Gemini {model} returned HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise GeminiError(f"Gemini {model} returned no result ({reason})")
        return candidates[0]

    @staticmethod
    def _parts(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
        return (candidate.get("content") or {}).get("parts") or []

    @staticmethod
    def _image_part(image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}}

    async def generate_json(
        self,
        system_instruction: str,
        prompt: str,
        response_schema: Dict[str, Any],
        images: Optional[List[tuple]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Returns the parsed JSON object produced under `response_schema` (OpenAPI-subset schema)."""
        parts: List[Dict[str, Any]] = [self._image_part(b, m) for b, m in (images or [])]
        parts.append({"text": prompt})
        body = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }
        candidate = await self._generate(self.text_model, body)
        text = "".join(p.get("text", "") for p in self._parts(candidate)).strip()
        if not text:
            raise GeminiError(f"Gemini returned no text (finishReason={candidate.get('finishReason')})")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise GeminiError(f"Gemini returned invalid JSON: {e}") from e

    async def edit_image(self, image_bytes: bytes, mime_type: str, prompt: str) -> bytes:
        """Sends a photo plus instructions to the image model and returns the first image it produces."""
        body = {
            "contents": [{"role": "user", "parts": [self._image_part(image_bytes, mime_type), {"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        candidate = await self._generate(self.image_model, body)
        for part in self._parts(candidate):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
        raise GeminiError(f"Gemini image model returned no image (finishReason={candidate.get('finishReason')})")


gemini_client = GeminiClient()
