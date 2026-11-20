#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ficha de equipo: la ficha corta de cada persona en el repo del equipo (quién es quién).

Solo librería estándar, Python 3.7 o más nuevo, Mac y Windows.

  ficha.py donde                       ¿hay un plugin de equipo instalado? Imprime CLAVE=valor:
                                         HAY=sí|no  PLUGIN=  MARKETPLACE=  REPO=dueño/repo  ORIGEN=
                                         EQUIPO_EN_REPO=plugins/<plugin>/equipo  INSTALADO=<carpeta equipo>
                                         NOTA=
  ficha.py slug "Nombre Apellido"      el nombre del archivo de la ficha (sin tildes ni espacios)
  ficha.py revisar <ficha.md>          revisa una ficha: solo los campos de la lista y nada personal.
                                         Código 0 = RESULTADO=OK, 1 = RECHAZADA, 2 = no se pudo leer
  ficha.py indice <carpeta equipo>     revisa todas las fichas de personas/, rehace EQUIPO.md y la lista de
                                         nombres en la descripción de la skill `equipo`. Si una ficha no
                                         pasa la revisión, no escribe nada y sale con 1
  ficha.py plantilla <plugin base del equipo> --equipo "Nombre"
                                       agrega al plugin base del equipo lo que hace falta (equipo/, la skill
                                         equipo, el hook que pone la lista en la mesa y .gitattributes).
                                         Se puede correr de nuevo: no duplica ni pisa nada
  ficha.py autoprueba                  prueba todo en una carpeta temporal (fichas inventadas)

En Windows: py -3 ficha.py …
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SKILL = AQUI.parent                                  # la carpeta de la skill ficha-de-equipo
PLANTILLA = SKILL / "plantilla"
C = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")

# ---------------------------------------------------------------------------------------------
# Campos de la ficha: la lista cerrada. Lo que no entra en uno de estos, no va.
CAMPOS = [
    "Cómo le dicen",
    "Rol y área",
    "De qué se encarga",
    "Qué le pueden pedir",
    "Clientes o proyectos que lleva",
    "Herramientas",
    "Cómo prefiere que le pidan las cosas",
]
OBLIGATORIOS = ["Rol y área", "De qué se encarga"]
# otras formas de escribir el mismo campo (ya sin tildes y en minúsculas)
ALIAS = {
    "apodo": "Cómo le dicen",
    "como le dicen": "Cómo le dicen",
    "rol": "Rol y área",
    "rol y area": "Rol y área",
    "de que se encarga": "De qué se encarga",
    "que le pueden pedir": "Qué le pueden pedir",
    "clientes": "Clientes o proyectos que lleva",
    "proyectos": "Clientes o proyectos que lleva",
    "clientes y proyectos": "Clientes o proyectos que lleva",
    "clientes o proyectos que lleva": "Clientes o proyectos que lleva",
    "herramientas": "Herramientas",
    "como prefiere que le pidan las cosas": "Cómo prefiere que le pidan las cosas",
    "como prefiere que le pidan": "Cómo prefiere que le pidan las cosas",
}

