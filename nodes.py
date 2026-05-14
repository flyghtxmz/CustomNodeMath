from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

from .ltxv_time_math import (
    build_debug_report,
    distribute_equal,
    effective_duration_seconds,
    format_segment_lengths,
    make_prompt_relay_payload,
    safe_ltxv_total_frames,
    segment_start_indices,
)


def _find_loaded_prompt_relay_encoder() -> Callable[..., tuple[Any, Any]] | None:
    for module in list(sys.modules.values()):
        if module is None or not hasattr(module, "_encode_relay"):
            continue
        module_file = str(getattr(module, "__file__", "") or "")
        if "PromptRelay" in module_file or hasattr(module, "PromptRelayEncode"):
            return getattr(module, "_encode_relay")
    return None


def _load_sibling_prompt_relay_encoder() -> Callable[..., tuple[Any, Any]]:
    current_dir = Path(__file__).resolve().parent
    custom_nodes_dir = current_dir.parent
    candidates = [
        custom_nodes_dir / "ComfyUI-PromptRelay",
        custom_nodes_dir / "ComfyUI-PromptRelay-main",
        current_dir / "ComfyUI-PromptRelay",
    ]

    for package_dir in candidates:
        init_file = package_dir / "__init__.py"
        nodes_file = package_dir / "nodes.py"
        if not init_file.exists() or not nodes_file.exists():
            continue

        alias = "_ltxv_auto_sync_external_prompt_relay"
        if alias not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                alias,
                init_file,
                submodule_search_locations=[str(package_dir)],
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[alias] = module
            spec.loader.exec_module(module)

        nodes_module = importlib.import_module(f"{alias}.nodes")
        if hasattr(nodes_module, "_encode_relay"):
            return getattr(nodes_module, "_encode_relay")

    raise RuntimeError(
        "ComfyUI-PromptRelay was not found. Install kijai/ComfyUI-PromptRelay "
        "next to this package in ComfyUI/custom_nodes."
    )


def _prompt_relay_encoder() -> Callable[..., tuple[Any, Any]]:
    loaded = _find_loaded_prompt_relay_encoder()
    if loaded is not None:
        return loaded
    return _load_sibling_prompt_relay_encoder()


def _parse_segment_lengths(segment_lengths: str) -> list[int]:
    values: list[int] = []
    for raw in (segment_lengths or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        values.append(max(1, int(float(raw))))
    return values


def _parse_timeline_data(timeline_data: str) -> tuple[list[str], list[int]]:
    if not timeline_data:
        return [], []
    try:
        payload = json.loads(timeline_data)
    except Exception:
        return [], []
    segments = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(segments, list):
        return [], []
    prompts: list[str] = []
    lengths: list[int] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        prompts.append(str(segment.get("prompt", "") or ""))
        try:
            lengths.append(max(1, int(float(segment.get("length", 1)))))
        except Exception:
            lengths.append(1)
    return prompts, lengths


def _split_local_prompts(local_prompts: str) -> list[str]:
    return [prompt.strip() for prompt in (local_prompts or "").split("|")]


def _join_local_prompts(prompts: list[str]) -> str:
    return " | ".join(prompt.strip() for prompt in prompts)


def _scale_lengths_to_total(lengths: list[int], total_frames: int) -> tuple[list[int], bool]:
    if not lengths:
        return [int(total_frames)], True
    total = int(total_frames)
    values = [max(1, int(v)) for v in lengths]
    if sum(values) == total:
        return values, False
    if total < len(values):
        values = values[:total]
        return [1] * len(values), True

    source_total = sum(values)
    exact = [value * total / source_total for value in values]
    result = [max(1, int(value)) for value in exact]

    while sum(result) > total:
        donor = max(range(len(result)), key=lambda idx: result[idx])
        if result[donor] <= 1:
            break
        result[donor] -= 1

    remainder = total - sum(result)
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i] - int(exact[i])), i))
    for i in range(remainder):
        result[order[i % len(order)]] += 1
    return result, True


def _first_four_outputs(lengths: list[int]) -> tuple[list[int], list[int], list[str]]:
    warnings: list[str] = []
    if len(lengths) > 4:
        warnings.append(f"Timeline has {len(lengths)} segments; first 4 are exposed for guide-image outputs.")
    if len(lengths) < 4:
        warnings.append(f"Timeline has only {len(lengths)} segments; missing segment outputs are zero-filled.")

    padded = [int(v) for v in lengths[:4]]
    padded.extend([0] * (4 - len(padded)))
    starts = [0, padded[0], padded[0] + padded[1], padded[0] + padded[1] + padded[2]]
    return padded, starts, warnings


