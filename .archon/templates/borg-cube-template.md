<!--
  BORG CUBE TEMPLATE — canonical module specification (project-agnostic)
  =====================================================================
  This is the authoritative structure for every `borg-cube.md`. The borg-sanitizer
  workflow fills it in per MAIN module. Submodules do NOT get their own borg-cube.md —
  they appear only in the parent module's "Submodule Structure" section.

  Standards basis:
    - Functional content        → ISO/IEC/IEEE 29148, IEEE 830 (SRS)
    - Non-functional content    → ISO/IEC 25010 (product quality model)
    - Architecture context      → arc42 / C4 (context, dependencies, decisions)

  Rules for filling this in:
    - Be factual and specific. State only what is verifiable from the code.
    - Language- and framework-agnostic: describe whatever the module actually is.
    - Fill in only the relevant non-functional characteristics; mark the rest "N/A".
    - Replace every <PLACEHOLDER>. Delete these HTML comments in the generated file.
    - Target length: 40–120 lines.
-->

# <Module Name> — Borg Cube Specification

**Path:** `<path/to/module>`
**Type:** main module
**Subsystem:** <e.g. backend service | frontend | CLI | library | worker — N/A if unclear>

## 1. Purpose & Scope
<!-- Functional (29148 §scope). One paragraph: what this module is responsible for and,
     explicitly, what it is NOT responsible for (its boundary). -->
<PURPOSE_AND_SCOPE>

## 2. Responsibilities / Functional Requirements
<!-- The concrete capabilities this module provides, as a numbered list. Each item is a
     verifiable behavior, not an implementation detail. -->
1. <REQUIREMENT>
2. <REQUIREMENT>

## 3. Public Interface / API
<!-- The contract other code depends on: exported functions / classes with signatures,
     HTTP routes (method + path), RPC handlers, CLI commands, events emitted. The stable
     surface — not internal helpers. -->
- `<signature / route / command>` — <description>

## 4. Data Models
<!-- Key persisted entities, transport schemas, or core types defined here, with their
     essential fields. Reference, don't dump. Write "none" if the module defines none. -->
- `<Model / Type>` — <key fields + meaning>

## 5. Dependencies & Integration Points
<!-- arc42 context. Inbound: who calls this module. Outbound: what this module calls
     (other project modules, external services, datastores, the filesystem, queues). -->
- **Calls / depends on:** <...>
- **Called by:** <...>
- **External systems:** <datastore, third-party API, message broker, ... | none>

## 6. Configuration
<!-- Environment variables, settings, or feature flags this module reads. "none" if none. -->
- `<SETTING / ENV_VAR>` — <purpose, default>

## 7. Non-Functional Characteristics (ISO/IEC 25010)
<!-- Fill in only what genuinely applies to THIS module. Mark the rest "N/A". -->
- **Security:** <auth requirements, trust boundary, input validation | N/A>
- **Reliability:** <failure modes, graceful degradation, retries, idempotency | N/A>
- **Performance Efficiency:** <hot paths, sync/async, known costs or limits | N/A>
- **Maintainability:** <coupling, where tests live, change hotspots | N/A>
- **Compatibility:** <data formats, protocol/API versioning, backends supported | N/A>
- **Usability:** <only for user-facing modules — the UX contract | N/A>
- **Portability:** <runtime/OS/storage assumptions, build targets | N/A>

## 8. Design Decisions & Constraints
<!-- The non-obvious WHY. Decisions a future maintainer would otherwise question or undo.
     Record the constraint and the rationale. -->
- <DECISION> — <rationale>

## 9. Submodule Structure
<!-- Nested code directories under this main module. MINIMAL info only — one line each.
     Submodules have NO own CLAUDE.md / borg-cube.md; this tree is their entire spec.
     Use "none" if this module has no submodules. -->
```
<module-path>/
├── <submodule>/   — <one-line purpose>  (<n> files; key: <file/export>)
└── <submodule>/   — <one-line purpose>  (<n> files; key: <file/export>)
```
