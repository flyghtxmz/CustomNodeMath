# ComfyUI LTXV Prompt Relay Visual Time Sync

Custom nodes for LTXV workflows that need Prompt Relay, safe frame math, and guide-image
timing outputs.

## Main Node

Use:

- `Prompt Relay Visual Time Sync`

This node is based on `PromptRelayEncodeTimeline` from
`kijai/ComfyUI-PromptRelay` and keeps the same visual timeline workflow:

- colored timeline blocks
- Add / Equalize / Delete
- draggable segment boundaries
- segment reorder by drag
- prompt editing per block
- frame/seconds ruler
- `fps`, `time_units`, `epsilon`, `relay_options`
- original `model` and `positive` Prompt Relay outputs

It adds LTXV time sync:

```text
total_frames = ceil(length_seconds * fps / safe_divisor) * safe_divisor + 1
```

Defaults:

```text
length_seconds = 30
fps = 24
safe_divisor = 8
total_frames = 721
```

When `length_seconds` or `fps` changes, including through linked master controls such as
`Length (seconds) MASTER` and `FPS MASTER`, the frontend updates `max_frames` and rescales
the visual timeline while preserving the segment proportions and prompts.

## Install With ComfyUI Manager

Use ComfyUI Manager's install-from-Git-URL option and paste this repository URL.

Manager should clone it into:

```text
ComfyUI/custom_nodes/<this-repository-name>
```

This repository root is already a ComfyUI custom node package:

```text
__init__.py
nodes.py
ltxv_time_math.py
web/
workflows/
```

Also install the official Prompt Relay package:

```text
ComfyUI/custom_nodes/ComfyUI-PromptRelay
```

This package does not modify or overwrite `ComfyUI-PromptRelay`. It imports/reuses the
official Prompt Relay encoder at runtime.

## Workflows

Ready workflow:

```text
workflows/FluxoChines1-com-ResolutionMaster-TimeMaster-VisualTimeSync.json
```

Previous backend workflow kept for rollback/reference:

```text
workflows/FluxoChines1-com-ResolutionMaster-TimeMaster-AutoPromptRelay.json
```

## How To Use

In the visual workflow, edit:

- `ResolutionMaster - VIDEO SIZE`
- `FPS MASTER (auto)`
- `Length (seconds) MASTER`
- the colored timeline blocks inside `Prompt Relay Visual Time Sync`

You do not need to copy `181, 180, 180, 180` manually. The hidden
`segment_lengths` and `local_prompts` fields are written by the visual timeline.

## Outputs

Besides the original Prompt Relay outputs:

- `model`
- `positive`

`Prompt Relay Visual Time Sync` returns:

- `total_frames`
- `segment_1_frames` through `segment_4_frames`
- `image_1_frame_idx` through `image_4_frame_idx`
- `segment_lengths_string`
- `local_prompts_string`
- `effective_duration_seconds`
- `debug_report`

Guide image starts are calculated as:

```text
image_1_frame_idx = 0
image_2_frame_idx = segment_1_frames
image_3_frame_idx = segment_1_frames + segment_2_frames
image_4_frame_idx = segment_1_frames + segment_2_frames + segment_3_frames
```

If the timeline has more than 4 segments, Prompt Relay still encodes all segments. The
specific guide-image outputs use the first 4 segments and the debug report notes that extra
segments exist.

## Credits And Upstream

`PromptRelayVisualTimeSync` is based on `PromptRelayEncodeTimeline` from:

```text
https://github.com/kijai/ComfyUI-PromptRelay
```

Files used as implementation references:

- `nodes.py`
- `__init__.py`
- `web/js/prompt_relay_timeline.js`

The copied/adapted frontend lives only inside this package under `web/`. The official
`ComfyUI-PromptRelay` package remains intact.

At the time this package was prepared, no separate `LICENSE` file was present in the
upstream repository. Keep upstream attribution when redistributing.

## Rollback

To use the older backend node workflow, load:

```text
workflows/FluxoChines1-com-ResolutionMaster-TimeMaster-AutoPromptRelay.json
```

To go back to the original official timeline manually:

1. Disable `Prompt Relay Visual Time Sync`.
2. Enable the disabled `PromptRelayEncodeTimeline` reference node in the workflow.
3. Reconnect its `model` output to `Set_model_relay`.
4. Reconnect its `positive` output to `Set_positive_relay` and `ConditioningZeroOut`.
5. Reconnect the old manual or calculated frame controls if you want manual guide timing.

## Tests

Local tests:

```bash
py -B -m unittest discover -s tests -v
```