def _visual_debug_report(
    *,
    fps: float,
    length_seconds: float,
    safe_divisor: int,
    max_frames_input: int,
    total_frames: int,
    effective_duration: float,
    segment_lengths: list[int],
    local_prompts_string: str,
    warnings: list[str],
) -> str:
    first_four, starts, output_warnings = _first_four_outputs(segment_lengths)
    lines = [
        "Prompt Relay Visual Time Sync",
        f"length_seconds: {float(length_seconds):.6f}",
        f"fps: {float(fps):g}",
        f"safe_divisor: {int(safe_divisor)}",
        f"max_frames_input: {int(max_frames_input)}",
        f"total_frames: {int(total_frames)}",
        f"effective_duration_seconds: {float(effective_duration):.6f}",
        f"segment_count: {len(segment_lengths)}",
        f"segment_lengths_string: {format_segment_lengths(segment_lengths)}",
        f"local_prompts_string: {local_prompts_string}",
        f"segment_1_frames: {first_four[0]}",
        f"segment_2_frames: {first_four[1]}",
        f"segment_3_frames: {first_four[2]}",
        f"segment_4_frames: {first_four[3]}",
        f"image_1_frame_idx: {starts[0]}",
        f"image_2_frame_idx: {starts[1]}",
        f"image_3_frame_idx: {starts[2]}",
        f"image_4_frame_idx: {starts[3]}",
    ]
    all_warnings = warnings + output_warnings
    if all_warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in all_warnings)
    return "\n".join(lines)


class SafeLTXVFrameCalculator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "length_seconds": ("FLOAT", {"default": 30.0, "min": 0.01, "max": 7200.0, "step": 0.1}),
                "fps": ("FLOAT", {"default": 24.0, "min": 0.1, "max": 240.0, "step": 0.1}),
                "safe_divisor": ("INT", {"default": 8, "min": 1, "max": 64, "step": 1}),
            }
        }

    RETURN_TYPES = ("INT", "FLOAT", "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = (
        "total_frames",
        "fps_float",
        "fps_int",
        "requested_duration_seconds",
        "effective_duration_seconds",
        "debug_report",
    )
    FUNCTION = "calculate"
    CATEGORY = "conditioning/prompt_relay"
    DESCRIPTION = "Calculates safe LTXV frame counts as ceil(seconds * fps / divisor) * divisor + 1."

    def calculate(self, length_seconds: float, fps: float, safe_divisor: int = 8):
        total_frames = safe_ltxv_total_frames(length_seconds, fps, safe_divisor)
        fps_float = float(fps)
        fps_int = int(round(fps_float))
        effective = effective_duration_seconds(total_frames, fps_float)
        segments = distribute_equal(total_frames)
        starts = segment_start_indices(segments)
        debug_report = build_debug_report(
            fps=fps_float,
            total_frames=total_frames,
            segment_lengths=segments,
            starts=starts,
            segment_lengths_string=format_segment_lengths(segments),
            local_prompts_string="",
            mode_used="equal",
            warnings=[],
            requested_duration_seconds=float(length_seconds),
            safe_divisor=int(safe_divisor),
        )
        return total_frames, fps_float, fps_int, float(length_seconds), effective, debug_report


