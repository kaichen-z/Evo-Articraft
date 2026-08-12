# Data provenance

This directory contains frozen, redistributable evaluation inputs rather than
credentials or local absolute paths.

- `annotations/annotations-2026-08-12.csv`: live annotation export retrieved
  from `https://failure-datasets-for-articraft.onrender.com/api/export` on
  2026-08-12. It contains 616 records: 282 completed under the new per-item
  schema and 334 legacy records whose unavailable new-item labels remain blank.
- `contracts-300/`: the 98 contracts present in Wanglin He's
  `Wanglin-He/evo-verifier` at commit `78437a9` on 2026-08-12. The directory
  name is the target batch size, not a claim that 300 contracts are complete.
- `contracts/`: the earlier 31-contract snapshot, retained only to reproduce
  the first development run. Current commands use `contracts-300/`.

The official Articraft asset repository was sparse-checked out separately at
runtime. Asset source is not copied into this submission.
