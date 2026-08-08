# doDSL — implementation plan

## 1. Responsibility and non-goals

doDSL is an orchestrator. The ownership split is deliberate:

```text
onlyDSL        authority, accepted state, integrity, repair, promotion
f2md           source file -> Markdown envelope
todo2code      code/docs/git -> intent evidence graph
twin-dsl       physical evidence, geometry, scene and Digital Twin runtime
doDSL          workspace, source snapshots, research and artifact recipes
```

doDSL does not become another SSOT implementation, CAD kernel, KiCad parser or
Digital Twin engine. It binds existing tools through fixed process adapters and
collects immutable receipts.

The first implementation milestone is intentionally P0-P2. A source ingestion
service must be reproducible and governed before it is allowed to manufacture a
PCB or printable object.

### Package ownership

The repository is a uv workspace with independently buildable distributions:

```text
packages/
├── dodsl-contracts   schemas, models, validators, semantic hashes, DSL
├── dodsl-core        workspace, atomic IO, dependency ports
├── dodsl-planning    ArtifactIntent and research candidate planning
└── dodsl-adapters    source, knowledge and onlyDSL SSOT adapters

apps/
└── dodsl-service     CLI, HTTP API and composition root
```

Allowed dependency graph:

```text
dodsl-contracts -> dodsl-core
dodsl-contracts + dodsl-core -> dodsl-planning
dodsl-contracts + dodsl-core -> dodsl-adapters
contracts + core + planning + adapters -> dodsl-service
```

In exact import terms, `contracts` has no internal dependencies; `core` imports
only contracts; planning and adapters import contracts/core but not each other;
the service is the only composition root. `tests/test_package_architecture.py`
fails when an upward dependency or application import crosses that boundary.

The system-owned process registry points to extracted implementation packages,
not compatibility exports in `dodsl.*`. Compatibility modules exist for one
migration period and do not define authority.

Further packages should be extracted when their first executable vertical
slice exists, rather than added as empty placeholders. Expected boundaries are
`dodsl-research`, `dodsl-electronics`, `dodsl-cad`, `dodsl-twin` and
`dodsl-verification`. Each must own contracts or execution logic that can be
built and tested independently; authority and application composition remain
outside those packages.

## 2. End-to-end state machine

```text
created
  -> sources_captured
  -> knowledge_compiled
  -> ssot_candidate_validated
  -> waiting_authority
  -> ssot_accepted
  -> research_planned
  -> artifact_candidate_built
  -> artifact_verified
  -> artifact_accepted
```

Failure is typed and persistent:

```text
waiting_interpretation
missing_evidence
source_unreachable
conversion_incomplete
authority_denied
erc_failed
drc_failed
geometry_validation_failed
manufacturing_validation_failed
```

No failure state is silently converted to success.

## 3. Workspace contract

```text
projects/<project-id>/
├── project.projectdsl
├── source/
│   ├── git/<source-id>/{repository,manifest.json}
│   ├── web/<host>/<snapshot-id>/{page.html,response-headers.json,manifest.json}
│   └── uploads/<content-id>/{original-file,manifest.json}
├── source-md/
├── source-md-dsl/
│   ├── knowledge-index.dsl
│   ├── knowledge-manifest.json
│   ├── intent/project-dodsl.dsl
│   ├── contracts/trust.dsl
│   └── development/{f2md,todo2code}/
├── SSOT/{current,candidate,receipts,revisions,manifest.dsl}
├── artifact/{pcb,cad,print,digital-twin,docs}/
├── .dodsl/{locks,runtime,queue}/
└── .onlydsl/{authority,cache,queue,runtime}/
```

`source/` is immutable primary evidence. `source-md/` and `source-md-dsl/` are
rebuildable projections. `SSOT/current` is accepted interpretation. `artifact/`
contains generated outputs and their receipts.

## 4. P0-P2: implemented foundation

### P0 — workspace and source capture

Implemented:

- strict `dodsl-request/v1` parser and JSON Schema;
- multiple GitHub and web sources per project;
- real Git clone with commit, tree, branch, origin and submodule declarations;
- raw HTML snapshot before any conversion;
- response headers, resolved URL, status, trust role and content hash;
- local file/photo import preserving original bytes;
- per-project non-blocking writer lock;
- atomic manifests and staging directory swaps.

Acceptance:

```text
same Git commit + same URL body + same uploads
  -> same source semantic hashes
```

Execution timestamps remain in source envelopes but outside semantic hashes.

### P1 — knowledge compiler

Implemented:

- existing Python f2md `convert_tree` integration;
- complete mirror into `source-md` including explicit stubs for binary sources;
- preferred `f2md.intent_compile` integration plus a versioned deterministic
  Markdown-evidence compiler for published f2md revisions that lack that module;
- deterministic KnowledgeIndexDSL grounded in raw byte hashes;
- canonical f2md intent packs with logical doDSL URIs, not host paths;
- todo2code deterministic pipeline for each cloned repository;
- todo2code execution metadata removed from its accepted semantic projection;
- aggregate knowledge/compile evidence URNs.

