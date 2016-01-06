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
    os.path.dirname(__file__), 'Storm_mainwindow_base.ui'))


class TwisterSolutionsMainWindow(QtGui.QMainWindow, FORM_CLASS):

    closingPlugin = QtCore.pyqtSignal()
    # custom signals
    updateAttribute = QtCore.pyqtSignal(str)

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(TwisterSolutionsMainWindow, self).__init__(parent)
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
        self.osmid_name = {}
        self.name_osmid = {}
        self.name_asset = {}
        self.timestamp_osmid = {}
        self.timestamp_geom = {}
        self.timestamp_QTableItemRow = {}

        # define legend maplayers
        self.roads = uf.getLegendLayerByName(self.iface, 'Roads')  # QVectorLayer
        self.locations = uf.getLegendLayerByName(self.iface, 'Emergency Locations')  # QVectorLayer
        self.incidents = uf.getLegendLayerByName(self.iface, 'Incidents')  # QVectorLayer
        self.service_area_police = uf.getLegendLayerByName(iface, 'Service Area Police')
        self.service_area_fire = uf.getLegendLayerByName(iface, 'Service Area Fire Brigade')
        self.shortest_routes = uf.getLegendLayerByName(iface, 'Shortest Routes')

        # empty output layers
        short_ids = uf.getAllFeatureIds(self.shortest_routes)
        res = self.shortest_routes.dataProvider().deleteFeatures(short_ids)

        # reset incidents
        self.cleanIncidents()

        # get/set global feature data
        self.incidentData = uf.getAllFeatures(self.incidents)
        self.incidentAtt = []
        for item in self.incidentData.items():
            self.incidentAtt.append(item[1].attributes())

        # set global dictionaries
        for item in zip(uf.getFieldValues(self.locations,'osm_id')[0],uf.getFieldValues(self.locations,'name')[0]):
            self.osmid_name[item[0]] = item[1]
        for item in zip(uf.getFieldValues(self.locations,'name')[0],uf.getFieldValues(self.locations,'Assets')[0]):
            self.name_asset[item[0]] = item[1]
        for item in zip(uf.getFieldValues(self.locations,'name')[0],uf.getFieldValues(self.locations,'osmid')[0]):
            self.name_osmid[item[0]] = item[1]

        # Initialize
        self.service_area_police.setScaleBasedVisibility(True)
        self.service_area_police.setMaximumScale(1.0)
        self.service_area_fire.setScaleBasedVisibility(True)
        self.service_area_fire.setMaximumScale(1.0)
        self.buildNetwork()
