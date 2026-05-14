from __future__ import annotations

import importlib
import importlib.util
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
        "next to ComfyUI-LTXV-PromptRelayAutoSync in ComfyUI/custom_nodes."
    )


def _prompt_relay_encoder() -> Callable[..., tuple[Any, Any]]:
    loaded = _find_loaded_prompt_relay_encoder()
    if loaded is not None:
        return loaded
    return _load_sibling_prompt_relay_encoder()


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


NODE_CLASS_MAPPINGS = {
    "SafeLTXVFrameCalculator": SafeLTXVFrameCalculator,
    "LTXVPromptRelayAutoSync": LTXVPromptRelayAutoSync,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SafeLTXVFrameCalculator": "Safe LTXV Frame Calculator",
    "LTXVPromptRelayAutoSync": "LTXV Prompt Relay Auto Sync",
}
