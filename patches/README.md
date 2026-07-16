# Release Manifest Format

Each `*.json` file in this directory describes one reviewed UU release. The
generic patch engine loads all approved manifests and identifies a binary by
its complete hash; it does not choose a patch from a version string or partial
signature.

## Top-level fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Manifest schema; currently `1` |
| `review_status` | Must be `approved`; audit drafts use `draft` |
| `product` | Human-readable upstream product name |
| `version` | Exact UU release/build identifier |
| `architecture` | Currently only `x86_64` |
| `installer` | Filename, official URL, and full SHA-256 |
| `server` | Server identity, patched identity, and bounded edits |
| `health_monitor` | Companion filename and original SHA-256 |
| `landmarks` | Semantic strings used to begin a new audit |
| `imports` | API boundaries whose behavior matters to the bridge |
| `review` | Method and evidence for approval |

## Patch entries

Every item in `server.patches` contains:

- a stable `id`
- a behavior-focused `description` and `rationale`
- the exact signature `file_offset`
- a generous unique `original` hexadecimal signature
- an equal-length `replacement` hexadecimal signature

The changed instruction bytes can be a small subset of the signature. Keeping
unchanged context around them makes accidental matches less likely. The engine
also verifies that signatures are unique, correctly positioned, and
non-overlapping.

## Lifecycle

1. `audit-gameviewer.py inspect` creates an ignored draft under `build/`.
2. A reviewer re-establishes semantics in the new disassembly and edits every
   candidate.
3. `audit-gameviewer.py finalize` derives the complete patched hash and emits
   a new approved manifest.
4. Disposable copy tests prove patch, verify, and byte-identical restore.
5. The new manifest and human evidence are committed together.

See [the complete upstream maintenance guide](../docs/upstream-maintenance.md).
