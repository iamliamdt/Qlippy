"""Small Qt5/Qt6 compatibility helpers."""

from qgis.PyQt import QtGui, QtWidgets

# QAction lives in QtGui on Qt6 and in QtWidgets on Qt5.
QAction = getattr(QtGui, "QAction", None) or getattr(QtWidgets, "QAction")


def event_pos(ev):
    """Widget-local position of a mouse event as QPoint."""
    if hasattr(ev, "position"):
        return ev.position().toPoint()
    return ev.pos()


def event_global_pos(ev):
    """Global position of a mouse event as QPoint."""
    if hasattr(ev, "globalPosition"):
        return ev.globalPosition().toPoint()
    return ev.globalPos()
