# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TwisterSolutions
                                 A QGIS plugin
 Storm
                             -------------------
        begin                : 2015-12-07
        copyright            : (C) 2015 by OT Willems & C Nijmeijer
        email                : oscarwillems+geo1005@gmail.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load TwisterSolutions class from file TwisterSolutions.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .Storm import TwisterSolutions
    return TwisterSolutions(iface)
