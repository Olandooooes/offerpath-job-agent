<div align="center">

# 🤖 OfferPath Job Agent

**[简体中文](README.md) · English**

### Tailor every application. Track every step.

An open-source Agent Skill for a more thoughtful job search.<br/>
Use your own AI to tailor each resume, review the actual PDF, and keep application records connected to OfferPath.

[🌐 Open OfferPath](https://offerpath.xingo.fun) · [🚀 Get started](#-get-started)

![A friendly blue robot tailoring a resume and checking application materials](assets/offerpath-companion.png)

**One resume per role · Checks before submission · Actual receipts · Traceable records**

</div>

## 🆕 Start with Codex

The current priority is **Codex + this GitHub Skill + a local OfferPath connector**. Supply your resume and full job description in Codex, tailor a resume for each role, review its actual PDF yourself, then sync the reported application outcome and attachment. There is no result-JSON copy-and-paste loop.

**No separate model API purchase is required.** Tailoring uses your existing Codex model access, subject to the platform's quotas and terms; unlimited free usage is not promised. The connector runs locally. No public service or live OfferPath website change is deployed.

| Capability | Current boundary |
| --- | --- |
| Codex skill and local MCP tools | Skill installation and MCP connection are separate steps; Python, PDF dependencies, and local configuration are required |
| Resume and job intake | Codex proposes facts for your confirmation and saves full job descriptions; private data stays outside the repository |
| Role-specific drafts and actual PDFs | Codex generates content; the connector checks references and versions and creates files. References alone do not establish truth |
| PDF approval | The person opens the local review card and approves the specific PDF. The AI must not click for them |
| Synthetic record sync | Uses a local simulated ledger and the actual PDF; no production account writes |
| Real OfferPath connection | Requires the owner's independent authorization; production integration and cloud preview need separate acceptance |
| Original Codex executor | `agent.py`, `setup.py`, the offline demo, private configuration, and Keychain authentication remain available |

[Codex installation and connection guide (Chinese) →](references/codex.md)

All 98 local synthetic tests pass. The installed Codex app-server has also connected, discovered tools, saved a draft, and retrieved its actual PDF. Fresh desktop GUI onboarding and production-account integration need separate acceptance. See the [Codex acceptance scope](docs/codex-acceptance.md).

Other clients, including QwenWork, are **deferred** while the Codex workflow is validated. Existing [QwenWork reference documentation](references/qwenwork.md) and code remain available; they are not the recommended onboarding path.

## 🌱 Why this project exists

A job search can quickly spread across recruiting websites, resume editors, email, and a growing spreadsheet. Which resume did you submit? Have you already applied through another channel? Where did you save the confirmation?

OfferPath Job Agent turns a careful application process into a reusable skill, with local tools to track materials, outcomes, and supporting evidence. You choose your direction and authorize each application batch; the Agent helps with the work.

## 📄 A resume tailored to each role

Start with the full job description and your verified experience. Map requirements to relevant work and projects, then adjust the summary, project order, emphasis, and wording for that role. Every claim must remain truthful.

Each application keeps its own source file, final PDF, tailoring notes, and rendered preview. The checker binds artifacts to their file hashes and rejects a PDF that is byte-identical to the base resume. Renaming a generic resume does not pass that check.

Content quality still requires actual review. Hashes and recorded attestations alone cannot establish that a resume is well tailored or that a review genuinely happened.

## 🔄 Application records synced to OfferPath

### [Visit OfferPath → offerpath.xingo.fun](https://offerpath.xingo.fun)

**The Agent helps prepare and execute applications. OfferPath helps you track what comes next.**

Use OfferPath to organize roles, application stages, resume attachments, notes, and next steps. You can also use the website independently to manage your job search.

With the sync adapter connected to your authorized account, confirmed applications can be linked to OfferPath records. The adapter uploads the PDF snapshot saved for that application, downloads the attachment again, and verifies its name, bytes, and hash. Actual cloud preview review is a separate completion step.

If an application succeeds but syncing is interrupted, recover the record and attachment without submitting the application again. Existing interview stages and user notes are preserved.

## 🧰 What it covers

| Stage | Work and evidence |
| --- | --- |
| Discover | Review complete job descriptions against your preferences; keep sources and screening rationale |
| Match | Map requirements to verified experience and record gaps |
| Tailor | Prepare a role-specific source file, PDF, change notes, and visual review |
| Check | Validate artifacts, authorization, and live duplicates |
| Confirm | Distinguish confirmed, unknown, and pending outcomes using actual receipts |
| Sync | Update OfferPath, download and verify the actual attachment, then review its preview |

**Developer preview:** The AI client and its available tools perform search and content tailoring. The local bridge checks references and versions, creates PDFs, and manages simulated records. The original Python executor validates real application packages, preserves execution state, and synchronizes with OfferPath. There is no one-click application bot, email sender, or scheduled follow-up service.

The original `agent.py` commands `check`, `reserve`, and `sync` require an accessible OfferPath account. The new connector has a separate local synthetic ledger; it is not the official status source and cannot authorize the original submission workflow.

## 🧭 The application workflow

```mermaid
flowchart LR
    A[Read full job description] --> B[Match verified experience]
    B --> C[Tailor resume]
    C --> D[Render and review]
    D --> E[Check authorization and live duplicates]
    E --> F[Submit once]
    F --> G[Verify actual receipt]
    G --> H[Sync to OfferPath]
    H --> I[Verify attachment and preview]
```

An application package contains the job description, experience mapping, tailoring notes, source files, final PDF, visual evidence, and receipt. After validation, the tool saves a persistent job lock and the actual PDF bytes in local SQLite. The Agent then applies within the current authorization using available browser tools.

An uncertain outcome stays locked as unknown. Do not retry a submission without resolving its status.

| Milestone | Meaning |
| --- | --- |
| Application confirmed | A supported platform receipt, candidate-center confirmation, or delivery evidence exists |
| Attachment verified | The actual OfferPath PDF has been downloaded; its name, bytes, and hash match |
| Workflow complete | The actual cloud preview has also been reviewed and evidence saved |

Clicking Submit or seeing an increased record count does not establish completion. Programmatic checks do not replace reviewing the resume and its preview.

## 🚀 Get started

### Recommended: the Codex chat connector

Follow the [Codex guide](references/codex.md) to install the GitHub Skill, create a new synthetic workspace outside the repository, and generate a local MCP configuration fragment. Merge the fragment into your Codex settings or configuration yourself, reload, and start a new task. **Installing the skill does not connect MCP tools.**

Once tools are available, ask Codex:

```text
$offerpath-job-agent
Choose one synthetic role and use the confirmed facts to tailor a resume
against its full job description. Show the actual PDF and local review link.
Wait for my own confirmation before continuing. Synthetic demo only;
do not connect a real account or submit a real application.
```

The MCP process automatically starts the local PDF review service; a separate server terminal is not needed. You must review and approve the actual PDF in its local card yourself. The AI must not click for you. After approval, you may ask Codex to simulate an outcome and sync the synthetic local record; simulated outcomes are not real receipts.

### Preserved: the original Codex application-package workflow

Existing private configurations continue to work without migration. Synthetic connector records do not issue submission permits for the original checker or clear historical unknown-outcome locks.

### 1. Run the synthetic tests

The original `agent.py` executor uses only the Python standard library. The chat connector also needs PDF dependencies. Use a virtual environment, install the connector dependencies, then run the full suite:

```sh
git clone https://github.com/Olandooooes/offerpath-job-agent.git
cd offerpath-job-agent
python3 -m pip install -r requirements-connector.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Tests use temporary files, synthetic materials, fake accounts, and a temporary loopback HTTP server. They do not need real credentials, send applications, or write production records. The HTTP integration test needs an environment that permits loopback listening.

The full suite also needs a CJK TrueType font. Linux CI installs `fonts-wqy-zenhei` and `poppler-utils`; see the [Codex setup guide](references/codex.md). The existing HTTP connector has a [historical synthetic acceptance report](docs/qwenwork-acceptance.md); those results do not establish Codex client or production account acceptance.

### 2. Install as a Codex skill

If the skill is not already installed, clone into the user skill directory shown in the official Codex documentation:

```sh
git clone https://github.com/Olandooooes/offerpath-job-agent.git \
  "$HOME/.agents/skills/offerpath-job-agent"
```

An existing compatible installation under `~/.codex/skills/` can remain; avoid duplicate copies. Preserve existing installations and local changes. Once Codex discovers the skill, invoke it with `$offerpath-job-agent`. To use the new chat tools, also complete the [local MCP connection](references/codex.md).

### 3. Create your private workspace

Use a **new directory outside the repository**. Omit `--workspace` to be prompted. Existing directories are never overwritten.

```sh
python3 scripts/setup.py init --workspace /path/to/new-private-workspace
python3 scripts/setup.py check --config /path/to/new-private-workspace/agent.local.json
```

The wizard creates private templates without networking or Keychain access. Local checks flag missing paths, paths inside the repository, and unchanged Keychain references. They do not verify credentials or personal facts. Complete your profile and existing Keychain references, then run `agent.py doctor` when ready. Setup does not authorize applications.


Start with the [configuration example](examples/private-config.example.json), [profile template](examples/profile.example.md), and [policy template](examples/policy.example.md). The templates, skill instructions, and technical reference documents are currently in Chinese; this English README provides the project overview and setup guide.

Keep your completed personal files outside the repository and configure real absolute paths:

```text
your-private-workspace/
├── AGENTS.md
├── agent.local.json
├── profile.md
├── facts.md
├── policy.md
├── workbench.md
├── batches/
└── runtime/
```

In your workspace's `AGENTS.md`, identify the private JSON configuration to use. Set your own locations, compensation preferences, verified facts, base resume, and authorization boundaries.

**The original Codex executor supports macOS Keychain authentication only.** Obtain an available independent automation authorization through your own OfferPath account and store it using system Keychain tools. Configuration references entry names, never plaintext tokens. Availability depends on your account; connection failure does not automatically create or expand permissions.

### 4. Start with preparation only

```text
$offerpath-job-agent
Find three roles matching my private profile. Read the full job descriptions,
tailor a resume for each role, and render and review the PDFs.
Save the application packages and matching rationale. Do not submit yet.
```

When ready, explicitly authorize the batch size, channels, and individual review requirements:

```text
$offerpath-job-agent
Apply to three qualified roles in this batch. Tailor and review every resume,
and check live duplicates before submission. Sync confirmed applications and
the actual attachments to OfferPath, review cloud previews, and report gaps.
```

Invoking the skill alone does not authorize sending. Batch authorization does not skip tailoring, review, or receipt verification.

## 🎭 Offline synthetic demo

No account required:

```sh
python3 scripts/demo.py --output /path/to/new-demo-directory
```

Open the generated `index.html` to see a fictional job description, before/after resume text, state transitions, and a simulated OfferPath record. `report.json` contains machine-readable results; synthetic PDFs and evidence files are also saved. The output must be a new directory outside the repository.

**No network calls, credential access, real applications, or real cloud writes.** Receipts and visual-review assertions are explicitly simulated. They are not real application evidence. This demonstrates validation and synchronization state; it does not generate resumes for real jobs or replace actual PDF rendering and review.

## 🛠 Development and testing

Entry point: `scripts/agent.py`. See the [application package contract](references/package.md) and [operations guide](references/operations.md) for complete fields and procedures (currently Chinese).

| Command | Behavior |
| --- | --- |
| `doctor` | Check private file locations and read-only OfferPath connectivity |
| `check` | Validate the package and query live records; does not issue a submission permit |
| `reserve` | Recheck, persist job locks, and save final PDF snapshots |
| `confirm` | Bind receipt evidence and record confirmed or unknown outcomes |
| `sync` | Read-only dry run by default; `--write` updates records and attachments |
| `preview` | Record actual cloud preview review evidence and complete the workflow |
| `status` | Show outcomes and synchronization progress for a batch |

```sh
python3 scripts/agent.py --config /path/to/private-workspace/agent.local.json doctor
python3 scripts/agent.py --config /path/to/private-workspace/agent.local.json \
  check --package /path/to/private-workspace/batches/package.json
```

The original automated tests cover renamed generic resumes, PDF reuse across batches, authorization limits, legacy sending locks, live deduplication, unknown outcomes, invalid receipts, saved attachment snapshots, interrupted sync recovery, foreign-attachment protection, and preservation of interview stages and notes. Synthetic PDFs and images are not evidence of real visual review.

## 🧩 Project structure

```text
offerpath-job-agent/
├── SKILL.md                 Agent workflow instructions
├── scripts/agent.py         Existing Codex validation, state, OfferPath sync
├── scripts/codex_bridge.py  Codex stdio MCP entry point and config generation
├── scripts/qwenwork.py      Shared local materials, PDF review, record service
├── requirements-connector.txt  PDF dependencies; no model API SDK
├── tests/test_agent.py      Synthetic and loopback HTTP integration tests
├── references/              Package contract and operational guidance
├── examples/                Templates without personal data
├── docs/                    Artwork notes
└── assets/                  Illustrated project cover
```

## 🪴 Roadmap

- [x] Per-role artifact versions and evidence checks
- [x] Persistent unknown-outcome locks and PDF snapshots
- [x] OfferPath record synchronization and attachment download verification
- [x] Separate cloud preview confirmation
- [x] Synthetic HTTP integration tests
- [x] Private workspace initialization and local configuration checks
- [x] Offline synthetic workflow demo
- [ ] Friendlier application-package editing
- [ ] Actual Codex client installation, tool discovery, and PDF confirmation acceptance
- [ ] Other AI clients (QwenWork deferred)
- [ ] Independent OfferPath authorization for ordinary users
- [ ] Windows and Linux production credential adapters
- [ ] Better assistance for assessing tailoring quality and more behavioral tests
- [ ] Improved concurrency handling within available API capabilities
- [ ] Explicit support for more recruiting channels and receipt collection

Unchecked items are plans, not available features. Share your use case in an issue or contribute a focused pull request.

## 🤝 Contribute

Read the [contribution guide](CONTRIBUTING.md) (currently Chinese). Use redacted or synthetic examples. Keep real resumes, confidential company materials, personal configurations, receipts, execution databases, and credentials out of public issues and commits.

The project grows from an evolving personal job-search workflow. Use it as a starting point for your own process, and retain relevant licenses and attribution when combining it with other projects.

Code is licensed under [MIT](LICENSE). The cartoon cover is AI-generated; see the [artwork notes](docs/artwork.md) for its provenance and prompt.

---

<div align="center">

**Prepare with care. Keep track of every step.**

[🌐 Organize your next opportunity with OfferPath](https://offerpath.xingo.fun)

</div>