# Lo que nunca va. Se busca sin tildes, en minúsculas y por palabra entera (así «fisioterapia» no es
# «terapia» y «dirección de arte» no es una dirección). Cada grupo: (qué es, patrones).
NUNCA = [
    ("un dato de salud", [
        r"enfermedad(es)?", r"enferm[oa]s?", r"diagnostic[oa]", r"diagnosticad[oa]", r"terapias?",
        r"terapeuta", r"psicolog[oa]", r"psiquiatra", r"ansiedad", r"depresion", r"embarazo",
        r"embarazada", r"licencia medica", r"reposo medico", r"baja medica", r"discapacidad",
        r"medicacion", r"medicamentos?", r"cirugia", r"tratamiento medico", r"salud mental",
        r"problemas? de salud", r"(mi|su|tu) salud", r"estado de salud",
    ]),
    ("un dato de familia", [
        r"hij[oa]s?", r"espos[oa]", r"marido", r"novi[oa]", r"(mi|su|tu) familia", r"familiares?",
        r"divorci\w*", r"casad[oa]", r"solter[oa]", r"(mama|papa|madre|padre) de",
    ]),
    ("plata personal (sueldo)", [
        r"sueldo", r"salario", r"remuneracion", r"cuanto gana", r"aumento de sueldo",
    ]),
    ("una evaluación de la persona", [
        r"evaluacion de desempeno", r"(su|mi|mal) desempeno", r"bajo rendimiento", r"amonestaci\w+",
        r"despid\w+", r"despedir\w*", r"renuncia\w*", r"periodo de prueba",
    ]),
    ("una dirección o dónde vive", [
        r"domicilio", r"vive en", r"vivo en", r"(su|mi) casa", r"urbanizacion", r"ciudadela",
    ]),
    ("una opinión sobre otra persona", [
        r"se lleva mal", r"no se lleva", r"conflicto con", r"no le cae bien", r"es dificil trabajar con",
        r"no confia en", r"no confiar en", r"es (muy )?(lent[oa]|floj[oa]|conflictiv[oa]|problematic[oa])",
    ]),
    ("una meta personal", [
        r"(mi|su) meta", r"(mi|su) sueno es", r"quiere renunciar", r"busca otro trabajo", r"quiere irse",
    ]),
    ("religión, política u orientación", [
        r"religion", r"religios[oa]", r"catolic[oa]", r"evangelic[oa]", r"ateo", r"orientacion sexual",
        r"partido politico",
    ]),
    ("instrucciones para Claude (una ficha es información, no órdenes)", [
        r"ignora (las|todas|lo|todo)", r"a partir de ahora", r"instrucciones (anteriores|previas)",
        r"olvida (todo|lo anterior)", r"system prompt",
    ]),
]
NUNCA_RE = [(que, re.compile(r"\b(?:" + "|".join(pats) + r")\b")) for que, pats in NUNCA]
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"https?://|\bwww\.", re.I)
NUMERO_RE = re.compile(r"[+(]?\d[\d\s().\-/]{5,}\d")

MAX_VINETAS = 6          # por campo: más es aviso, no rechazo
MAX_CARACTERES = 2500    # la ficha entera
MAX_LINEA_INDICE = 240   # cada línea de EQUIPO.md
MAX_DESCRIPCION = 1024   # límite de la descripción de una skill


