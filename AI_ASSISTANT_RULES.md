# AI Assistant Development Rules

This document contains rules and best practices for AI assistants working on this codebase.

## Git Commands

### Always Push in a Single Command (PowerShell)

**Rule**: When pushing changes to git, always use a single command with PowerShell syntax.

**Why**: PowerShell doesn't support `&&` for chaining commands. Use semicolons (`;`) instead.

**Correct Syntax**:
```powershell
git add file1.py file2.py; git commit -m "Commit message"; git push
```

**Incorrect Syntax** (will fail in PowerShell):
```bash
git add file1.py file2.py && git commit -m "Commit message" && git push
```

**Example**:
```powershell
git add accounting/utils.py accounting/views.py multitenancy/tasks.py; git commit -m "Improve OFX import to combine NAME and MEMO fields into description; Fix execute_import_job to accept lookup_cache parameter"; git push
```

**Note**: The shell environment is PowerShell on Windows, so always use semicolons (`;`) to chain commands, not `&&`.

