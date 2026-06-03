#!/usr/bin/env python3
"""
Agent script that controls opencode to write code.
Usage: python agent.py <repo_url> [branch]

Workflow:
1. Clone/pull git repository
2. Set up .agent/ directory (gitignored)
3. Read .agent/step.txt to determine current step
4. Execute the step using opencode
5. Advance to next step and repeat until all steps complete

Steps: analyze -> plan -> plan-check -> implement -> review
"""

import os
import sys
import subprocess
from pathlib import Path


STEPS = ["analyze", "plan", "plan-check", "implement", "review"]

STEP_INSTRUCTIONS = {
    "analyze": (
        "Analyze this codebase thoroughly. Look for:\n"
        "- Bugs or potential bugs\n"
        "- Possible enhancements or improvements\n"
        "- TODO comments or missing features\n"
        "- Any technical debt worth addressing\n\n"
        "If you find something significant, do ALL of the following:\n"
        "1. Write a descriptive branch name to .agent/branch.txt "
        "(e.g. fix-login-crash or add-tests-for-api)\n"
        "2. Write a clear description of the finding to .agent/note.txt\n"
        "3. Write 'plan' to .agent/step.txt\n\n"
        "If nothing worth addressing is found, do NOT modify any .agent/ files."
    ),
    "plan": (
        "Read .agent/note.txt to understand the finding to address.\n"
        "Create a detailed implementation plan covering specific files to "
        "modify, changes to make, and order of implementation.\n"
        "Write the plan to .agent/plan.txt\n"
        "After writing the plan, write 'plan-check' to .agent/step.txt."
    ),
    "plan-check": (
        "Review the plan in .agent/plan.txt. Verify it is complete, correct, "
        "and addresses the finding in .agent/note.txt. Check for missing "
        "edge cases, potential issues, and consistency with the codebase. "
        "If .agent/implement-note.txt exists, read it for context on what "
        "went wrong during implementation. If .agent/review.txt exists, "
        "read it for review feedback. "
        "Write your review to .agent/plan-check.txt\n"
        "If the plan needs changes, write 'plan' to .agent/step.txt so it "
        "can be revised.\n"
        "If the plan is good to go, write 'implement' to .agent/step.txt."
    ),
    "implement": (
        "Read .agent/plan.txt and .agent/note.txt. Implement the changes "
        "described in the plan. Make all necessary modifications to the "
        "codebase. After implementation, write a summary to "
        ".agent/implement-note.txt describing what was changed and any issues.\n"
        "If implementation succeeded, write 'review' to .agent/step.txt.\n"
        "If implementation failed or had issues, write 'plan-check' to "
        ".agent/step.txt to request a re-plan."
    ),
    "review": (
        "Review the implementation by comparing changes with the plan in "
        ".agent/plan.txt. Verify all planned changes were implemented "
        "correctly. Check for bugs, style issues, and test coverage. "
        "Write your review to .agent/review.txt\n"
        "If review passes, write 'done' to .agent/step.txt.\n"
        "If issues found, write 'implement' or 'plan-check' to "
        ".agent/step.txt to fix or re-plan."
    ),
}


