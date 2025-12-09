# Git Commands - PowerShell Syntax

**CRITICAL**: Always push changes in a single command using PowerShell syntax.

- PowerShell does NOT support `&&` for chaining commands
- Use semicolons (`;`) to chain commands instead
- The shell environment is PowerShell on Windows

**Correct Syntax**:
```powershell
git add file1.py file2.py; git commit -m "Commit message"; git push
```

**Incorrect Syntax** (will fail):
```bash
git add file1.py file2.py && git commit -m "Commit message" && git push
```

**Example**:
```powershell
git add accounting/utils.py accounting/views.py multitenancy/tasks.py; git commit -m "Description of changes"; git push
```

**Rule**: When the user asks to "push" or "commit and push", always use the PowerShell semicolon syntax in a single command.

