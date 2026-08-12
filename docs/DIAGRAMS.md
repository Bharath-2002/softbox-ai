# Diagrams

Companion to [ARCHITECTURE.md](./ARCHITECTURE.md). Decision references (`D1`…`D24`) point back to
it.

1. [Application flow](#1-application-flow) — 1a setup, 1b runtime
2. [State machines](#2-state-machines) — the lifecycles the flow moves through
3. [Architecture — layering](#3-architecture--layering-and-import-rules)
4. [Architecture — runtime](#4-architecture--runtime-topology)
5. [Database](#5-database) — four grouped ER diagrams

---

## 1. Application flow

Split in two because they run on different clocks: **1a** is configuration a tenant does once per
category; **1b** is what happens every time a product is added.

### 1a · Setup — once per category

```mermaid
flowchart LR

subgraph S1["1 · Category & spec (D10–D13, D15)"]
  direction TB
  T1["Sign in via SSO / OIDC"] --> T2["Create category — e.g. Saree<br/>subcategories inherit the parent spec"]
  T2 --> T3["Custom attributes<br/>price · fabric · brand<br/>semantic_role promotes<br/>some to real columns"]
  T2 --> T4["Variant axes<br/>colour → affects_imagery = true<br/>size → affects_imagery = false"]
  T2 --> T5["INPUT slot POOL<br/>border · bunthi · blouse<br/>captured once,<br/>shared by all catalog slots"]
  T2 --> T6["CATALOG slots<br/>close-up · human-worn<br/>styled hero"]
  T5 --> T7["Map each catalog slot →<br/>the input slots it needs"]
  T6 --> T7
  T3 --> T8["Publish → category_spec_version N"]
  T4 --> T8
  T7 --> T8
end

subgraph S2["2 · Templates — many per catalog slot (D14)"]
  direction TB
  M1["Add a template"] --> M2{"Reference image<br/>or authored text scene?"}
  M2 -- "text scene" --> M5
  M2 -- "reference image" --> M3["Vision analysis agent"]
  M3 --> M4["Structured analysis +<br/>prompt_template with placeholders"]
  M4 --> M5["Validate every placeholder<br/>resolves against this slot's<br/>declared input requirements"]
  M5 -- "ok" --> M6["status = analysed<br/>selectable"]
  M5 -- "unresolved" --> M7["status = invalid<br/>reason shown to the user"]
end

subgraph S7["Spec change — the path most systems get wrong (D15)"]
  direction TB
  V1["Tenant edits a published spec"] --> V2{"Change class?"}
  V2 -- "additive-optional" --> V3["Auto-applies · new catalog slots<br/>offered as a backfill job"]
  V2 -- "additive-REQUIRED" --> V4["Existing products → needs_attention<br/>regeneration blocked until filled"]
  V2 -- "retire a slot" --> V5["History kept · hidden from new capture<br/>published images stay published"]
  V2 -- "rename a key" --> V6["NOT PERMITTED<br/>retire and add"]
  V3 --> V7["Publish → version N+1"]
  V4 --> V7
  V5 --> V7
end

T8 --> M1
T8 -.->|"products pin the version they were captured under"| V1
M6 -.->|"available to products in 1b"| S3ENTRY["→ 1b · Product capture"]
```

### 1b · Runtime — every product

```mermaid
flowchart LR

subgraph S3["3 · Capture (D11, D12, §6.1)"]
  direction TB
  P1["Select category<br/>→ pins spec_version"] --> P2["Fill attributes<br/>validated by the Pydantic model<br/>compiled from the pinned spec"]
  P2 --> P3["Capture one photo per input slot"]
  P3 --> P4["NORMALISE<br/>validate → de-crease<br/>colour → deskew → crop"]
  P4 -- "blurry / underexposed" --> P4R["Rejected with an actionable reason<br/>staff retakes on the spot"]
  P4R --> P3
  P4 -- "ok" --> P5{"Colour variants?"}
  P5 -- "photographed" --> P6["Variant-level input images"]
  P5 -- "recolour" --> P7["Falls back to product inputs<br/>colour + hex injected into the prompt"]
  P5 -- "single colour" --> P8
  P6 --> P8["Choose a template<br/>per catalog slot"]
  P7 --> P8
  P8 --> P9["status = ready"]
end

subgraph S4["4 · Generation (D18, D19, D24)"]
  direction TB
  G1["Save & Generate"] --> G2["Reserve quota — conditional UPDATE<br/>inside the enqueue transaction"]
  G2 -- "over budget" --> G2X["Rejected · nothing enqueued<br/>no partial spend"]
  G2 -- "reserved" --> G3["generation_request · fan out =<br/>imagery-affecting axis combos<br/>× required catalog slots"]
  G3 --> G4["One generation_item<br/>per combination"]
  G4 --> G5["Worker renders the prompt<br/>scene + input refs + attrs + variant"]
  G5 --> G6["Nano Banana 2"]
  G6 --> G7["Store asset + lineage<br/>model · prompt_version · seed<br/>params · cost · latency"]
end

subgraph S5["5 · QC & approval (D16, D20)"]
  direction TB
  Q1["Automated QC agent<br/>subject · framing · motif fidelity<br/>colour delta · artefacts · safety"] --> Q2{"Pass?"}
  Q2 -- "no" --> Q3{"Retries left?"}
  Q3 -- "yes" --> Q3B["Retry: new seed,<br/>then a different template"]
  Q3 -- "no" --> Q4["qc_failed → human review<br/>ALWAYS, even when<br/>approval is disabled"]
  Q2 -- "yes" --> Q5{"approval.required?<br/>platform → tenant<br/>→ category → product"}
  Q5 -- "true" --> Q6["Approval queue"]
  Q6 -- "reject" --> Q7["rejected →<br/>regenerate or discard"]
  Q6 -- "approve" --> Q8["approved"]
  Q5 -- "false" --> Q8
end

subgraph S6["6 · Content & publishing (D21–D23)"]
  direction TB
  C1["Copywriting agent<br/>per channel · per locale"] --> C2["Brand rules +<br/>forbidden-claim validation"]
  C2 --> C3["content_drafts<br/>same approval gate as imagery"]
  C3 --> C4["Channel renditions from the master<br/>crop per aspect ratio"]
  C4 --> C5["publications — idempotency_key<br/>COMMITTED BEFORE any external call"]
  C5 --> C6{"Scheduled?"}
  C6 -- "later" --> C7["due_at poller"]
  C6 -- "now" --> C8["Per-account<br/>token-bucket dispatch"]
  C7 --> C8
  C8 --> C9["Storefront"]
  C8 --> C10["Instagram"]
  C8 --> C11["Facebook"]
  C8 --> C12["Pinterest"]
  C9 --> C13["Record external_post_id<br/>+ permalink · fetch metrics later"]
  C10 --> C13
  C11 --> C13
  C12 --> C13
end

P9 --> G1
G7 --> Q1
Q3B --> G5
Q8 --> C1
```

---

## 2. State machines

Each is a persisted status column, not in-memory workflow state (D19). The queue executes one
step and commits one transition; a reconciler sweeps for due, stuck and retryable rows.

### Template

```mermaid
stateDiagram-v2
    [*] --> uploaded: reference image added
    [*] --> analysed: text scene preset authored
    uploaded --> analysing
    analysing --> analysis_failed: provider error
    analysis_failed --> analysing: retry, bounded
    analysis_failed --> [*]: dead
    analysing --> invalid: placeholder does not resolve
    analysing --> analysed: validation passed
    invalid --> analysing: fixed and re-analysed
    analysed --> archived: superseded by a new version
    archived --> [*]
    note right of analysed
        Only analysed templates
        are selectable for generation
    end note
```

### Product / variant

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> ready: all required attrs + input images present
    ready --> generating: Save and Generate
    generating --> review: images passed QC, approval required
    generating --> approved: images passed QC, approval disabled
    review --> approved: approver accepts
    review --> rejected: approver declines
    rejected --> generating: regenerate
    approved --> publishing
    publishing --> published
    published --> needs_attention: spec adds a required field
    ready --> needs_attention: spec adds a required field
    needs_attention --> ready: missing data supplied
```

### Generation

```mermaid
stateDiagram-v2
    state "generation_request" as REQ {
        [*] --> queued
        queued --> running
        running --> succeeded: all items ok
        running --> partially_failed: some items dead
        running --> failed: all items dead
        queued --> cancelled
        running --> cancelled
    }
    state "generation_item — immutable attempt log" as ITEM {
        [*] --> pending
        pending --> item_running
        item_running --> item_succeeded
        item_running --> item_failed: retryable
        item_failed --> item_running: backoff + jitter
        item_failed --> dead: retry budget exhausted
    }
    state "catalog_image — current state per variant × slot" as IMG {
        [*] --> pending_qc
        pending_qc --> qc_failed: automated QC rejected
        qc_failed --> pending_qc: retried with a new seed or template
        qc_failed --> human_review: retry budget exhausted
        pending_qc --> pending_approval: approval.required = true
        pending_qc --> img_approved: approval.required = false
        pending_approval --> img_approved
        pending_approval --> img_rejected
        img_approved --> superseded: regenerated
    }
```

### Publication

```mermaid
stateDiagram-v2
    [*] --> scheduled
    scheduled --> dispatching: due_at reached AND rate-limit token available
    dispatching --> published: provider accepted
    dispatching --> pub_failed: provider error
    pub_failed --> dispatching: retry, re-checking the provider first
    pub_failed --> dead: retry budget exhausted
    scheduled --> cancelled
    published --> [*]
    note right of dispatching
        idempotency_key is committed
        BEFORE the external call.
        Double-posting to a customer's
        Instagram is the top-severity
        failure in this system.
    end note
```

---

## 3. Architecture — layering and import rules

Arrows are **allowed import directions** (D5). Enforced by `import-linter` in CI (D6).

```mermaid
flowchart TB

subgraph CORE["app/ — layered core, import-linter enforced"]
  direction TB
  API["<b>api/</b><br/>FastAPI routers · request/response schemas<br/>auth dependencies · error mapping"]
  AG["<b>agents/</b><br/>template analysis · QC review · copywriting<br/>deterministic control flow over model ports"]
  FE["<b>features/</b><br/>use cases · owns the transaction boundary<br/>emits domain events"]
  SV["<b>services/</b><br/>domain services + ALL PORTS as Protocols<br/>repositories · storage · models · channels · queue"]
  EN["<b>entities/</b><br/>pure domain model · invariants · events<br/>zero SQLAlchemy, zero FastAPI, zero I/O"]
  SH["<b>shared/</b><br/>ids · Result · base errors · clock · pagination"]

  API --> AG
  AG --> FE
  FE --> SV
  SV --> EN
  EN --> SH
  API --> FE
  API --> SV
  API --> EN
  AG --> SV
  FE --> EN
end

subgraph INF["app/infrastructure/ — adapters"]
  direction TB
  I1["persistence/<br/>SQLAlchemy repos · imperative mapping · UoW"]
  I2["storage/<br/>S3 presigned upload · content addressing"]
  I3["providers/<br/>Nano Banana 2 · text LLM · vision"]
  I4["channels/<br/>meta · pinterest · storefront"]
  I5["queue/<br/>Postgres SKIP LOCKED driver<br/>outbox relay"]
  I6["identity/<br/>OIDC · token store · crypto"]
end

BS["<b>app/bootstrap/</b><br/>composition root · DI wiring · app factory"]

BS --> INF
BS --> API
INF -. "implement the Protocols declared in services/" .-> SV

FORBID["<b>✕ FORBIDDEN</b><br/>api · agents · features · services · entities<br/>may NEVER import infrastructure directly.<br/>They depend on Protocols only."]
CORE -.- FORBID
FORBID -.- INF
```

The contract that makes this real, in `setup.cfg`:

```ini
[importlinter:contract:layers]
type = layers
layers = app.api
         app.agents
         app.features
         app.services
         app.entities
         app.shared

[importlinter:contract:infra_isolation]
type = forbidden
source_modules = app.api, app.agents, app.features, app.services, app.entities
forbidden_modules = app.infrastructure

[importlinter:contract:pure_domain]
type = forbidden
source_modules = app.entities
forbidden_modules = sqlalchemy, fastapi, redis, boto3, httpx
```

---

## 4. Architecture — runtime topology

```mermaid
flowchart TB

subgraph CLIENTS["Clients"]
  CL1["Tenant admin console"]
  CL2["Storefront — React<br/>tenant resolved from Host header"]
  CL3["Platform operator console"]
end

subgraph EDGE["Edge"]
  CDN["CDN — image delivery"]
  LB["Load balancer"]
end

subgraph PROC["Application processes"]
  APIP["<b>API service</b><br/>/platform · /admin<br/>/public · /webhooks"]
  WRK["<b>Workers</b><br/>normalise · analyse · generate<br/>QC · write copy · render · publish"]
  POL["<b>Poller / reconciler</b><br/>due_at scheduling · stuck runs<br/>outbox relay · token refresh"]
end

subgraph DATA["State — Postgres is the only stateful service in v1 (D19)"]
  PG[("Postgres 16<br/>RLS FORCED · composite tenant FKs<br/>workflow state · queue · rate limits<br/>PITR backups")]
  OBJ[("S3-compatible — R2<br/>inputs · templates<br/>generated · renditions")]
end

subgraph EXTAI["External — AI providers"]
  NB["Nano Banana 2<br/>image generation"]
  VIS["Vision model<br/>template analysis · QC"]
  TXT["Text LLM<br/>product + social copy"]
end

subgraph EXTCH["External — channels & platform"]
  META["Meta Graph API<br/>Instagram · Facebook"]
  PIN["Pinterest API v5"]
  IDP["Google Workspace / Entra<br/>OIDC"]
  KMS["KMS / secret manager<br/>envelope encryption"]
  OTEL["OpenTelemetry · Sentry"]
end

CL1 --> LB
CL2 --> LB
CL3 --> LB
CL2 --> CDN
CDN --> OBJ

LB --> APIP
APIP --> PG
APIP --> OBJ
APIP --> IDP
APIP --> KMS

PG -->|"LISTEN/NOTIFY + SKIP LOCKED"| WRK
WRK --> PG
WRK --> OBJ
WRK --> NB
WRK --> VIS
WRK --> TXT
WRK --> META
WRK --> PIN
WRK --> KMS

POL --> PG
POL --> META
POL --> PIN

APIP --> OTEL
WRK --> OTEL
POL --> OTEL

CL2 -. "presigned PUT — bytes never touch the API" .-> OBJ
```

**Why three process types.** The API must stay responsive while generation takes tens of seconds
per image. Workers scale independently on queue depth. The poller is separate because a queue does
not reliably schedule across restarts and redeploys — `due_at` in Postgres does.

---

## 5. Database

Split into four groups. One diagram with all ~30 tables is unreadable, and these groups map to the
milestones in the plan.

Conventions applying to **every** tenant-scoped table (D1, D2, D3):

- `tenant_id UUID NOT NULL`, plus `UNIQUE (tenant_id, id)`
- every FK between tenant-scoped tables is **composite** — `FOREIGN KEY (tenant_id, x_id)` — so a
  cross-tenant reference is structurally unrepresentable
- `ENABLE` **and** `FORCE ROW LEVEL SECURITY`, policy on `current_setting('app.current_tenant')`,
  set with `SET LOCAL` inside the transaction
- `created_at`, `updated_at` timestamptz; soft delete only where history matters

FK columns below are shown singly for readability; each is composite in the DDL.

### 5a · Identity, tenancy and audit (D4)

```mermaid
erDiagram
    TENANTS ||--o{ TENANT_MEMBERSHIPS : "has members"
    TENANTS ||--o{ TENANT_DOMAINS : "resolves storefront by"
    TENANTS ||--o{ API_KEYS : "issues"
    TENANTS ||--o{ AUDIT_LOG : "records"
    USERS ||--o{ TENANT_MEMBERSHIPS : "belongs to"
    USERS ||--o{ IDENTITIES : "authenticates via"
    USERS ||--o{ SESSIONS : "holds"
    USERS ||--o| PLATFORM_ADMINS : "may be"
    USERS ||--o{ AUDIT_LOG : "acted"

    TENANTS {
        uuid id PK
        text name
        text slug UK
        text status "active pending suspended"
        text plan
        timestamptz created_at
    }
    TENANT_DOMAINS {
        uuid id PK
        uuid tenant_id FK
        text hostname UK "storefront Host header lookup"
        bool is_primary
        bool verified
    }
    USERS {
        uuid id PK
        citext email UK
        bool email_verified
        text display_name
        text status
    }
    IDENTITIES {
        uuid id PK
        uuid user_id FK
        text provider "google entra saml"
        text subject "provider sub claim"
        jsonb raw_claims
    }
    PLATFORM_ADMINS {
        uuid user_id PK "explicit grant - domain match is NEVER sufficient"
        text granted_by
        timestamptz granted_at
    }
    TENANT_MEMBERSHIPS {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        text role "owner admin catalog_manager approver viewer"
        jsonb extra_capabilities
    }
    SESSIONS {
        uuid id PK
        uuid user_id FK
        uuid tenant_id FK "active tenant"
        text refresh_token_hash
        timestamptz expires_at
        timestamptz revoked_at
    }
    API_KEYS {
        uuid id PK
        uuid tenant_id FK
        text name
        text key_hash
        jsonb scopes
        timestamptz last_used_at
    }
    AUDIT_LOG {
        uuid id PK
        uuid tenant_id FK
        uuid actor_user_id FK
        text action
        text subject_type
        uuid subject_id
        jsonb before
        jsonb after
        inet ip
        timestamptz occurred_at
    }
```

### 5b · Taxonomy and catalog specification (D10–D15)

This group is the generic core — nothing here knows what a saree is.

```mermaid
erDiagram
    TENANTS ||--o{ CATEGORIES : "owns"
    CATEGORIES ||--o{ CATEGORIES : "parent of"
    CATEGORIES ||--o{ CATEGORY_SPEC_VERSIONS : "versioned by"
    CATEGORIES ||--o{ ATTRIBUTE_DEFINITIONS : "defines"
    CATEGORIES ||--o{ VARIANT_AXES : "defines"
    CATEGORIES ||--o{ INPUT_IMAGE_SLOTS : "defines pool"
    CATEGORIES ||--o{ CATALOG_IMAGE_SLOTS : "defines outputs"
    VARIANT_AXES ||--o{ VARIANT_AXIS_VALUES : "allows"
    CATALOG_IMAGE_SLOTS ||--o{ CATALOG_SLOT_INPUT_REQUIREMENTS : "requires"
    INPUT_IMAGE_SLOTS ||--o{ CATALOG_SLOT_INPUT_REQUIREMENTS : "is used by"
    CATALOG_IMAGE_SLOTS ||--o{ CATALOG_TEMPLATES : "has many"
    ASSETS ||--o{ CATALOG_TEMPLATES : "reference image, nullable"
    ASSETS ||--o{ INPUT_IMAGE_SLOTS : "example shot"

    CATEGORIES {
        uuid id PK
        uuid tenant_id FK
        uuid parent_id FK "children inherit and may extend or override by key"
        ltree path
        int depth
        text key
        text name
        text slug
        int current_spec_version
        int draft_spec_version
        bool is_active
    }
    CATEGORY_SPEC_VERSIONS {
        uuid id PK
        uuid tenant_id FK
        uuid category_id FK
        int version
        text status "draft published archived"
        jsonb snapshot "full resolved spec including inherited"
        jsonb change_summary
        timestamptz published_at
    }
    ATTRIBUTE_DEFINITIONS {
        uuid id PK
        uuid tenant_id FK
        uuid category_id FK "the category that OWNS it"
        text key
        text label
        text data_type "text money enum bool date decimal"
        text semantic_role "title description price sku brand colour - projects to a real column"
        bool is_required
        bool is_filterable
        bool is_public
        jsonb validation
        jsonb ui
        int introduced_in_version
        int retired_in_version "NULL = live"
    }
    VARIANT_AXES {
        uuid id PK
        uuid tenant_id FK
        uuid category_id FK
        text key "colour size fabric"
        text label
        bool affects_imagery "drives the generation fan-out"
        int introduced_in_version
        int retired_in_version
    }
    VARIANT_AXIS_VALUES {
        uuid id PK
        uuid tenant_id FK
        uuid axis_id FK
        text value
        text label
        jsonb metadata "hex swatch"
    }
    INPUT_IMAGE_SLOTS {
        uuid id PK
        uuid tenant_id FK
        uuid category_id FK
        text key "border bunthi blouse"
        text label
        text description "becomes the IMAGE n role line in the prompt"
        text capture_guidance
        uuid example_asset_id FK
        jsonb normalisation "per-slot preprocessing depth"
        bool is_required
        int introduced_in_version
        int retired_in_version
    }
    CATALOG_IMAGE_SLOTS {
        uuid id PK
        uuid tenant_id FK
        uuid category_id FK
        text key "closeup human_worn styled_hero"
        text label
        text aspect_ratio
        int target_width
        int target_height
        bool is_required
        int introduced_in_version
        int retired_in_version
    }
    CATALOG_SLOT_INPUT_REQUIREMENTS {
        uuid catalog_image_slot_id PK "composite PK with input_image_slot_id"
        uuid input_image_slot_id PK
        uuid tenant_id FK
        text role "how this input is used here"
        int prompt_position "the IMAGE n index"
        bool is_required
    }
    CATALOG_TEMPLATES {
        uuid id PK
        uuid tenant_id FK
        uuid catalog_image_slot_id FK
        text name
        int version
        text kind "analysed_image or authored_scene"
        uuid source_asset_id FK "NULL for authored text scenes"
        text status "uploaded analysing analysed invalid archived"
        jsonb analysis "composition camera light background grade"
        text prompt_template "scene and placement only - never the product"
        text prompt_version
        text analysis_model
        jsonb params "blouse_render seed_policy etc"
        bool is_default
    }
    ASSETS {
        uuid id PK
        uuid tenant_id FK
        text storage_key
        bytea sha256 "content addressed, dedups"
        text kind "template input generated derivative"
        uuid parent_asset_id FK
        text mime
        int width
        int height
        bigint bytes
        jsonb meta
    }
```

### 5c · Products, variants and generation (D12, D17, D18)

```mermaid
erDiagram
    CATEGORIES ||--o{ PRODUCTS : "classifies"
    CATEGORY_SPEC_VERSIONS ||--o{ PRODUCTS : "pinned by"
    PRODUCTS ||--o{ PRODUCT_VARIANTS : "has"
    PRODUCTS ||--o{ PRODUCT_INPUT_IMAGES : "captured for"
    PRODUCT_VARIANTS ||--o{ PRODUCT_INPUT_IMAGES : "may override"
    INPUT_IMAGE_SLOTS ||--o{ PRODUCT_INPUT_IMAGES : "filled by"
    ASSETS ||--o{ PRODUCT_INPUT_IMAGES : "raw + normalised"
    PRODUCT_VARIANTS ||--o{ GENERATION_REQUESTS : "triggers"
    GENERATION_REQUESTS ||--o{ GENERATION_ITEMS : "fans out into"
    CATALOG_IMAGE_SLOTS ||--o{ GENERATION_ITEMS : "targets"
    CATALOG_TEMPLATES ||--o{ GENERATION_ITEMS : "rendered from"
    GENERATION_ITEMS ||--o| CATALOG_IMAGES : "winning attempt becomes"
    PRODUCT_VARIANTS ||--o{ CATALOG_IMAGES : "displays"
    ASSETS ||--o{ CATALOG_IMAGES : "stores"

    PRODUCTS {
        uuid id PK
        uuid tenant_id FK
        uuid category_id FK
        uuid spec_version_id FK "pinned at creation - regeneration reproduces original intent"
        text slug
        text status "draft ready generating review approved publishing published needs_attention"
        jsonb attributes "SOURCE OF TRUTH - GIN indexed"
        text title "projected from semantic_role"
        text sku "projected"
        bigint price_amount "projected"
        char price_currency "projected"
        uuid created_by FK
    }
    PRODUCT_VARIANTS {
        uuid id PK
        uuid tenant_id FK
        uuid product_id FK
        text sku
        jsonb axis_values "colour maroon, size free"
        jsonb attributes "sparse overrides"
        text status
        bool is_default
        int position
    }
    PRODUCT_INPUT_IMAGES {
        uuid id PK
        uuid tenant_id FK
        uuid product_id FK
        uuid variant_id FK "NULL = shared by all variants"
        uuid input_image_slot_id FK
        uuid raw_asset_id FK
        uuid normalised_asset_id FK "what generation actually consumes"
        text normalisation_status "captured validating normalising ready rejected"
        text rejection_reason
    }
    GENERATION_REQUESTS {
        uuid id PK
        uuid tenant_id FK
        uuid product_id FK
        uuid variant_id FK
        uuid spec_version_id FK
        text status "queued running succeeded partially_failed failed cancelled"
        jsonb settings_snapshot
        uuid quota_reservation_id FK
        uuid requested_by FK
    }
    GENERATION_ITEMS {
        uuid id PK
        uuid tenant_id FK
        uuid request_id FK
        uuid catalog_image_slot_id FK
        uuid template_id FK
        int attempt_no
        text status "pending running succeeded failed dead"
        text provider
        text model "nano-banana-2"
        jsonb model_params
        bigint seed
        text prompt_rendered
        text prompt_version
        uuid_array input_asset_ids
        uuid output_asset_id FK
        bigint cost_micros
        int latency_ms
        text error_code
        text error_detail
    }
    CATALOG_IMAGES {
        uuid id PK
        uuid tenant_id FK
        uuid variant_id FK
        uuid catalog_image_slot_id FK
        uuid asset_id FK
        uuid generation_item_id FK
        text status "pending_qc qc_failed human_review pending_approval approved rejected"
        jsonb qc_result "fidelity colour_delta artefacts safety"
        bool is_primary
        uuid approved_by FK
        timestamptz approved_at
        text rejection_reason
        uuid superseded_by FK "partial UNIQUE per variant+slot WHERE superseded_by IS NULL"
    }
```

> **`generation_items` and `catalog_images` are both required and are not redundant.**
> `generation_items` is the immutable attempt log — which model, prompt version, seed, cost, and
> why it failed. It is what makes a result reproducible, a regression diagnosable, and per-tenant
> cost attributable. `catalog_images` is mutable current state with approval status. Regenerating
> is a two-statement transaction: set `superseded_by` on the live row **and** insert the new one,
> together — otherwise the partial unique index raises a duplicate key in production.

### 5d · Content, publishing, settings and ops (D16, D19, D21–D24)

```mermaid
erDiagram
    PRODUCT_VARIANTS ||--o{ CONTENT_DRAFTS : "described by"
    PRODUCT_VARIANTS ||--o{ PUBLICATIONS : "published as"
    CONTENT_DRAFTS ||--o{ PUBLICATIONS : "carries copy for"
    TENANTS ||--o{ SOCIAL_ACCOUNTS : "connects"
    SOCIAL_ACCOUNTS ||--o{ CHANNELS : "exposes"
    CHANNELS ||--o{ PUBLICATIONS : "target of"
    CHANNELS ||--o{ CHANNEL_RENDER_SPECS : "requires crops"
    CATALOG_IMAGES ||--o{ PUBLICATION_MEDIA : "attached to"
    PUBLICATIONS ||--o{ PUBLICATION_MEDIA : "includes"
    TENANTS ||--o{ SETTINGS : "configures"
    TENANTS ||--o{ USAGE_EVENTS : "meters"
    TENANTS ||--o{ QUOTA_RESERVATIONS : "bounded by"
    TENANTS ||--o{ WORKFLOW_RUNS : "runs"
    WORKFLOW_RUNS ||--o{ WORKFLOW_STEPS : "advances through"

    CONTENT_DRAFTS {
        uuid id PK
        uuid tenant_id FK
        uuid variant_id FK
        text channel
        text locale
        text title
        text body
        text_array hashtags
        text alt_text
        text model
        text prompt_version
        text status "draft pending_approval approved rejected"
        uuid edited_by FK
    }
    SOCIAL_ACCOUNTS {
        uuid id PK
        uuid tenant_id FK
        text provider "instagram facebook pinterest"
        text external_account_id
        text display_name
        bytea credentials_encrypted "AES-256-GCM, DEK wrapped by KMS"
        text encryption_key_id "enables background re-wrap rotation"
        jsonb scopes
        timestamptz access_expires_at
        text status
        text last_error
    }
    CHANNELS {
        uuid id PK
        uuid tenant_id FK
        uuid social_account_id FK "NULL for the storefront channel"
        text kind "storefront instagram facebook pinterest"
        text external_target_id "page id, board id"
        jsonb capabilities "aspect ratios, max media, caption length"
        jsonb rate_limit "token bucket config - verified against provider docs"
        bool is_enabled
    }
    CHANNEL_RENDER_SPECS {
        uuid id PK
        uuid tenant_id FK
        uuid channel_id FK
        text aspect_ratio
        int width
        int height
        text crop_strategy
        jsonb safe_zones
    }
    PUBLICATIONS {
        uuid id PK
        uuid tenant_id FK
        uuid variant_id FK
        uuid channel_id FK
        uuid content_draft_id FK
        text idempotency_key UK "COMMITTED BEFORE the external call"
        text status "scheduled dispatching published failed dead cancelled"
        timestamptz due_at "poller driven - a queue does not schedule reliably"
        timestamptz published_at
        text external_post_id
        text permalink
        jsonb payload
        int attempts
        text last_error
        jsonb metrics "fetched back later"
    }
    PUBLICATION_MEDIA {
        uuid id PK
        uuid tenant_id FK
        uuid publication_id FK
        uuid catalog_image_id FK
        uuid rendition_asset_id FK "derivative built at publish time"
        int position
    }
    SETTINGS {
        uuid id PK
        uuid tenant_id FK
        text scope_type "platform tenant category product"
        uuid scope_id
        text key "approval.required approval.required_channels qc.min_confidence"
        jsonb value
    }
    USAGE_EVENTS {
        uuid id PK
        uuid tenant_id FK
        text metric "image_generated tokens_used publish_sent"
        numeric quantity
        bigint unit_cost_micros
        text ref_type
        uuid ref_id
        timestamptz occurred_at
    }
    QUOTA_RESERVATIONS {
        uuid id PK
        uuid tenant_id FK
        text period "2026-08"
        text metric
        bigint limit_value
        bigint reserved "conditional UPDATE inside the enqueue txn"
        bigint committed
    }
    OUTBOX_EVENTS {
        uuid id PK
        uuid tenant_id FK
        text event_type
        jsonb payload
        text status "pending dispatched dead"
        int attempts
        timestamptz available_at
    }
    WORKFLOW_RUNS {
        uuid id PK
        uuid tenant_id FK
        text workflow "generate_catalog publish_variant analyse_template"
        text subject_type
        uuid subject_id
        text status
        text current_step
        timestamptz due_at "reconciler sweeps due and stuck runs"
        jsonb context
    }
    WORKFLOW_STEPS {
        uuid id PK
        uuid tenant_id FK
        uuid run_id FK
        text step
        text status
        int attempt
        text idempotency_key
        jsonb result
        text error
    }
```

---

## Index-and-constraint notes worth carrying into the migrations

| Table | Constraint | Why |
|---|---|---|
| every tenant table | `UNIQUE (tenant_id, id)` + composite FKs | cross-tenant references become unrepresentable (D2) |
| `catalog_images` | `UNIQUE (tenant_id, variant_id, catalog_image_slot_id) WHERE superseded_by IS NULL` | one live image per slot, full history kept (D18) |
| `publications` | `UNIQUE (idempotency_key)` | the double-post guard (D21) |
| `assets` | `UNIQUE (tenant_id, sha256, kind)` | dedups the same photo across variants (D17) |
| `products` | GIN on `attributes` | filtering on tenant-defined fields (D11) |
| `settings` | `UNIQUE (scope_type, scope_id, key)` | deterministic resolution (D16) |
| `quota_reservations` | `UNIQUE (tenant_id, period, metric)` | the conditional UPDATE target (D24) |
| `outbox_events` | partial index on `status = 'pending'` | relay polls a small hot set (D19) |
| `workflow_runs` | index on `(status, due_at)` | reconciler sweep (D19) |
| spec tables | `UNIQUE (tenant_id, category_id, key) WHERE retired_in_version IS NULL` | keys unique among live rows only (D15) |