The f2md Markdown front matter deliberately retains converter runtime data.
KnowledgeIndexDSL excludes absolute paths, mtimes and durations from the
semantic fingerprint.

The fallback compiler is not an NL interpretation fallback. It only splits a
derived Markdown document into source-anchored `claim` evidence. Free-form
project intent still remains `waiting_interpretation` until a validated LLM
structured output exists.

### P2 — candidate SSOT

Implemented:

- external bridge to `onlydsl ssot init/status/reconcile`;
- bounded section selection instead of copying the entire source corpus;
- immutable evidence URNs;
- generated TrustDSL;
- candidate validation and SemanticDiffDSL;
- explicit prohibition on promotion from doDSL.

Promotion remains:

```text
onlydsl ssot promote <candidate> \
  --authority-hash sha256:<aql-contract> \
  --testql urn:subactor:testql:sha256:<result> \
  --eql urn:subactor:eql:sha256:<result>
```

## 5. P3 — research planner

### Implemented foundation

The first P3 boundary is operational:

- strict `dodsl.artifact-intent-proposal/v1` validation;
- proposal binding to the current knowledge semantic hash;
- explicit human/LLM producer provenance;
- deterministic `ArtifactIntentDSL`, `ResearchGapDSL` and `ResearchPlanDSL`;
- one typed gap per explicitly required evidence field;
- system-owned operation name with no model-provided executable URI;
- staging under `.dodsl/queue/artifact-intent` with `execution: not_performed`
  and `ssotPromotion: not_performed`.

The DQL execution adapter and evidence-backed `ComponentDSL` acceptance remain
the next P3 increment. A generated research plan is not yet a research result.

### New contracts

```text
ArtifactIntentDSL
CapabilityRequirementDSL
ResearchGapDSL
ResearchPlanDSL
ComponentDSL
```

Free-form NL must go through an LLM structured-output gateway. If the gateway
is absent or invalid, state remains `waiting_interpretation`. Regex and keyword
matching may validate syntax but may not interpret the requested device.

Example gap:

```text
RESEARCH_GAP usb-c-power-controller
NEED manufacturer
NEED mpn
NEED supply-range
NEED package
NEED pinout
NEED footprint
NEED dimensions
REQUIRE evidence-kind manufacturer-datasheet
END_RESEARCH_GAP
```

ResearchPlanDSL compiles to the existing `subactor.dql-crawl/v1` profile.
The crawler must preserve HTML/PDF bodies under `source/web`, respect robots,
host/path allowlists, URL budgets and SSRF restrictions.

Acceptance:

- no accepted pin, package, voltage or dimension without source URI/hash/anchor;
- conflicting sources remain visible as separate claims;
- TrustDSL ranks sources but does not silently choose a winner;
- DQL output becomes a new candidate, never a direct accepted fact.

## 6. P4 — electronics knowledge and schematic

### Contracts

```text
ComponentDSL -> BOMDSL -> CircuitDSL -> SchematicBuildDSL
```

Required ComponentDSL fields:

```text
manufacturer, MPN, lifecycle, category
electrical limits and units
package and body dimensions
pin names, pin numbers and pin functions
symbol library reference
footprint library reference
3D model reference
datasheet evidence per critical field
```

CircuitDSL is connectivity and behavior, not a KiCad file. A deterministic
adapter maps accepted components and nets into `.kicad_sch`. The adapter may use
only libraries pinned in the process pack and exact component revisions.

Mandatory checks before PCB:

- power-domain compatibility;
- absolute maximum and operating voltage checks;
- current/thermal budget;
- pull-up, decoupling and protection contracts;
- connector pin and polarity checks;
- KiCad ERC with JSON report and violation exit code;
- independent EQL read-back of output hashes.

Electrical safety, mains voltage, batteries and high-current loads require a
stricter authority class and human engineering review. Passing ERC alone does
not prove that a circuit is safe or fit for manufacture.

## 7. P5 — PCB and manufacturing package

### Contracts

```text
PCBIntentDSL
PlacementConstraintDSL
RoutingConstraintDSL
ManufacturingProfileDSL
PCBBuildReceiptDSL
```

Pipeline:

```text
accepted schematic
  -> board outline and stack-up
  -> constrained placement candidate
  -> routing candidate
  -> kicad-cli pcb drc --schematic-parity
  -> Gerber + drill + position + BOM
  -> STEP/3D export
  -> manufacturing receipt
```

Acceptance requires:

- schematic parity;
- zero blocking DRC findings;
- board dimensions within contract;
- connectors on declared edges and orientations;
- antenna, creepage, keep-out and mounting constraints;
- every footprint and 3D model bound to the accepted MPN/package;
- generated manufacturing files hashed and listed in the receipt.

Automated autorouting must be treated as a candidate producer. It cannot waive
constraints or promote itself.

## 8. P6 — mechanical CAD and printable artifacts

### Contracts

```text
GeometryIntentDSL
MechanicalEnvelopeDSL
GeometryBuildDSL
GeometryValidationDSL
ManufacturingPrintDSL
GeometryBuildReceiptDSL
```

