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
from PyQt4.QtGui import QAction, QMainWindow, QBrush, QColor
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

        self.firstRun = True

        # define globals
        # interface
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        # network analysis
        self.network_layer = []
        self.tied_points = []
        self.graph = QgsGraph()
        # network nodes
        self.tied_points_police = []
        self.tied_points_fire = []
        self.tied_points_incidents = []
        # global dictionaries
        self.osmid_ID = {}
        self.osmid_name = {}
        self.osmid_type = {}
        self.osmid_asset = {}
        self.name_osmid = {}
        self.name_asset = {}
        self.name_type = {}
        self.timestamp_osmid = {}
        self.timestamp_QTableItemRow = {}
        self.timestamp_osmid_cost = {}
        self.timestamp_ID = {}


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
        self.cleanAssets()

        # get/set global feature data
        # set global dictionaries
        self.dataInit()

        # Initialize
        # set pushbutton layer visibility
        self.service_area_police.setScaleBasedVisibility(True)
        self.service_area_police.setMaximumScale(1.0)
        self.service_area_fire.setScaleBasedVisibility(True)
        self.service_area_fire.setMaximumScale(1.0)
        # initiate network functionality
        self.buildNetwork()
        #self.calculateRoutes()
        self.calculateAllRoutes() # self.formatTable() included in function

        # Set extent to the extent of our layer
        self.WidgetCanvas.setExtent(self.roads.extent())

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
    def dataInit(self):
        self.incidentData = uf.getAllFeatures(self.incidents)
        self.incidentAtt = []
        self.incidentID = []
        for item in self.incidentData.items():
            self.incidentAtt.append(item[1].attributes())
            self.incidentID.append(item[1].id())

        for n,item in list(enumerate(self.incidentAtt)):
            self.timestamp_ID[item[0]] = self.incidentID[n]

        self.locationData = uf.getAllFeatures(self.locations)
        self.locationAtt = []
        self.locationID = []
        for item in self.locationData.items():
            self.locationAtt.append(item[1].attributes())
            self.locationID.append(item[1].id())

        for n,item in list(enumerate(self.locationAtt)):
            self.osmid_ID[item[0]] = self.locationID[n]

        for item in self.locationAtt:
            self.osmid_name[item[0]] = item[2]
            self.osmid_asset[item[0]] = item[4]
            self.osmid_type[item[0]] = item[3]
            self.name_asset[item[2]] = item[4]
            self.name_osmid[item[2]] = item[0]
            self.name_type[item[2]] = item[3]

    def cleanIncidents(self):
        attr = {6 : 'false', 7 : 'false', 13 : '', 14: ''}
        ids = uf.getAllFeatureIds(self.incidents)
        attr_map = {}
        for id in ids:
            attr_map[id] = attr
        self.incidents.dataProvider().changeAttributeValues(attr_map)

    def cleanAssets(self):
        attr = {4: 2}
        ids = uf.getAllFeatureIds(self.locations)
        attr_map = {}
        for id in ids:
            attr_map[id] = attr
        self.locations.dataProvider().changeAttributeValues(attr_map)

