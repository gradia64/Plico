"""Controllo di contenuto dei README tradotti (usato dalla CI, non dal pacchetto).

Confronta ogni variante con il sorgente italiano per sezione e verifica che
non siano spariti pezzi: identificatori di file/script citati, voci di elenco,
linguaggio dei blocchi di codice. Non guarda la prosa — quello resta un lavoro
di lettura — ma è il controllo che avrebbe intercettato una sezione riscritta
con una procedura vecchia, che i conteggi di heading e fence lasciano passare.

Uso: python3 readme-i18n-content.py
Configurazione in cima: SRC, VARIANTS, IGNORE.
"""

import os
import re
import sys

SRC = "README.it.md"
VARIANTS = ["README.md", "README.fr.md", "README.de.md", "README.es.md"]

# Identificatori che possono legittimamente cambiare da lingua a lingua:
# esempi localizzati (`nome.pdf` / `name.pdf`) e simili. Si aggiungono qui,
# non si disattiva il controllo.
IGNORE = set()

CODEISH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
EXT = (".py", ".sh", ".yml", ".yaml", ".toml", ".md", ".ts", ".po", ".1",
       ".desktop", ".xml", ".json", ".sig", ".asc", ".qm", ".deb")


def sections(path):
    """(titolo, righe) per ogni sezione ##, ignorando i blocchi di codice."""
    out, cur, buf, fenced = [], "(introduzione)", [], False
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            out.append((cur, buf))
            cur = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    out.append((cur, buf))
    return out


def identifiers(lines):
    out = set()
    for span in re.findall(r"`([^`\n]+)`", "\n".join(lines)):
        span = span.strip()
        if CODEISH.match(span) and ("/" in span or span.endswith(EXT)):
            out.add(span)
    return out


def bullets(lines):
    return len(re.findall(r"^\s*- ", "\n".join(lines), re.M))


def fences(path):
    """Linguaggio dichiarato da ogni blocco, in ordine di apertura."""
    out, fenced = [], False
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.startswith("```"):
            if not fenced:
                out.append(line[3:].strip())
            fenced = not fenced
    return out


def main():
    if not os.path.exists(SRC):
        print(f"{SRC}: manca")
        return 1
    base = sections(SRC)
    base_fences = fences(SRC)
    errors = []
    for v in VARIANTS:
        if not os.path.exists(v):
            errors.append(f"{v}: manca")
            continue
        var = sections(v)
        if len(var) != len(base):
            errors.append(f"{v}: {len(var)} sezioni ## contro {len(base)} di {SRC}")
            continue
        vf = fences(v)
        if vf != base_fences:
            detail = [(i, a, b) for i, (a, b) in enumerate(zip(base_fences, vf)) if a != b]
            errors.append(
                f"{v}: blocchi di codice dichiarati diversamente: {detail[:3]}"
                + ("" if len(vf) == len(base_fences)
                   else f" ({len(vf)} blocchi contro {len(base_fences)})")
            )
        for (name, a), (_, b) in zip(base, var):
            missing = identifiers(a) - identifiers(b) - IGNORE
            if missing:
                errors.append(f"{v}: sezione «{name}»: mancano {sorted(missing)}")
            if bullets(a) != bullets(b):
                errors.append(
                    f"{v}: sezione «{name}»: {bullets(b)} voci di elenco contro {bullets(a)}"
                )
    if errors:
        print("\n".join(errors))
        return 1
    print(f"OK: identificatori, voci di elenco e blocchi allineati in {len(VARIANTS)} varianti")
    return 0


if __name__ == "__main__":
    sys.exit(main())
