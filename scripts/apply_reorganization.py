"""Runner temporário da recuperação completa do Prospector."""
from pathlib import Path
import base64
import zlib

HERE = Path(__file__).resolve().parent
payload = "".join((HERE / f".reorg_payload_{i}").read_text(encoding="utf-8").strip() for i in range(6))
source = zlib.decompress(base64.b64decode(payload)).decode("utf-8")
exec(compile(source, "scripts/reorganize_complete.py", "exec"), globals(), globals())

# A transformação restaurou a CI definitiva. Remove todo o mecanismo temporário
# no mesmo commit para que ele nunca faça parte da main nem rode novamente.
for i in range(6):
    (HERE / f".reorg_payload_{i}").unlink(missing_ok=True)
(Path(__file__).resolve().parents[1] / ".github" / "workflows" / "apply-reorganization.yml").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
