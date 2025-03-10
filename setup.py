#!/usr/bin/env python3
"""The xonsh installer."""
# Note: Do not embed any non-ASCII characters in this file until pip has been
# fixed. See https://github.com/xonsh/xonsh/issues/487.
import os
import sys
import subprocess

from setuptools import setup, find_packages
from setuptools.command.sdist import sdist
from setuptools.command.install import install
from setuptools.command.develop import develop
from setuptools.command.build_py import build_py
from setuptools.command.install_scripts import install_scripts

TABLES = [
    "xonsh/lexer_table.py",
    "xonsh/parser_table.py",
    "xonsh/completion_parser_table.py",
    "xonsh/__amalgam__.py",
    "xonsh/completers/__amalgam__.py",
    "xonsh/history/__amalgam__.py",
    "xonsh/prompt/__amalgam__.py",
    "xonsh/procs/__amalgam__.py",
]


def clean_tables():
    """Remove the lexer/parser modules that are dynamically created."""
    for f in TABLES:
        if os.path.isfile(f):
            os.remove(f)
            print("Removed " + f)


os.environ["XONSH_DEBUG"] = "1"
from xonsh import __version__ as XONSH_VERSION


def amalgamate_source():
    """Amalgamates source files."""
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        import amalgamate
    except ImportError:
        print("Could not import amalgamate, skipping.", file=sys.stderr)
        return
    amalgamate.main(
        [
            "amalgamate",
            "--debug=XONSH_NO_AMALGAMATE",
            "xonsh",
            "xonsh.completers",
            "xonsh.history",
            "xonsh.prompt",
            "xonsh.procs",
        ]
    )
    sys.path.pop(0)


def build_tables():
    """Build the lexer/parser modules."""
    print("Building lexer and parser tables.", file=sys.stderr)
    root_dir = os.path.abspath(os.path.dirname(__file__))
    sys.path.insert(0, root_dir)
    from xonsh.parser import Parser
    from xonsh.parsers.completion_context import CompletionContextParser

    Parser(
        yacc_table="parser_table",
        outputdir=os.path.join(root_dir, "xonsh"),
        yacc_debug=True,
    )
    CompletionContextParser(
        yacc_table="completion_parser_table",
        outputdir=os.path.join(root_dir, "xonsh"),
        debug=True,
    )
    sys.path.pop(0)


def dirty_version():
    """
    If install/sdist is run from a git directory (not a conda install), add
    a devN suffix to reported version number and write a gitignored file
    that holds the git hash of the current state of the repo to be queried
    by ``xonfig``
    """
    try:
        _version = subprocess.check_output(["git", "describe", "--tags"])
    except Exception:
        print("failed to find git tags", file=sys.stderr)
        return False
    _version = _version.decode("ascii")
    try:
        _, N, sha = _version.strip().split("-")
    except ValueError:  # tag name may contain "-"
        print("failed to parse git version", file=sys.stderr)
        return False
    sha = sha.strip("g")
    replace_version(N)
    _cmd = ["git", "show", "-s", "--format=%cd", "--date=local", sha]
    try:
        _date = subprocess.check_output(_cmd)
        _date = _date.decode("ascii")
        # remove weekday name for a shorter string
        _date = " ".join(_date.split()[1:])
    except:
        _date = ""
        print("failed to get commit date", file=sys.stderr)
    with open("xonsh/dev.githash", "w") as f:
        f.write(f"{sha}|{_date}")
    print("wrote git version: " + sha, file=sys.stderr)
    return True


ORIGINAL_VERSION_LINE = None


def replace_version(N):
    """Replace version in `__init__.py` with devN suffix"""
    global ORIGINAL_VERSION_LINE
    with open("xonsh/__init__.py") as f:
        raw = f.read()
    lines = raw.splitlines()
    msg_assert = "__version__ must be the first line of the __init__.py"
    assert "__version__" in lines[0], msg_assert
    ORIGINAL_VERSION_LINE = lines[0]
    lines[0] = lines[0].rstrip(' "') + f'.dev{N}"'
    upd = "\n".join(lines) + "\n"
    with open("xonsh/__init__.py", "w") as f:
        f.write(upd)


