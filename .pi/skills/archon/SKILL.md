---
name: archon
description: Run Archon CLI workflows from Pi, create Archon workflows or command files, set up Archon, or manage Archon configuration. Use when the user wants to use Archon from this repo rather than doing the work directly in Pi.
---

# Archon CLI Skill for Pi

This is the Pi-adapted version of the Archon skill. Use it when the user wants to delegate work to the Archon CLI, author Archon workflow YAML or command files, initialize `.archon/`, or troubleshoot Archon setup.

Archon is a separate CLI orchestrator. In Pi, use this skill to **drive Archon through shell commands** and to **author Archon files in the repo**.

## Available Workflows (live)

Run:

```bash
archon workflow list
```

If that fails, read `guides/setup.md`.

## Routing

Determine the user's intent and dispatch to the appropriate guide:

| Intent | Action |
|--------|--------|
| Setup / install / how to use | Read `guides/setup.md` |
| Config / settings | Read `guides/config.md` |
| Initialize `.archon/` in a repo | Read `references/repo-init.md` |
| Create a workflow | Read `references/workflow-dag.md` |
| Quick parameter lookup | Read `references/parameter-matrix.md` |
| Advanced features (hooks / MCP / skills) | Read `references/dag-advanced.md` |
| Create a command file | Read `references/authoring-commands.md` |
| Variable substitution reference | Read `references/variables.md` |
| CLI command reference | Read `references/cli-commands.md` |
| Run an interactive workflow | Read `references/interactive-workflows.md` |
| Workflow good practices / anti-patterns | Read `references/good-practices.md` |
| Troubleshoot a failing / stuck workflow | Read `references/troubleshooting.md` |
| Run a workflow (default) | Continue with "Running Workflows" below |

If the intent is ambiguous, ask the user to clarify.

## Using archon.diy

The local reference pages are the primary source. If they do not cover the needed case, use the live docs at [archon.diy](https://archon.diy).

Useful entry points:

- [Getting started](https://archon.diy/getting-started/overview/)
- [Workflow authoring](https://archon.diy/guides/authoring-workflows/)
- [Command authoring](https://archon.diy/guides/authoring-commands/)
- [CLI reference](https://archon.diy/reference/cli/)
- [Configuration](https://archon.diy/reference/configuration/)
- [Troubleshooting](https://archon.diy/reference/troubleshooting/)

## Running Workflows

### Core Command

```bash
archon workflow run <workflow-name> --branch <branch-name> "<message>"
```

### Pi-specific rules

1. Prefer worktree isolation with `--branch` unless the user explicitly wants `--no-worktree`.
2. Because Pi does not provide Claude Code's background task protocol for shell commands, treat long-running Archon executions carefully.
3. Default behavior in Pi:
   - For quick commands like `workflow list`, `doctor`, `validate`, `isolation list`: run them directly.
   - For long-running `workflow run` commands: either run them only when the user explicitly asks, or give the user the exact command to run in their own terminal.
4. If you do run a long Archon workflow from Pi, warn the user that the shell call may block until completion.
5. For multiple issues or PRs, keep one Archon run per command and per branch.

### Isolation Modes

| Mode | Flag | When to Use |
|------|------|-------------|
| Worktree (default) | `--branch <name>` | Default |
| Custom start-point | `--branch <name> --from <base>` | Start from a specific branch |
| Direct checkout | `--no-worktree` | Only if explicitly requested |
| Resume failed run | `--resume` | Resume a failed run |

### Workflow Selection

Match the user's intent to a workflow from the live list. Common patterns:

| User Intent | Typical Workflow | Branch Pattern |
|-------------|------------------|----------------|
| Fix issue #X | `archon-fix-github-issue` | `fix/issue-{N}` |
| Review PR #X fully | `archon-comprehensive-pr-review` | `review/pr-{N}` |
| Quick review PR #X | `archon-smart-pr-review` | `review/pr-{N}` |
| Validate PR #X | `archon-validate-pr` | `review/pr-{N}` |
| Implement from plan | `archon-feature-development` | `feat/{name}` |
| Plan and implement feature | `archon-idea-to-pr` | `feat/{name}` |
| Execute a plan file | `archon-plan-to-pr` | `feat/{name}` |
| Resolve conflicts | `archon-resolve-conflicts` | `resolve/pr-{N}` |
| Create issue | `archon-create-issue` | `issue/{name}` |
| Safe refactor | `archon-refactor-safely` | `refactor/{name}` |
| Architecture review | `archon-architect` | `review/{name}` |
| Guided dev / PIV loop | `archon-piv-loop` | `piv/{name}` |
| Interactive PRD | `archon-interactive-prd` | `prd/{name}` |
| General help | `archon-assist` | `assist/{description}` |

If no workflow clearly matches, use `archon-assist`.

## Other Useful CLI Commands

```bash
archon workflow list
archon workflow list --json
archon workflow status
archon workflow search <query>
archon workflow install <slug>
archon isolation list
archon isolation cleanup
archon isolation cleanup --merged
archon continue <branch> [message]
archon complete <branch>
archon doctor
archon version
```

## Authoring Quick Start

Archon workflows live in `.archon/workflows/` and command files live in `.archon/commands/`.

### Minimal workflow

```yaml
name: my-workflow
description: What this workflow does
provider: claude
model: sonnet
nodes:
  - id: first-node
    command: my-command
  - id: second-node
    prompt: "Use the output: $first-node.output"
    depends_on: [first-node]
```

### Minimal command file

```markdown
---
description: What this command does
argument-hint: <expected arguments>
---

# My Command

User request: $ARGUMENTS
Workflow artifacts: $ARTIFACTS_DIR
```

For full details, read:

- `references/workflow-dag.md`
- `references/authoring-commands.md`
- `references/variables.md`
- `references/dag-advanced.md`

## Example interactions

**User**: Use Archon to fix issue #42  
**Pi action**:
```bash
archon workflow run archon-fix-github-issue --branch fix/issue-42 "Fix issue #42"
```

**User**: Have Archon review PR #15  
**Pi action**:
```bash
archon workflow run archon-comprehensive-pr-review --branch review/pr-15 "Review PR #15"
```

**User**: Create a workflow that reviews code and runs tests  
Read `references/workflow-dag.md`, then create the workflow under `.archon/workflows/`.

**User**: Write a command file for investigating bugs  
Read `references/authoring-commands.md`, then create the `.md` file under `.archon/commands/`.

**User**: Set up Archon in this repo  
Read `references/repo-init.md`, then create the `.archon/` structure.