###self.calculateServiceArea(self.tied_points_police, 'Police',  1500, True)
        self.calculateRoutes()
        self.formatTable(self.incidents)

        # Set extent to the extent of our layer
        self.WidgetCanvas.setExtent(self.incidents.extent())

        # Set up the map canvas layer set
        layers = []
        for item in uf.getLegendLayers(self.iface):
            cl = QgsMapCanvasLayer(item)
            layers.append(cl)
        self.WidgetCanvas.setLayerSet(layers)

        # Solve
        self.policeSAButton.clicked.connect(self.open_police_sa)
        self.fireSAButton.clicked.connect(self.open_fire_sa)
        self.dispatchButton.clicked.connect(self.dispatch)
        self.resolveButton.clicked.connect(self.resolve)
        self.reportTable.itemSelectionChanged.connect(self.zoomToIncident)


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
    def cleanIncidents(self):
        attr = {6 : 'false', 7 : 'false'}
        ids = uf.getAllFeatureIds(self.incidents)
        attr_map = {}
        for id in ids:
            attr_map[id] = attr
        self.incidents.dataProvider().changeAttributeValues(attr_map)

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

            for item in list(enumerate(attributesTimestamp,1)):
                self.timestamp_QTableItemRow[item[1]] = item[0]

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
        self.refreshCanvas()


    """
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
                    uf.loadTempLayer(area_layer,shown)
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
    """

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
        range_incidents = range(len(self.tied_points_police)+len(self.tied_points_fire),len(self.tied_points))
        # store the route results in layer called "Shortest Routes"
        layer = self.shortest_routes
        fields = layer.pendingFields()
        for i,origin in list(enumerate(range_incidents)):
            # depending on necesairy departments, destination is either police or fire or both
            police_att_incident = self.incidentData.items()[i][1][8]
            fire_att_incident = self.incidentData.items()[i][1][9]
            timestamp_att_incident = self.incidentData.items()[i][1][0]
            incident_dispatched = self.incidentData.items()[i][1][6]
            dep_osmids = []
            if police_att_incident == 'true' and incident_dispatched == 'false':
                path_list = []
                cost_list = []
                osmid_list = []
                for n, destination in list(enumerate(range_police)):
                    police_att_asset = policeData.items()[n][1][4]
                    # if assets available: calculate route
                    if police_att_asset > 0:
                        # calculate the shortest path for the given origin and destination
                        path,__ = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                        line = QgsLineStringV2()
                        for point in path:
                            line.addVertex(QgsPointV2(point))
                        cost = line.length()
                        path_list.append(line)
                        cost_list.append(cost)
                        osmid_list.append(policeData.items()[n][1][0])
                    else:
                        continue

                # zip path list on cost
                cost_path_osmid = zip(cost_list, path_list,osmid_list)
                # sort path on cost
                sorted_path = sorted(cost_path_osmid, key=lambda path: path[0])
                sorted_paths = [x for x in sorted_path if x[0] != 0.0]
                route_cost,route_path, route_osmid = zip(*sorted_paths)
                # insert route line
                feat = QgsFeature(fields)
                # set attributes
                feat.setAttribute(fields[0].name(), timestamp_att_incident)
                feat.setAttribute(fields[1].name(), route_cost[0])
                feat.setAttribute(fields[2].name(), route_osmid[0])
                # set geometry
                feat.setGeometry(QgsGeometry(route_path[0]))
                # write feature to layer
                (res, outFeats) = layer.dataProvider().addFeatures([feat])
                # write timestamp : osmid to internal dictionary
                self.timestamp_osmid[timestamp_att_incident] = route_osmid[0]
                self.timestamp_geom[timestamp_att_incident] = path_list[0]
                dep_osmids.append(route_osmid[0])


            if fire_att_incident == 'true' and incident_dispatched == 'false':
                path_list = []
                cost_list = []
                osmid_list = []
                for n,destination in list(enumerate(range_fire)):
                    fire_att_asset = fireData.items()[n][1][4]
                    # if assets available: calculate route
                    if fire_att_asset > 0:
                        # calculate the shortest path for the given origin and destination
                        path,__ = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                        line = QgsLineStringV2()
                        for point in path:
                            line.addVertex(QgsPointV2(point))
                        cost = line.length()
                        path_list.append(line)
                        cost_list.append(cost)
                        osmid_list.append(fireData.items()[n][1][0])
                    else:
                        continue

                # zip path list on cost
                cost_path_osmid = zip(cost_list, path_list,osmid_list)
                # sort path on cost
                sorted_path = sorted(cost_path_osmid, key=lambda path: path[0])
                sorted_paths = [x for x in sorted_path if x[0] != 0.0]
                route_cost,route_path, route_osmid = zip(*sorted_paths)
                # insert route line
                feat = QgsFeature(fields)
                # set attributes
                feat.setAttribute(fields[0].name(), timestamp_att_incident)
                feat.setAttribute(fields[1].name(), route_cost[0])
                feat.setAttribute(fields[2].name(), route_osmid[0])
                # set geometry
                feat.setGeometry(QgsGeometry(route_path[0]))
                # write feature to layer
                (res, outFeats) = layer.dataProvider().addFeatures([feat])
                # write timestamp : osmid to internal dictionary
                self.timestamp_osmid[timestamp_att_incident] = route_osmid[0]
                self.timestamp_geom[timestamp_att_incident] = path_list[0]
                dep_osmids.append(route_osmid[0])

            if fire_att_incident == 'true' and police_att_incident == 'true':
                self.timestamp_osmid[timestamp_att_incident] = dep_osmids

        self.refreshCanvas()
        self.insertReport('Shortest Routes Calculated')
        self.assignDepartmentsToIncidents()

    def calculateClosestRoutes(self):
        """
        each incident find closes department, instead of calculating routes to every department construct a line and
        find shortest line, then calculate route
        """
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
        range_incidents = range(len(self.tied_points_police)+len(self.tied_points_fire),len(self.tied_points))
        # store the route results in layer called "Shortest Routes"
        layer = self.shortest_routes
        fields = layer.pendingFields()
        for i,origin in list(enumerate(range_incidents)):
            # depending on necesairy departments, destination is either police or fire or both
            police_att_incident = self.incidentData.items()[i][1][8]
            fire_att_incident = self.incidentData.items()[i][1][9]
            timestamp_att_incident = self.incidentData.items()[i][1][0]
            incident_dispatched = self.incidentData.items()[i][1][6]
            incident_resolved = self.incidentData.items()[i][1][7]
            dep_osmids = []
            if police_att_incident == 'true':
                line_list = []
                cost_list = []
                destination_list = []
                osmid_list = []
                for n,destination in list(enumerate(range_police)):
                    police_att_asset = fireData.items()[n][1][4]
                    # if assets available: calculate route
                    if police_att_asset > 0:
                        # from incident to department
                        line = QLineF(self.tied_points[origin].x(), self.tied_points[origin].y(),
                                      self.tied_points[destination].x(), self.tied_points[destination].y())
                        cost = line.length()
                        line_list.append(line)
                        cost_list.append(cost)
                        destination_list.append(destination)
                        osmid_list.append(fireData.items()[n][1][0])
                    else:
                        continue

                # zip path list on cost
                cost_line_tpdest_osmid = zip(cost_list, line_list, destination_list, osmid_list)
                # sort path on cost
                sorted_path = sorted(cost_line_tpdest_osmid, key=lambda path: path[0])
                route_to_calculate = sorted_path[0]
                path, __ = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, route_to_calculate[2])
                # insert route line
                feat = QgsFeature(fields)
                # set attributes
                feat.setAttribute(fields[0].name(), timestamp_att_incident) # TIMESTAMP
                feat.setAttribute(fields[1].name(), route_to_calculate[0])  # COST
                feat.setAttribute(fields[2].name(), route_to_calculate[3])  # OSMID
                # set geometry
                geometry = QgsGeometry.fromPolyline(path)
                feat.setGeometry(geometry)
                # write feature to layer
                (res, outFeats) = layer.dataProvider().addFeatures([feat])
                # write timestamp : osmid to internal dictionary
                self.timestamp_osmid[timestamp_att_incident] = route_to_calculate[3]
                self.timestamp_geom[timestamp_att_incident] = geometry
                dep_osmids.append(route_to_calculate[3])


            if fire_att_incident == 'true':
                line_list = []
                cost_list = []
                destination_list = []
                osmid_list = []
                for n,destination in list(enumerate(range_fire)):
                    fire_att_asset = fireData.items()[n][1][4]
                    # if assets available: calculate route
                    if fire_att_asset > 0:
                        # from incident to department
                        line = QLineF(self.tied_points[origin].x(), self.tied_points[origin].y(),
                                      self.tied_points[destination].x(), self.tied_points[destination].y())
                        cost = line.length()
                        line_list.append(line)
                        cost_list.append(cost)
                        destination_list.append(destination)
                        osmid_list.append(fireData.items()[n][1][0])
                    else:
                        continue

                # zip path list on cost
                cost_line_tpdest_osmid = zip(cost_list, line_list, destination_list, osmid_list)
                # sort path on cost
                sorted_path = sorted(cost_line_tpdest_osmid, key=lambda path: path[0])
                route_to_calculate = sorted_path[0]
                path, __ = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, route_to_calculate[2])
                # insert route line
                feat = QgsFeature(fields)
                # set attributes
                feat.setAttribute(fields[0].name(), timestamp_att_incident) # TIMESTAMP
                feat.setAttribute(fields[1].name(), route_to_calculate[0])  # COST
                feat.setAttribute(fields[2].name(), route_to_calculate[3])  # OSMID
                # set geometry
                geometry = QgsGeometry.fromPolyline(path)
                feat.setGeometry(geometry)
                # write feature to layer
                (res, outFeats) = layer.dataProvider().addFeatures([feat])
                # write timestamp : osmid to internal dictionary
                self.timestamp_osmid[timestamp_att_incident] = route_to_calculate[3]
                self.timestamp_geom[timestamp_att_incident] = geometry
                dep_osmids.append(route_to_calculate[3])

            if fire_att_incident == 'true' and police_att_incident == 'true':
                self.timestamp_osmid[timestamp_att_incident] = dep_osmids

        self.refreshCanvas()
        self.insertReport('Shortest Routes Calculated')
        self.assignDepartmentsToIncidents()

    def assignDepartmentsToIncidents(self):
        timestamps,__ = uf.getFieldValues(self.shortest_routes,'timestamp')
        osmids,__ = uf.getFieldValues(self.shortest_routes,'osmid')
        timestamp_osmid = zip(timestamps,osmids)
        set_timestamps = list(set(timestamps))
        self.insertReport('Assigning incidents to departments')

        # self.timestamps_osmid = dictonary of shortest routes with osmid


        """
        for item in set_timestamps:
            indexes = [i for i,x in enumerate(timestamp_osmid) if x[0] == item]
            self.insertReport(str(indexes))
            if len(indexes) == 1:
                row =  self.timestamp_QTableItemRow[timestamp_osmid[indexes[0]][0]]
                string = self.osmid_name[timestamp_osmid[indexes[0]][1]]
                self.reportTable.setItem(row, 4, QtGui.QTableWidgetItem(string))

            elif len(indexes) == 2:
                dep_a = timestamp_osmid[indexes[0]]
                dep_b = timestamp_osmid[indexes[1]]
                dep_names = self.osmid_name[dep_a]+", "+self.osmid_name[dep_b]
                self.reportTable.setItem(
                        self.timestamp_QTableItemRow[item[0]], 4, QtGui.QTableWidgetItem(dep_names))
            else:
                continue
        """

