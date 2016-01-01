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
from qgis.gui import *
from PyQt4.QtGui import QAction, QMainWindow
from PyQt4.QtCore import *
import processing

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
        self.network_layer = []
        self.tied_points = []
        self.police_points_osmid = []
        self.fire_points_osmid = []
        self.tied_points_police = []
        self.tied_points_fire = []
        self.tied_points_incidents = []
        self.graph = QgsGraph()

        # define legend maplayers
        self.roads = uf.getLegendLayerByName(self.iface, 'Roads')  # QVectorLayer
        self.locations = uf.getLegendLayerByName(self.iface, 'Emergency Locations')  # QVectorLayer
        self.incidents = uf.getLegendLayerByName(self.iface, 'Incidents')  # QVectorLayer
        self.service_area_police = uf.getLegendLayerByName(iface, 'Service Area Police')
        self.service_area_fire = uf.getLegendLayerByName(iface, 'Service Area Fire Brigade')

        # get global feature data
        self.incidentData = uf.getAllFeatures(self.incidents)
        self.incidentAtt = []
        for item in self.incidentData.items():
            self.incidentAtt.append(item[1].attributes())

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
        self.service_area_police.setScaleBasedVisibility(True)
        self.service_area_fire.setMaximumScale(1.0)
        self.service_area_fire.setScaleBasedVisibility(True)
        self.service_area_fire.setMaximumScale(1.0)
        self.buildNetwork()
        #self.calculateServiceArea(self.tied_points_police, 'Police',  1500, True)
        self.formatTable(self.incidents)

        self.calculateRoutes()

        # draw standalone canvas
        w = MyWnd(self.iface.activeLayer())
        w.show()

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
    def cleanIncidents(self, layer):
        pass

        """
        layer.startEditing()
        features = uf.getAllFeatureIds(layer)
        for feature in features:
            layer.changeAttributeValue(feature, 6, 'false')

        layer.commitChanges()
        uf.reloadLayer(layer)
        """

    def formatTable(self, layer):
        if layer:
            self.reportTable.setColumnCount(5)
            self.reportTable.setHorizontalHeaderLabels(["Timestamp", "Subtype", "Dispatch","Resolved","Department"])
            features = uf.getAllFeatures(layer)
            self.reportTable.setRowCount(len(features))
            fieldnames = uf.getFieldNames(layer)
            attributesTimestamp = uf.getFieldValues(layer, fieldnames[0], null=True, selection=False)[0]
            attributesSubtype = uf.getFieldValues(layer, fieldnames[2], null=True, selection=False)[0]
            attributesDispatch = uf.getFieldValues(layer, fieldnames[6], null=True, selection=False)[0]
            attributesResolved = uf.getFieldValues(layer, fieldnames[7], null=True, selection=False)[0]


            for i in range(len(features)):
                self.reportTable.setItem(i, 0, QtGui.QTableWidgetItem(str(attributesTimestamp[i])))
                self.reportTable.setItem(i, 1, QtGui.QTableWidgetItem(str(attributesSubtype[i])))
                self.reportTable.setItem(i, 2, QtGui.QTableWidgetItem(str(attributesDispatch[i])))
                self.reportTable.setItem(i, 3, QtGui.QTableWidgetItem(str(attributesResolved[i])))
                self.reportTable.setItem(i, 4, QtGui.QTableWidgetItem("None"))

            self.reportTable.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(2, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(3, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(4, QtGui.QHeaderView.Stretch)
            self.reportTable.resizeRowsToContents()


    def getNetwork(self):
        roads_layer = self.roads
        if roads_layer:
            # see if there is an obstacles layer to subtract roads from the network
            obstacles_layer = self.incidents
            if obstacles_layer:
                # retrieve roads outside obstacles (inside = False)
                features = uf.getFeaturesByIntersection(roads_layer, obstacles_layer, False)
                # add these roads to a new temporary layer
                road_network = uf.createTempLayer('Temp_Network', 'LINESTRING', roads_layer.crs().postgisSrid(), [], [])
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
            police_points = [feature.geometry().asPoint() for ids, feature in police_sources.items()]
            self.police_points_osmid = [feature.attributes()[0] for ids, feature in police_sources.items()]
            len_police = len(police_points)
            source_points.extend(police_points)
            fire_sources = uf.getFeaturesByExpression(self.locations, """\"type\"=\'fire_station\'""")
            fire_points = [feature.geometry().asPoint() for ids, feature in fire_sources.items()]
            self.fire_points_osmid = [feature.attributes()[0] for ids, feature in fire_sources.items()]
            len_fire = len(fire_points)
            source_points.extend(fire_points)
            selected_incidents = uf.getAllFeatures(self.incidents)
            source_incidents = [feature.geometry().asPoint() for ids, feature in selected_incidents.items()]
            total_points = source_points + source_incidents
            # build the graph including these points
            if len(total_points) > 1:
                self.graph, self.tied_points = uf.makeUndirectedGraph(self.network_layer, total_points)
                # the tied points are the new source_points on the graph
                if self.graph and self.tied_points:
                    self.tied_points_police = self.tied_points[0:(len_police)]
                    self.tied_points_fire = self.tied_points[len_police:(len_police+len_fire)]
                    self.tied_points_incidents = self.tied_points[(len_police+len_fire)::]
                    text = "network is built for %s locations and %s incidents (runtime: %s)" % (len(source_points), len(source_incidents), time.clock())
                    self.insertReport(text)
                    uf.showMessage(self.iface, text, type='Info', lev=3, dur=10)

    def calculateServiceArea(self, features, f_type, cutoff, shown=False):      # EMPTY TEMP OUTPUT LAYER !!!
        options = len(features)
        layer_name =  'Service_Area_%s' % str(cutoff)
        if options > 0:
            # empty list of serviceareas
            # origin is given as an index in the tied_points list
            for origin in range(len(features)):
                service_area = uf.calculateServiceArea(self.canvas, self.graph, features, origin, cutoff)
                area_layer = uf.getLegendLayerByName(self.iface, layer_name)
                # create one if it doesn't exist
                if not area_layer:
                    attribs = ['cost']
                    types = [QtCore.QVariant.Double]
                    area_layer = uf.createTempLayer(layer_name,'POINT',self.network_layer.crs().postgisSrid(), attribs, types)
                    uf.loadTempLayer(area_layer,shown=True)
                # insert service area points
                geoms = []
                values = []
                for point in service_area.itervalues():
                    # each point is a tuple with geometry and cost
                    geoms.append(point[0])
                    # in the case of values, it expects a list of multiple values in each item - list of lists
                    values.append([cutoff])
                uf.insertTempFeatures(area_layer, geoms, values)
                self.refreshCanvas()
            area_layer = uf.getLegendLayerByName(self.iface, layer_name)
            if area_layer:
                attribs = ['cost']
                types = [QtCore.QVariant.Double]
                output_layer = uf.createTempLayer(('Service_Area '+f_type),'POLYGON',self.network_layer.crs().postgisSrid(), attribs, types)
                uf.loadTempLayer(output_layer,shown=False)
                layer = processing.runandload('qgis:concavehull', area_layer, 0.3, False, False, None)
                self.insertReport(str(layer))

    def calculateRoutes(self):
        policeData = uf.getFeaturesByExpression(self.locations, """\"type\"=\'police\'""")
        policeAtt = []
        for item in policeData.items():
            policeAtt.append(item[1].attributes())

        fireData = uf.getFeaturesByExpression(self.locations, """\"type\"=\'fire_station\'""")
        fireAtt = []
        for item in fireData.items():
            fireAtt.append(item[1].attributes())

        # origin and destination must be in the set of tied_points
        origin_set = self.tied_points_incidents
        range_police = range(0,len(self.tied_points_police))
        range_fire = range(len(self.tied_points_police),len(self.tied_points_police)+len(self.tied_points_fire))
        range_incidents = range(len(self.tied_points_police)+len(self.tied_points_fire)-1,len(self.tied_points)-1)
        layer = uf.getLegendLayerByName(self.iface,"Shortest Routes")

        for i,origin in enumerate(range_incidents):
            # depending on necesairy departments, destination is either police or fire or both
            police_att_incident = self.incidentData.items()[i][1][8]
            self.insertReport(str(police_att_incident))
            fire_att_incident = self.incidentData.items()[i][1][9]
            timestamp_att_incident = self.incidentData.items()[i][1][0]

            if police_att_incident == 'true':
                path_list = []
                cost_list = []
                osmid_list = []
                for n, destination in enumerate(range_police):
                    police_att_asset = policeData.items()[n][1][4]
                    if police_att_asset > 0:
                        # calculate the shortest path for the given origin and destination
                        path,cost = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                        path_list.append(QgsGeometry.fromPolyline(path))
                        cost_list.append(cost)
                        osmid_list.append(policeData.items()[n][1][0])
                    else:
                        continue
                # sort path list on cost
                cost_path_osmid = zip(cost_list, path_list,osmid_list)
                sorted_path = sorted(cost_path_osmid)
                route_cost,route_path, route_osmid = zip(*sorted_path)
                # store the route results in layer called "Shortest Routes"
                layer = uf.getLegendLayerByName(self.iface,"Shortest Routes")
                # insert route line
                feat = QgsFeature(layer.pendingFields())
                feat.setAttributes([[0, timestamp_att_incident], [1,route_cost[0]], [2,route_osmid[0]]])
                # Or set a single attribute by key or by index:
                #feat.setAttribute('name', 'hello')
                #feat.setAttribute(0, 'hello')
                feat.setGeometry(route_path[0])
                (res, outFeats) = layer.dataProvider().addFeatures([feat])

                self.insertReport(str(type(route_path[0])))
            if fire_att_incident == 'true':
                path_list = []
                cost_list = []
                osmid_list = []
                for n,destination in enumerate(range_fire):
                    fire_att_asset = fireData.items()[n][1][4]
                    if fire_att_asset > 0:
                        # calculate the shortest path for the given origin and destination
                        path,cost = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                        path_list.append(QgsGeometry.fromPolyline(path))
                        cost_list.append(cost)
                        osmid_list.append(fireData.items()[n][1][0])
                    else:
                        continue
                # sort path list on cost
                cost_path_osmid = zip(cost_list, path_list,osmid_list)
                sorted_path = sorted(cost_path_osmid)
                route_cost,route_path, route_osmid = zip(*sorted_path)
                # store the route results in layer called "Shortest Routes"
                layer = uf.getLegendLayerByName(self.iface,"Shortest Routes")
                # insert route line
                feat = QgsFeature(layer.pendingFields())
                feat.setAttributes([[0, timestamp_att_incident], [1,route_cost[0]], [2,route_osmid[0]]])
                # Or set a single attribute by key or by index:
                #feat.setAttribute('name', 'hello')
                #feat.setAttribute(0, 'hello')
                feat.setGeometry(route_path[0])
                (res, outFeats) = layer.dataProvider().addFeatures([feat])
        self.refreshCanvas()

    def updateShortestRoute(self):
        att_list = uf.getFieldValues(self.locations,'assets')
        if 0 not in att_list:
            policeData = uf.getFeaturesByExpression(self.locations, """\"type\"=\'police\'""")
            policeAtt = []
            for item in policeData.items():
                policeAtt.append(item[1].attributes())

            fireData = uf.getFeaturesByExpression(self.locations, """\"type\"=\'fire_station\'""")
            fireAtt = []
            for item in fireData.items():
                fireAtt.append(item[1].attributes())

            # origin and destination must be in the set of tied_points
            origin_set = self.tied_points_incidents
            range_police = range(0,len(self.tied_points_police))
            range_fire = range(len(self.tied_points_police),len(self.tied_points_police)+len(self.tied_points_fire))
            range_incidents = range(len(self.tied_points_police)+len(self.tied_points_fire)-1,len(self.tied_points)-1)
            layer = uf.getLegendLayerByName(self.iface,"Shortest Routes")

            for i,origin in enumerate(range_incidents):
                # depending on necesairy departments, destination is either police or fire or both
                police_att_incident = self.incidentData[i][8]
                fire_att_incident = self.incidentData[i][9]
                timestamp_att_incident = self.incidentData[i][0]

                if police_att_incident == 'true':
                    path_list = []
                    cost_list = []
                    osmid_list = []
                    for n, destination in enumerate(range_police):
                        police_att_asset = policeData[n][4]
                        if police_att_asset > 0:
                            # calculate the shortest path for the given origin and destination
                            path,cost = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                            path_list.append(QgsGeometry.fromPolyline(path))
                            cost_list.append(cost)
                            osmid_list.append(policeData[n][0])
                        else:
                            continue
                    # sort path list on cost
                    cost_path_osmid = zip(cost_list, path_list,osmid_list)
                    sorted_path = sorted(cost_path_osmid)
                    route_cost,route_path, route_osmid = zip(*sorted_path)
                    # store the route results in layer called "Shortest Routes"
                    layer = uf.getLegendLayerByName(self.iface,"Shortest Routes")
                    # insert route line
                    feat = QgsFeature(layer.pendingFields())
                    feat.setAttributes([[0, timestamp_att_incident], [1,route_cost[0]], [2,route_osmid[0]]])
                    # Or set a single attribute by key or by index:
                    #feat.setAttribute('name', 'hello')
                    #feat.setAttribute(0, 'hello')
                    feat.setGeometry(route_path[0])
                    (res, outFeats) = layer.dataProvider().addFeatures([feat])

                    self.insertReport(str(type(route_path[0])))
                if fire_att_incident == 'true':
                    path_list = []
                    cost_list = []
                    for n,destination in enumerate(range_fire):
                        fire_att_asset = fireData[n][4]
                        if fire_att_asset > 0:
                            # calculate the shortest path for the given origin and destination
                            path,cost = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                            path_list.append(QgsGeometry.fromPolyline(path))
                            cost_list.append(cost)
                            osmid_list.append(fireData[n][0])
                        else:
                            continue
                    # sort path list on cost
                    cost_path_osmid = zip(cost_list, path_list,osmid_list)
                    sorted_path = sorted(cost_path_osmid)
                    route_cost,route_path, route_osmid = zip(*sorted_path)
                    # store the route results in layer called "Shortest Routes"
                    layer = uf.getLegendLayerByName(self.iface,"Shortest Routes")
                    # insert route line
                    feat = QgsFeature(layer.pendingFields())
                    feat.setAttributes([[0, timestamp_att_incident], [1,route_cost[0]], [2,route_osmid[0]]])
                    # Or set a single attribute by key or by index:
                    #feat.setAttribute('name', 'hello')
                    #feat.setAttribute(0, 'hello')
                    feat.setGeometry(route_path[0])
                    (res, outFeats) = layer.dataProvider().addFeatures([feat])
            self.refreshCanvas()
        else:
            return

#######
#    SOLVE
#######
    def open_police_sa(self):
        if self.policeSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'button checked'
            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_police.setScaleBasedVisibility(False)
        else:
            # checked = false: hide layer
            text = 'button unchecked'
            # uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_police.setScaleBasedVisibility(True)

    def open_fire_sa(self):
        if self.fireSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'button checked'
            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_police.setScaleBasedVisibility(False)

        else:
            # checked = false: hide layer
            text = 'button unchecked'
            # uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_police.setScaleBasedVisibility(True)

    def dispatch(self):
        selected = self.reportTable.selectedItems()
        if selected == []:
            return
        else:
            rowList = []
            for item in selected:
                rownumb = self.reportTable.row(item)
                if rownumb not in rowList:
                    rowList.append(rownumb)

            self.incidents.startEditing()
            for rownumber in rowList:
                self.reportTable.setItem(rownumber,2,QtGui.QTableWidgetItem('true'))

                feature = []
                timestamp = int(self.reportTable.item(rownumber,0).text())
                feature = uf.getFeatureIdsByListValues(self.incidents,'timestamp',[timestamp])
                self.insertReport(str(feature))
                self.incidents.changeAttributeValue(feature[0], 6, 'true')
            self.incidents.commitChanges()

            text = 'Dispatched'
            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
        # change asset count of emergency location -1

    def resolve(self):
        selected = self.reportTable.selectedItems()
        if selected == []:
            return
        else:
            rowList = []
            for item in selected:
                rownumb = self.reportTable.row(item)
                if rownumb not in rowList:
                    rowList.append(rownumb)

            self.incidents.startEditing()
            for rownumber in rowList:
                self.reportTable.setItem(rownumber,3,QtGui.QTableWidgetItem('true'))

                feature = []
                timestamp = int(self.reportTable.item(rownumber,0).text())
                feature = uf.getFeatureIdsByListValues(self.incidents,'timestamp',[timestamp])
                self.insertReport(str(feature))
                self.incidents.changeAttributeValue(feature[0], 7, 'true')
            self.incidents.commitChanges()
        text = 'Resolved'
        uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
        # change asset count of emergency location +1

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
    def refreshCanvas(self):
        if self.canvas.isCachingEnabled():
            self.canvas.clearCache()
        else:
            self.canvas.refresh()

    def updateLayers(self):
        layers = uf.getLegendLayers(self.iface, 'all', 'all')

    def setSelectedLayer(self):
        layer_name = self.selectLayerCombo.currentText()
        layer = uf.getLegendLayerByName(self.iface, layer_name)


class MyWnd(QMainWindow):
    def __init__(self, layer):
        QMainWindow.__init__(self)

        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(Qt.white)

        self.canvas.setExtent(layer.extent())
        self.canvas.setLayerSet([QgsMapCanvasLayer(layer)])

        self.setCentralWidget(self.canvas)

        actionZoomIn = QAction("Zoom in", self)
        actionZoomOut = QAction("Zoom out", self)
        actionPan = QAction("Pan", self)

        actionZoomIn.setCheckable(True)
        actionZoomOut.setCheckable(True)
        actionPan.setCheckable(True)

        self.connect(actionZoomIn, SIGNAL("triggered()"), self.zoomIn)
        self.connect(actionZoomOut, SIGNAL("triggered()"), self.zoomOut)
        self.connect(actionPan, SIGNAL("triggered()"), self.pan)

        self.toolbar = self.addToolBar("Canvas actions")
        self.toolbar.addAction(actionZoomIn)
        self.toolbar.addAction(actionZoomOut)
        self.toolbar.addAction(actionPan)

        # create the map tools
        self.toolPan = QgsMapToolPan(self.canvas)
        self.toolPan.setAction(actionPan)
        self.toolZoomIn = QgsMapToolZoom(self.canvas, False) # false = in
        self.toolZoomIn.setAction(actionZoomIn)
        self.toolZoomOut = QgsMapToolZoom(self.canvas, True) # true = out
        self.toolZoomOut.setAction(actionZoomOut)

        self.pan()

    def zoomIn(self):
        self.canvas.setMapTool(self.toolZoomIn)

    def zoomOut(self):
        self.canvas.setMapTool(self.toolZoomOut)

    def pan(self):
        self.canvas.setMapTool(self.toolPan)