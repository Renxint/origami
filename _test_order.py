
from PyQt6.QtCore import Qt
from PyQt6.QtNetwork import QLocalSocket  # This is what setup_single_instance uses
# Now try the lazy import
from src.gui.dialogs.webview_login import _ensure_webengine
QEV, QEP, QEPg = _ensure_webengine()
print('OK - WebEngine loaded AFTER QtNetwork')

