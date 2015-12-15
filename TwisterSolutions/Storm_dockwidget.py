# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GEO1005DockWidget
                            A QGIS plugin
 SDSS Test
                            -------------------
        begin                : 2015-11-20
        git sha              : $Format:%H$
        copyright            : (C) 2015 by OT Willems & C Nijmeijer
        email                : oscarwillems+geo1005@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt4 import QtGui, QtCore, uic
from qgis.core import *
from qgis.networkanalysis import *
# Initialize Qt resources from file resources.py
import resources
import time


import os
import os.path
import random

from . import utility_functions as uf


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'Storm_dockwidget_base.ui'))


class TwisterSolutionsDockWidget(QtGui.QDockWidget, FORM_CLASS):

    closingPlugin = QtCore.pyqtSignal()
    # custom signals
    updateAttribute = QtCore.pyqtSignal(str)

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(TwisterSolutionsDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        # define globals
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.roads = uf.getLegendLayerByName(self.iface, 'Roads')  # QVectorLayer
        self.locations = uf.getLegendLayerByName(self.iface, 'Emergency Locations')  # QVectorLayer
        self.incidents = uf.getLegendLayerByName(self.iface, 'Incidents')  # QVectorLayer

        self.graph = QgsGraph()
        self.tied_points = []

        # set up GUI operation signals
        self.iface.projectRead.connect(self.updateLayers)
        self.iface.newProjectCreated.connect(self.updateLayers)

        # Solve
        self.policeSAButton.clicked.connect(self.open_police_sa)
        self.fireSAButton.clicked.connect(self.open_fire_sa)
        self.dispatchButton.clicked.connect(self.dispatch)
        self.resolveButton.clicked.connect(self.resolve)

        # Report

        # Initialize
        self.buildNetwork()
        self.formatTable(self.incidents)
        self.calculateServiceArea(self.tied_points_police, 'Police',  1500, True)
        self.open_police_sa()
        self.open_fire_sa()

    def closeEvent(self, event):
        # disconnect interface signals
        self.iface.projectRead.disconnect(self.updateLayers)
        self.iface.newProjectCreated.disconnect(self.updateLayers)

        self.closingPlugin.emit()
        event.accept()

#######
#    DATA
#######

#######
#    INITIALIZE
#######
    def formatTable(self,layer):
        self.reportTable.setColumnCount(4)
        self.reportTable.setHorizontalHeaderLabels(["Timestamp","Subtype","Dispatch","DepartmentID"])
        features = uf.getAllFeatures(layer)
        self.reportTable.setRowCount(len(features))
        fieldnames = uf.getFieldNames(layer)
        attributesTimestamp = uf.getFieldValues(layer, fieldnames[0], null=True, selection=False)[0]
        attributesSubtype = uf.getFieldValues(layer, fieldnames[2], null=True, selection=False)[0]
        attributesDispatch = uf.getFieldValues(layer, fieldnames[6], null=True, selection=False)[0]

        for i in range(len(features)):
            self.reportTable.setItem(i,0,QtGui.QTableWidgetItem(str(attributesTimestamp[i])))
            self.reportTable.setItem(i,1,QtGui.QTableWidgetItem(str(attributesSubtype[i])))
            self.reportTable.setItem(i,2,QtGui.QTableWidgetItem(str(attributesDispatch[i])))


    def getNetwork(self):
        roads_layer = self.roads
        if roads_layer:
            # see if there is an obstacles layer to subtract roads from the network
            obstacles_layer = self.incidents
            if obstacles_layer:
                # retrieve roads outside obstacles (inside = False)
                features = uf.getFeaturesByIntersection(roads_layer, obstacles_layer, False)
                # add these roads to a new temporary layer
                road_network = uf.createTempLayer('Temp_Network','LINESTRING',roads_layer.crs().postgisSrid(),[],[])
                road_network.dataProvider().addFeatures(features)
            else:
                road_network = roads_layer
            return road_network
        else:
            return

    def buildNetwork(self):
        time.clock()
        self.network_layer = self.getNetwork()
        if self.network_layer:
            # get the points to be used as origin and destination
            # in this case point location of each emergency service
            source_points = []
            police_sources = uf.getFeaturesByExpression(self.locations, """\"type\"=\'police\'""")
            fire_sources = uf.getFeaturesByExpression(self.locations, """\"type\"=\'fire_station\'""")
            police_points = [feature.geometry().asPoint() for id, feature in police_sources.items()]
            len_police = len(police_points)
            source_points.extend(police_points)
            fire_points = [feature.geometry().asPoint() for id, feature in fire_sources.items()]
            len_fire = len(fire_points)
            source_points.extend(fire_points)
            selected_incidents = uf.getAllFeatures(self.incidents)
            source_incidents = [feature.geometry().asPoint() for id, feature in selected_incidents.items()]
            total_points = source_points + source_incidents
            # build the graph including these points
            if len(total_points) > 1:
                self.graph, self.tied_points = uf.makeUndirectedGraph(self.network_layer, total_points)
                # the tied points are the new source_points on the graph
                if self.graph and self.tied_points:
                    self.tied_points_police = self.tied_points[0:(len_police-1)]
                    self.tied_points_fire = self.tied_points[len_police:(len_police+len_fire-1)]
                    self.tied_points_incidents = self.tied_points[(len_police+len_fire)::]
                    text = "network is built for %s locations and %s incidents (runtime: %s)" % (len(source_points), len(source_incidents), time.clock())
                    self.insertReport(text)
                    uf.showMessage(self.iface, text, type='Info', lev=3, dur=10)

    def calculateServiceArea(self, features, f_type, cutoff, shown=False):      # EMPTY TEMP OUTPUT LAYER !!!
        options = len(features)
        if options > 0:
            # empty list of serviceareas
            # origin is given as an index in the tied_points list
            for origin in range(len(features)):
                service_area, service_poly = uf.calculateServiceArea(self.canvas, self.graph, features, origin, cutoff)
                # store the service area results in temporary layer called "Service_Area"
                area_layer = uf.getLegendLayerByName(self.iface, "Service Area "+f_type)
                # create one if it doesn't exist
                if not area_layer:
                    attribs = ['cost']
                    types = [QtCore.QVariant.Double]
                    area_layer = uf.createTempLayer('Service Area '+f_type, 'POLYGON', self.network_layer.crs().postgisSrid(), attribs, types)
                    uf.loadTempLayer(area_layer, shown)  # False -> Keeps layer hidden
                # insert service area
                geoms = service_poly.asPolygon()
                values = cutoff
                uf.insertTempFeatures(area_layer, geoms, values)
                uf.showMessage(self.iface, 'Check', type='Info', lev=3, dur=1)
                self.refreshCanvas(area_layer)

        """
        if show:
            # show layer
        else:
            # dont show layer

        """

    def calculateRoute(self):
        # origin and destination must be in the set of tied_points
        options = len(self.tied_points)
        if options > 1:
            # origin and destination are given as an index in the tied_points list
            # calculate the shortest path for the given origin and destination
            path = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
            # store the route results in temporary layer called "Routes"
            routes_layer = uf.getLegendLayerByName(self.iface, "Routes")
            # create one if it doesn't exist
            if not routes_layer:
                attribs = ['id']
                types = [QtCore.QVariant.String]
                routes_layer = uf.createTempLayer('Routes','LINESTRING',self.network_layer.crs().postgisSrid(), attribs, types)
                uf.loadTempLayer(routes_layer)
            # insert route line
            uf.insertTempFeatures(routes_layer, [path], [['testing',100.00]])
            self.refreshCanvas(routes_layer)

#######
#    SOLVE
#######
    def open_police_sa(self):
        if self.policeSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'button checked'
            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            """
            layer = get(hidden layer)
            if layer:
                pass
                # Show Layer
            else:
                # calculate service area and show layer
                self.calculateServiceArea(self.tied_points_police, 'Police',  15)
            """
        else:
            # checked = false: hide layer
            text = 'button unchecked'
            # uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            # layer.hide()

    def open_fire_sa(self):
        if self.fireSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'button checked'
            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            """
            layer = get(hidden layer)
            if layer:
                # Show Layer
            else:
                # calculate service area and show layer
                self.calculateServiceArea(self.tied_points_fire, 'Fire Brigade', 20)
            """
        else:
            # checked = false: hide layer
            text = 'button unchecked'
            # uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            # layer.hide()

    def dispatch(self):
        text = 'Dispatched'
        uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
        # change asset count of emergency location -1

    def resolve(self):
        text = 'Resolved'
        uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
        # change asset count of emergency location +1

        """
        if true count of feature field "obstructed" changes:
            # update graph and service area
            self.buildNetwork()
            self.open_police_sa()
            self.open_fire_sa()
        else:
            # keep graph and service area
            pass
        """
#######
#    REPORTING
#######
    # report window functions
    def updateReport(self, report):
        self.reportList.clear()
        self.reportList.addItems(report)

    def insertReport(self, item):
        self.reportList.insertItem(0, item)

    def clearReport(self):
        self.reportList.clear()

#######
#    QGIS
#######
    def refreshCanvas(self, layer):
        if self.canvas.isCachingEnabled():
            layer.setCacheImage(None)
        else:
            self.canvas.refresh()

    def updateLayers(self):
        layers = uf.getLegendLayers(self.iface, 'all', 'all')

    def setSelectedLayer(self):
        layer_name = self.selectLayerCombo.currentText()
        layer = uf.getLegendLayerByName(self.iface, layer_name)