#######
#    INITIALIZE
#######
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
            source_points = [feature.geometry().asPoint() for ids, feature in self.locationData.items()]
            type_source_points = []
            for attribute in self.locationAtt:
                type_source_points.append(attribute[3])
            source_incidents = [feature.geometry().asPoint() for ids, feature in self.incidentData.items()]
            timestamp_source_incidents = []
            for attribute in self.incidentAtt:
                timestamp_source_incidents.append(attribute[0])
            total_points = source_points + source_incidents
            att_total_points = type_source_points + timestamp_source_incidents
            # build the graph including these points
            if len(total_points) > 1:
                self.graph, self.tied_points = uf.makeUndirectedGraph(self.network_layer, total_points)
                # the tied points are the new source_points on the graph
                if self.graph and self.tied_points:
                    self.tied_points_police = []
                    for (x,att) in list(enumerate(type_source_points)):
                        if att == 'police':
                            self.tied_points_police.append(x)
                        else:
                            continue
                    self.tied_points_fire = []
                    for (x,att) in list(enumerate(type_source_points)):
                        if att == 'fire_station':
                            self.tied_points_fire.append(x)
                        else:
                            continue
                    self.tied_points_incidents = range(len(source_points),len(self.tied_points))

                    text = "Network is built for %s locations and %s incidents (runtime: %s)" % (len(source_points), len(source_incidents), time.clock())
                    self.insertReport(text)
                    self.messageBar.pushMessage('INFO',text, level=0, duration=10)
        self.refreshCanvas()

    def calculateAllRoutes(self):
        #
        time.clock()
        fields = self.shortest_routes.pendingFields()
        features = []
        for i,index_inc in list(enumerate(self.tied_points_incidents)):
            # depending on necesairy departments, destination is either police or fire or both
            origin = index_inc
            police_att_incident = self.incidentAtt[i][8]
            fire_att_incident = self.incidentAtt[i][9]
            timestamp_att_incident = self.incidentAtt[i][0]
            incident_dispatched = self.incidentAtt[i][6]
            incident_resolved = self.incidentAtt[i][7]
            dep_osmids = []
            route_dict = {}
            if police_att_incident == 'true' and incident_dispatched == 'false':
                path_list = []
                cost_list = []
                osmid_list = []
                for index_loc in self.tied_points_police:
                    destination = index_loc
                    police_att_asset = self.locationAtt[index_loc][4]
                    # calculate the shortest path for the given origin and destination
                    path,__ = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                    line = QgsLineStringV2()
                    for point in path:
                        line.addVertex(QgsPointV2(point.x(),point.y()))
                    cost = line.length()
                    path_list.append(line)
                    cost_list.append(cost)
                    osmid_list.append(self.locationAtt[index_loc][0])

                    if cost > 0.0:
                        route_dict[self.locationAtt[index_loc][0]] = cost # COST is property of line, implicitly included
                        # insert route line
                        feat = QgsFeature(fields)
                        # set attributes
                        feat.setAttribute(fields[0].name(), int(timestamp_att_incident))
                        feat.setAttribute(fields[1].name(),cost) # COST
                        feat.setAttribute(fields[2].name(), self.locationAtt[index_loc][0]) # OSMID
                        feat.setAttribute(fields[3].name(), 'false') # DISPATCHED
                        feat.setAttribute(fields[4].name(), 'false') # RESOLVED
                        # set geometry
                        feat.setGeometry(QgsGeometry(line)) # GEOM
                        # write feature to layer
                        features.append(feat)
                    else:
                        continue
                # zip path list on cost
                cost_osmid_path = zip(cost_list, osmid_list, path_list)
                # sort path on cost
                sorted_path = sorted(cost_osmid_path)
                sorted_paths = [x for x in sorted_path if x[0] != 0.0]

                # write timestamp : osmid to internal dictionary
                self.timestamp_osmid[timestamp_att_incident] = sorted_paths[0][1]
                dep_osmids.append(sorted_paths[0][1])

            if fire_att_incident == 'true' and incident_dispatched == 'false':
                path_list = []
                cost_list = []
                osmid_list = []
                for index_loc in self.tied_points_fire:
                    destination = index_loc
                    police_att_asset = self.locationAtt[index_loc][4]
                    # calculate the shortest path for the given origin and destination
                    path,__ = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
                    line = QgsLineStringV2()
                    for point in path:
                        line.addVertex(QgsPointV2(point.x(),point.y()))
                    cost = line.length()
                    path_list.append(line)
                    cost_list.append(cost)
                    osmid_list.append(self.locationAtt[index_loc][0])
                    if cost > 0.0:
                        route_dict[self.locationAtt[index_loc][0]] = cost # COST is property of line, implicitly included
                        # insert route line
                        feat = QgsFeature(fields)
                        # set attributes
                        feat.setAttribute(fields[0].name(), int(timestamp_att_incident))
                        feat.setAttribute(fields[1].name(),cost) # COST
                        feat.setAttribute(fields[2].name(), self.locationAtt[index_loc][0]) # OSMID
                        feat.setAttribute(fields[3].name(), 'false') # DISPATCHED
                        feat.setAttribute(fields[4].name(), 'false') # RESOLVED
                        # set geometry
                        feat.setGeometry(QgsGeometry(line)) # GEOM
                        # write feature to layer
                        features.append(feat)
                    else:
                        continue

                # zip path list on cost
                cost_osmid_path = zip(cost_list, osmid_list, path_list)
                # sort path on cost
                sorted_path = sorted(cost_osmid_path)
                sorted_paths = [x for x in sorted_path if x[0] != 0.0]

                # write timestamp : osmid to internal dictionary
                self.timestamp_osmid[timestamp_att_incident] = sorted_paths[0][1]
                dep_osmids.append(sorted_paths[0][1])

            if fire_att_incident == 'true' and police_att_incident == 'true':
                self.timestamp_osmid[timestamp_att_incident] = dep_osmids

            self.timestamp_osmid_cost[timestamp_att_incident] = route_dict
        self.shortest_routes.startEditing()
        self.shortest_routes.addFeatures(features,False)
        self.shortest_routes.commitChanges()
        self.refreshCanvas()
        self.insertReport('%s shortest routes calculated (runtime: %s)' % (len(features),time.clock()))
        self.assignDepartmentsToIncidents()

    def assignDepartmentsToIncidents(self, recalc=None):
        if self.firstRun == False and recalc:
            for incident in self.incidentAtt:
                timestamp = incident[0]
                dispatched = incident[6]
                fire_needed = incident[9]
                police_needed = incident[8]
                if not dispatched == 'true':
                    route_dict = self.timestamp_osmid_cost[timestamp] # OSMID : COST
                    osmid_cost = sorted(route_dict.items(), key=lambda route:route[1])
                    dep_osmids = []
                    if police_needed == 'true':
                        for osmid, cost in osmid_cost:
                            if self.osmid_type[osmid] == 'police' and self.osmid_asset[osmid] > 0:
                                self.timestamp_osmid[timestamp] = osmid
                                dep_osmids.append(osmid)
                                break
                            else:
                                continue
                    if fire_needed == 'true':
                        for osmid, cost in osmid_cost:
                            if self.osmid_type[osmid] == 'fire_station' and self.osmid_asset[osmid] > 0:
                                self.timestamp_osmid[timestamp] = osmid
                                dep_osmids.append(osmid)
                                break
                            else:
                                continue
                    if fire_needed == 'true' and police_needed == 'true':
                        self.timestamp_osmid[timestamp] = dep_osmids
            self.updateTable()
            self.dataInit()

        else:
            self.formatTable()
            self.dataInit()
            self.firstRun = False
        return

    def formatTable(self):
        if self.incidents:
            layer = self.incidents
            self.reportTable.setColumnCount(5)
            self.reportTable.setHorizontalHeaderLabels(["Timestamp", "Subtype", "Dispatch","Resolved","Department"])
            self.reportTable.setRowCount(len(self.incidentAtt))
            for item in list(enumerate(self.incidentAtt,1)):
                self.timestamp_QTableItemRow[item[1][0]] = item[0]

            for i in range(len(self.incidentAtt)):
                timestamp = self.incidentAtt[i][0]
                self.reportTable.setItem(i, 0, QtGui.QTableWidgetItem(str(self.incidentAtt[i][0])))
                self.reportTable.setItem(i, 1, QtGui.QTableWidgetItem(str(self.incidentAtt[i][2])))
                self.reportTable.setItem(i, 2, QtGui.QTableWidgetItem(str(self.incidentAtt[i][6])))
                self.reportTable.setItem(i, 3, QtGui.QTableWidgetItem(str(self.incidentAtt[i][7])))
                if type(self.timestamp_osmid[timestamp]) == list :
                    police_osmid = self.timestamp_osmid[timestamp][0]
                    dep_police = self.osmid_name[police_osmid]
                    fire_osmid = self.timestamp_osmid[timestamp][1]
                    dep_fire = self.osmid_name[fire_osmid]
                    names = dep_police+', '+dep_fire
                    self.reportTable.setItem(i, 4, QtGui.QTableWidgetItem(names))
                else:
                    self.reportTable.setItem(i, 4, QtGui.QTableWidgetItem(self.osmid_name[self.timestamp_osmid[timestamp]]))

            self.reportTable.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(2, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(3, QtGui.QHeaderView.ResizeToContents)
            self.reportTable.horizontalHeader().setResizeMode(4, QtGui.QHeaderView.Stretch)
            self.reportTable.resizeRowsToContents()
        return

    def updateTable(self):
        if self.incidents:
            for i in range(len(self.incidentAtt)):
                timestamp = self.incidentAtt[i][0]
                self.reportTable.setItem(i, 0, QtGui.QTableWidgetItem(str(self.incidentAtt[i][0])))
                self.reportTable.setItem(i, 1, QtGui.QTableWidgetItem(str(self.incidentAtt[i][2])))
                self.reportTable.setItem(i, 2, QtGui.QTableWidgetItem(str(self.incidentAtt[i][6])))
                self.reportTable.setItem(i, 3, QtGui.QTableWidgetItem(str(self.incidentAtt[i][7])))
                if type(self.timestamp_osmid[timestamp]) == list :
                    police_osmid = self.timestamp_osmid[timestamp][0]
                    dep_police = self.osmid_name[police_osmid]
                    fire_osmid = self.timestamp_osmid[timestamp][1]
                    dep_fire = self.osmid_name[fire_osmid]
                    names = dep_police+', '+dep_fire
                    self.reportTable.setItem(i, 4, QtGui.QTableWidgetItem(names))
                else:
                    self.reportTable.setItem(i, 4, QtGui.QTableWidgetItem(self.osmid_name[self.timestamp_osmid[timestamp]]))
        return

#######
#    SOLVE
#######
    def open_police_sa(self):
        if self.policeSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'Service Area Police checked'
            self.messageBar.pushMessage('INFO',text, level=0, duration=1)
            self.service_area_police.setScaleBasedVisibility(False)
        else:
            # checked = false: hide layer
            text = 'Service Area Police unchecked'
            # self.messageBar.pushMessage('INFO',text, level=3, duration=1)
            self.service_area_police.setScaleBasedVisibility(True)
        self.refreshCanvas()

    def open_fire_sa(self):
        if self.fireSAButton.isChecked():
            # checked = true: show layer in iface
            text = 'Service Area Fire checked'
            self.messageBar.pushMessage('INFO',text, level=0, duration=1)
            self.service_area_fire.setScaleBasedVisibility(False)
        else:
            # checked = false: hide layer
            text = 'Service Area Fire unchecked'
            # self.messageBar.pushMessage('INFO',text, level=3, duration=1)
            self.service_area_fire.setScaleBasedVisibility(True)
        self.refreshCanvas()

    def dispatch(self):
        recalculate = False
        selected = self.reportTable.selectedItems()
        if selected == []:
            return
        else:
            rowList = []
            for item in selected:
                rownumb = self.reportTable.row(item)
                if rownumb not in rowList:
                    rowList.append(rownumb)
            try:
                for rownumber in rowList:
                    incident = int(self.reportTable.item(rownumber,0).text())
                    if self.reportTable.item(rownumber,2).text() == 'true':
                        text = 'Incident with timestamp %s allready dispatched' % incident
                        self.insertReport(text)
                        self.messageBar.pushMessage('INFO',text, level=0, duration=2)
                    else:
                        department = str(self.reportTable.item(rownumber,4).text())
                        timestamp = int(self.reportTable.item(rownumber,0).text())
                        if ', ' in department:
                            departmentList = department.split(', ')
                        else:
                            departmentList = [department]
                        self.locations.startEditing()
                        self.incidents.startEditing()
                        for item in departmentList:
                            asset = self.name_asset[item]
                            if asset > 0:
                                newAsset = asset - 1
                                self.name_asset[item] = newAsset
                                self.osmid_asset[item] = newAsset
                                id = self.osmid_ID[self.name_osmid[item]]
                                self.locations.changeAttributeValue(id, 4, newAsset)
                                if newAsset == 0:
                                    recalculate = True
                                self.incidents.changeAttributeValue(self.timestamp_ID[incident], 6, 'true')
                                depType = self.name_type[item]
                                if depType == 'police':
                                    self.incidents.changeAttributeValue(self.timestamp_ID[timestamp], 10, item)
                                elif depType == 'fire_station':
                                    self.incidents.changeAttributeValue(self.timestamp_ID[timestamp], 11, item)
                                dep_osmid = self.name_osmid[item]
                                route_id = uf.getFeatureIDFromTable(self.shortest_routes,['id','osmid'], [(incident,dep_osmid)])
                                attr_map = {route_id[0]:{3:'true'}}
                                self.shortest_routes.dataProvider().changeAttributeValues(attr_map)
                                text = 'Department %s is dispatched to incident %s, Assets -1' % (item,incident)
                                self.insertReport(text)
                            else:
                                text = 'Department %s has insufficient assets!' % item
                                self.insertReport(text)
                                self.messageBar.pushMessage('CRITICAL',text, level=2, duration=5)
                        self.locations.commitChanges()
                        self.incidents.commitChanges()
                    self.reportTable.setItem(rownumber,2,QtGui.QTableWidgetItem('true'))
            except:
                text = 'Something went wrong while dispatching to incident %s,\ntry again. If problem persists, reload plugin' % incident
                self.insertReport(text)
                self.messageBar.pushMessage('WARNING',text, level=1, duration=2)
            else:
                text = 'Incident(s)dispatched, more detail in log window'
                self.insertReport(" ")
                self.messageBar.pushMessage('SUCCES',text, level=3, duration=3)

        self.refreshCanvas()
        self.dataInit()
        if recalculate:
            self.assignDepartmentsToIncidents('recalc')

    def resolve(self):
        recalculate = False
        selected = self.reportTable.selectedItems()
        if not selected:
            return
        else:
            rowList = []
            for item in selected:
                rownumb = self.reportTable.row(item)
                rowList.append(rownumb)
            rowList = list(set(rowList))
            try:
                for rownumber in rowList:
                    if self.reportTable.item(rownumb,2).text() == 'false':
                        text = 'Need to dispatch first'
                        self.insertReport(text)
                        self.messageBar.pushMessage('WARNING',text, level=1, duration=2)
                    else:
                        if self.reportTable.item(rownumb,3).text() == 'true':
                            incident = self.reportTable.item(rownumb,0).text()
                            text = 'Incident with timestamp %s allready resolved' % incident
                            self.insertReport(text)
                            self.messageBar.pushMessage('INFO',text, level=0, duration=1)
                        else:
                            # start resolving incident
                            department = self.reportTable.item(rownumber,4).text()
                            timestamp = int(self.reportTable.item(rownumber,0).text())
                            if ', ' in department:
                                departmentList = department.split(', ')
                            else:
                                departmentList = [department]

                            self.locations.startEditing()
                            self.incidents.startEditing()

                            for item in departmentList:
                                # update asset of emergency location
                                asset = self.name_asset[item]
                                newAsset = asset + 1
                                self.name_asset[item] = newAsset
                                self.osmid_asset[item] = newAsset
                                id = self.osmid_ID[self.name_osmid[item]]
                                self.locations.changeAttributeValue(id, 4, newAsset)
                                if newAsset == 1:
                                    recalculate = True
                                # set attributes of shortest route
                                osmid = self.name_osmid[item]
                                route_id = uf.getFeatureIDFromTable(self.shortest_routes,['id','osmid'], [(timestamp,osmid)])
                                attr_map = {route_id[0]:{4:'true'}}
                                self.shortest_routes.dataProvider().changeAttributeValues(attr_map)
                                # set attributes of incident data
                                self.incidents.changeAttributeValue(self.timestamp_ID[timestamp], 7, 'true')
                                text = 'Department %s has resolved incident %s, Assets +1' % (item,timestamp)
                                self.insertReport(text)
                            self.locations.commitChanges()
                            self.incidents.commitChanges()
                    self.reportTable.setItem(rownumber,3,QtGui.QTableWidgetItem('true'))
            except:
                incident = self.reportTable.item(rownumb,0).text()
                text = 'Something went wrong while resolving incident %s,\ntry again. If problem persists, reload plugin' % incident
                self.insertReport(text)
                self.messageBar.pushMessage('WARNING',text, level=1, duration=2)
            else:
                text = 'Incident(s)resolved, more detail in log window'
                self.insertReport(" ")
                self.messageBar.pushMessage('SUCCESS', text, level=3,duration=3)
        self.refreshCanvas()
        self.dataInit()
        if recalculate:
            self.assignDepartmentsToIncidents('recalc')

    def zoomToIncident(self):
        selected = self.reportTable.selectedItems()
        if selected == []:
            return
        else:
            timestamps = []
            osmids = []
            rownumbs = []
            for item in selected:
                rownumb = self.reportTable.row(item)
                rownumbs.append(rownumb)
            rownumbs = list(set(rownumbs))
            for rownumb in rownumbs:
                timestamp = int(self.reportTable.item(rownumb,0).text())
                name_field = self.reportTable.item(rownumb,4).text()
                if ', ' in name_field:
                    names = name_field.split(', ')
                    osmid = [self.name_osmid[names[0]],self.name_osmid[names[1]]]
                else:
                    name = name_field
                    osmid = self.name_osmid[name_field]
                osmids.append(osmid)
                timestamps.append(timestamp)
        if len(timestamps) > 0:
            tup_list = zip(timestamps,osmids) # list of tuples (timestamp,[osmid,osmid])
            uf.selectFeaturesFromTable(self.shortest_routes,['id','osmid'], tup_list)
            self.WidgetCanvas.zoomToSelected(self.shortest_routes)
            self.refreshCanvas()
        else:
            return
        return

#######
#    REPORTING
#######
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

#######
#    REMOVED FUNCTIONALITY
#######
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