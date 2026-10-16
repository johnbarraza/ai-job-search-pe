#!/usr/bin/env python3
"""Profiles: one workspace per person (or per job-search identity), side by side.

Every command in this framework reads one candidate's files from fixed paths in the
folder Claude Code is opened in (CLAUDE.md, the skill files, cv/, documents/, the
tracker, job_scraper/ state). So a second person needs a second workspace, not a second
set of files in the same one. A profile is that workspace: a git worktree at
perfiles/<nombre>/ on the local branch perfil/<nombre>. Creating one downloads nothing
(it shares this repository's history); each profile keeps its own profile files, CVs,
tracker and seen jobs; and framework updates flow in with `actualizar`.

Personal data never leaves the machine: perfiles/ is gitignored, and `crear` installs a
local pre-push hook that refuses to push any perfil/* branch to any remote.

Usage (run from anywhere inside the repository):
    python tools/perfiles.py crear <nombre> [--cv <archivo>] [--jev]
    python tools/perfiles.py lista
    python tools/perfiles.py ruta <nombre>
    python tools/perfiles.py actualizar <nombre>|--todos [--guardar]
    python tools/perfiles.py borrar <nombre> [--si]

`/setup --user <nombre>` calls `crear` and then writes that person's profile into
perfiles/<nombre>/. Open Claude Code inside perfiles/<nombre>/ to use it day to day.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

PROFILES_DIR = "perfiles"
BRANCH_PREFIX = "perfil/"
HOOK_MARKER = "ai-job-search perfiles: pre-push guard"
HOOK = f"""#!/bin/sh
# {HOOK_MARKER}
# Installed by tools/perfiles.py. Profile branches hold personal data (CV, contact
# details, salary expectations) and must never reach a remote.
while read local_ref local_sha remote_ref remote_sha; do
  case "$local_ref" in
    refs/heads/{BRANCH_PREFIX}*)
      echo "pre-push: $local_ref es un perfil personal y no se sube a ningún remoto." >&2
      exit 1
      ;;
  esac
done
exit 0
"""
PLACEHOLDER = "[YOUR_NAME]"


class ProfileError(Exception):
    pass


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise ProfileError(f"git {' '.join(args)} falló: {(proc.stderr or proc.stdout).strip()}")
    return proc


def main_root(start: Path) -> Path:
    """The main worktree's root, even when called from inside a profile worktree."""
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=start).stdout.strip()
    return Path(common).parent


def slug(name: str) -> str:
    s = unicodedata.normalize("NFD", name.strip().lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", s or ""):
        raise ProfileError(f"nombre de perfil no válido: {name!r} (usa letras, números y guiones)")
    return s


def worktrees(root: Path) -> list[dict]:
    """Registered worktrees as [{path, branch}] from `git worktree list --porcelain`."""
    out, cur = [], {}
    for line in git("worktree", "list", "--porcelain", cwd=root).stdout.splitlines():
        if line.startswith("worktree "):
            cur = {"path": Path(line[9:]).resolve(), "branch": None}
            out.append(cur)
        elif line.startswith("branch ") and cur:
            cur["branch"] = line[7:].removeprefix("refs/heads/")
    return out


def profile_path(root: Path, name: str) -> Path:
    return (root / PROFILES_DIR / name).resolve()


def find_profile(root: Path, name: str) -> dict | None:
    target = profile_path(root, name)
    return next((w for w in worktrees(root) if w["path"] == target), None)


def branch_exists(root: Path, branch: str) -> bool:
    return git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}", cwd=root, check=False).returncode == 0


def ensure_ignored(root: Path) -> str:
    """perfiles/ must be ignored by the main worktree; fall back to the local exclude file
    for checkouts whose .gitignore predates this tool."""
    probe = f"{PROFILES_DIR}/x"
    if git("check-ignore", "-q", probe, cwd=root, check=False).returncode == 0:
        return "ignorado por .gitignore"
    exclude = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root).stdout.strip()) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as fh:
        fh.write(f"\n# Profiles (tools/perfiles.py): personal workspaces, never committed\n{PROFILES_DIR}/\n")
    return "ignorado por .git/info/exclude"