Inputs include accepted PCB STEP, connector transforms, mounting holes,
clearances, wall thickness, printer profile and explicit units.

Pipeline:

```text
MechanicalEnvelopeDSL
  -> deterministic OpenSCAD/CAD adapter
  -> STEP/3MF/STL
  -> mesh manifold/watertight checks
  -> bbox, orientation and clearance validation
  -> GLB
  -> physical-evidence receipt for twin-dsl
```

3MF should be preferred as the manufacturing handoff when printer metadata and
units matter; STL remains an explicitly unit-bound export. OpenSCAD runs via
fixed CLI options and writes its dependency file so included geometry is part of
the receipt.

## 9. P7 — photos and dimensions

A photograph is observation evidence, not measured geometry.

```text
photos + camera metadata + calibration target + known dimensions
  -> vision proposal
  -> GeometryIntentDSL with KNOWN/OBSERVED/UNKNOWN
  -> parametric CAD candidate
  -> multi-view render comparison
  -> dimensional validation
```

Rules:

- one uncalibrated image cannot establish depth or hidden wall thickness;
- lens distortion and perspective must be modeled;
- a known scale/fiducial or explicit dimensions are required;
- inferred values remain assumptions with uncertainty;
- `measured` quality is reserved for measurements and calibrated reconstruction;
- unknown cutouts, threads and fasteners block a manufacturing-ready result.

Acceptance should include silhouette/landmark error per view, exact known
dimension residuals and a report of unobservable parameters.

## 10. P8 — Digital Twin assembly

PCB, enclosure, firmware and external components receive stable component IDs.
The assembly uses OpenUSD references for normal composition and payloads for
optionally loaded heavy geometry.

```text
Device
├── Electronics/PCB
├── Mechanical/Bottom
├── Mechanical/Lid
├── Interfaces/Connectors
└── Cyber/Firmware
```

Validation covers transforms, units, axes, hierarchy, part-of relations,
connector alignment, collisions, clearances and evidence lineage. Flattening is
an export option, not the authoritative authoring model.

## 11. P9 — artifact recipes and autonomous repair

ArtifactRecipeDSL defines a dependency DAG. Exact executable URIs come from the
system-owned registry after AQL preflight.

```text
ProjectIntegrity finding
  -> RepairPlanDSL
  -> AQL + EQL preflight
  -> exact OQL/URI operation
  -> isolated build workspace
  -> TestQL + domain validator
  -> EQL read-back
  -> candidate SSOT revision
```

Examples of typed findings:

```text
COMPONENT_PINOUT_EVIDENCE_MISSING
SYMBOL_FOOTPRINT_PACKAGE_MISMATCH
ERC_BLOCKING_VIOLATION
PCB_SCHEMATIC_PARITY_FAILED
PCB_DRC_CLEARANCE_VIOLATION
GEOMETRY_KNOWN_DIMENSION_DRIFT
ENCLOSURE_CONNECTOR_COLLISION
MESH_NOT_WATERTIGHT
PRINT_PROFILE_UNSUPPORTED_OVERHANG
USD_ASSET_REFERENCE_UNRESOLVED
```

Every finding maps to an allowlisted repair operation. Unknown findings are
deferred; they do not become arbitrary model commands.

## 12. P10 — required E2E examples

1. `github-to-3d`: repository plus CAD sources to GLB/OpenUSD Twin.
2. `photo-to-printable-enclosure`: calibrated views and dimensions to 3MF/STL.
3. `description-to-pcb-and-enclosure`: ArtifactIntentDSL to BOM, schematic,
   ERC, PCB, DRC, manufacturing files, PCB STEP, enclosure and Digital Twin.

The controlled flagship is `ESP32 environmental controller`. Required final
receipts:

```text
SourceSnapshotReceipt
KnowledgeCompileReceipt
SSOTPromotionReceipt
ResearchReceipt
ComponentEvidenceReceipt
SchematicBuildReceipt + ERC
PCBBuildReceipt + DRC + parity
GeometryBuildReceipt + dimensional checks
PrintValidationReceipt
USDAssemblyReceipt
ProjectIntegrityDSL
TestQLDSL
EQL receipt
```

## 13. Delivery sequence and gates

| Phase | Deliverable | Gate |
|---|---|---|
| P0 | source workspace | reproducible raw hashes |
| P1 | Markdown/DSL knowledge | deterministic semantic hash |
| P2 | SSOT candidate | no direct current write |
| P3 | grounded research | critical fields have evidence |
| P4 | schematic | ERC and electrical contracts pass |
| P5 | PCB | DRC, parity and manufacturing package pass |
| P6 | CAD/print | geometry and mesh checks pass |
| P7 | photo reconstruction | unknowns remain explicit |
| P8 | USD Twin | assembly/transform/evidence checks pass |
| P9 | autonomous recipes | AQL/TestQL/EQL closure |
| P10 | three E2E projects | clean rebuild from empty workspace |

Only after a phase gate is repeatable should its outputs become prerequisites
for the next phase.
