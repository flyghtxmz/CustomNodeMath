from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple


SEGMENT_COUNT = 4


def safe_ltxv_total_frames(length_seconds: float, fps: float, safe_divisor: int = 8) -> int:
    """Return ceil(seconds * fps / divisor) * divisor + 1."""
    seconds = float(length_seconds)
    fps_value = float(fps)
    divisor = int(safe_divisor)
    if seconds <= 0:
        raise ValueError("length_seconds must be greater than 0.")
    if fps_value <= 0:
        raise ValueError("fps must be greater than 0.")
    if divisor <= 0:
        raise ValueError("safe_divisor must be greater than 0.")
    return int(math.ceil(seconds * fps_value / divisor) * divisor + 1)


def effective_duration_seconds(total_frames: int, fps: float) -> float:
    frames = int(total_frames)
    fps_value = float(fps)
    if frames < 1:
        raise ValueError("total_frames must be at least 1.")
    if fps_value <= 0:
        raise ValueError("fps must be greater than 0.")
    return (frames - 1) / fps_value


def _validate_total_for_segments(total_frames: int, segment_count: int = SEGMENT_COUNT) -> int:
    frames = int(total_frames)
    if frames < segment_count:
        raise ValueError(
            f"total_frames must be at least {segment_count} to create "
            f"{segment_count} non-empty segments."
        )
    return frames


def distribute_equal(total_frames: int) -> List[int]:
    """Four-segment LTX split where segment 1 receives the +1 frame."""
    frames = _validate_total_for_segments(total_frames)
    base = (frames - 1) // SEGMENT_COUNT
    segment_1 = base + 1
    segment_2 = base
    segment_3 = base
    segment_4 = frames - segment_1 - segment_2 - segment_3
    return [segment_1, segment_2, segment_3, segment_4]


def _largest_remainder_from_exact(exact_values: Sequence[float], total_frames: int) -> List[int]:
    frames = _validate_total_for_segments(total_frames, len(exact_values))
    if len(exact_values) != SEGMENT_COUNT:
        raise ValueError(f"Expected {SEGMENT_COUNT} segment values.")

    values = [max(0.0, float(v)) for v in exact_values]
    if sum(values) <= 0:
        return distribute_equal(frames)

    scale = frames / sum(values)
    exact = [v * scale for v in values]
    result = [int(math.floor(v)) for v in exact]
    remainder = frames - sum(result)

    order = sorted(
        range(len(exact)),
        key=lambda i: (-(exact[i] - math.floor(exact[i])), -exact[i], i),
    )
    for i in range(remainder):
        result[order[i % len(order)]] += 1

    for i, value in enumerate(result):
        if value >= 1:
            continue
        result[i] = 1
        while sum(result) > frames:
            donor = max(range(len(result)), key=lambda idx: result[idx])
            if donor == i or result[donor] <= 1:
                break
            result[donor] -= 1

    while sum(result) < frames:
        donor = max(range(len(result)), key=lambda idx: exact[idx])
        result[donor] += 1

    while sum(result) > frames:
        donor = max(range(len(result)), key=lambda idx: result[idx])
        if result[donor] <= 1:
            raise ValueError("Could not enforce non-empty segment lengths.")
        result[donor] -= 1

    return result


def distribute_by_weights(total_frames: int, weights: Iterable[float]) -> Tuple[List[int], str, List[str]]:
    warnings: List[str] = []
    values = [float(v) for v in list(weights)[:SEGMENT_COUNT]]
    values += [1.0] * (SEGMENT_COUNT - len(values))

    if any(v < 0 for v in values):
        warnings.append("Negative segment weights were clamped to zero.")
    clamped = [max(0.0, v) for v in values]
    if sum(clamped) <= 0:
        warnings.append("Invalid segment weights; falling back to equal mode.")
        return distribute_equal(total_frames), "equal", warnings

    return _largest_remainder_from_exact(clamped, total_frames), "weights", warnings


def distribute_by_seconds(
    total_frames: int,
    fps: float,
    seconds_values: Iterable[float],
) -> Tuple[List[int], str, List[str]]:
    warnings: List[str] = []
    fps_value = float(fps)
    if fps_value <= 0:
        raise ValueError("fps must be greater than 0.")

    values = [float(v) for v in list(seconds_values)[:SEGMENT_COUNT]]
    values += [0.0] * (SEGMENT_COUNT - len(values))
    if any(v < 0 for v in values):
        warnings.append("Negative segment seconds were clamped to zero.")
    clamped = [max(0.0, v) for v in values]
    if sum(clamped) <= 0:
        warnings.append("Invalid segment seconds; falling back to equal mode.")
        return distribute_equal(total_frames), "equal", warnings

    frame_values = [v * fps_value for v in clamped]
    return _largest_remainder_from_exact(frame_values, total_frames), "seconds", warnings


def distribute_segments(
    total_frames: int,
    fps: float,
    segment_mode: str = "equal",
    weights: Iterable[float] = (1.0, 1.0, 1.0, 1.0),
    seconds_values: Iterable[float] = (0.0, 0.0, 0.0, 0.0),
) -> Tuple[List[int], str, List[str]]:
    mode = (segment_mode or "equal").strip().lower()
    if mode == "weights":
        return distribute_by_weights(total_frames, weights)
    if mode == "seconds":
        return distribute_by_seconds(total_frames, fps, seconds_values)
    if mode != "equal":
        return distribute_equal(total_frames), "equal", [f"Unknown segment_mode '{segment_mode}'; using equal."]
    return distribute_equal(total_frames), "equal", []


