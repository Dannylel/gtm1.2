import json
import re
import time
from dataclasses import dataclass
from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)
import logging

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """
    Returned by GeminiProvider.chat().
    Carries the reply text alongside exact token counts from the API response,
    so callers can log usage without a second API call.
    """
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int


class GeminiProvider:
    """
    OpenRouter-backed LLM provider.

    Two public methods:
    - generate_structured(): single-turn JSON extraction. Returns a validated
      Pydantic model. Token usage is logged to the console only (return type
      unchanged so ICPBuilder needs no edits).
    - chat(): multi-turn conversation. Returns ChatResult with text + token
      counts so callers can persist usage logs.
    """

    # gemini-2.5-flash is a *thinking* model: its reasoning tokens are drawn
    # from the same completion budget as the visible answer. Left uncapped, the
    # reasoning trace can starve a large JSON object and truncate it mid-stream.
    # We cap thinking so the structured JSON always has room to finish.
    _STRUCTURED_REASONING_TOKENS = 1024

    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.model = settings.ai_chat_chat_model
        logger.info(f"GeminiProvider initialized model={self.model}")
        self.client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.app_site_url,
                "X-Title": settings.app_site_name,
            },
        )

    # ------------------------------------------------------------------
    # Multi-turn chat (conversational / advanced ICP modes)
    # ------------------------------------------------------------------

    def chat(self, messages: list[dict[str, str]], system_prompt: str) -> ChatResult:
        """
        Send a full conversation history and get a plain-text reply.

        The system_prompt is identical on every turn so Gemini caches it
        automatically — only the new messages cost tokens from turn 2 onwards.
        X-OpenRouter-Cache also enables caching at OpenRouter's layer.

        Returns ChatResult with the reply text and exact token counts from
        the API response (not estimates).
        """
        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        logger.info(f"CHAT REQUEST | model={self.model} turns={len(messages)}")

        t0 = time.monotonic()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=0.7,
            max_tokens=self.settings.ai_chat_reply_max_tokens,
            extra_headers={"X-OpenRouter-Cache": "1"},
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        reason = response.choices[0].finish_reason
        raw = response.choices[0].message.content
        logger.info(
            "OPENROUTER RAW RESPONSE: %s %s",
            json.dumps(raw, indent=2),
            json.dumps(reason, indent=2)

        )
        if not raw:
            raise ValueError("OpenRouter returned an empty response.")

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        logger.info(
            f"CHAT RESPONSE | latency={latency_ms}ms "
            f"prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} "
            f"total_tokens={total_tokens}"
        )

        return ChatResult(
            text=raw.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Single-turn structured output (ICP generation — unchanged callers)
    # ------------------------------------------------------------------

    def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        logger.info(f"generate_structured called schema={schema.__name__}")
        final_prompt = f"""
{prompt}

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Do not wrap the JSON in triple backticks.
"""
        token_attempts = self._build_token_attempts(self.settings.ai_structured_max_tokens)
        last_error = None

        for attempt, max_tokens in enumerate(token_attempts, start=1):
            try:
                raw_text, usage = self._call_openrouter(
                    final_prompt=final_prompt,
                    max_tokens=max_tokens,
                    # schema=schema,

                )
                json_text = self._extract_json(raw_text)
                data = json.loads(json_text)
                return schema.model_validate(data)

            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                # Malformed, truncated, or schema-invalid output. The most common
                # cause here is thinking-token truncation, which MORE completion
                # room can fix — so retry with a larger budget rather than giving up.
                last_error = exc
                logger.warning(
                    f"Structured parse failed (attempt {attempt}/{len(token_attempts)}, "
                    f"max_tokens={max_tokens}): {exc}. Retrying with a larger budget if available."
                )
                continue

            except Exception as exc:
                # Transport / provider errors. Hard credit-quota failures cannot be
                # solved by changing tokens, so abort immediately on those.
                last_error = exc
                error_text = str(exc).lower()
                if (
                    "402" in error_text
                    or "more credits" in error_text
                    or "insufficient" in error_text
                    or "quota" in error_text
                ):
                    logger.error(f"OpenRouter credit/quota error — not retryable: {exc}")
                    break
                logger.warning(
                    f"OpenRouter call error (attempt {attempt}/{len(token_attempts)}): {exc}. Retrying."
                )
                continue

        raise ValueError(
            f"Structured generation failed after {len(token_attempts)} attempt(s). "
            f"Last error: {last_error}"
        )

    def _call_openrouter(self, final_prompt: str, max_tokens: int) -> tuple[str, object]:
    # def _call_openrouter(self, final_prompt: str, max_tokens: int, schema) -> tuple[str, object]:
        logger.info(f"STRUCTURED REQUEST | model={self.model} max_tokens={max_tokens}")
        t0 = time.monotonic()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise JSON generation assistant for a GTM AI platform. "
                        "Return valid JSON only."
                    ),
                },
                {"role": "user", "content": final_prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            # Force JSON mode (supported by gemini-2.5-flash via OpenRouter) so the
            # model cannot wrap the object in prose or code fences.
            response_format={"type": "json_object"},
            # response_format={
            #     "type": "json_schema",
            #     "json_schema": {
            #         "name": "icp_output",
            #         "strict": True,
            #         "schema": schema.model_json_schema(),
            #     },
            # },
            # Cap the thinking budget so reasoning tokens don't starve the JSON.
            extra_body={"reasoning": {"max_tokens": self._STRUCTURED_REASONING_TOKENS},
                        # "provider": {"require_parameters": True},},
            },
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = response.usage

        finish_reason = (
            response.choices[0].finish_reason if response.choices else None
        )
        logger.info(
            f"STRUCTURED RESPONSE | latency={latency_ms}ms finish_reason={finish_reason} "
            f"prompt_tokens={usage.prompt_tokens if usage else '?'} "
            f"completion_tokens={usage.completion_tokens if usage else '?'} "
            f"total_tokens={usage.total_tokens if usage else '?'}"
        )

        raw_text = response.choices[0].message.content
        if not raw_text:
            # Empty content almost always means the budget was consumed before any
            # visible tokens were emitted. Surface it as a retryable error.
            raise ValueError(
                f"OpenRouter returned empty content (finish_reason={finish_reason})."
            )

        return raw_text.strip(), usage

    def _build_token_attempts(self, configured_max_tokens: int) -> list[int]:
        """
        Build an ESCALATING ladder of completion budgets.

        A truncated / invalid JSON object needs MORE room to finish, not less,
        so each retry raises the ceiling instead of lowering it.
        """
        base = configured_max_tokens if configured_max_tokens and configured_max_tokens > 0 else 4000
        candidates = [base, int(base * 1.5), base * 2, 12000]

        seen = set()
        attempts = []
        for value in candidates:
            if value > 0 and value not in seen:
                seen.add(value)
                attempts.append(value)
        return attempts

    def _extract_json(self, text: str) -> str:
        """
        Extract a single balanced JSON object from the model output.

        Unlike a greedy `\\{.*\\}` regex (which on truncated text silently returns
        a broken fragment ending at the last *nested* brace), this scans for the
        first fully balanced object, ignoring braces inside string literals. If the
        object never closes, it raises — signalling the caller to retry with a
        larger token budget rather than handing json.loads a guaranteed failure.
        """
        cleaned = text.strip()

        # Strip code fences if the model added them despite JSON mode.
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        start = cleaned.find("{")
        if start == -1:
            raise ValueError(f"No JSON object found in response:\n{text[:500]}")

        depth = 0
        in_string = False
        escape = False
        end = None

        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end is None:
            raise ValueError(
                "JSON object is not balanced (output likely truncated before completion)."
            )

        candidate = cleaned[start : end + 1]
        # Remove trailing commas before a closing brace/bracket: {"a": 1,} -> {"a": 1}
        candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
        return candidate