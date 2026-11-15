"""Qlippy: a paperclip assistant for QGIS that helps, and harasses."""


def classFactory(iface):  # noqa: N802 (QGIS API)
    from .plugin import QlippyPlugin

    return QlippyPlugin(iface)
