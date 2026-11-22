# Blast Radius selector

Submission for the [RWX Blast Radius track](https://www.joinbuilders.org/buildathon/tracks/blast-radius). The image reads independent sqlglot patches from `/data/commits` and the test inventory from `/data/tests.json`, then prints one JSON line per commit. It uses only Python's standard library at runtime.

## Method

All committed indexes were derived from sqlglot commit `eb11aec4be8cb2122afe713a4816662c3f0fb2fa` and its tests. There are no sample-patch fingerprints, known failing-test answers, or edit-kind answer tables in the image.

1. Map each SQL fixture to the test method that loads it.
2. Record per-test source-line coverage. Trace optimizer and executor work in process so coverage includes work otherwise hidden in child processes. Add a separate dependency index for expression serialization across process boundaries.
3. For a patch, combine line coverage with the start of the enclosing condition. For class constants, follow attribute reads and the dialect used by the test. Numeric-escape mapping changes use the changed escape key and SQL literals from the pinned tests.
4. Prove a few edits equivalent from pinned-source facts: identity and equality for known enum or simple-object values; a comparison boundary that cannot equal a fixed-length tuple; and copying a freshly constructed expression. Unknown edits remain selected by coverage.
5. Schedule selected tests with longest-test-first placement for each worker count from 1 to 8 and choose the lowest `largest load + 2 seconds × workers` cost.

Source-test edits select the touched test method or its class. Unmapped fixtures, suspicious structural edits, and comments inserted into Python string interiors use wider fallbacks to avoid a 300-second miss.

## Local check

Use the [official starter kit](https://www.joinbuilders.org/buildathon/tracks/blast-radius/files/blast-radius-sample.tar.gz) for `sample/` and `score.py`:

```powershell
$env:BLAST_DATA = (Resolve-Path '..\starter\sample').Path
python selector.py > output.jsonl
python ..\starter\score.py ..\starter\sample ..\starter\sample\answers.json output.jsonl
python tools\test_core.py
```

The current sample output is valid with **99.034 simulated seconds and zero misses**. The server adds container CPU time and uses the middle of three runs. The final commits are unseen, so this sample result is not a final-score claim.

## Rebuilding the maps

`tools/coverage_plugin.py` records test contexts under `pytest`. Run the suite from the pinned sqlglot checkout with `SKIP_INTEGRATION=0`, `PYTHONPATH` pointing to this repository, and `-p tools.coverage_plugin`. Set `BLAST_COVERAGE_FILE` to keep coverage runs separate. `BLAST_IN_PROCESS_OPTIMIZER=1` and `BLAST_IN_PROCESS_EXECUTOR=1` make the respective subprocess tests traceable in separate runs. `tools/export_coverage.py` merges those coverage data files and writes `coverage.json.gz`.

The other `tools/build_*_index.py` scripts produce the static maps from the same checkout and the starter's `tests.json`. `requirements.lock` is the starter's pinned test environment; `coverage==7.10.7` was added locally for map generation. These tools are not copied into the runtime image.
