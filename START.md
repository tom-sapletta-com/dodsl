# doDSL — aktualnie uruchomiona usługa

> Plik tymczasowy. Stan sprawdzony: `2026-08-08T22:47:38+02:00`.

## Usługa

```text
service: dodsl
version: 0.1.0
container: dodsl-dodsl-1
health: healthy
API: http://127.0.0.1:18788/
health URL: http://127.0.0.1:18788/health
boundary: source -> source-md -> source-md-dsl -> SSOT candidate
model commands: forbidden
automatic SSOT promotion: forbidden
```

Start i status:

```bash
cd /home/tom/github/tom-sapletta-com/dodsl
docker compose up -d --build dodsl
docker compose ps
curl http://127.0.0.1:18788/health
docker compose logs -f dodsl
```

Zatrzymanie:

```bash
docker compose stop dodsl
```

## API

```text
POST /v1/projects
GET  /v1/projects/{project-id}
POST /v1/projects/{project-id}/ingest
POST /v1/projects/{project-id}/compile
POST /v1/projects/{project-id}/reconcile
POST /v1/projects/{project-id}/artifact-intents
```

Jeżeli `DODSL_API_TOKEN` jest ustawiony, należy dodać nagłówek:

```text
Authorization: Bearer <token>
```

## Aktualny test P0–P2

Projekt `dodsl-smoke` został utworzony z:

```text
Git: https://github.com/octocat/Hello-World.git
WWW: https://example.com/
```

Zweryfikowany wynik:

```text
source files: 5
Markdown files: 5
DSL/projection files: 13
knowledge semantic hash:
  sha256:b1465c0e368707d1120581758c7ab2380663cfedc4639a8a646a2682f21e7177
todo2code: compiled
SSOT candidate: created and validated
candidate id: dodsl-b1465c0e368707d1-e230cbd8
SSOT promotion: not_performed
ArtifactIntent candidate: artifact-bf182f2461e4c2dc2dda
research gaps: 8
research execution: not_performed
workspace packages: 5 independently buildable distributions
kernel packages: onlydsl-contracts/core/ssot 0.0.8 @ onlyDSL 9d89195
doDSL tests: 24 passed
onlyDSL regression tests: 110 passed
```

Status projektu:

```bash
curl http://127.0.0.1:18788/v1/projects/dodsl-smoke | jq .
```

Odpowiedź zawiera `serviceVersion` oraz `lastIteration.at`, `stage`,
`semanticHash` i — gdy dotyczy — `candidateId`.

## Gdzie czytać źródła, DSL i logi

```text
projects/dodsl-smoke/source/                     surowe repo i raw page.html
projects/dodsl-smoke/source-md/                  projekcja Markdown
projects/dodsl-smoke/source-md-dsl/              DSL i indeks wiedzy
projects/dodsl-smoke/source-md-dsl/knowledge-index.dsl
projects/dodsl-smoke/source-md-dsl/knowledge-manifest.json
projects/dodsl-smoke/source-md-dsl/contracts/trust.dsl
projects/dodsl-smoke/source-md-dsl/development/f2md/
projects/dodsl-smoke/source-md-dsl/development/todo2code/
projects/dodsl-smoke/.dodsl/runtime/              receipts ostatnich etapów
projects/dodsl-smoke/SSOT/candidate/              kandydaci Accepted Truth
projects/dodsl-smoke/SSOT/manifest.dsl            zaakceptowany root SSOT
```

Logi procesu w terminalu:

```bash
docker compose logs --tail=200 dodsl
```

## Granica aktualnej wersji

P0–P2 działa: intake, normalizacja wiedzy i kandydat SSOT. Fundament P3 tworzy
typowany ArtifactIntent, ResearchGapDSL i ResearchPlanDSL, ale celowo nie wykonuje
jeszcze researchu. KiCad/ERC/DRC, CAD, STL/3MF, rekonstrukcja ze zdjęć i OpenUSD
są opisane w `docs/IMPLEMENTATION_PLAN.md`, ale nie są jeszcze adapterami
wykonawczymi wersji `0.1.0`. doDSL nie raportuje tych artefaktów jako gotowych.
