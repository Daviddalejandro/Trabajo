"""Genera MDM_Prototipo_Colab.ipynb (cuaderno autocontenido para Google Colab).
Se mantiene como script para que el cuaderno sea reproducible y revisable en Git:
    python colab/build_notebook.py
"""
import json
from pathlib import Path

OUT = Path(__file__).with_name("MDM_Prototipo_Colab.ipynb")

cells: list[dict] = []


def md(text: str) -> None:
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")})


def code(text: str) -> None:
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.strip("\n")})


md("""
# Prototipo MDM/RDM Party · Colsubsidio — ejecución en Google Colab

Este cuaderno levanta el prototipo completo en una máquina temporal de Google (PostgreSQL 16 + API + consola web)
y le entrega un **enlace para abrir la consola en su navegador** mientras el cuaderno esté en ejecución.
No instala nada en su computador. Todos los datos son **sintéticos**.

**Cómo usarlo:** menú *Entorno de ejecución → Ejecutar todo* (o `Ctrl+F9`). Tarda entre 3 y 5 minutos.
Al final de la sección 5 aparece el enlace a la consola. Las secciones 6 y 7 son opcionales (pruebas guiadas
por código y guardado de resultados en Drive).

> Cuando cierre el cuaderno o Colab se desconecte por inactividad, la máquina temporal se borra.
> Lo que quiera conservar se guarda en Drive con la sección 7.
""")

md("## 1 · Parámetros")
code('''
#@title Origen del código y conjunto de datos { display-mode: "form" }
#@markdown **Origen del código.** `github`: clona el repositorio público (recomendado: siempre trae la última versión de la rama).
#@markdown `drive`: usa un zip guardado en su Drive (`make zip-colab`), útil si el repositorio pasa a ser privado o no hay acceso a GitHub.
ORIGEN = "github"  #@param ["github", "drive"]
ZIP_EN_DRIVE = "MDM_RDM_Prototipo/08_Colab/mdm-rdm-prototype.zip"  #@param {type:"string"}
GITHUB_REPO = "https://github.com/Daviddalejandro/Trabajo.git"  #@param {type:"string"}
GITHUB_RAMA = "claude/pensive-ptolemy-bg3ikj"  #@param {type:"string"}
GITHUB_TOKEN = ""  #@param {type:"string"}
#@markdown **Conjunto de datos inicial.** `validacion`: SAP ECC + sistema de crédito (zona gris V2, V18, V3).
#@markdown `demo`: los 21 casos A–U de la especificación (deja B, K y U en la consola).
CONJUNTO = "validacion"  #@param ["validacion", "demo"]
#@markdown **Carpeta de Drive** donde se guardan los resultados de la sección 7.
CARPETA_RESULTADOS = "MDM_RDM_Prototipo/08_Colab/resultados"  #@param {type:"string"}
print("Parámetros listos.")
''')

md("## 2 · Google Drive y código del prototipo")
code('''
import os, subprocess, shutil, sys, time, pathlib
from google.colab import drive
drive.mount("/content/drive", force_remount=False)

os.chdir("/content")                     # nunca borrar la carpeta en la que estamos parados (reejecución de la celda)
RAIZ = pathlib.Path("/content/mdm")
if RAIZ.exists():
    shutil.rmtree(RAIZ)
RAIZ.mkdir(parents=True)

if ORIGEN == "drive":
    zip_path = pathlib.Path("/content/drive/MyDrive") / ZIP_EN_DRIVE
    assert zip_path.exists(), f"No encuentro el zip en Drive: {zip_path}"
    subprocess.run(["unzip", "-q", str(zip_path), "-d", str(RAIZ)], check=True)
else:
    url = GITHUB_REPO
    if GITHUB_TOKEN:
        url = url.replace("https://", f"https://{GITHUB_TOKEN}@")
    r = subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", GITHUB_RAMA, url, str(RAIZ / "repo")],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("git clone falló: " + r.stderr.strip()[-1500:])
    shutil.move(str(RAIZ / "repo" / "mdm-rdm-prototype"), str(RAIZ / "mdm-rdm-prototype"))

PROTO = next(RAIZ.rglob("mdm-rdm-prototype"))
BACKEND = PROTO / "backend"
os.chdir(BACKEND)
print("Código listo en", PROTO)
print("Migraciones:", sorted(p.name for p in (BACKEND / "alembic" / "versions").glob("*.py")))
''')

