"""Archon workflow YAML generation for skills.

This module provides template-based YAML generation that the agent
(can call via API) uses to create new, valid Archon workflow files.
The generated YAML follows the pattern established by borg-nanoprobe.yaml
and borg-queen.yaml.
"""

from typing import Optional


# Base template for skill-generated workflows
# Follows borg-nanoprobe.yaml structure: init -> execute -> record pattern
_SKILL_WORKFLOW_TEMPLATE = """name: {name}
description: |
  {description}
provider: pi
model: {model}
worktree:
  enabled: true

nodes:
  - id: init
    bash: |
      mkdir -p "$ARTIFACTS_DIR/input" "$ARTIFACTS_DIR/output" "$ARTIFACTS_DIR/state" "$ARTIFACTS_DIR/review"

  - id: discover
    depends_on: [init]
    context: fresh
    provider: pi
    model: {discovery_model}
    prompt: |
      You are executing the skill "{name}".
      Category: {category}
      Tags: {tags}

      DISCOVERY PHASE:
      1. Read any input from $ARTIFACTS_DIR/input/
      2. Understand the scope and requirements
      3. Identify what needs to be done
      4. Write your discovery plan to $ARTIFACTS_DIR/state/plan.md

    output_format:
      type: object
      properties:
        scope: {{ type: string }}
        steps: {{ type: array, items: {{ type: string }} }}
        estimated_complexity: {{ type: string, enum: ["simple", "moderate", "complex"] }}

  - id: execute
    depends_on: [discover]
    context: fresh
    provider: pi
    model: {model}
    prompt: |
      You are executing the skill "{name}".

      EXECUTION PHASE:
      Follow the plan from $ARTIFACTS_DIR/state/plan.md.
      {execution_instructions}

      Use the artifacts directory to pass data between steps.
      Write results to $ARTIFACTS_DIR/output/.
      Log progress to $ARTIFACTS_DIR/state/execution.log.

    output_format:
      type: object
      properties:
        status: {{ type: string, enum: ["success", "failed", "needs-review"] }}
        summary: {{ type: string }}
        artifacts: {{ type: array, items: {{ type: string }} }}
        issues_found: {{ type: array, items: {{ type: string }}, default: [] }}

  - id: review
    depends_on: [execute]
    context: fresh
    provider: pi
    model: {review_model}
    when: "$execute.output.status == 'needs-review' or $execute.output.issues_found | length > 0"
    prompt: |
      REVIEW PHASE for skill "{name}":
      1. Review the execution results in $ARTIFACTS_DIR/output/
      2. Check for issues listed in $execute.output.issues_found
      3. Validate the output quality
      4. Write review findings to $ARTIFACTS_DIR/review/findings.md

    output_format:
      type: object
      properties:
        verdict: {{ type: string, enum: ["PASS", "FAIL", "NEEDS_FIX"] }}
        critical_findings: {{ type: array, items: {{ type: string }}, default: [] }}
        suggestions: {{ type: array, items: {{ type: string }}, default: [] }}

  - id: fix
    depends_on: [review]
    context: fresh
    provider: pi
    model: {model}
    when: "$review.output.verdict == 'NEEDS_FIX'"
    prompt: |
      FIX PHASE for skill "{name}":
      1. Read review findings from $ARTIFACTS_DIR/review/findings.md
      2. Fix all CRITICAL and HIGH findings
      3. Fix MEDIUM findings when straightforward
      4. Write fixes to $ARTIFACTS_DIR/output/

  - id: record
    depends_on: [fix, review]
    bash: |
      # Record execution metadata
      echo "Skill {name} completed at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$ARTIFACTS_DIR/state/execution.log"
      echo "Category: {category}" >> "$ARTIFACTS_DIR/state/execution.log"
      echo "Tags: {tags}" >> "$ARTIFACTS_DIR/state/execution.log"
"""


def generate_skill_yaml(
    name: str,
    description: str,
    model: str = "lm-studio/qwen/qwen3.6-35b-a3b-mtp",
    discovery_model: str = "lm-studio/qwen/qwen3.5-9b",
    review_model: str = "lm-studio/qwen/qwen3.5-9b",
    category: str = "general",
    tags: list[str] | None = None,
    execution_instructions: str = "",
) -> str:
    """Generate a complete Archon workflow YAML for a skill.

    Args:
        name: Skill name (used as workflow name and file name)
        description: What the skill does
        model: Primary model for execution nodes
        discovery_model: Model for discovery/planning nodes (smaller/faster)
        review_model: Model for review nodes
        category: Human-readable category
        tags: Skill tags
        execution_instructions: Additional instructions for the execute node

    Returns:
        Complete YAML string ready to write to .archon/workflows/{name}.yaml
    """
    if tags is None:
        tags = []

    tags_str = ", ".join(tags) if tags else "auto"

    return _SKILL_WORKFLOW_TEMPLATE.format(
        name=name,
        description=description,
        model=model,
        discovery_model=discovery_model,
        review_model=review_model,
        category=category,
        tags=tags_str,
        execution_instructions=execution_instructions or "Execute the skill as described.",
    )


