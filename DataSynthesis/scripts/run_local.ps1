param(
  [string]$Workflow = "workflows/text_synthesis.yaml"
)

python -m synthesis_engine.cli.main validate -c $Workflow
python -m synthesis_engine.cli.main run -c $Workflow
