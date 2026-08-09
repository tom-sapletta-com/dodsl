# doDSL


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.2.1-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.06-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-3.6h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.0632 (3 commits)
- 👤 **Human dev:** ~$364 (3.6h @ $100/h, 30min dedup)

Generated on 2026-08-10 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---



`doDSL` is a governed `sources -> knowledge -> candidate SSOT -> artifacts`
service. It accepts explicit GitHub repositories, web pages and uploaded files,
preserves their original bytes, compiles normalized Markdown and typed knowledge,
then asks onlyDSL to stage an SSOT candidate.

doDSL never promotes `SSOT/current`, executes model-provided commands, invents a
process URI, changes AQL, or treats an LLM response as evidence.

## Implemented vertical slice (P0-P3 foundation)

```text
explicit request
  -> project workspace
  -> source/git      (real clone + exact commit/tree)
  -> source/web      (raw page.html + headers + manifest)
  -> source/uploads  (byte-preserving import)
  -> source-md       (existing f2md tree conversion)
  -> source-md-dsl   (knowledge index + f2md intents + todo2code evidence bundle)
  -> onlydsl ssot reconcile
  -> SSOT/candidate  (never automatic promotion)
  -> typed ArtifactIntent proposal bound to the current knowledge hash
  -> ResearchGapDSL + ResearchPlanDSL (no execution)
```

Raw HTML is the primary source. Markdown is a derived projection, not a
replacement for HTML.

## Package workspace

```text
packages/dodsl-contracts  pure schemas, validation, hashes and DSL renderers
packages/dodsl-core       workspace runtime, atomic IO and dependency ports
packages/dodsl-planning   governed ArtifactIntent and research planning
packages/dodsl-adapters   Git, web, f2md, todo2code and onlyDSL adapters
apps/dodsl-service        CLI, HTTP API and composition root
```

`dodsl-contracts` reuses canonical hashing and
`DevelopmentEvidenceBundleDSL` from the independently built
`onlydsl-contracts` package pinned to an exact onlyDSL source revision. The
Docker composition also installs `onlydsl-core` and `onlydsl-ssot` from that
same revision because the read-only onlyDSL CLI bridge uses their compatibility
facades. doDSL does not copy kernel contracts or make onlyDSL depend on doDSL.

The dependency direction is enforced by an architecture test:

```text
contracts <- core
contracts + core <- planning
contracts + core <- adapters
contracts + core + planning + adapters <- service
```

Every member has its own `pyproject.toml` and can produce an independent wheel
and sdist. The root [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
provides one reproducible `uv.lock`. Compatibility exports keep existing
`dodsl.*` imports working during the transition.

## Quick start

```bash
uv sync

export ONLYDSL_SSOT_COMMAND="/home/tom/github/tom-sapletta-com/onlyDSL/.venv/bin/python /home/tom/github/tom-sapletta-com/onlyDSL/server.py ssot"
export TODO2CODE_COMMAND="node /home/tom/github/semcod/todo2code/dist/src/cli.js"

uv run dodsl --projects-root ./projects run examples/esp32-environment-controller/request.json
```

Run individual stages:

```bash
uv run dodsl --projects-root ./projects init request.json
uv run dodsl --projects-root ./projects ingest my-project
uv run dodsl --projects-root ./projects import-file my-project enclosure-front.jpg
uv run dodsl --projects-root ./projects compile my-project --require-todo2code
uv run dodsl --projects-root ./projects reconcile my-project
uv run dodsl --projects-root ./projects status my-project
uv run dodsl --projects-root ./projects plan-artifact my-project artifact-intent.json
```

Workspace verification:

```bash
uv run pytest -q
uv build --package dodsl-contracts
uv build --package dodsl-core
uv build --package dodsl-planning
uv build --package dodsl-adapters
uv build --package dodsl
```

`reconcile` only creates and validates a candidate. Promotion remains an
explicit onlyDSL operation requiring an AQL contract hash and immutable
TestQL/EQL receipts.

## Docker

```bash
cp .env.example .env
docker compose up -d --build
curl http://127.0.0.1:18788/health
```

The image pins todo2code, f2md and the independently buildable onlyDSL contract,
core and SSOT packages to exact source commits. The development Compose stack
also mounts the local onlyDSL checkout read-only for its CLI composition layer.

Compose runs doDSL as `${DODSL_UID:-1000}:${DODSL_GID:-1000}` so generated
Markdown, DSL and SSOT candidates remain readable by the host user. Set both
values in `.env` when the host account uses different identifiers.

## HTTP API

```text
GET  /health
POST /v1/projects
GET  /v1/projects/{id}
POST /v1/projects/{id}/ingest
POST /v1/projects/{id}/compile
POST /v1/projects/{id}/reconcile
POST /v1/projects/{id}/artifact-intents
```

Set `DODSL_API_TOKEN` outside local development to require a Bearer token.

## Security invariants

- Git uses fixed subprocess arguments, no shell, no credential prompts and no
  global/system Git configuration.
- Production Git intake accepts only credential-free `https://github.com/org/repo`.
- Web intake blocks private, loopback, link-local and non-global addresses,
  restricts redirects to the original host and caps response size.
- todo2code is invoked with all semantic LLM stages disabled. Its graph,
  diagnostics and semantic run manifest are content-addressed and bound to the
  exact Git commit/tree in `development-evidence.dsl`. Execution time, run ID
  and duration remain in `.dodsl/runtime` and cannot perturb the semantic hash.
- todo2code code-change plans remain proposals with `execution=not_performed`;
  neither todo2code nor doDSL grants AQL authority or applies their patches.
- When a pinned f2md release lacks `intent_compile`, doDSL uses its versioned,
  deterministic Markdown evidence compiler. It only creates source-anchored
  claims; it does not interpret free-form requests.
- Free-form user text is preserved but remains `waiting_interpretation`; doDSL
  does not replace a missing LLM interpretation with keyword heuristics.
- Human or LLM artifact proposals must use the strict
  `dodsl.artifact-intent-proposal/v1` contract and bind the current knowledge
  hash. LLM proposals require model and response-hash provenance.
- Artifact planning writes only `.dodsl/queue`; it neither executes research
  operations nor writes `SSOT/current`.
- Only a system-owned process registry maps operations to executable adapters.
- SSOT evidence uses content-addressed `urn:*:sha256:<64-hex>` identifiers.

See [Implementation plan](docs/IMPLEMENTATION_PLAN.md) for the complete P3-P10
electronics, PCB, CAD, photo reconstruction and Digital Twin roadmap.


## License

Licensed under Apache-2.0.