class LTXVPromptRelayAutoSync:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "latent": ("LATENT",),
                "global_prompt": ("STRING", {"multiline": True, "default": ""}),
                "segment_1_prompt": ("STRING", {"multiline": True, "default": ""}),
                "segment_2_prompt": ("STRING", {"multiline": True, "default": ""}),
                "segment_3_prompt": ("STRING", {"multiline": True, "default": ""}),
                "segment_4_prompt": ("STRING", {"multiline": True, "default": ""}),
                "total_frames": ("INT", {"default": 721, "min": 4, "max": 100000, "step": 1}),
                "fps": ("FLOAT", {"default": 24.0, "min": 0.1, "max": 240.0, "step": 0.1}),
                "requested_duration_seconds": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 7200.0, "step": 0.1},
                ),
                "epsilon": ("FLOAT", {"default": 0.001, "min": 0.000001, "max": 0.99, "step": 0.0001}),
                "segment_mode": (["equal", "weights", "seconds"], {"default": "equal"}),
                "segment_1_weight": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1000.0, "step": 0.1}),
                "segment_2_weight": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1000.0, "step": 0.1}),
                "segment_3_weight": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1000.0, "step": 0.1}),
                "segment_4_weight": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1000.0, "step": 0.1}),
                "segment_1_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 7200.0, "step": 0.1}),
                "segment_2_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 7200.0, "step": 0.1}),
                "segment_3_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 7200.0, "step": 0.1}),
                "segment_4_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 7200.0, "step": 0.1}),
            },
            "optional": {
                "relay_options": ("RELAY_OPTIONS",),
            },
        }

    RETURN_TYPES = (
        "MODEL",
        "CONDITIONING",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "STRING",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "model",
        "positive",
        "total_frames",
        "segment_1_frames",
        "segment_2_frames",
        "segment_3_frames",
        "segment_4_frames",
        "image_1_frame_idx",
        "image_2_frame_idx",
        "image_3_frame_idx",
        "image_4_frame_idx",
        "segment_lengths_string",
        "local_prompts_string",
        "debug_report",
    )
    FUNCTION = "encode"
    CATEGORY = "conditioning/prompt_relay"
    DESCRIPTION = "Builds 4 synced Prompt Relay segments from total LTXV frames and patches the model."

    def encode(
        self,
        model,
        clip,
        latent,
        global_prompt: str,
        segment_1_prompt: str,
        segment_2_prompt: str,
        segment_3_prompt: str,
        segment_4_prompt: str,
        total_frames: int,
        fps: float,
        requested_duration_seconds: float = 0.0,
        epsilon: float = 0.001,
        segment_mode: str = "equal",
        segment_1_weight: float = 1.0,
        segment_2_weight: float = 1.0,
        segment_3_weight: float = 1.0,
        segment_4_weight: float = 1.0,
        segment_1_seconds: float = 0.0,
        segment_2_seconds: float = 0.0,
        segment_3_seconds: float = 0.0,
        segment_4_seconds: float = 0.0,
        relay_options=None,
    ):
        segment_prompts = [
            segment_1_prompt,
            segment_2_prompt,
            segment_3_prompt,
            segment_4_prompt,
        ]
        payload = make_prompt_relay_payload(
            total_frames=int(total_frames),
            fps=float(fps),
            global_prompt=global_prompt,
            segment_prompts=segment_prompts,
            segment_mode=segment_mode,
            weights=[segment_1_weight, segment_2_weight, segment_3_weight, segment_4_weight],
            seconds_values=[segment_1_seconds, segment_2_seconds, segment_3_seconds, segment_4_seconds],
            requested_duration_seconds=(
                float(requested_duration_seconds) if float(requested_duration_seconds) > 0 else None
            ),
            strict_prompts=True,
        )

        encode_relay = _prompt_relay_encoder()
        patched, conditioning = encode_relay(
            model,
            clip,
            latent,
            global_prompt or "",
            payload["local_prompts_string"],
            payload["segment_lengths_string"],
            float(epsilon),
            relay_options,
        )
        segments = payload["segment_lengths"]
        starts = payload["starts"]
        return (
            patched,
            conditioning,
            payload["total_frames"],
            segments[0],
            segments[1],
            segments[2],
            segments[3],
            starts[0],
            starts[1],
            starts[2],
            starts[3],
            payload["segment_lengths_string"],
            payload["local_prompts_string"],
            payload["debug_report"],
        )