#######
#    SOLVE
#######
    def open_police_sa(self):
        if self.policeSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'Service Area Police checked'
            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_police.setScaleBasedVisibility(False)
        else:
            # checked = false: hide layer
            text = 'Service Area Police unchecked'
            # uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_police.setScaleBasedVisibility(True)
        self.refreshCanvas()


    def open_fire_sa(self):
        if self.fireSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'Service Area Fire checked'
            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_fire.setScaleBasedVisibility(False)

        else:
            # checked = false: hide layer
            text = 'Service Area Fire unchecked'
            # uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
            self.service_area_fire.setScaleBasedVisibility(True)
        self.refreshCanvas()


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
                if self.reportTable.item(rownumb,2).text() == 'true':
                    text = 'Allready dispatched'
                    uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
                else:
                    self.reportTable.setItem(rownumber,2,QtGui.QTableWidgetItem('true'))
                    timestamp = int(self.reportTable.item(rownumber,0).text())
                    feature = uf.getFeatureIdsByListValues(self.incidents,'timestamp',[timestamp])
                    self.incidents.changeAttributeValue(feature[0], 6, 'true')
                    department = self.reportTable.item(rownumber,4).text()
                    if ', ' in department:
                        departmentList = department.split(',')
                    else:
                        departmentList = [department]

                    self.locations.startEditing()
                    for item in departmentList:
                        feature = uf.getFeatureIdsByListValues(self.locations,'name',item)
                        asset = self.name_asset[item]
                        if asset >0:
                            newAsset = asset - 1
                            self.name_asset[item] = newAsset
                            self.locations.changeAttributeValue(feature[0], 4, newAsset)
                            text = 'Department '+str(item)+' is dispatched to incident with timestamp '+str(timestamp)+', Assets-1'
                            self.insertReport(text)
                            text = 'Dispatched'
                            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
                            # if self.name_asset[item] == 0:
                            # recalculate shorest route departments
                        else:
                            text = 'Department has insufficient assets!'
                            uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
                    self.locations.commitChanges()

            self.incidents.commitChanges()
        self.refreshCanvas()

    def resolve(self):
        selected = self.reportTable.selectedItems()
        if selected == []:
            return
        else:
            rowList = []
            for item in selected:
                rownumb = self.reportTable.row(item)
                if rownumb not in rowList:
                    if self.reportTable.item(rownumb,2).text() == 'true':
                        rowList.append(rownumb)
                    else:
                        text = 'Need to dispatch first'
                        uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)

            self.incidents.startEditing()
            for rownumber in rowList:
                self.reportTable.setItem(rownumber,3,QtGui.QTableWidgetItem('true'))
                timestamp = int(self.reportTable.item(rownumber,0).text())
                feature = uf.getFeatureIdsByListValues(self.incidents,'timestamp',[timestamp])
                self.insertReport(str(feature))
                self.incidents.changeAttributeValue(feature[0], 7, 'true')
                department = self.reportTable.item(rownumber,4).text()
                if ', ' in department:
                    departmentList = department.split(',')
                else:
                    departmentList = [department]

                self.locations.startEditing()
                for item in departmentList:
                    feature = uf.getFeatureIdsByListValues(self.locations,'name',item)
                    asset = self.name_asset[item]
                    newAsset = asset + 1
                    self.name_asset[item] = newAsset
                    self.locations.changeAttributeValue(feature[0], 4, newAsset)
                    text = 'Incident with timestamp '+str(timestamp)+' resolved, Assets '+str(item)+' +1'
                    self.insertReport(text)

                    # update shortest routes

                self.locations.commitChanges()

            self.incidents.commitChanges()
            if rowList == []:
                return
            else:
                text = 'Resolved'
                uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
        self.refreshCanvas()

    def zoomToIncident(self):
        selected = self.reportTable.selectedItems()
        if selected == []:
            return
        else:
            timestamps = []
            for item in selected:
                rownumb = self.reportTable.row(item)
                timestamp = int(self.reportTable.item(rownumb,0).text())
                timestamps.append(timestamp)

            unique_timestamps = list(set(timestamps))
            self.insertReport(str(unique_timestamps))
        if len(unique_timestamps) > 0:
            uf.selectFeaturesByListValues(self.incidents,'timestamp', unique_timestamps)
            self.refreshCanvas()
            if len(unique_timestamps) < 2:
                self.WidgetCanvas.zoomToSelected(self.incidents)
                self.WidgetCanvas.zoomScale(20000.0)
                self.refreshCanvas()
            else:
                self.WidgetCanvas.zoomToSelected(self.incidents)
                if self.WidgetCanvas.scale() < 20000.0:
                    self.WidgetCanvas.zoomScale(20000.0)
                self.refreshCanvas()
        else:
            return

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
        layers = []
        for item in uf.getLegendLayers(self.iface):
            cl = QgsMapCanvasLayer(item)
            layers.append(cl)
        self.WidgetCanvas.setLayerSet(layers)
        self.WidgetCanvas.refreshAllLayers()

    def updateLayers(self):
        layers = uf.getLegendLayers(self.iface, 'all', 'all')

    def setSelectedLayer(self):
        layer_name = self.selectLayerCombo.currentText()
        layer = uf.getLegendLayerByName(self.iface, layer_name)