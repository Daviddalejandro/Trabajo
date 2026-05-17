"""Entry point de la aplicacion Windows."""
from __future__ import annotations

import sys

from .config import settings
from .logging_config import configure_logging, get_logger


def run() -> int:
    """Inicia la app PyQt6.

    Importamos PyQt6 dentro de la funcion para que tareas headless (CLI,
    tests, generacion de plantillas) no requieran Qt instalado.
    """
    configure_logging()
    log = get_logger(__name__)
    log.info("Iniciando {} v{}", settings.app_name, settings.app_version)

    from PyQt6.QtWidgets import QApplication

    # Nota: en PyQt6 el high-DPI scaling es automatico (no requiere
    # AA_EnableHighDpiScaling, esa flag se removio en Qt6).
    app = QApplication(sys.argv)
    app.setApplicationName(settings.app_name)
    app.setOrganizationName("BPMN Platform")

    from .ui.main_window import create_main_window

    window = create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