def restore_version():
    """If we touch the version in __init__.py discard changes after install."""
    if ORIGINAL_VERSION_LINE is None:
        return
    with open("xonsh/__init__.py") as f:
        raw = f.read()
    lines = raw.splitlines()
    lines[0] = ORIGINAL_VERSION_LINE
    upd = "\n".join(lines) + "\n"
    with open("xonsh/__init__.py", "w") as f:
        f.write(upd)


class xbuild_py(build_py):
    """Xonsh specialization of setuptools build_py class."""

    def run(self):
        clean_tables()
        build_tables()
        amalgamate_source()
        # add dirty version number
        dirty = dirty_version()
        super().run()
        if dirty:
            restore_version()


class xinstall(install):
    """Xonsh specialization of setuptools install class.
    For production, let setuptools generate the
    startup script, e.g: `pip installl .' rather than
    relying on 'python setup.py install'."""

    def run(self):
        clean_tables()
        build_tables()
        amalgamate_source()
        # add dirty version number
        dirty = dirty_version()

        super().run()
        if dirty:
            restore_version()


class xsdist(sdist):
    """Xonsh specialization of setuptools sdist class."""

    def make_release_tree(self, basedir, files):
        clean_tables()
        build_tables()
        amalgamate_source()
        dirty = dirty_version()
        files.extend(TABLES)
        super().make_release_tree(basedir, files)
        if dirty:
            restore_version()


# Hack to overcome pip/setuptools problem on Win 10.  See:
#   https://github.com/tomduck/pandoc-eqnos/issues/6
#   https://github.com/pypa/pip/issues/2783

# Custom install_scripts command class for setup()
class install_scripts_quoted_shebang(install_scripts):
    """Ensure there are quotes around shebang paths with spaces."""

    def write_script(self, script_name, contents, mode="t", *ignored):
        shebang = str(contents.splitlines()[0])
        if (
            shebang.startswith("#!")
            and " " in shebang[2:].strip()
            and '"' not in shebang
        ):
            quoted_shebang = '#!"%s"' % shebang[2:].strip()
            contents = contents.replace(shebang, quoted_shebang)
        super().write_script(script_name, contents, mode, *ignored)


class install_scripts_rewrite(install_scripts):
    """Change default python3 to the concrete python binary used to install/develop inside xon.sh script"""

    def run(self):
        super().run()
        if not self.dry_run:
            for file in self.get_outputs():
                if file.endswith("xon.sh"):
                    # this is the value distutils use on its shebang translation
                    bs_cmd = self.get_finalized_command("build_scripts")
                    exec_param = getattr(bs_cmd, "executable", None)

                    with open(file) as f:
                        content = f.read()

                    processed = content.replace(" python3 ", f' "{exec_param}" ')

                    with open(file, "w") as f:
                        f.write(processed)


# The custom install needs to be used on Windows machines
cmdclass = {
    "install": xinstall,
    "sdist": xsdist,
    "build_py": xbuild_py,
}
if os.name == "nt":
    cmdclass["install_scripts"] = install_scripts_quoted_shebang
else:
    cmdclass["install_scripts"] = install_scripts_rewrite


class xdevelop(develop):
    """Xonsh specialization of setuptools develop class."""

    def run(self):
        clean_tables()
        build_tables()
        dirty = dirty_version()
        develop.run(self)
        if dirty:
            restore_version()

    def install_script(self, dist, script_name, script_text, dev_path=None):
        if script_name == "xon.sh":
            # change default python3 to the concrete python binary used to install/develop inside xon.sh script
            script_text = script_text.replace(" python3 ", f' "{sys.executable}" ')
        super().install_script(dist, script_name, script_text, dev_path)