def ensure_hook(root: Path) -> str:
    custom = git("config", "--get", "core.hooksPath", cwd=root, check=False).stdout.strip()
    if custom:
        return (f"AVISO: core.hooksPath apunta a {custom}; no se instaló el hook pre-push para no tocar una "
                f"carpeta de hooks compartida. No hagas push de ramas {BRANCH_PREFIX}*.")
    hooks = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root).stdout.strip()) / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    if hook.exists():
        if HOOK_MARKER in hook.read_text(encoding="utf-8", errors="replace"):
            return "hook pre-push ya instalado"
        return (f"AVISO: ya existe {hook} y no es de esta herramienta; no se tocó. Agrega a mano el bloqueo "
                f"de ramas {BRANCH_PREFIX}* o no hagas push de esas ramas.")
    hook.write_text(HOOK, encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    return "hook pre-push instalado (bloquea push de ramas perfil/*)"


def is_configured(path: Path) -> bool:
    claude = path / "CLAUDE.md"
    return claude.is_file() and PLACEHOLDER not in claude.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------- commands

def cmd_crear(root: Path, args) -> dict:
    name = slug(args.nombre)
    path = profile_path(root, name)
    branch = BRANCH_PREFIX + name
    notes = [ensure_ignored(root), ensure_hook(root)]
    existing = find_profile(root, name)
    if existing:
        created = False
    else:
        if path.exists():
            raise ProfileError(f"{path} ya existe y no es un perfil registrado; muévelo o bórralo primero")
        if branch_exists(root, branch):
            git("worktree", "add", str(path), branch, cwd=root)
        else:
            git("worktree", "add", "-b", branch, str(path), args.base, cwd=root)
        created = True
    if args.cv:
        src = Path(args.cv).expanduser()
        if not src.is_file():
            raise ProfileError(f"no existe el archivo de CV {src}")
        dest_dir = path / "documents" / "cv"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_dir / src.name)
        notes.append(f"CV copiado a documents/cv/{src.name}")
    if args.jev:
        git("submodule", "update", "--init", "vendor/jev-browse", cwd=path)
        notes.append("submódulo vendor/jev-browse inicializado")
    return {
        "perfil": name,
        "ruta": str(path),
        "rama": branch,
        "creado": created,
        "configurado": is_configured(path),
        "notas": notes,
        "siguiente": f'cd "{path}" y abre Claude Code ahí; luego /setup (o /setup --user {name} desde la raíz)',
    }


def cmd_lista(root: Path, args) -> dict:
    base = (root / PROFILES_DIR).resolve()
    rows = []
    for w in worktrees(root):
        if w["path"].parent == base and (w["branch"] or "").startswith(BRANCH_PREFIX):
            rows.append({
                "perfil": w["path"].name,
                "ruta": str(w["path"]),
                "rama": w["branch"],
                "configurado": is_configured(w["path"]),
            })
    return {"perfiles": rows}


def cmd_ruta(root: Path, args) -> dict:
    name = slug(args.nombre)
    if not find_profile(root, name):
        raise ProfileError(f"no existe el perfil {name!r}; créalo con: python tools/perfiles.py crear {name}")
    return {"perfil": name, "ruta": str(profile_path(root, name))}


def cmd_actualizar(root: Path, args) -> dict:
    names = [r["perfil"] for r in cmd_lista(root, args)["perfiles"]] if args.todos else [slug(args.nombre)]
    if not args.todos and not args.nombre:
        raise ProfileError("indica un perfil o --todos")
    results = []
    for name in names:
        prof = find_profile(root, name)
        if not prof:
            results.append({"perfil": name, "estado": "no existe"})
            continue
        path = prof["path"]
        dirty = git("status", "--porcelain", cwd=path).stdout.strip()
        if dirty and not args.guardar:
            results.append({"perfil": name, "estado": "cambios sin guardar",
                            "detalle": "vuelve a correr con --guardar para guardarlos en la rama local del perfil antes de actualizar"})
            continue
        if dirty:
            git("add", "-A", cwd=path)
            git("commit", "-q", "-m", f"perfil {name}: guardar cambios locales", cwd=path)
        merge = git("merge", "--no-edit", args.base, cwd=path, check=False)
        if merge.returncode != 0:
            results.append({"perfil": name, "estado": "conflicto",
                            "detalle": f"resuelve los conflictos en {path} (git status) y haz commit; o 'git merge --abort' para deshacer"})
            continue
        results.append({"perfil": name, "estado": "actualizado", "detalle": merge.stdout.strip().splitlines()[-1] if merge.stdout.strip() else ""})
    return {"base": args.base, "resultados": results}