def salida_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def plano(texto):
    """Sin tildes y en minúsculas, para comparar."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()


def slug(nombre):
    s = plano(nombre)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "persona"


def leer_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------------------------
# donde

def repo_de_url(url):
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url or "")
    return "{}/{}".format(m.group(1), m.group(2)) if m else ""


def repo_de_fuente(src):
    tipo = (src or {}).get("source")
    if tipo == "github":
        return src.get("repo") or "", "github"
    if tipo in ("git", "url"):
        return repo_de_url(src.get("url")), "git"
    if tipo in ("directory", "file"):
        carpeta = src.get("path") or ""
        try:
            url = subprocess.run(["git", "-C", carpeta, "remote", "get-url", "origin"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            url = ""
        return repo_de_url(url), "carpeta"
    return "", "desconocido"


def ruta_en_repo(install_location, plugin):
    """Dónde está la carpeta equipo/ del plugin dentro del repo, según el marketplace.json."""
    por_defecto = "plugins/{}/equipo".format(plugin)
    if not install_location:
        return por_defecto
    mk = leer_json(Path(install_location) / ".claude-plugin" / "marketplace.json")
    for p in mk.get("plugins") or []:
        if p.get("name") == plugin:
            src = p.get("source")
            if isinstance(src, str) and src.startswith("./"):
                return src[2:].rstrip("/") + "/equipo"
    return por_defecto


def donde():
    inst = (leer_json(C / "plugins" / "installed_plugins.json").get("plugins") or {})
    kms = leer_json(C / "plugins" / "known_marketplaces.json")
    hallados = []   # (plugin, marketplace, carpeta instalada, origen app)
    for clave, lista in inst.items():
        if "@" not in clave:
            continue
        plugin, mkt = clave.split("@", 1)
        for e in lista or []:
            ip = Path(e.get("installPath") or "")
            if str(ip) and (ip / "equipo" / "EQUIPO.md").is_file():
                hallados.append((plugin, mkt, ip, False))
    synced = C / "plugins" / "synced"
    if synced.is_dir():
        for patron in ("*/*/equipo/EQUIPO.md", "*/*/*/equipo/EQUIPO.md", "*/*/*/*/equipo/EQUIPO.md"):
            for f in synced.glob(patron):
                ip = f.parent.parent
                nombre = leer_json(ip / ".claude-plugin" / "plugin.json").get("name") or ip.name
                hallados.append((nombre, "", ip, True))
    out = {"HAY": "no", "PLUGIN": "", "MARKETPLACE": "", "REPO": "", "ORIGEN": "", "EQUIPO_EN_REPO": "",
           "INSTALADO": "", "NOTA": ""}
    if not hallados:
        out["NOTA"] = "No hay ningún plugin instalado con equipo/EQUIPO.md: no hay repo de equipo."
    else:
        plugin, mkt, ip, app = hallados[0]
        out.update(HAY="sí", PLUGIN=plugin, MARKETPLACE=mkt, INSTALADO=str(ip / "equipo"))
        if app:
            out["ORIGEN"] = "app"
            try:
                rel = ip.relative_to(synced)
                balde = synced / rel.parts[0]
                filas = leer_json(balde / ".marketplaces.json").get("rows") or []
                repos = [(f.get("name") or "", repo_de_fuente(f.get("source"))[0]) for f in filas]
                repos = [(n, r) for n, r in repos if r]
                elegido = [r for n, r in repos if n and n in rel.parts]
                out["REPO"] = elegido[0] if elegido else (repos[0][1] if len(repos) == 1 else "")
            except Exception:
                pass
            out["EQUIPO_EN_REPO"] = "plugins/{}/equipo".format(plugin)
        else:
            km = kms.get(mkt) or {}
            out["REPO"], out["ORIGEN"] = repo_de_fuente(km.get("source"))
            out["EQUIPO_EN_REPO"] = ruta_en_repo(km.get("installLocation"), plugin)
        if not out["REPO"]:
            out["NOTA"] = "No se pudo saber el repo del equipo: preguntarle a la persona de dónde lo instaló."
        if len(hallados) > 1:
            otros = ", ".join(h[0] for h in hallados[1:])
            out["NOTA"] = (out["NOTA"] + " " if out["NOTA"] else "") + \
                "Hay más de un plugin de equipo ({}): se usa el primero; preguntar cuál si no es ese.".format(otros)
    for k, v in out.items():
        print("{}={}".format(k, v))
    return 0


# ---------------------------------------------------------------------------------------------
# revisar

def campo_de(titulo):
    t = plano(titulo).strip().rstrip(":").strip()
    return ALIAS.get(t, "")


def partir(texto):
    """(nombre, {campo: [líneas]}, problemas, avisos) de una ficha."""
    problemas, avisos = [], []
    nombre, actual = "", None
    campos = {}
    for n, linea in enumerate(texto.splitlines(), 1):
        s = linea.strip()
        if not s:
            continue
        if s.startswith("# "):
            if nombre:
                problemas.append("línea {}: hay un segundo título; la ficha es de una sola persona".format(n))
            else:
                nombre = s[2:].strip()
            continue
        if s.startswith("## "):
            c = campo_de(s[3:])
            if not c:
                problemas.append("línea {}: «{}» no es un campo de la ficha (la lista: {})".format(
                    n, s[3:].strip(), "; ".join(CAMPOS)))
                actual = "__fuera__"
            elif c in campos:
                problemas.append("línea {}: el campo «{}» está dos veces".format(n, c))
                actual = c
            else:
                campos[c] = []
                actual = c
            continue
        if s.startswith("#"):
            problemas.append("línea {}: subtítulo fuera de la lista («{}»)".format(n, s))
            continue
        if actual is None:
            if not (s.startswith("_") and s.endswith("_")):
                problemas.append("línea {}: texto fuera de los campos («{}»)".format(n, s[:60]))
            continue
        if actual != "__fuera__":
            campos[actual].append(s)
    if not nombre:
        problemas.append("falta el título con el nombre («# Nombre Apellido»)")
    for c in OBLIGATORIOS:
        if not campos.get(c):
            problemas.append("falta el campo «{}»".format(c))
    for c, lineas in campos.items():
        vinetas = [l for l in lineas if l.startswith(("-", "*", "•"))]
        if len(vinetas) > MAX_VINETAS:
            avisos.append("«{}» tiene {} viñetas: mejor {} o menos".format(c, len(vinetas), MAX_VINETAS))
    if len(texto) > MAX_CARACTERES:
        avisos.append("la ficha tiene {} caracteres: mejor menos de {}".format(len(texto), MAX_CARACTERES))
    return nombre, campos, problemas, avisos


def datos_que_no_van(texto):
    problemas = []
    for n, linea in enumerate(texto.splitlines(), 1):
        p = plano(linea)
        for m in EMAIL_RE.finditer(linea):
            problemas.append("línea {}: un correo («{}»)".format(n, m.group(0)))
        if URL_RE.search(linea):
            problemas.append("línea {}: un link (los links personales no van; el canal sí: «por correo», «por WhatsApp»)".format(n))
        for m in NUMERO_RE.finditer(linea):
            if sum(ch.isdigit() for ch in m.group(0)) >= 9:
                problemas.append("línea {}: parece un teléfono o un documento («{}»)".format(n, m.group(0).strip()))
        for que, rx in NUNCA_RE:
            m = rx.search(p)
            if m:
                problemas.append("línea {}: «{}» es {}".format(n, m.group(0), que))
    return problemas


def revisar_texto(texto):
    nombre, campos, problemas, avisos = partir(texto)
    problemas += datos_que_no_van(texto)
    return nombre, campos, problemas, avisos


def revisar(ruta):
    p = Path(ruta)
    try:
        texto = p.read_text(encoding="utf-8")
    except Exception as e:
        print("FICHA={}".format(p))
        print("RESULTADO=ERROR")
        print("PROBLEMA=no se pudo leer: {}".format(e))
        return 2
    nombre, _, problemas, avisos = revisar_texto(texto)
    print("FICHA={}".format(p))
    print("NOMBRE={}".format(nombre))
    print("RESULTADO={}".format("RECHAZADA" if problemas else "OK"))
    for x in problemas:
        print("PROBLEMA={}".format(x))
    for x in avisos:
        print("AVISO={}".format(x))
    return 1 if problemas else 0


# ---------------------------------------------------------------------------------------------
# indice

def sin_vineta(s):
    return re.sub(r"^[-*•]\s*", "", s).strip()


def corto(s, n):
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip(" ,;.") + "…"


def linea_indice(nombre, campos, archivo):
    apodo = sin_vineta((campos.get("Cómo le dicen") or [""])[0]).strip("«»\"' ")
    rol = sin_vineta((campos.get("Rol y área") or [""])[0]).rstrip(".")
    pedir = [sin_vineta(x).rstrip(".") for x in (campos.get("Qué le pueden pedir") or [])[:2]]
    if not pedir:
        pedir = [sin_vineta(x).rstrip(".") for x in (campos.get("De qué se encarga") or [])[:1]]
    cabeza = "- **{}**".format(nombre)
    if apodo and plano(apodo) != plano(nombre):
        cabeza += " («{}»)".format(apodo)
    cola = " → personas/{}".format(archivo)
    rol_txt = " — {}.".format(corto(rol, 70)) if rol else ""
    libre = MAX_LINEA_INDICE - len(cabeza) - len(rol_txt) - len(cola) - len(" Pedirle: .")
    ped_txt = " Pedirle: {}.".format(corto("; ".join(pedir), max(libre, 20))) if pedir else ""
    return cabeza + rol_txt + ped_txt + cola


def titulo_equipo(equipo_md):
    try:
        for l in Path(equipo_md).read_text(encoding="utf-8").splitlines():
            if l.startswith("# "):
                return l[2:].strip()
    except Exception:
        pass
    return "Equipo"


NOTA_EQUIPO = ("_Quién es quién: una línea por persona. La ficha completa de cada una está en personas/ "
               "(skill equipo). Se actualiza con «actualiza mi ficha del equipo»; no se edita a mano._")
MARCA = "Personas del equipo:"


def nueva_descripcion(desc, nombres):
    base = desc.split(MARCA)[0].rstrip()
    for lista in (nombres, sorted({n.split()[0] for n in nombres})):
        frase = "{} {}.".format(MARCA, ", ".join(lista) if lista else "(todavía nadie)")
        d = (base + " " + frase).strip()
        if len(d) <= MAX_DESCRIPCION:
            return d
    return (base + " {} {} personas (la lista está en equipo/EQUIPO.md).".format(MARCA, len(nombres))).strip()


def actualizar_skill_equipo(skill_md, nombres):
    """Pone los nombres en la descripción de la skill equipo, para que se cargue al nombrar a alguien
    aunque el hook no corra (Cowork). Devuelve True si la encontró."""
    p = Path(skill_md)
    if not p.is_file():
        return False
    t = p.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", t, re.S)
    if not m:
        return False
    front = m.group(1)
    d = re.search(r'^description:\s*"(.*)"\s*$', front, re.M)
    if not d:
        return False
    limpios = [re.sub(r'["\\]', "", n) for n in nombres]
    desc = nueva_descripcion(d.group(1), limpios)
    front2 = front[: d.start()] + 'description: "{}"'.format(desc) + front[d.end():]
    p.write_text("---\n" + front2 + "\n---\n" + t[m.end():], encoding="utf-8")
    return True


def indice(carpeta):
    eq = Path(carpeta)
    personas = eq / "personas"
    if not personas.is_dir():
        print("ERROR=no existe {}".format(personas))
        return 2
    filas, nombres, malas = [], [], []
    for f in sorted(personas.glob("*.md")):
        if f.name.startswith(("_", ".")) or f.name.upper().startswith("LEEME"):
            continue
        texto = f.read_text(encoding="utf-8")
        nombre, campos, problemas, _ = revisar_texto(texto)
        if problemas:
            malas.append((f.name, problemas))
            continue
        filas.append((plano(nombre), linea_indice(nombre, campos, f.name)))
        nombres.append(nombre)
    if malas:
        for nombre_archivo, problemas in malas:
            for x in problemas:
                print("RECHAZADA={}: {}".format(nombre_archivo, x))
        print("RESULTADO=NO SE ESCRIBIÓ NADA (corregir esas fichas primero)")
        return 1
    filas.sort()
    nombres.sort(key=plano)
    destino = eq / "EQUIPO.md"
    titulo = titulo_equipo(destino)
    cuerpo = "# {}\n{}\n\n".format(titulo, NOTA_EQUIPO)
    cuerpo += "\n".join(l for _, l in filas) + "\n" if filas else \
        "(Todavía no hay fichas. Cada persona arma la suya con «arma mi ficha del equipo».)\n"
    destino.write_text(cuerpo, encoding="utf-8")
    skill_md = eq.parent / "skills" / "equipo" / "SKILL.md"
    ok_skill = actualizar_skill_equipo(skill_md, nombres)
    print("PERSONAS={}".format(len(filas)))
    print("EQUIPO_MD={}".format(destino))
    print("SKILL_EQUIPO={}".format(skill_md if ok_skill else "no encontrada (¿falta la plantilla?)"))
    print("RESULTADO=OK")
    return 0


# ---------------------------------------------------------------------------------------------
# plantilla

ENTRADA_HOOK = {
    "hooks": [{
        "type": "command",
        "command": "sh \"${CLAUDE_PLUGIN_ROOT}/hooks/equipo-en-la-mesa.sh\"; exit 0",
        "timeout": 10,
    }]
}


def poner_hook(plugin):
    """Suma el SessionStart del equipo a hooks/hooks.json sin tocar los que ya están."""
    hj = plugin / "hooks" / "hooks.json"
    datos = leer_json(hj) if hj.is_file() else \
        {"description": "Pone la lista del equipo en la mesa al empezar cada conversación."}
    if hj.is_file() and not datos:
        return "hooks.json existe pero no se pudo leer: no se tocó (revisarlo a mano)"
    datos.setdefault("hooks", {})
    lista = datos["hooks"].setdefault("SessionStart", [])
    ya = any("equipo-en-la-mesa.sh" in (h.get("command") or "")
             for grupo in lista for h in (grupo.get("hooks") or []))
    if ya:
        return "el hook ya estaba"
    lista.append(json.loads(json.dumps(ENTRADA_HOOK)))
    hj.parent.mkdir(parents=True, exist_ok=True)
    hj.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "hook agregado a hooks/hooks.json"


def copiar_si_falta(origen, destino, reemplazos=None):
    if destino.exists():
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    t = origen.read_text(encoding="utf-8")
    for k, v in (reemplazos or {}).items():
        t = t.replace(k, v)
    destino.write_text(t, encoding="utf-8")
    return True


def plantilla(plugin_dir, equipo):
    plugin = Path(plugin_dir).resolve()
    if not (plugin / ".claude-plugin" / "plugin.json").is_file():
        print("ERROR={} no es la carpeta de un plugin (falta .claude-plugin/plugin.json)".format(plugin))
        return 2
    r = {"{{EQUIPO}}": equipo}
    hechos = []
    if copiar_si_falta(PLANTILLA / "equipo" / "EQUIPO.md.plantilla", plugin / "equipo" / "EQUIPO.md", r):
        hechos.append("equipo/EQUIPO.md")
    gk = plugin / "equipo" / "personas" / ".gitkeep"
    if not gk.exists():
        gk.parent.mkdir(parents=True, exist_ok=True)
        gk.write_text("", encoding="utf-8")
        hechos.append("equipo/personas/")
    if copiar_si_falta(PLANTILLA / "skills" / "equipo" / "SKILL.md.plantilla",
                       plugin / "skills" / "equipo" / "SKILL.md", r):
        hechos.append("skills/equipo/SKILL.md")
    gancho = plugin / "hooks" / "equipo-en-la-mesa.sh"
    if not gancho.exists():
        gancho.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(PLANTILLA / "hooks" / "equipo-en-la-mesa.sh"), str(gancho))
        hechos.append("hooks/equipo-en-la-mesa.sh")
    hechos.append(poner_hook(plugin))
    propia = plugin / "skills" / "ficha-de-equipo"
    if not propia.exists() and SKILL.resolve() != propia.resolve():
        shutil.copytree(str(SKILL), str(propia), ignore=shutil.ignore_patterns("__pycache__"))
        hechos.append("skills/ficha-de-equipo (copiada)")
    raiz = plugin.parent.parent
    if (raiz / ".claude-plugin" / "marketplace.json").is_file():
        ga = raiz / ".gitattributes"
        regla = "*.sh text eol=lf"
        previo = ga.read_text(encoding="utf-8") if ga.exists() else ""
        if regla not in previo:
            ga.write_text(previo + ("" if not previo or previo.endswith("\n") else "\n") +
                          "# Los .sh con fin de línea de Mac, para que los hooks anden en Windows (Git Bash)\n" +
                          regla + "\n", encoding="utf-8")
            hechos.append(".gitattributes")
    for h in hechos:
        print("HECHO={}".format(h))
    print("RESULTADO=OK")
    return 0


# ---------------------------------------------------------------------------------------------
# autoprueba

FICHAS_PRUEBA = {
    "ana-ejemplo.md": """# Ana Ejemplo
