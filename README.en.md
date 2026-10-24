<div align="center">

# 🤖 OfferPath Job Agent

**[简体中文](README.md) · English**

### Tailor every application. Track every step.

An open-source Agent Skill for a more thoughtful job search.<br/>
Read the role, tailor your resume, verify the outcome, and keep your records together.

[🌐 Open OfferPath](https://offerpath.xingo.fun) · [🚀 Get started](#-get-started)

![A friendly blue robot tailoring a resume and checking application materials](assets/offerpath-companion.png)

**One resume per role · Checks before submission · Actual receipts · Traceable records**

</div>

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

**Developer preview:** Search, resume production, and browser interactions are performed by the Agent running the skill and its available tools. The included Python program handles validation, persistent state, and OfferPath synchronization. There is no one-click application bot, email sender, or scheduled follow-up service.

The current `check`, `reserve`, and `sync` commands require an accessible OfferPath account. You can read the skill, prepare materials, and run synthetic tests offline; there is no alternate local ledger adapter for these commands.

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

### 1. Run the synthetic tests

The executor uses only the Python standard library. CI runs on Python 3.9 and 3.12.

```sh
git clone https://github.com/Olandooooes/offerpath-job-agent.git
cd offerpath-job-agent
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Tests use temporary files, synthetic materials, fake accounts, and a temporary loopback HTTP server. They do not need real credentials, send applications, or write production records. The HTTP integration test needs an environment that permits loopback listening.

### 2. Install as a Codex skill

If the skill is not already installed, clone into your skills directory:

```sh
git clone https://github.com/Olandooooes/offerpath-job-agent.git \
  "$HOME/.codex/skills/offerpath-job-agent"
```

Preserve existing installations and local changes. Once Codex discovers the skill, invoke it with `$offerpath-job-agent`.

### 3. Create your private workspace

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

**Real-account authentication currently supports macOS Keychain only.** Obtain an available independent automation authorization through your own OfferPath account and store it using system Keychain tools. Configuration references entry names, never plaintext tokens. Availability depends on your account; connection failure does not automatically create or expand permissions.

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

The 25 automated tests cover renamed generic resumes, PDF reuse across batches, authorization limits, legacy sending locks, live deduplication, unknown outcomes, invalid receipts, saved attachment snapshots, interrupted sync recovery, foreign-attachment protection, and preservation of interview stages and notes. Synthetic PDFs and images are not evidence of real visual review.

## 🧩 Project structure

```text
offerpath-job-agent/
├── SKILL.md                 Agent workflow instructions
├── scripts/agent.py         Validation, persistent state, OfferPath sync
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
- [ ] Friendlier setup and application-package editing
- [ ] Windows and Linux credential adapters
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