def cmd_borrar(root: Path, args) -> dict:
    name = slug(args.nombre)
    prof = find_profile(root, name)
    if not prof:
        raise ProfileError(f"no existe el perfil {name!r}")
    plan = {"perfil": name, "ruta": str(prof["path"]), "rama": prof["branch"],
            "se_borra": "la carpeta completa del perfil (incluidos documents/, CVs y tracker) y su rama local"}
    if not args.si:
        plan["accion"] = "simulación: nada se borró; repite con --si para confirmar"
        return plan
    git("worktree", "remove", "--force", str(prof["path"]), cwd=root)
    if prof["branch"]:
        git("branch", "-D", prof["branch"], cwd=root)
    plan["accion"] = "borrado"
    return plan


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true", help="salida JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crear", aliases=["create"], help="crear (o reabrir) un perfil")
    c.add_argument("nombre")
    c.add_argument("--cv", help="copiar este archivo de CV a documents/cv/ del perfil")
    c.add_argument("--jev", action="store_true", help="inicializar el submódulo jev-browse en el perfil")
    c.add_argument("--base", default="master", help="rama de la que parte el perfil (default: master)")
    sub.add_parser("lista", aliases=["list"], help="listar perfiles")
    r = sub.add_parser("ruta", aliases=["path"], help="ruta de un perfil")
    r.add_argument("nombre")
    u = sub.add_parser("actualizar", aliases=["update"], help="traer las mejoras de la rama base al perfil")
    u.add_argument("nombre", nargs="?")
    u.add_argument("--todos", action="store_true")
    u.add_argument("--guardar", action="store_true", help="guardar antes los cambios pendientes del perfil (commit local)")
    u.add_argument("--base", default="master")
    b = sub.add_parser("borrar", aliases=["remove"], help="borrar un perfil (pide --si)")
    b.add_argument("nombre")
    b.add_argument("--si", action="store_true", help="confirmar el borrado")
    args = ap.parse_args(argv)

    handlers = {"crear": cmd_crear, "create": cmd_crear, "lista": cmd_lista, "list": cmd_lista,
                "ruta": cmd_ruta, "path": cmd_ruta, "actualizar": cmd_actualizar, "update": cmd_actualizar,
                "borrar": cmd_borrar, "remove": cmd_borrar}
    try:
        root = main_root(Path.cwd())
        result = handlers[args.cmd](root, args)
    except ProfileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(args.cmd, result))
    if args.cmd in ("borrar", "remove") and not args.si:
        return 2
    if args.cmd in ("actualizar", "update") and any(r["estado"] in ("conflicto", "cambios sin guardar") for r in result["resultados"]):
        return 1
    return 0


def render(cmd: str, result: dict) -> str:
    if cmd in ("lista", "list"):
        rows = result["perfiles"]
        if not rows:
            return "No hay perfiles. Crea uno con: python tools/perfiles.py crear <nombre>  (o /setup --user <nombre>)"
        return "\n".join(f"  {r['perfil']:<20} {'configurado' if r['configurado'] else 'sin configurar':<15} {r['ruta']}" for r in rows)
    if cmd in ("actualizar", "update"):
        return "\n".join(f"  {r['perfil']:<20} {r['estado']}{(' - ' + r['detalle']) if r.get('detalle') else ''}" for r in result["resultados"])
    return "\n".join(f"{k}: {v if not isinstance(v, list) else '; '.join(v)}" for k, v in result.items())


if __name__ == "__main__":
    sys.exit(main())
