import subprocess, sys, os

results = []

def run(label, cmd):
    r = subprocess.run(
        ["powershell", "-Command", cmd],
        capture_output=True, text=True
    )
    results.append({
        "check": label,
        "output": r.stdout.strip(),
        "error": r.stderr.strip(),
        "code": r.returncode
    })

# FIX 1: Worker comment added
run("detection worker ownership comment",
    "Select-String -Path backend/app/detection/worker.py "
    "-Pattern 'Redis Key Ownership|DOES NOT WRITE|observation:logs' "
    "| ForEach-Object { $_.ToString() }")

# FIX 2: failure_tag consistency
run("backend escalation failure field name",
    "Select-String -Path backend/app/healing/verification_worker.py "
    "-Pattern 'failure_type|failure_tag' "
    "| ForEach-Object { $_.ToString() }")

run("frontend escalation failure field name",
    "Select-String -Path frontend/src/designSystem.ts "
    "-Pattern 'failure_type|failure_tag' "
    "| ForEach-Object { $_.ToString() }")

run("all frontend failure field references",
    "Get-ChildItem -Recurse frontend/src -Include *.ts,*.tsx "
    "| Select-String -Pattern 'failure_type|failure_tag' "
    "| ForEach-Object { $_.ToString() }")

# FIX 3: Dead files deleted
run("dead files deleted",
    "foreach($f in @("
    "'backend/app/observation/store.py',"
    "'backend/app/observation/schemas.py',"
    "'backend/app/db/models.py',"
    "'backend/app/db/session.py',"
    "'backend/niramay.db',"
    "'backend/app/verify_system.py',"
    ")) { if(Test-Path $f) { echo STILL_EXISTS:$f } else { echo DELETED:$f } }")

run("no imports from deleted files",
    "Get-ChildItem -Recurse backend/app -Include *.py "
    "| Select-String -Pattern "
    "'from app\\.observation\\.store|from app\\.observation\\.schemas|from app\\.db|from app\\.verify_system' "
    "| ForEach-Object { $_.ToString() }; "
    "if(-not $?) { echo NONE_FOUND }")

# GITIGNORE
run("gitignore exists and covers key patterns",
    "Select-String -Path .gitignore -Pattern '\\*.db|node_modules|__pycache__|.env' "
    "| Measure-Object | Select-Object -ExpandProperty Count")

run("gitignore covers niramay.db",
    "Select-String -Path .gitignore -Pattern 'niramay.db' "
    "| ForEach-Object { $_.ToString() }")

# README
run("readme exists",
    "if(Test-Path README.md) { echo EXISTS } else { echo NOT_FOUND }")

run("readme key sections present",
    "Select-String -Path README.md "
    "-Pattern 'Architecture|Tech Stack|Getting Started|API Endpoints|Detection Engines|Redis Keys' "
    "| Measure-Object | Select-Object -ExpandProperty Count")

# NO REGRESSIONS: confirm still no sqlite
run("still no sqlite in active code",
    "Get-ChildItem -Recurse backend/app/api,backend/app/detection,"
    "backend/app/healing,backend/app/ingestion -Include *.py "
    "| Select-String -Pattern 'from app\\.db|sqlalchemy|get_db|db\\.query' "
    "| ForEach-Object { $_.ToString() }; "
    "if(-not $?) { echo NONE_FOUND }")

# NO REGRESSIONS: detection index still pure
run("detection index still pure function",
    "$m = Select-String -Path backend/app/detection/index.py "
    "-Pattern 'redis|opensearch|sqlite|lpush|rpush|write_' "
    "| Where-Object { $_.Line -notmatch '^\\s*#' -and $_.Line -notmatch '\"\"\"' -and $_.Line -notmatch \"'''\" }; "
    "if($m) { $m | ForEach-Object { $_.ToString() } } else { echo PURE_CONFIRMED }")

# CONFIRM: middleware deleted, no rabbitmq publishing from Niramay
run("middleware deleted confirmed",
    "if(Test-Path backend/app/observation/middleware.py) "
    "{ echo STILL_EXISTS } else { echo DELETED_CONFIRMED }")

run("no rabbitmq_publisher in active code",
    "Get-ChildItem -Recurse backend/app -Include *.py "
    "| Select-String -Pattern 'rabbitmq_publisher' "
    "| ForEach-Object { $_.ToString() }; "
    "if(-not $?) { echo NONE_FOUND }")

# FULL TEST SUITE
run("full test suite after all changes",
    "Set-Location backend; python test_imports.py 2>&1")

# PROJECT STRUCTURE FINAL
run("final project structure",
    "Get-ChildItem -Recurse -File backend/app -Include *.py "
    "| Where-Object { $_.FullName -notmatch '__pycache__' } "
    "| ForEach-Object { $_.FullName.Replace((Get-Location).Path + '\\', '') } "
    "| Sort-Object")

# PRINT REPORT
print("=" * 60)
print("NIRAMAY FINAL CLEANUP VERIFICATION REPORT")
print("=" * 60)
for r in results:
    print(f"\n>>> {r['check'].upper()}")
    print("-" * 40)
    if r['output']:
        print(r['output'])
    if r['error']:
        print(f"STDERR: {r['error'][:300]}")
    if not r['output'] and not r['error']:
        print("(no output)")
print("\n" + "=" * 60)
print("END OF REPORT - PASTE THIS OUTPUT FOR REVIEW")
print("=" * 60)