md("## 3 · PostgreSQL 16 y dependencias de Python (2–3 minutos)")
code('''
%%bash
set -e
export DEBIAN_FRONTEND=noninteractive
if [ ! -x /usr/lib/postgresql/16/bin/pg_ctl ]; then
  apt-get -qq update >/dev/null
  apt-get -qq install -y postgresql-common >/dev/null 2>&1
  /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y >/dev/null 2>&1 || true
  apt-get -qq update >/dev/null
  apt-get -qq install -y postgresql-16 >/dev/null 2>&1 || apt-get -qq install -y postgresql >/dev/null 2>&1
fi
service postgresql stop >/dev/null 2>&1 || true   # el clúster por defecto (5432) no se usa; el prototipo crea el suyo en 5433
ls -d /usr/lib/postgresql/*/bin
''')
code('''
import subprocess, sys, glob
PGBIN = sorted(glob.glob("/usr/lib/postgresql/*/bin"))[-1]
print("PostgreSQL:", PGBIN)
r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], capture_output=True, text=True)
print("Dependencias Python instaladas." if r.returncode == 0 else r.stderr[-2000:])
''')

md("## 4 · Base de datos, catálogos RDM y datos sintéticos")
code('''
import os, subprocess, sys
ENV = dict(os.environ, PGBIN=PGBIN, PGDATA_LOCAL="/content/pgdata",
           DATABASE_URL="postgresql+psycopg://mdm@127.0.0.1:5433/mdm_prototype",
           UI_DIST_DIR=str(PROTO / "colab" / "ui"), PYTHONUNBUFFERED="1")

def sh(*args, check=True):
    r = subprocess.run(list(args), env=ENV, capture_output=True, text=True)
    print(r.stdout[-4000:], r.stderr[-1500:] if r.returncode else "", sep="")
    if check and r.returncode:
        raise SystemExit(f"Falló: {' '.join(args)}")
    return r

sh("bash", str(PROTO / "scripts" / "db_local.sh"), "start")
sh(sys.executable, "-m", "alembic", "upgrade", "head")   # crea los esquemas rdm, mdm y staging
sh(sys.executable, "cli.py", "db-check")                 # verifica conexión y esquemas (después de migrar)
sh(sys.executable, "cli.py", "rdm-seed")
if CONJUNTO == "demo":
    sh(sys.executable, "cli.py", "demo")
else:
    sh(sys.executable, "cli.py", "validation-load")
''')

md("""
## 5 · Consola web

La API sirve la consola compilada en el mismo puerto. El enlace de abajo funciona **solo para usted** y
**mientras este cuaderno esté en ejecución**. Ábralo en una pestaña nueva; también se muestra embebido.
""")
code('''
import subprocess, time, urllib.request, os
API_LOG = open("/content/api.log", "w")
API_PROC = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
                       env=ENV, stdout=API_LOG, stderr=subprocess.STDOUT, cwd=str(BACKEND))
for _ in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2); break
    except Exception:
        time.sleep(1)
else:
    print(open("/content/api.log").read()[-3000:]); raise SystemExit("La API no arrancó")

from google.colab import output
URL = output.eval_js("google.colab.kernel.proxyPort(8000)")
print("Consola de Stewardship:", URL + "#/stewardship")
print("Tablero:", URL + "#/")
print("Política de matching (grupos, umbrales, vetos; simular y publicar como JEFATURA):", URL + "#/matching")
print("Modelo relacional, cargas masivas/transaccionales y buckets:", URL + "#/modelo")
print("Swagger de la API:", URL + "docs")
from IPython.display import HTML, display
display(HTML(f'<p style="font-size:1.1em"><a href="{URL}#/stewardship" target="_blank">🔗 Abrir la consola en una pestaña nueva</a></p>'))
output.serve_kernel_port_as_iframe(8000, path="/#/stewardship", height=900)
''')

