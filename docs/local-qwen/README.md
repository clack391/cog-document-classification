# Running local Qwen

The files we use to run the Cog live with local Qwen. The steps, and why each
change is needed, are in [docs/suite-notes.md](../suite-notes.md#running-local-qwen).

| File | What it is | Where it goes |
|---|---|---|
| `pixi.toml`, `serve.sh`, `restart.sh` | A CUDA build of llama.cpp serving cog-qwen's pinned model, with a 3,000-token cap on thinking | `llama-cuda/` in the suite workspace, next to `cog-qwen/` |
| `cog-system-one-adapter-enforce-schema.diff` | Adds the adapter setting `enforce_schema` | Apply in `cog-system-one-adapter/` |
| `cog-qwen-enable-thinking.diff` | Adds the cog-qwen setting `enable_thinking` | Apply in `cog-qwen/` |
| `qwen-local-3.json`, `system-one-qwen-3.json` | Workbench bind requests for the two bindings | Pass to `suite -- bind` |

The two patches are local changes to suite repos, made against their pins
(cog-qwen `c18c0a8`, cog-system-one-adapter `bb3a4ca`). They are not part of the
suite.
