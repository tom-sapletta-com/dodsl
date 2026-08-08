# doDSL

`doDSL` is a governed `sources -> knowledge -> candidate SSOT -> artifacts`
service. It accepts explicit GitHub repositories, web pages and uploaded files,
preserves their original bytes, compiles normalized Markdown and typed knowledge,
then asks onlyDSL to stage an SSOT candidate.

doDSL never promotes `SSOT/current`, executes model-provided commands, invents a
process URI, changes AQL, or treats an LLM response as evidence.

## Implemented vertical slice (P0-P2)

```text
explicit request
  -> project workspace
  -> source/git      (real clone + exact commit/tree)
  -> source/web      (raw page.html + headers + manifest)
  -> source/uploads  (byte-preserving import)
  -> source-md       (existing f2md tree conversion)
  -> source-md-dsl   (knowledge index + f2md intents + todo2code graph)
  -> onlydsl ssot reconcile
  -> SSOT/candidate  (never automatic promotion)
```

Raw HTML is the primary source. Markdown is a derived projection, not a
replacement for HTML.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e /home/tom/github/bioxfoundry/twin-dsl/py/f2md
.venv/bin/pip install 'markitdown>=0.1,<1'
.venv/bin/pip install -e .

export ONLYDSL_SSOT_COMMAND="/home/tom/github/tom-sapletta-com/onlyDSL/.venv/bin/python /home/tom/github/tom-sapletta-com/onlyDSL/server.py ssot"
export TODO2CODE_COMMAND="node /home/tom/github/semcod/todo2code/dist/src/cli.js"

dodsl --projects-root ./projects run examples/esp32-environment-controller/request.json
```

Run individual stages:

```bash
dodsl --projects-root ./projects init request.json
dodsl --projects-root ./projects ingest my-project
dodsl --projects-root ./projects import-file my-project enclosure-front.jpg
dodsl --projects-root ./projects compile my-project --require-todo2code
dodsl --projects-root ./projects reconcile my-project
dodsl --projects-root ./projects status my-project
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

The image pins the todo2code and f2md source commits. The development Compose
stack mounts the local onlyDSL checkout read-only because the currently
published `onlyDSL==0.0.7` wheel predates its SSOT package.

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
```

Set `DODSL_API_TOKEN` outside local development to require a Bearer token.

## Security invariants

- Git uses fixed subprocess arguments, no shell, no credential prompts and no
  global/system Git configuration.
- Production Git intake accepts only credential-free `https://github.com/org/repo`.
- Web intake blocks private, loopback, link-local and non-global addresses,
  restricts redirects to the original host and caps response size.
- todo2code is invoked with all semantic LLM stages disabled.
- When a pinned f2md release lacks `intent_compile`, doDSL uses its versioned,
  deterministic Markdown evidence compiler. It only creates source-anchored
  claims; it does not interpret free-form requests.
- Free-form user text is preserved but remains `waiting_interpretation`; doDSL
  does not replace a missing LLM interpretation with keyword heuristics.
- Only a system-owned process registry maps operations to executable adapters.
- SSOT evidence uses content-addressed `urn:*:sha256:<64-hex>` identifiers.

See [Implementation plan](docs/IMPLEMENTATION_PLAN.md) for the complete P3-P10
electronics, PCB, CAD, photo reconstruction and Digital Twin roadmap.
