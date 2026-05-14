# ComfyUI LTXV Prompt Relay Auto Sync

Custom node package for 4-segment LTXV workflows using kijai/ComfyUI-PromptRelay.

## Install

Copy this folder to:

```text
ComfyUI/custom_nodes/ComfyUI-LTXV-PromptRelayAutoSync
```

Also install the original Prompt Relay node next to it:

```text
ComfyUI/custom_nodes/ComfyUI-PromptRelay
```

Restart ComfyUI. The menu will show:

- `LTXV Prompt Relay Auto Sync`
- `Safe LTXV Frame Calculator`

## Use

In the final workflow, edit only:

- `ResolutionMaster - VIDEO SIZE`: width, height, horizontal/vertical ratio.
- `FPS MASTER (auto)`.
- `Length (seconds) MASTER`.
- The 4 segment prompt fields inside `LTXV Prompt Relay Auto Sync`.

Optional controls:

- `segment_mode = weights`: use the four segment weights.
- `segment_mode = seconds`: use the four segment seconds.
- `segment_mode = equal`: default equal split.

## How sync works

`Safe LTXV Frame Calculator` uses:

```text
ceil(seconds * fps / 8) * 8 + 1
```

This keeps `(frames - 1)` divisible by 8.

`LTXV Prompt Relay Auto Sync` receives `total_frames` and builds:

```text
segment_lengths_string = "seg1, seg2, seg3, seg4"
local_prompts_string = "prompt1 | prompt2 | prompt3 | prompt4"
```

It then calls Prompt Relay's official `_encode_relay` function. The node passes frame-space
segment lengths to Prompt Relay and lets Prompt Relay do its own latent-space conversion.

## Guide image sync

The node outputs:

```text
image_1_frame_idx = 0
image_2_frame_idx = segment_1_frames
image_3_frame_idx = segment_1_frames + segment_2_frames
image_4_frame_idx = segment_1_frames + segment_2_frames + segment_3_frames
```

The final workflow connects those outputs to `LTXVAddGuideMulti`, so guide images move with
FPS and duration changes.

## Why no manual segment lengths

The old `PromptRelayEncodeTimeline` stores `segment_lengths` in its widget data. Changing FPS
or duration can leave those widget lengths stale. This node rebuilds the segment lengths on
every run from `total_frames`, so there is nothing to copy manually.

## Rollback

To go back to the old timeline node:

1. Bypass or delete `LTXV Prompt Relay Auto Sync`.
2. Enable `PromptRelayEncodeTimeline` in the group `OLD PROMPT RELAY TIMELINE - DISABLED`.
3. Reconnect old timeline output `model` to `Set_model_relay`.
4. Reconnect old timeline output `positive` to `Set_positive_relay` and `ConditioningZeroOut`.
5. Reconnect the old manual/math segment frame controls to the `frames_seg1`, `frames_seg2`,
   `frames_seg3`, and `frames_seg4` setters if you want manual guide timing again.

To disable this custom node completely, remove this folder from `custom_nodes` and restart
ComfyUI.

## Dependencies

- ComfyUI
- kijai/ComfyUI-PromptRelay
- The same LTXV, KJNodes, VideoHelperSuite, rgthree, mxToolkit and other nodes already required
  by the supplied workflow