_Ficha de equipo · actualizada el jue 19-11-2026 · con el OK de Ana._

## Cómo le dicen
Anita

## Rol y área
Productora · área de producción

## De qué se encarga
- Presupuestos y cronogramas de rodaje
- Permisos de locación
- Lleva la cuenta de una clínica de fisioterapia

## Qué le pueden pedir
- Cotizaciones de rodaje
- Fechas de entrega de un proyecto

## Herramientas
- Excel, Drive, ClickUp

## Cómo prefiere que le pidan las cosas
- Por ClickUp, con dos días de anticipación
""",
    "bruno-prueba.md": """# Bruno Prueba
_Ficha de equipo · actualizada el jue 19-11-2026 · con el OK de Bruno._

## Rol y área
Editor de video · área de postproducción

## De qué se encarga
- Edición de reels y spots
- Dirección de arte de las piezas cortas (campañas 2019-2024)

## Qué le pueden pedir
- Cortes rápidos para redes
- Exportes en 9:16 y 1:1

## Clientes o proyectos que lleva
- Marca de café (reels semanales)

## Herramientas
- Premiere, After Effects, Claude
""",
    "carla-muestra.md": """# Carla Muestra

## Rol y área
Diseñadora gráfica · área creativa

## De qué se encarga
- Piezas para redes y presentaciones
- Mide el desempeño de las campañas en redes
- Trabaja con Cristian en las propuestas