md("""
## 6 · Pruebas guiadas por código (opcional)

Las mismas acciones de la consola, desde Python, para dejar un registro reproducible. La cabecera `X-Actor`
identifica quién decide (regla dura 3.12: toda decisión lleva justificación y queda auditada).
""")
code('''
import json, urllib.request, urllib.parse
import pandas as pd
from IPython.display import display

BASE = "http://127.0.0.1:8000/api/v1"

def api(path, method="GET", body=None, actor="steward.mdm", role="STEWARD", **params):
    q = {k: v for k, v in params.items() if v is not None}
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Actor": actor, "X-Role": role})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": json.loads(e.read() or b"{}")}

def cola(decision=None):
    items = api("/matches", decision=decision, status="PENDING", limit=200)
    items = items.get("items", items) if isinstance(items, dict) else items
    df = pd.DataFrame([{"par": m["match_sk"], "score": m["total_score"], "decision": m["decision"], "estado": m["match_status"],
                        "A": m.get("party_a_sk"), "B": m.get("party_b_sk")} for m in items])
    display(df); return df

def detalle(match_sk):
    m = api(f"/matches/{match_sk}")
    b = m.get("decision_basis") or {}
    print(f"Par #{m['match_sk']} · evidencia {m['total_score']} % sobre cobertura {b.get('coverage', '?')} % · {m['decision']} · {m['match_status']}"
          f" · decidido por {b.get('decided_by', 'reglas v1')} (política v{b.get('policy_version', '?')})")
    cols = ["attribute", "state", "points", "weight", "value_a", "value_b", "algorithm", "similarity"]
    df = pd.DataFrame(m["score_detail"]); display(df[[c for c in cols if c in df.columns]])
    display(pd.DataFrame(m["sources"]))
    return m

def decidir(match_sk, decision, justificacion, actor="steward.mdm", role="STEWARD"):
    """decision: MERGE | NO_MATCH | ESCALATE"""
    r = api(f"/matches/{match_sk}/decision", "POST", {"action": decision, "justification": justificacion}, actor=actor, role=role)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1500]); return r

def tareas(actor):
    t = api("/review-tasks", actor=actor, assignee=actor, status="RECEIVED")
    display(pd.DataFrame(t)); return t

def decidir_tarea(task_sk, decision, justificacion, actor):
    r = api(f"/review-tasks/{task_sk}/decision", "POST", {"decision": decision, "justification": justificacion}, actor=actor)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1500]); return r

def vista360(party_sk):
    p = api(f"/parties/{party_sk}/golden")
    print(json.dumps({k: p[k] for k in list(p)[:12]}, ensure_ascii=False, indent=1)[:3000]); return p

def politica(entity="PERSON"):
    """Política de decisión v2 activa (SPEC §8.4 bis): grupos de suficiencia, umbrales sobre evidencia, vetos."""
    r = api("/matching/policy", entity=entity)
    print(f"{entity} · política v{r['active']['version']} · versiones {[v['version'] for v in r['versions']]}")
    print(json.dumps(r["active"]["params"], ensure_ascii=False, indent=1)[:4000]); return r

def simular_politica(params, entity="PERSON", scope="pending"):
    """Qué cambiaría en la cola (o en todos los pares) con otra política, sin persistir nada."""
    r = api("/matching/policy/simulate", "POST", {"entity": entity, "params": params, "scope": scope})
    print(json.dumps(r.get("summary", r), ensure_ascii=False, indent=1)[:3000]); return r

def publicar_politica(params, nota, entity="PERSON"):
    """Solo JEFATURA: crea la versión N+1 (la anterior queda inmutable, regla dura 3.7) y recalcula la cola."""
    r = api("/matching/policy", "POST", {"entity": entity, "params": params, "note": nota}, actor="jefatura.gd", role="JEFATURA")
    print(json.dumps(r, ensure_ascii=False, indent=1)[:2000])
    print(json.dumps(api("/matching/recalculate", "POST", actor="jefatura.gd", role="JEFATURA", entity=entity), ensure_ascii=False, indent=1)[:3000]); return r

def match_preview(**datos):
    """Ej.: match_preview(party_type="PERSON", first_name="Ana", first_surname="Rangel", birth_date="1953-03-14",
              identifiers=[{"id_type": "CC", "id_number": "948298165"}], emails=["ana@x.test"], phones=["+573001234567"])"""
    r = api("/parties/match-preview", "POST", datos)
    print(json.dumps(r, ensure_ascii=False, indent=1)[:4000]); return r

print("Zona gris actual:")
cola()
''')
code('''
#@title Ejemplo · decidir un par de la zona gris con dos owners (caso V2 del conjunto de validación)
PAR = 188  #@param {type:"integer"}
m = detalle(PAR)
owners = [s["data_steward"] for s in m["sources"]]
r = decidir(PAR, "MERGE", "Misma persona: TI antigua vs CC (no comparables), coinciden nombre, apellidos, fecha y correo (grupo G3)")
if len(owners) > 1:
    for owner in owners:
        t = api("/review-tasks", actor=owner, assignee=owner, status="RECEIVED")
        for task in t:
            if task["match_sk"] == PAR:
                decidir_tarea(task["task_sk"], "MERGE", f"Owner {owner}: evidencia suficiente", actor=owner)
print("\\nCola después de la decisión:")
cola()
''')