def run(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(result.stderr)
        sys.exit(1)
    return result.stdout.strip()


def setup(repo_path):
    agent_dir = repo_path / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    gitignore = repo_path / ".gitignore"
    content = gitignore.read_text() if gitignore.exists() else ""
    if ".agent/" not in content:
        with open(gitignore, "a") as f:
            f.write("\n# Agent working directory\n.agent/\n")

    return agent_dir


def get_step(agent_dir):
    step_file = agent_dir / "step.txt"
    if not step_file.exists():
        return None
    step = step_file.read_text().strip()
    if step not in STEPS and step != "done":
        print(f"Unknown step: {step}")
        sys.exit(1)
    return step


def set_step(agent_dir, step):
    (agent_dir / "step.txt").write_text(step)


def run_opencode(repo_path, instruction, step):
    prompt_file = repo_path / ".agent" / f"{step}_prompt.txt"
    prompt_file.write_text(instruction)

    print(f"\n{'='*60}")
    print(f"  Step: {step}")
    print(f"{'='*60}")

    cmd = f'opencode --yes "{instruction}"'
    result = subprocess.run(
        cmd, shell=True, cwd=str(repo_path), capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Step '{step}' failed (exit code: {result.returncode})")
        out = result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout
        err = result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr
        print(out)
        print(err)
        return False
    return True


def advance_step(agent_dir, step):
    idx = STEPS.index(step)
    if idx + 1 < len(STEPS):
        next_step = STEPS[idx + 1]
        set_step(agent_dir, next_step)
        print(f"Advanced to step: {next_step}")
        return next_step
    else:
        set_step(agent_dir, "done")
        print("All steps completed!")
        return "done"


def main():
    if len(sys.argv) < 2:
        print("Usage: agent.py <repo_url> [branch]")
        sys.exit(1)

    repo_url = sys.argv[1]
    branch = sys.argv[2] if len(sys.argv) > 2 else None

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    workspace = Path.cwd() / "workspace"
    workspace.mkdir(exist_ok=True)
    repo_path = workspace / repo_name

    if not repo_path.exists():
        print(f"Cloning {repo_url}...")
        cmd = f"git clone {repo_url}"
        if branch:
            cmd += f" -b {branch}"
        run(cmd, cwd=str(workspace))
    else:
        print(f"Updating {repo_name}...")
        run("git pull --ff-only", cwd=str(repo_path))

    agent_dir = setup(repo_path)
    original_branch = run("git rev-parse --abbrev-ref HEAD", cwd=str(repo_path))
    step = get_step(agent_dir)

    if step is None:
        step = STEPS[0]
        set_step(agent_dir, step)
        print(f"Starting with step: {step}")
    elif step == "done":
        print("All steps complete. Delete .agent/step.txt to restart.")
        return

    while step and step != "done":
        instruction = STEP_INSTRUCTIONS[step]
        ok = run_opencode(repo_path, instruction, step)
        if not ok:
            sys.exit(1)

        if step == "analyze":
            branch_file = agent_dir / "branch.txt"
            if branch_file.exists():
                branch_name = branch_file.read_text().strip()
                branch_file.unlink()
                print(f"Creating and switching to branch: {branch_name}")
                run(f"git checkout -b {branch_name}", cwd=str(repo_path))
            new_step = get_step(agent_dir)
            if new_step == step or new_step is None:
                set_step(agent_dir, "done")
                step = "done"
                print("No issues found. Nothing to do.")
            else:
                step = new_step
        elif step in ("plan", "plan-check", "implement", "review"):
            new_step = get_step(agent_dir)
            expected = {"plan": "plan-check", "plan-check": ("plan", "implement"), "implement": ("plan-check", "review"), "review": ("implement", "plan-check", "done")}
            if new_step == step or new_step is None:
                fallback = expected[step] if isinstance(expected[step], str) else expected[step][0]
                print(f"Agent did not advance from {step}, defaulting to {fallback}")
                set_step(agent_dir, fallback)
                step = fallback
            else:
                print(f"After {step}, agent set next step to: {new_step}")
                step = new_step
        else:
            step = advance_step(agent_dir, step)

    current_branch = run("git rev-parse --abbrev-ref HEAD", cwd=str(repo_path))
    if current_branch != original_branch:
        print(f"Committing and pushing branch: {current_branch}")
        note_file = agent_dir / "note.txt"
        msg = "Agent changes"
        if note_file.exists():
            msg = note_file.read_text().strip()[:72]
        run("git add -A", cwd=str(repo_path))
        run(f'git commit -m "{msg}"', cwd=str(repo_path))
        run(f"git push origin {current_branch}", cwd=str(repo_path))
        print(f"Switching back to: {original_branch}")
        run(f"git checkout {original_branch}", cwd=str(repo_path))
    print("\nAll steps completed successfully!")


if __name__ == "__main__":
    main()