## Cómo prefiere que le pidan las cosas
- Por correo, con el brief completo
""",
}

FICHA_MALA = """# Dario Fuera
_Ficha de equipo._

## Rol y área
Asistente de producción

## De qué se encarga
- Compras para los rodajes
- WhatsApp 099 123 4567, correo dario.fuera@ejemplo.com
- Los viernes sale temprano por su terapia

## Metas
- Quiere ser director
"""


def autoprueba():
    salida_utf8()
    resultados = []

    def chequeo(nombre, ok, detalle=""):
        resultados.append(ok)
        print("{} {}{}".format("✅" if ok else "❌", nombre, " — " + detalle if detalle and not ok else ""))

    def correr(*args, entorno=None):
        r = subprocess.run([sys.executable, str(Path(__file__).resolve())] + list(args),
                           capture_output=True, text=True, encoding="utf-8", env=entorno)
        return r.returncode, r.stdout + r.stderr

    tmp = Path(tempfile.mkdtemp(prefix="ficha-equipo-"))
    try:
        # un repo de equipo de mentira, con un hook que ya estaba
        repo = tmp / "repo"
        plugin = repo / "plugins" / "prueba-base"
        (repo / ".claude-plugin").mkdir(parents=True)
        (repo / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
            "name": "equipo-prueba", "owner": {"name": "Prueba"},
            "plugins": [{"name": "prueba-base", "source": "./plugins/prueba-base",
                         "description": "Plugin base de un equipo de prueba."}]}, indent=2), encoding="utf-8")
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({
            "name": "prueba-base", "description": "Equipo de prueba.", "author": {"name": "Prueba"}}),
            encoding="utf-8")
        (plugin / "hooks").mkdir()
        (plugin / "hooks" / "hooks.json").write_text(json.dumps({
            "description": "Hooks de antes.",
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo listo; exit 0"}]}]}}),
            encoding="utf-8")

        c1, _ = correr("plantilla", str(plugin), "--equipo", "Estudio de Prueba")
        c2, _ = correr("plantilla", str(plugin), "--equipo", "Estudio de Prueba")
        hj = leer_json(plugin / "hooks" / "hooks.json")
        n_inicio = sum(1 for g in hj.get("hooks", {}).get("SessionStart", []) for h in g.get("hooks", [])
                       if "equipo-en-la-mesa.sh" in h.get("command", ""))
        chequeo("plantilla: se aplica dos veces sin duplicar el hook",
                c1 == 0 and c2 == 0 and n_inicio == 1, "SessionStart={}".format(n_inicio))
        chequeo("plantilla: respeta los hooks que ya estaban", "Stop" in hj.get("hooks", {}))
        chequeo("plantilla: skill equipo, EQUIPO.md, ficha-de-equipo y .gitattributes",
                (plugin / "skills" / "equipo" / "SKILL.md").is_file()
                and (plugin / "equipo" / "EQUIPO.md").is_file()
                and (plugin / "skills" / "ficha-de-equipo" / "scripts" / "ficha.py").is_file()
                and "eol=lf" in (repo / ".gitattributes").read_text(encoding="utf-8"))

        personas = plugin / "equipo" / "personas"
        for nombre, texto in FICHAS_PRUEBA.items():
            (personas / nombre).write_text(texto, encoding="utf-8")
            cod, out = correr("revisar", str(personas / nombre))
            chequeo("revisar: {} pasa".format(nombre), cod == 0 and "RESULTADO=OK" in out, out)

        mala = tmp / "dario-fuera.md"
        mala.write_text(FICHA_MALA, encoding="utf-8")
        cod, out = correr("revisar", str(mala))
        chequeo("privacidad: la ficha con teléfono y salud sale RECHAZADA",
                cod == 1 and "RESULTADO=RECHAZADA" in out, out)
        chequeo("privacidad: encuentra el teléfono", "teléfono" in out, out)
        chequeo("privacidad: encuentra el dato de salud", "dato de salud" in out, out)
        chequeo("privacidad: encuentra el correo", "un correo" in out, out)
        chequeo("privacidad: encuentra el campo que no está en la lista", "«Metas» no es un campo" in out, out)
        cod_ok, out_ok = correr("revisar", str(personas / "bruno-prueba.md"))
        chequeo("sin falsas alarmas: años, «dirección de arte», «fisioterapia», «desempeño de las campañas», Cristian",
                cod_ok == 0 and "PROBLEMA" not in out_ok and
                "PROBLEMA" not in correr("revisar", str(personas / "ana-ejemplo.md"))[1] and
                "PROBLEMA" not in correr("revisar", str(personas / "carla-muestra.md"))[1], out_ok)

        cod, out = correr("indice", str(plugin / "equipo"))
        eq = (plugin / "equipo" / "EQUIPO.md").read_text(encoding="utf-8")
        filas = [l for l in eq.splitlines() if l.startswith("- **")]
        chequeo("indice: EQUIPO.md con una línea por persona", cod == 0 and len(filas) == 3, out + eq)
        chequeo("indice: líneas cortas", all(len(l) <= MAX_LINEA_INDICE for l in filas))
        skill_txt = (plugin / "skills" / "equipo" / "SKILL.md").read_text(encoding="utf-8")
        d = re.search(r'^description:\s*"(.*)"\s*$', skill_txt, re.M)
        chequeo("indice: los nombres quedan en la descripción de la skill equipo",
                bool(d) and all(n in d.group(1) for n in ("Ana Ejemplo", "Bruno Prueba", "Carla Muestra"))
                and len(d.group(1)) <= MAX_DESCRIPCION, d.group(1) if d else skill_txt[:300])

        shutil.copyfile(str(mala), str(personas / "dario-fuera.md"))
        cod, out = correr("indice", str(plugin / "equipo"))
        eq2 = (plugin / "equipo" / "EQUIPO.md").read_text(encoding="utf-8")
        chequeo("indice: con una ficha mala no escribe nada", cod == 1 and eq2 == eq, out)
        (personas / "dario-fuera.md").unlink()

        # el hook: imprime la lista, calla si no hay, y corta si es muy larga
        sh = shutil.which("sh")
        gancho = plugin / "hooks" / "equipo-en-la-mesa.sh"
        if not sh:
            print("⏭️  hook: no hay sh en esta computadora (en Windows lo trae Git Bash); no se probó")
        else:
            r = subprocess.run([sh, str(gancho)], input="{}", capture_output=True, text=True, encoding="utf-8")
            chequeo("hook: pone la lista en la mesa", r.returncode == 0 and "Bruno Prueba" in r.stdout, r.stdout + r.stderr)
            (plugin / "equipo" / "EQUIPO.md").write_text(eq.split("\n- **")[0] + "\n", encoding="utf-8")
            r = subprocess.run([sh, str(gancho)], input="{}", capture_output=True, text=True, encoding="utf-8")
            chequeo("hook: sin fichas no dice nada", r.returncode == 0 and r.stdout.strip() == "", r.stdout)
            (plugin / "equipo" / "EQUIPO.md").unlink()
            r = subprocess.run([sh, str(gancho)], input="{}", capture_output=True, text=True, encoding="utf-8")
            chequeo("hook: sin EQUIPO.md no dice nada ni falla", r.returncode == 0 and r.stdout.strip() == "", r.stdout)
            grande = "# Equipo grande\n" + "".join("- **Persona {}** — Rol {}. → personas/p{}.md\n".format(i, i, i)
                                                   for i in range(150))
            (plugin / "equipo" / "EQUIPO.md").write_text(grande, encoding="utf-8")
            r = subprocess.run([sh, str(gancho)], input="{}", capture_output=True, text=True, encoding="utf-8")
            n_lineas = len(r.stdout.splitlines())
            chequeo("hook: una lista muy larga se corta (tope de líneas y de largo)",
                    r.returncode == 0 and n_lineas <= 83 and len(r.stdout.encode("utf-8")) <= 8300
                    and "skill equipo" in r.stdout, "{} líneas".format(n_lineas))
            (plugin / "equipo" / "EQUIPO.md").write_text(eq, encoding="utf-8")

        # donde: con una instalación de mentira
        conf = tmp / "config"
        (conf / "plugins").mkdir(parents=True)
        (conf / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "prueba-base@equipo-prueba": [{"scope": "user", "installPath": str(plugin)}]}}), encoding="utf-8")
        (conf / "plugins" / "known_marketplaces.json").write_text(json.dumps({"equipo-prueba": {
            "source": {"source": "github", "repo": "estudio-prueba/claude-equipo"},
            "installLocation": str(repo)}}), encoding="utf-8")
        entorno = dict(os.environ, CLAUDE_CONFIG_DIR=str(conf))
        cod, out = correr("donde", entorno=entorno)
        chequeo("donde: encuentra el plugin del equipo y su repo",
                "HAY=sí" in out and "REPO=estudio-prueba/claude-equipo" in out
                and "EQUIPO_EN_REPO=plugins/prueba-base/equipo" in out, out)
        vacio = tmp / "config-vacio"
        vacio.mkdir()
        cod, out = correr("donde", entorno=dict(os.environ, CLAUDE_CONFIG_DIR=str(vacio)))
        chequeo("donde: sin equipo dice HAY=no", "HAY=no" in out, out)

        chequeo("slug: «Ana Lucía Pérez» → ana-lucia-perez", slug("Ana Lucía Pérez") == "ana-lucia-perez")
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)

    bien = sum(1 for r in resultados if r)
    print("\nRESULTADO={}/{} {}".format(bien, len(resultados), "✅" if bien == len(resultados) else "❌"))
    return 0 if bien == len(resultados) else 1


# ---------------------------------------------------------------------------------------------

def main(argv):
    salida_utf8()
    if not argv:
        print(__doc__)
        return 2
    cmd, resto = argv[0], argv[1:]
    if cmd == "donde":
        return donde()
    if cmd == "slug" and resto:
        print(slug(" ".join(resto)))
        return 0
    if cmd == "revisar" and resto:
        return revisar(resto[0])
    if cmd == "indice" and resto:
        return indice(resto[0])
    if cmd == "plantilla" and resto:
        equipo = "el equipo"
        if "--equipo" in resto:
            i = resto.index("--equipo")
            if i + 1 < len(resto):
                equipo = resto[i + 1]
            resto = resto[:i] + resto[i + 2:]
        return plantilla(resto[0], equipo)
    if cmd == "autoprueba":
        return autoprueba()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
