from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
import zoneinfo
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from serial_writer.config import Settings, ModelSpec
from serial_writer.trace import BudgetExceeded, BudgetGuard, append_event

T = TypeVar("T", bound=BaseModel)


class QuotaExhausted(Exception):
    def __init__(self, reset_at: str):
        self.reset_at = reset_at
        super().__init__(f"Daily quota exhausted for all models. Resets at {reset_at}")


class LLMResult(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    thought_tokens: int = 0
    latency_s: float
    model: str
    wait_s: float = 0.0
    fallbacks: List[str] = Field(default_factory=list)
    real_cost_usd: float = 0.0
    notional_cost_usd: float = 0.0


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        run_dir: Path,
        transport: Optional[Any] = None,
        clock: Optional[Any] = None,
    ):
        self.settings = settings
        self.run_dir = run_dir
        self.transport = transport
        self.clock = clock or (lambda: time.time())
        self.genai_client = None

        if not transport and settings.gemini_api_key:
            self.genai_client = genai.Client(api_key=settings.gemini_api_key)

        self.sticky_primaries: Dict[str, str] = {}
        self.request_timestamps: Dict[str, List[float]] = {}
        self.token_timestamps: Dict[str, List[Tuple[float, int]]] = {}
        self.budget_guard = BudgetGuard(
            per_episode_cap=settings.per_episode_cost_cap_usd,
            max_calls_per_episode=settings.max_calls_per_episode,
            total_cap=settings.total_budget_cap_usd,
            run_dir=run_dir,
        )

    def _get_tz_date(self) -> str:
        try:
            tz = zoneinfo.ZoneInfo(self.settings.day_boundary_tz)
        except Exception:
            tz = timezone.utc
        now = datetime.fromtimestamp(self.clock(), tz=tz)
        return now.strftime("%Y-%m-%d")

    def _get_next_reset_time(self) -> str:
        try:
            tz = zoneinfo.ZoneInfo(self.settings.day_boundary_tz)
        except Exception:
            tz = timezone.utc
        now = datetime.fromtimestamp(self.clock(), tz=tz)
        tomorrow = now.date() + timedelta(days=1)
        reset_dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=tz)
        return reset_dt.isoformat()

    def _load_quota(self) -> Dict[str, Any]:
        quota_path = self.run_dir / "quota.json"
        if quota_path.exists():
            try:
                return json.loads(quota_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_quota(self, quota_data: Dict[str, Any]) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        quota_path = self.run_dir / "quota.json"
        quota_path.write_text(json.dumps(quota_data, indent=2), encoding="utf-8")

    def _record_usage(self, model_name: str, req_count: int = 1, tok_count: int = 0) -> None:
        quota_data = self._load_quota()
        today = self._get_tz_date()
        date_data = quota_data.get(today, {})
        model_data = date_data.get(model_name, {"requests": 0, "tokens": 0, "exhausted": False})

        model_data["requests"] += req_count
        model_data["tokens"] += tok_count
        date_data[model_name] = model_data
        quota_data[today] = date_data
        self._save_quota(quota_data)

    def _mark_exhausted(self, model_name: str) -> None:
        quota_data = self._load_quota()
        today = self._get_tz_date()
        date_data = quota_data.get(today, {})
        model_data = date_data.get(model_name, {"requests": 0, "tokens": 0, "exhausted": False})
        model_data["exhausted"] = True
        date_data[model_name] = model_data
        quota_data[today] = date_data
        self._save_quota(quota_data)

    def _check_remaining_rpd(self, model_name: str, spec: ModelSpec) -> int:
        quota_data = self._load_quota()
        today = self._get_tz_date()
        model_data = quota_data.get(today, {}).get(model_name, {})
        if model_data.get("exhausted", False):
            return 0
        used_requests = model_data.get("requests", 0)
        return max(0, spec.rpd - used_requests)

    def _calculate_rate_wait(self, model_name: str, spec: ModelSpec, est_tokens: int) -> float:
        now = self.clock()
        cutoff_min = now - 60.0

        req_times = [t for t in self.request_timestamps.get(model_name, []) if t > cutoff_min]
        self.request_timestamps[model_name] = req_times

        tok_times = [(t, n) for t, n in self.token_timestamps.get(model_name, []) if t > cutoff_min]
        self.token_timestamps[model_name] = tok_times

        req_wait = 0.0
        if len(req_times) >= spec.rpm:
            req_wait = req_times[0] + 60.0 - now

        current_tokens = sum(n for _, n in tok_times)
        tok_wait = 0.0
        if current_tokens + est_tokens > spec.tpm and tok_times:
            tok_wait = tok_times[0][0] + 60.0 - now

        return max(0.0, req_wait, tok_wait)

    def list_available_models(self) -> List[str]:
        if self.transport and hasattr(self.transport, "list_models"):
            return self.transport.list_models()
        if not self.genai_client:
            return list(self.settings.models.keys())
        models_page = self.genai_client.models.list()
        return [m.name for m in models_page]

    def _call_gemini(
        self,
        model_id: str,
        contents: str,
        config: Optional[types.GenerateContentConfig] = None,
    ) -> Dict[str, Any]:
        if self.transport:
            return self.transport.execute(model_id, contents, config)

        if not self.genai_client:
            raise ValueError("GEMINI_API_KEY is not set.")

        response = self.genai_client.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )

        in_tok = 0
        out_tok = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            in_tok = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            out_tok = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        return {
            "text": response.text or "",
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
        }

    def complete_with_model(
        self,
        model_id: str,
        system: str,
        user: str,
        *,
        step: str = "llm_call",
        episode: Optional[int] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> LLMResult:
        contents = f"{system}\n\n{user}" if system else user
        t0 = self.clock()
        res_data = self._call_gemini(model_id, contents, None)
        latency = self.clock() - t0

        return LLMResult(
            text=res_data.get("text", ""),
            input_tokens=res_data.get("usage", {}).get("input_tokens", 0),
            output_tokens=res_data.get("usage", {}).get("output_tokens", 0),
            latency_s=latency,
            model=model_id,
        )

    def complete(
        self,
        role: str,
        system: str,
        user: str,
        *,
        step: str = "llm_call",
        episode: Optional[int] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResult:
        chain = self.settings.roles.get(role, [])
        if not chain:
            raise ValueError(f"No models configured for role: {role}")

        est_prompt_tokens = int((len(system) + len(user)) / 4)
        selected_name = None
        fallbacks_used = []
        total_wait_s = 0.0

        candidates = list(chain)
        primary = self.sticky_primaries.get(role)
        if primary in candidates:
            candidates.remove(primary)
            candidates.insert(0, primary)

        best_candidate = None
        best_wait = 999999.0

        for cand_name in candidates:
            spec = self.settings.models.get(cand_name)
            if not spec:
                continue

            if self._check_remaining_rpd(cand_name, spec) <= 1:
                fallbacks_used.append(f"skipped_{cand_name}_rpd_exhausted")
                continue

            if spec.max_prompt_tokens < est_prompt_tokens:
                fallbacks_used.append(f"skipped_{cand_name}_prompt_too_large")
                continue

            wait_s = self._calculate_rate_wait(cand_name, spec, est_prompt_tokens)
            if wait_s < 20.0:
                best_candidate = cand_name
                best_wait = wait_s
                break
            elif wait_s < best_wait:
                best_candidate = cand_name
                best_wait = wait_s

        if not best_candidate:
            raise QuotaExhausted(self._get_next_reset_time())

        selected_name = best_candidate
        spec = self.settings.models[selected_name]

        if primary and primary != selected_name:
            append_event(
                self.run_dir,
                step=step,
                episode=episode,
                role=role,
                decision="model_switch",
                notes=f"Switched sticky primary from {primary} to {selected_name}",
            )
        self.sticky_primaries[role] = selected_name

        if best_wait > 0.0:
            time.sleep(best_wait)
            total_wait_s += best_wait

        contents = user
        sys_prompt = system if spec.system_prompt else None
        if not spec.system_prompt and system:
            contents = f"[SYSTEM INSTRUCTION]\n{system}\n\n[USER INPUT]\n{user}"

        cfg_kwargs: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if sys_prompt:
            cfg_kwargs["system_instruction"] = sys_prompt

        if schema and spec.json_mode:
            cfg_kwargs["response_mime_type"] = "application/json"
            cfg_kwargs["response_schema"] = schema

        thinking_val = self.settings.thinking.get(role, "off")
        if thinking_val != "off" and hasattr(types, "ThinkingConfig"):
            # If the SDK expects ThinkingConfig object or specific keys
            try:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=thinking_val if isinstance(thinking_val, int) else None
                )
            except Exception:
                # Fallback for SDK compatibility
                pass

        config = types.GenerateContentConfig(**cfg_kwargs) if hasattr(types, "GenerateContentConfig") else None

        result_text = ""
        in_tok = 0
        out_tok = 0
        thought_tok = 0
        attempt = 0
        last_error: Exception | None = None
        t0 = self.clock()

        while attempt < self.settings.max_retries:
            try:
                estimated_cost = (
                    est_prompt_tokens / 1_000_000.0 * spec.price_in
                    + max_tokens / 1_000_000.0 * spec.price_out
                )
                budget_episode = episode if episode is not None else 0
                self.budget_guard.check_before_call(
                    budget_episode,
                    estimated_cost=max(estimated_cost, 0.000001),
                )
                attempt += 1
                res_dict = self._call_gemini(selected_name, contents, config)
                result_text = res_dict.get("text", "")
                usage = res_dict.get("usage", {})
                in_tok = usage.get("input_tokens", est_prompt_tokens)
                out_tok = usage.get("output_tokens", int(len(result_text) / 4))
                last_error = None
                break
            except Exception as err:
                if isinstance(err, BudgetExceeded):
                    raise
                err_msg = str(err)
                last_error = err
                if "401" in err_msg or "403" in err_msg:
                    raise RuntimeError(f"Authentication failure (401/403). Check GEMINI_API_KEY: {err_msg}")
                if "thinking" in err_msg.lower() and config and hasattr(config, "thinking_config"):
                    config.thinking_config = None
                    continue
                transient_service_error = any(
                    marker in err_msg.upper()
                    for marker in ("502", "503", "504", "UNAVAILABLE", "INTERNAL")
                )
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or transient_service_error:
                    self.budget_guard.record_llm_call(budget_episode, 0.0)
                    if "daily" in err_msg.lower() or "per_day" in err_msg.lower():
                        self._mark_exhausted(selected_name)
                        return self.complete(
                            role, system, user, step=step, episode=episode, max_tokens=max_tokens, temperature=temperature, schema=schema
                        )
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                    append_event(
                        self.run_dir,
                        event="llm_attempt",
                        step=step,
                        episode=episode,
                        role=role,
                        model=selected_name,
                        retry_n=attempt,
                        decision="retry",
                        error=err_msg,
                    )
                    time.sleep(backoff)
                    total_wait_s += backoff
                else:
                    self.budget_guard.record_llm_call(budget_episode, 0.0)
                    append_event(
                        self.run_dir,
                        event="llm_attempt",
                        step=step,
                        episode=episode,
                        role=role,
                        model=selected_name,
                        retry_n=attempt - 1,
                        decision="failure" if attempt >= self.settings.max_retries else "retry",
                        error=err_msg,
                    )
                    if attempt >= self.settings.max_retries:
                        raise err

        if last_error is not None:
            append_event(
                self.run_dir,
                step=step,
                episode=episode,
                role=role,
                model=selected_name,
                retry_n=attempt,
                decision="failure",
                error=str(last_error),
            )
            raise last_error

        latency = self.clock() - t0
        now = self.clock()

        self.request_timestamps.setdefault(selected_name, []).append(now)
        self.token_timestamps.setdefault(selected_name, []).append((now, in_tok + out_tok))
        self._record_usage(selected_name, req_count=1, tok_count=in_tok + out_tok)

        notional_cost = (
            0.0
            if self.transport is not None
            else (in_tok / 1_000_000.0 * spec.price_in) + (out_tok / 1_000_000.0 * spec.price_out)
        )

        self.budget_guard.record_llm_call(budget_episode, notional_cost)

        llm_res = LLMResult(
            text=result_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            thought_tokens=thought_tok,
            latency_s=latency,
            model=selected_name,
            wait_s=total_wait_s,
            fallbacks=fallbacks_used,
            real_cost_usd=0.0,
            notional_cost_usd=notional_cost,
        )

        append_event(
            self.run_dir,
            event="llm_call",
            synthetic=self.transport is not None,
            step=step,
            episode=episode,
            role=role,
            model=selected_name,
            in_tok=in_tok,
            out_tok=out_tok,
            latency_s=latency,
            wait_s=total_wait_s,
            retry_n=attempt - 1,
            fallback_used=",".join(fallbacks_used),
            notional_cost_usd=notional_cost,
            decision="success",
        )

        return llm_res

    def complete_json(
        self,
        role: str,
        system: str,
        user: str,
        schema: Type[T],
        *,
        step: str = "complete_json",
        episode: Optional[int] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> Tuple[T, LLMResult]:
        res = self.complete(
            role=role,
            system=system,
            user=user,
            step=step,
            episode=episode,
            max_tokens=max_tokens,
            temperature=temperature,
            schema=schema,
        )

        parsed = self._extract_and_parse_json(res.text, schema)
        if parsed:
            return parsed, res

        repair_prompt = (
            f"The previous output failed JSON validation for schema {schema.__name__}.\n"
            f"Output was:\n{res.text}\n\n"
            f"Provide a valid JSON object strictly matching schema fields."
        )
        repair_res = self.complete(
            role=role,
            system="You repair invalid JSON text.",
            user=repair_prompt,
            step=f"{step}_repair",
            episode=episode,
            max_tokens=max_tokens,
            temperature=0.0,
            schema=schema,
        )

        repaired_parsed = self._extract_and_parse_json(repair_res.text, schema)
        if repaired_parsed:
            return repaired_parsed, repair_res

        raise ValueError(f"Failed to parse JSON for schema {schema.__name__} after repair call. Raw: {repair_res.text}")

    def _extract_and_parse_json(self, text: str, schema: Type[T]) -> Optional[T]:
        try:
            data = json.loads(text)
            return schema.model_validate(data)
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                return schema.model_validate(data)
            except Exception:
                pass
        return None
