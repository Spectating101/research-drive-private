"""Research integrity tooling: fingerprinting, DSR/PBO, attribution, costs, factors."""

from pathlib import Path

# The monorepo keeps newer research capabilities under ``alpha/src/research``
# while legacy compatibility modules remain in this package.  Pytest and
# long-running services can import the root ``src`` package before adding the
# Alpha tree to sys.path, so expose both locations through one package path.
_alpha_research = Path(__file__).resolve().parents[2] / "alpha" / "src" / "research"
if _alpha_research.is_dir():
    __path__.append(str(_alpha_research))

from src.research.fingerprint import make_fingerprint, stamp

__all__ = ["make_fingerprint", "stamp"]