def validate_generated_yaml(yaml_content: str) -> tuple[bool, list[str]]:
    """Validate that generated YAML content is structurally sound.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    try:
        import yaml
    except ImportError:
        return False, ["PyYAML not installed"]

    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return False, [f"YAML parse error: {e}"]

    if not isinstance(parsed, dict):
        return False, ["Root element must be a mapping"]

    # Required fields
    for field in ("name", "nodes"):
        if field not in parsed:
            errors.append(f"Missing required field: {field}")

    # Name must match filename convention
    name = parsed.get("name", "")
    if name and (not name.replace("-", "").replace("_", "").isalnum()):
        errors.append(f"Invalid workflow name: {name} (use alphanumeric, hyphens, underscores)")

    # Nodes must be a list
    nodes = parsed.get("nodes", [])
    if not isinstance(nodes, list):
        errors.append("Nodes must be a list")
    elif len(nodes) == 0:
        errors.append("At least one node is required")
    else:
        # First node should not have depends_on (or depend on nothing)
        first_node = nodes[0]
        if "depends_on" in first_node:
            errors.append("First node should not have depends_on")

        # Check each node has id
        for i, node in enumerate(nodes):
            if "id" not in node:
                errors.append(f"Node {i} missing 'id' field")

    return len(errors) == 0, errors


def generate_self_improvement_workflow() -> str:
    """Generate a self-improvement workflow template.

    This workflow enables the agent to:
    1. Analyze its own performance (review ActionMemory)
    2. Identify patterns and gaps
    3. Create new skills to fill those gaps
    4. Update existing skills based on feedback

    Returns:
        YAML string for the self-improvement workflow
    """
    return """name: borgos-self-improvement
description: |
  Self-improvement workflow: Analyze execution history, identify patterns,
  create or update skills, and record lessons learned.
  Runs as a heartbeat turn to give BorgOS proactive self-improvement capability.
provider: pi
model: lm-studio/qwen/qwen3.6-35b-a3b-mtp
worktree:
  enabled: true

nodes:
  - id: init
    bash: |
      mkdir -p "$ARTIFACTS_DIR/analysis" "$ARTIFACTS_DIR/skills" "$ARTIFACTS_DIR/notes"

  - id: analyze-performance
    depends_on: [init]
    context: fresh
    provider: pi
    model: lm-studio/qwen/qwen3.6-35b-a3b-mtp
    prompt: |
      ANALYSIS PHASE — Self-Improvement for BorgOS:

      1. Review recent execution patterns (check $ARTIFACTS_DIR for prior data)
      2. Identify recurring failures, bottlenecks, or gaps in capabilities
      3. Look for opportunities to create new skills or improve existing ones
      4. Consider: What tasks does the user ask about most? What fails most often?

      Write your analysis to $ARTIFACTS_DIR/analysis/findings.md
      Include:
      - Top 3 recurring issues
      - Top 3 capability gaps
      - Recommended actions (create skill, update skill, fix process)

    output_format:
      type: object
      properties:
        recurring_issues: { type: array, items: { type: string }, default: [] }
        capability_gaps: { type: array, items: { type: string }, default: [] }
        recommended_actions: { type: array, items: { type: string }, default: [] }

  - id: create-skills
    depends_on: [analyze-performance]
    context: fresh
    provider: pi
    model: lm-studio/qwen/qwen3.6-35b-a3b-mtp
    when: "$analyze-performance.output.recommended_actions | length > 0"
    prompt: |
      SKILL CREATION PHASE:

      Based on the analysis findings, create new skills to fill identified gaps.
      For each recommended action that involves creating a new skill:
      1. Design the skill (name, description, model, tags, category)
      2. Generate the Archon workflow YAML
      3. Write the YAML to $ARTIFACTS_DIR/skills/{skill_name}.yaml
      4. Document the new skill in $ARTIFACTS_DIR/analysis/new-skills.md

  - id: create-notes
    depends_on: [analyze-performance]
    context: fresh
    provider: pi
    model: lm-studio/qwen/qwen3.5-9b
    prompt: |
      NOTE CREATION PHASE:

      Create a concise summary note from the analysis findings.
      Write to $ARTIFACTS_DIR/notes/self-improvement-$(date +%Y-%m-%d).md

      Include:
      - Date and time
      - Key findings (top 3 issues, top 3 gaps)
      - Actions taken (new skills created, existing skills updated)
      - Lessons learned
      - Recommendations for next heartbeat

  - id: summarize
    depends_on: [create-skills, create-notes]
    context: fresh
    provider: pi
    model: lm-studio/qwen/qwen3.5-9b
    prompt: |
      FINAL SUMMARY for BorgOS self-improvement run.

      Read the outputs from previous nodes and create a concise summary.
      Write to $ARTIFACTS_DIR/summary.md

      The summary should be actionable — what should BorgOS do next time?
    output_format:
      type: object
      properties:
        summary: { type: string }
        next_actions: { type: array, items: { type: string }, default: [] }
"""
