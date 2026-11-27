import subprocess
import sys

APP_MODULES = (
    "orgbrain.api",
    "orgbrain.worker",
    "orgbrain.mcp_server",
    "orgbrain.slack.bot",
    "orgbrain.connectors.folder",
    "orgbrain.cli",
)


def test_app_modules_do_not_import_torch():
    out = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", "import " + ", ".join(APP_MODULES)],
        capture_output=True,
        text=True,
        check=True,
    )
    imported = {line.rsplit("|", 1)[-1].strip() for line in out.stderr.splitlines() if "|" in line}
    top = {name.split(".")[0] for name in imported}
    assert "torch" not in top
    assert "sentence_transformers" not in top