def main():
    """The main entry point."""
    try:
        if "--name" not in sys.argv:
            logo_fname = os.path.join(os.path.dirname(__file__), "logo.txt")
            with open(logo_fname, "rb") as f:
                logo = f.read().decode("utf-8")
            print(logo)
    except UnicodeEncodeError:
        pass
    with open(os.path.join(os.path.dirname(__file__), "README.rst")) as f:
        readme = f.read()
    scripts = ["scripts/xon.sh"]
    skw = dict(
        name="xonsh",
        description="Python-powered, cross-platform, Unix-gazing shell",
        long_description=readme,
        license="BSD",
        version=XONSH_VERSION,
        author="Anthony Scopatz",
        maintainer="Anthony Scopatz",
        author_email="scopatz@gmail.com",
        url="https://xon.sh",
        platforms="Cross Platform",
        project_urls={
            "Changelog": "https://github.com/xonsh/xonsh/blob/main/CHANGELOG.rst",
            "Repository": "https://github.com/xonsh/xonsh",
            "Documentation": "https://xon.sh/contents.html",
            "Issue tracker": "https://github.com/xonsh/xonsh/issues",
        },
        classifiers=[
            "Development Status :: 4 - Beta",
            "Environment :: Console",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: BSD License",
            "Natural Language :: English",
            "Operating System :: OS Independent",
            "Programming Language :: Python :: 3 :: Only",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3",
            "Topic :: System :: Shells",
            "Topic :: System :: System Shells",
        ],
        keywords="python shell cli command-line prompt xonsh",
        packages=[
            "xonsh",
            "xonsh.ply.ply",
            "xonsh.ptk_shell",
            "xonsh.procs",
            "xonsh.parsers",
            "xonsh.xoreutils",
            "xontrib",
            "xonsh.completers",
            "xonsh.history",
            "xonsh.prompt",
            "xonsh.lib",
            "xonsh.webconfig",
            "xompletions",
        ],
        package_dir={
            "xonsh": "xonsh",
            "xontrib": "xontrib",
            "xompletions": "xompletions",
            "xonsh.lib": "xonsh/lib",
            "xonsh.webconfig": "xonsh/webconfig",
        },
        package_data={
            "xonsh": ["*.json", "*.githash"],
            "xontrib": ["*.xsh"],
            "xonsh.lib": ["*.xsh"],
            "xonsh.webconfig": [
                "*.html",
                "js/app.min.js",
                "js/bootstrap.min.css",
                "js/LICENSE-bootstrap",
            ],
        },
        cmdclass=cmdclass,
        scripts=scripts,
    )
    # We used to avoid setuptools 'console_scripts' due to startup performance
    # concerns which have since been resolved, so long as install is done
    # via `pip install .` and not `python setup.py install`.
    skw["entry_points"] = {
        "pygments.lexers": [
            "xonsh = xonsh.pyghooks:XonshLexer",
            "xonshcon = xonsh.pyghooks:XonshConsoleLexer",
        ],
        "pytest11": ["xonsh = xonsh.pytest_plugin"],
        "console_scripts": [
            "xonsh = xonsh.main:main",
            "xonsh-cat = xonsh.xoreutils.cat:main",
            "xonsh-uname = xonsh.xoreutils.uname:main",
            "xonsh-uptime = xonsh.xoreutils.uptime:main",
        ],
    }
    skw["cmdclass"]["develop"] = xdevelop
    skw["extras_require"] = {
        "ptk": ["prompt-toolkit>=3.0", "pyperclip"],
        "pygments": ["pygments>=2.2"],
        "mac": ["gnureadline"],
        "linux": ["distro"],
        "proctitle": ["setproctitle"],
        "zipapp": ['importlib_resources; python_version < "3.7"'],
        "full": [
            "prompt-toolkit>=3",
            "pyperclip",
            "pygments>=2.2",
            "distro; platform_system=='Linux'",  # PEP 508 platform specifiers
            "setproctitle; platform_system=='Windows'",
            "gnureadline; platform_system=='Darwin'",
        ],
    }
    skw["python_requires"] = ">=3.7"
    setup(**skw)


if __name__ == "__main__":
    main()
