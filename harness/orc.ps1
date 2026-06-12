#!/usr/bin/env pwsh
# Thin alias for the orchestrate harness: orc validate brief.md, orc dispatch ..., etc.
python "$PSScriptRoot\orchestrate_run.py" @args
exit $LASTEXITCODE
