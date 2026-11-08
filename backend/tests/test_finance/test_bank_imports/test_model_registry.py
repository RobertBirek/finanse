import subprocess
import sys


def test_application_registers_import_tables_before_document_lifecycle_queries() -> None:
    """A targeted legacy document test must not depend on collecting importer tests first."""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            (
                "import app.main; from app.database import Base; "
                "assert 'bank_import_sources' in Base.metadata.tables, "
                "'Import tables must exist before a document lifecycle query can use them'"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