class PromptRelayVisualTimeSync:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "latent": ("LATENT",),
                "global_prompt": ("STRING", {"multiline": True, "default": ""}),
                "length_seconds": ("FLOAT", {"default": 30.0, "min": 0.01, "max": 7200.0, "step": 0.1}),
                "fps": ("FLOAT", {"default": 24.0, "min": 0.1, "max": 240.0, "step": 0.1}),
                "safe_divisor": ("INT", {"default": 8, "min": 1, "max": 64, "step": 1}),
                "max_frames": ("INT", {"default": 721, "min": 1, "max": 100000, "step": 1}),
                "timeline_data": ("STRING", {"default": ""}),
                "local_prompts": ("STRING", {"multiline": True, "default": ""}),
                "segment_lengths": ("STRING", {"default": ""}),
                "epsilon": ("FLOAT", {"default": 0.001, "min": 0.000001, "max": 0.99, "step": 0.0001}),
                "time_units": (["frames", "seconds"], {"default": "frames"}),
            },
            "optional": {
                "relay_options": ("RELAY_OPTIONS",),
            },
        }

    RETURN_TYPES = (
        "MODEL",
        "CONDITIONING",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "STRING",
        "STRING",
        "FLOAT",
        "STRING",
    )
    RETURN_NAMES = (
        "model",
        "positive",
        "total_frames",
        "segment_1_frames",
        "segment_2_frames",
        "segment_3_frames",
        "segment_4_frames",
        "image_1_frame_idx",
        "image_2_frame_idx",
        "image_3_frame_idx",
        "image_4_frame_idx",
        "segment_lengths_string",
        "local_prompts_string",
        "effective_duration_seconds",
        "debug_report",
    )
    FUNCTION = "encode"
    CATEGORY = "LTXV/Prompt Relay"
    DESCRIPTION = (
        "Visual Prompt Relay timeline based on kijai/ComfyUI-PromptRelay, with safe LTXV "
        "length_seconds/fps frame sync and guide-image timing outputs."
    )

    def encode(
        self,
        model,
        clip,
        latent,
        global_prompt: str,
        length_seconds: float,
        fps: float,
        safe_divisor: int,
        max_frames: int,
        timeline_data: str,
        local_prompts: str,
        segment_lengths: str,
        epsilon: float,
        time_units: str = "frames",
        relay_options=None,
    ):
        total_frames = safe_ltxv_total_frames(length_seconds, fps, safe_divisor)
        effective_duration = effective_duration_seconds(total_frames, fps)
        warnings: list[str] = []

        timeline_prompts, timeline_lengths = _parse_timeline_data(timeline_data)
        prompt_list = _split_local_prompts(local_prompts)
        if not any(prompt.strip() for prompt in prompt_list) and timeline_prompts:
            prompt_list = timeline_prompts

        lengths = _parse_segment_lengths(segment_lengths)
        if not lengths and timeline_lengths:
            lengths = timeline_lengths
        if not lengths:
            if prompt_list:
                base = total_frames // len(prompt_list)
                lengths = [base] * len(prompt_list)
                lengths[0] += total_frames - sum(lengths)
                warnings.append("segment_lengths was empty; generated an equal split from prompt count.")
            else:
                lengths = [total_frames]
                warnings.append("segment_lengths and local_prompts were empty; using a single full-length segment.")

        if not any(prompt.strip() for prompt in prompt_list) and timeline_prompts:
            prompt_list = timeline_prompts
        if len(prompt_list) < len(lengths):
            prompt_list.extend([""] * (len(lengths) - len(prompt_list)))
            warnings.append("Some timeline segments have empty prompts.")
        elif len(prompt_list) > len(lengths):
            prompt_list = prompt_list[: len(lengths)]
            warnings.append("Extra prompts without matching segment lengths were ignored.")

        lengths, was_rescaled = _scale_lengths_to_total(lengths, total_frames)
        if was_rescaled:
            warnings.append("Timeline segment lengths were rescaled to the calculated total_frames.")

        if int(max_frames) != int(total_frames):
            warnings.append("max_frames input differed from calculated total_frames; calculated value was used.")

        local_prompts_string = _join_local_prompts(prompt_list)
        segment_lengths_string = format_segment_lengths(lengths)
        if not any(prompt.strip() for prompt in prompt_list):
            raise ValueError("PromptRelayVisualTimeSync requires at least one non-empty timeline segment prompt.")

        encode_relay = _prompt_relay_encoder()
        patched, conditioning = encode_relay(
            model,
            clip,
            latent,
            global_prompt or "",
            local_prompts_string,
            segment_lengths_string,
            float(epsilon),
            relay_options,
        )

        first_four, starts, _ = _first_four_outputs(lengths)
        debug_report = _visual_debug_report(
            fps=float(fps),
            length_seconds=float(length_seconds),
            safe_divisor=int(safe_divisor),
            max_frames_input=int(max_frames),
            total_frames=int(total_frames),
            effective_duration=float(effective_duration),
            segment_lengths=lengths,
            local_prompts_string=local_prompts_string,
            warnings=warnings,
        )

        return (
            patched,
            conditioning,
            int(total_frames),
            first_four[0],
            first_four[1],
            first_four[2],
            first_four[3],
            starts[0],
            starts[1],
            starts[2],
            starts[3],
            segment_lengths_string,
            local_prompts_string,
            float(effective_duration),
            debug_report,
        )


NODE_CLASS_MAPPINGS = {
    "SafeLTXVFrameCalculator": SafeLTXVFrameCalculator,
    "LTXVPromptRelayAutoSync": LTXVPromptRelayAutoSync,
    "PromptRelayVisualTimeSync": PromptRelayVisualTimeSync,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SafeLTXVFrameCalculator": "Safe LTXV Frame Calculator",
    "LTXVPromptRelayAutoSync": "LTXV Prompt Relay Auto Sync",
    "PromptRelayVisualTimeSync": "Prompt Relay Visual Time Sync",
}
