# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Gisquick plugin
 Publish your projects into Gisquick application
 ***************************************************************************/
"""
from __future__ import absolute_import

def classFactory(iface):
    from .webgisplugin import WebGisPlugin
    return WebGisPlugin(iface)
