# doDSL — aktualnie uruchomiona usługa

> Plik tymczasowy. Stan sprawdzony: `2026-08-08T23:11:21+02:00`.

## Usługa

```text
service: dodsl
version: 0.2.0
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
DSL/projection files: 16
knowledge semantic hash:
  sha256:c918b55bb5b3eadab0e8abbbf1f01e979cd76e96fb9aca16fc8fafdb78bf767f
todo2code: compiled, assessment accepted
development evidence bundles: 1 accepted / 0 incomplete
invalid development evidence bundles: 0
blocking development diagnostics: 0
development evidence URI:
  urn:onlydsl:development-evidence:sha256:7c65453adebf716a4e08aab09ed8f107e551f93232c011a61dfe5b47a55491ac
SSOT candidate: created and validated
candidate id: dodsl-c918b55bb5b3eada-c1db33b4
SSOT promotion: not_performed
ArtifactIntent candidate: artifact-bf182f2461e4c2dc2dda
research gaps: 8
research execution: not_performed
workspace packages: 5 independently buildable distributions
kernel packages: onlydsl-contracts/core/ssot 0.0.9 @ onlyDSL 5983bae
doDSL tests: 26 passed
onlyDSL regression tests: 114 passed
```

Status projektu:

```bash
curl http://127.0.0.1:18788/v1/projects/dodsl-smoke | jq .
```

Odpowiedź zawiera `serviceVersion`, `lastIteration.at`, `stage`,
`semanticHash`, `candidateId` oraz `developmentEvidence.items` z dokładną
rewizją Git, wersją producenta, oceną, liczbą diagnostyk i immutable URI.

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
projects/dodsl-smoke/source-md-dsl/development/todo2code/hello-world-28314a8e9f/development-evidence.dsl
projects/dodsl-smoke/source-md-dsl/development/todo2code/hello-world-28314a8e9f/manifest.semantic.json
projects/dodsl-smoke/.dodsl/runtime/              receipts ostatnich etapów
projects/dodsl-smoke/SSOT/candidate/              kandydaci Accepted Truth
projects/dodsl-smoke/SSOT/manifest.dsl            zaakceptowany root SSOT
```

Logi procesu w terminalu:

```bash
docker compose logs --tail=200 dodsl
```

## Granica aktualnej wersji

P0–P2 działa: intake, normalizacja wiedzy, DevelopmentEvidenceBundleDSL i
walidowany kandydat SSOT. Fundament P3 tworzy
typowany ArtifactIntent, ResearchGapDSL i ResearchPlanDSL, ale celowo nie wykonuje
jeszcze researchu. KiCad/ERC/DRC, CAD, STL/3MF, rekonstrukcja ze zdjęć i OpenUSD
są opisane w `docs/IMPLEMENTATION_PLAN.md`, ale nie są jeszcze adapterami
wykonawczymi wersji `0.2.0`. doDSL nie raportuje tych artefaktów jako gotowych.

Uwaga diagnostyczna: obraz zawiera todo2code z `package.json` 0.5.1, lecz jego
`T2C_VERSION` w audytach raportuje 0.5.0. Bundle zachowuje wersję zgłoszoną przez
runtime (`0.5.0`) zamiast ją korygować. To pozostaje regresją wersjonowania do
naprawy po stronie todo2code; nie wpływa na content hash grafu ani authority.