def segment_start_indices(segment_lengths: Sequence[int]) -> List[int]:
    if len(segment_lengths) != SEGMENT_COUNT:
        raise ValueError(f"Expected {SEGMENT_COUNT} segment lengths.")
    starts = [0]
    cursor = 0
    for length in segment_lengths[:-1]:
        cursor += int(length)
        starts.append(cursor)
    return starts


def format_segment_lengths(segment_lengths: Sequence[int]) -> str:
    return ", ".join(str(int(v)) for v in segment_lengths)


def build_local_prompts_string(segment_prompts: Sequence[str]) -> str:
    if len(segment_prompts) != SEGMENT_COUNT:
        raise ValueError(f"Expected {SEGMENT_COUNT} segment prompts.")
    return " | ".join((prompt or "").strip() for prompt in segment_prompts)


def prompt_warnings(global_prompt: str, segment_prompts: Sequence[str]) -> List[str]:
    warnings: List[str] = []
    if not (global_prompt or "").strip():
        warnings.append("global_prompt is empty.")
    for index, prompt in enumerate(segment_prompts, start=1):
        if not (prompt or "").strip():
            warnings.append(f"segment_{index}_prompt is empty.")
    return warnings


def build_debug_report(
    fps: float,
    total_frames: int,
    segment_lengths: Sequence[int],
    starts: Sequence[int],
    segment_lengths_string: str,
    local_prompts_string: str,
    mode_used: str,
    warnings: Sequence[str],
    requested_duration_seconds: float | None = None,
    safe_divisor: int | None = None,
) -> str:
    fps_value = float(fps)
    effective = effective_duration_seconds(total_frames, fps_value)
    lines = [
        "LTXV Prompt Relay Auto Sync",
        f"FPS: {fps_value:g}",
        f"total_frames: {int(total_frames)}",
        f"effective_duration_seconds: {effective:.6f}",
        f"distribution_mode_used: {mode_used}",
        f"segment_1_frames: {int(segment_lengths[0])}",
        f"segment_2_frames: {int(segment_lengths[1])}",
        f"segment_3_frames: {int(segment_lengths[2])}",
        f"segment_4_frames: {int(segment_lengths[3])}",
        f"image_1_frame_idx: {int(starts[0])}",
        f"image_2_frame_idx: {int(starts[1])}",
        f"image_3_frame_idx: {int(starts[2])}",
        f"image_4_frame_idx: {int(starts[3])}",
        f"segment_lengths_string: {segment_lengths_string}",
        f"local_prompts_string: {local_prompts_string}",
    ]
    if requested_duration_seconds is not None and requested_duration_seconds > 0:
        delta = effective - float(requested_duration_seconds)
        lines.insert(2, f"requested_duration_seconds: {float(requested_duration_seconds):.6f}")
        lines.insert(4, f"duration_delta_seconds: {delta:.6f}")
    if safe_divisor is not None:
        lines.append(f"safe_divisor: {int(safe_divisor)}")
    if warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def make_prompt_relay_payload(
    total_frames: int,
    fps: float,
    global_prompt: str,
    segment_prompts: Sequence[str],
    segment_mode: str = "equal",
    weights: Iterable[float] = (1.0, 1.0, 1.0, 1.0),
    seconds_values: Iterable[float] = (0.0, 0.0, 0.0, 0.0),
    requested_duration_seconds: float | None = None,
    strict_prompts: bool = True,
) -> dict:
    segments, mode_used, warnings = distribute_segments(
        total_frames,
        fps,
        segment_mode,
        weights=weights,
        seconds_values=seconds_values,
    )
    starts = segment_start_indices(segments)
    segment_lengths_string = format_segment_lengths(segments)
    local_prompts_string = build_local_prompts_string(segment_prompts)
    warnings.extend(prompt_warnings(global_prompt, segment_prompts))

    if strict_prompts:
        empty_segments = [
            f"segment_{idx}_prompt"
            for idx, prompt in enumerate(segment_prompts, start=1)
            if not (prompt or "").strip()
        ]
        if empty_segments:
            raise ValueError(
                "LTXV Prompt Relay Auto Sync: fill all 4 segment prompts. "
                f"Empty fields: {', '.join(empty_segments)}."
            )

    debug_report = build_debug_report(
        fps=fps,
        total_frames=total_frames,
        segment_lengths=segments,
        starts=starts,
        segment_lengths_string=segment_lengths_string,
        local_prompts_string=local_prompts_string,
        mode_used=mode_used,
        warnings=warnings,
        requested_duration_seconds=requested_duration_seconds,
    )
    return {
        "total_frames": int(total_frames),
        "segment_lengths": segments,
        "starts": starts,
        "segment_lengths_string": segment_lengths_string,
        "local_prompts_string": local_prompts_string,
        "debug_report": debug_report,
        "mode_used": mode_used,
        "warnings": warnings,
    }
