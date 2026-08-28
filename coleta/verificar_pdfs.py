import sqlite3, hashlib
from pathlib import Path

con = sqlite3.connect("file:acervo.db?mode=ro", uri=True)
linhas = con.execute(
    "SELECT arquivo, sha256 FROM edicao WHERE sha256 IS NOT NULL").fetchall()
print(f"conferindo {len(linhas)} PDFs contra o sha256 gravado no banco", flush=True)

ruins, ausentes, erros = [], [], []
for i, (arquivo, esperado) in enumerate(linhas, 1):
    caminho = Path(arquivo)
    if not caminho.exists():
        ausentes.append(arquivo)
        continue
    try:
        digestor = hashlib.sha256()
        with caminho.open("rb") as fluxo:
            for bloco in iter(lambda: fluxo.read(4 << 20), b""):
                digestor.update(bloco)
        if digestor.hexdigest() != esperado:
            ruins.append(arquivo)
    except Exception as exc:
        erros.append(f"{arquivo}: {str(exc)[:70]}")
    if i % 500 == 0:
        print(f"  {i}/{len(linhas)}", flush=True)

print(f"RESULTADO: {len(linhas)} conferidos | {len(ruins)} hash diferente | "
      f"{len(ausentes)} ausentes | {len(erros)} erro de leitura")
for x in (ruins + ausentes + erros)[:10]:
    print("   ", x)
