"""Tests for tools/perfiles.py (Peru fork): one workspace per person.

Each test builds a throwaway repository with a local bare remote, so worktree creation,
the gitignore fallback and the pre-push guard are exercised for real, offline.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "perfiles.py"


# Isolate every git call (ours and the tool's) from the developer's global/system git
# config: a global core.hooksPath or init.defaultBranch would change what is tested.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=ENV)


@unittest.skipIf(shutil.which("git") is None, "git not installed")
class Perfiles(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.remote = base / "remote.git"
        self.root = base / "repo"
        git("init", "-q", "--bare", str(self.remote), cwd=base)
        git("init", "-q", "-b", "master", str(self.root), cwd=base)
        for k, v in (("user.name", "Test"), ("user.email", "test@example.com")):
            git("config", k, v, cwd=self.root)
        (self.root / "CLAUDE.md").write_text("# Job Application Assistant for [YOUR_NAME]\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("documents/cv/**\n", encoding="utf-8")
        git("add", "-A", cwd=self.root)
        git("commit", "-q", "-m", "template", cwd=self.root)
        git("remote", "add", "origin", str(self.remote), cwd=self.root)
        git("push", "-q", "origin", "master", cwd=self.root)

    def run_tool(self, *args, cwd=None, expect=0):
        proc = subprocess.run([sys.executable, str(TOOL), "--json", *args], cwd=cwd or self.root,
                              capture_output=True, text=True, encoding="utf-8", env=ENV)
        self.assertEqual(proc.returncode, expect, proc.stderr + proc.stdout)
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def test_crear_makes_a_worktree_on_a_local_profile_branch(self):
        out = self.run_tool("crear", "María José")
        self.assertEqual((out["perfil"], out["rama"], out["creado"]), ("maria-jose", "perfil/maria-jose", True))
        path = Path(out["ruta"])
        self.assertTrue((path / "CLAUDE.md").is_file())
        self.assertFalse(out["configurado"])
        self.assertEqual(git("branch", "--show-current", cwd=path).stdout.strip(), "perfil/maria-jose")

    def test_crear_is_idempotent(self):
        self.run_tool("crear", "ana")
        again = self.run_tool("crear", "ana")
        self.assertFalse(again["creado"])

    def test_profiles_never_show_up_in_the_template_status(self):
        self.run_tool("crear", "ana")
        self.assertEqual(git("status", "--porcelain", cwd=self.root).stdout.strip(), "")

    def test_cv_is_copied_into_the_ignored_documents_folder(self):
        cv = Path(self._tmp.name) / "cv_ana.tex"
        cv.write_text("\\documentclass{moderncv}", encoding="utf-8")
        out = self.run_tool("crear", "ana", "--cv", str(cv))
        self.assertTrue((Path(out["ruta"]) / "documents" / "cv" / "cv_ana.tex").is_file())

    def test_pre_push_hook_blocks_profile_branches_but_not_master(self):
        out = self.run_tool("crear", "ana")
        path = Path(out["ruta"])
        (path / "CLAUDE.md").write_text("# Job Application Assistant for Ana\n", encoding="utf-8")
        git("commit", "-qam", "perfil ana", cwd=path)
        blocked = git("push", "origin", "perfil/ana", cwd=path)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("perfil personal", blocked.stderr)
        self.assertNotEqual(git("push", "--all", "origin", cwd=self.root).returncode, 0)
        (self.root / "README.md").write_text("template change\n", encoding="utf-8")
        git("add", "-A", cwd=self.root)
        git("commit", "-qm", "template", cwd=self.root)
        self.assertEqual(git("push", "origin", "master", cwd=self.root).returncode, 0)

    def test_an_existing_foreign_hook_is_left_alone(self):
        hook = self.root / ".git" / "hooks" / "pre-push"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        out = self.run_tool("crear", "ana")
        self.assertTrue(any("AVISO" in n for n in out["notas"]))
        self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")

    def test_lista_reports_configured_profiles(self):
        out = self.run_tool("crear", "ana")
        self.run_tool("crear", "luis")
        (Path(out["ruta"]) / "CLAUDE.md").write_text("# Job Application Assistant for Ana\n", encoding="utf-8")
        rows = {r["perfil"]: r["configurado"] for r in self.run_tool("lista")["perfiles"]}
        self.assertEqual(rows, {"ana": True, "luis": False})

    def test_lista_and_ruta_work_from_inside_a_profile(self):
        out = self.run_tool("crear", "ana")
        rows = self.run_tool("lista", cwd=out["ruta"])["perfiles"]
        self.assertEqual([r["perfil"] for r in rows], ["ana"])
        self.assertEqual(self.run_tool("ruta", "ana", cwd=out["ruta"])["ruta"], out["ruta"])

    def test_actualizar_brings_template_updates_and_keeps_personal_data(self):
        out = self.run_tool("crear", "ana")
        path = Path(out["ruta"])
        (path / "CLAUDE.md").write_text("# Job Application Assistant for Ana\n", encoding="utf-8")
        (self.root / "tool.py").write_text("print('v2')\n", encoding="utf-8")
        git("add", "-A", cwd=self.root)
        git("commit", "-qm", "framework update", cwd=self.root)
        refused = self.run_tool("actualizar", "ana", expect=1)
        self.assertEqual(refused["resultados"][0]["estado"], "cambios sin guardar")
        done = self.run_tool("actualizar", "ana", "--guardar")
        self.assertEqual(done["resultados"][0]["estado"], "actualizado")
        self.assertTrue((path / "tool.py").is_file())
        self.assertIn("Ana", (path / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertNotIn("Ana", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_borrar_needs_confirmation(self):
        out = self.run_tool("crear", "ana")
        dry = self.run_tool("borrar", "ana", expect=2)
        self.assertIn("simulación", dry["accion"])
        self.assertTrue(Path(out["ruta"]).exists())
        self.run_tool("borrar", "ana", "--si")
        self.assertFalse(Path(out["ruta"]).exists())
        self.assertEqual(self.run_tool("lista")["perfiles"], [])

    def test_gitignore_fallback_uses_the_local_exclude_file(self):
        self.run_tool("crear", "ana")
        exclude = (self.root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertIn("perfiles/", exclude)

    def test_names_are_slugged_inside_perfiles_and_junk_is_rejected(self):
        out = self.run_tool("crear", "../../etc")
        self.assertEqual(out["perfil"], "etc")
        self.assertEqual(Path(out["ruta"]).parent, (self.root / "perfiles").resolve())
        proc = subprocess.run([sys.executable, str(TOOL), "crear", "!!!"], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8", env=ENV)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no válido", proc.stderr)

    def test_a_shared_hooks_path_is_not_written_to(self):
        shared = Path(self._tmp.name) / "shared-hooks"
        shared.mkdir()
        git("config", "core.hooksPath", str(shared), cwd=self.root)
        out = self.run_tool("crear", "ana")
        self.assertTrue(any("core.hooksPath" in n for n in out["notas"]))
        self.assertEqual(list(shared.iterdir()), [])


class RepoWiring(unittest.TestCase):
    def test_the_template_ignores_perfiles(self):
        self.assertIn("perfiles/", (REPO / ".gitignore").read_text(encoding="utf-8").splitlines())

    def test_setup_documents_the_user_flag(self):
        setup = (REPO / ".claude" / "commands" / "setup.md").read_text(encoding="utf-8")
        self.assertIn("--user <nombre>", setup)
        self.assertIn("python tools/perfiles.py crear", setup)


if __name__ == "__main__":
    unittest.main()