md("""
## 6 bis · Vitrina S1–S7 (opcional): digitación muy parecida, homónimo, tres documentos, NIT, todo mal digitado

Carga en modo DELTA siete casos sintéticos sobre la base actual y verifica cada uno. Imprime el `party_sk` y el `match_sk`:
S1–S3 y S6 (todos los campos con un error de digitación) se ven en la Consola de Stewardship; S4 (golden con CC + pasaporte + TI) y S5
(organización) en la Vista 360; S7 (sin bucket común) en el explorador de buckets.
Los lotes quedan en **Modelo y cargas → Cargas y buckets**, donde también está el simulador de carga transaccional.
""")
code('''
sh(sys.executable, "cli.py", "showcase")
print("\\nCola después de la vitrina:")
cola()
''')

md("## 7 · Guardar resultados en Drive (opcional)")
code('''
import datetime, shutil, pathlib, json, urllib.request
sh(sys.executable, "cli.py", "export-drive", "--out", "/content/export")
sello = datetime.datetime.now().strftime("%Y%m%d_%H%M")
destino = pathlib.Path("/content/drive/MyDrive") / CARPETA_RESULTADOS / sello
destino.mkdir(parents=True, exist_ok=True)
shutil.copytree("/content/export", destino / "entregables", dirs_exist_ok=True)
resumen = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/v1/stats").read())
(destino / "stats.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2))
shutil.copy("/content/api.log", destino / "api.log")
print("Resultados guardados en Drive:", destino)
''')

md("## 8 · Apagar (opcional; Colab lo hace solo al cerrar)")
code('''
API_PROC.terminate()
sh("bash", str(PROTO / "scripts" / "db_local.sh"), "stop", check=False)
print("API y base de datos detenidas.")
''')

nb = {
    "cells": cells,
    "metadata": {
        "colab": {"name": "MDM_Prototipo_Colab.ipynb", "provenance": []},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
for i, c in enumerate(nb["cells"]):
    c["id"] = f"c{i:02d}"
OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("Escrito", OUT, "con", len(cells), "celdas")
