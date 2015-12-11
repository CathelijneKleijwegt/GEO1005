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
		self.roads = 'Roads'
		self.locations = 'Emergency Locations'
		self.incidents = 'Incidents'
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
		self.open_police_sa()
		self.open_fire_sa()
		# self.initialize()

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
	def initialize(self):
		# create network with emergency and incident locations as points/nodes
		#buildNetwork()
		"""
		police_aos= uf.calculateServiceArea()
		fire_aos
		"""

		pass

	def getNetwork(self):
		roads_layer = uf.getLegendLayerByName(self.iface, self.roads)
		if roads_layer:
			# see if there is an obstacles layer to subtract roads from the network
			obstacles_layer = uf.getLegendLayerByName(self.iface, "Incidents")
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
		start = time.clock()
		self.network_layer = self.getNetwork()
		if self.network_layer:
			# get the points to be used as origin and destination
			# in this case point location of each emergency service

			selected_sources = uf.getAllFeatures(uf.getLegendLayerByName(self.iface, self.locations))
			source_points = [feature.geometry().asPoint() for id, feature in selected_sources.items()]
			selected_incidents = uf.getAllFeatures(uf.getLegendLayerByName(self.iface, self.incidents))
			source_incidents = [feature.geometry().asPoint() for id, feature in selected_incidents.items()]
			total_points = source_points + source_incidents
			# build the graph including these points
			if len(total_points) > 1:
				self.graph, self.tied_points = uf.makeUndirectedGraph(self.network_layer, total_points)
				# the tied points are the new source_points on the graph
				if self.graph and self.tied_points:
					text = "network is built for %s locations and %s incidents (runtime: %s)" % (len(source_points), len(source_incidents), time.clock())
				uf.showMessage(self.iface, text, type='Info', lev=3, dur=10)
				return

	def calculateServiceArea(self, features, f_type, cutoff, shown=False):
		options = len(features)

		if options > 0:
			# origin is given as an index in the tied_points list
			origin = random.randint(1,options-1)
			service_area = uf.calculateServiceArea(self.graph, features, origin, cutoff)
			# store the service area results in temporary layer called "Service_Area"
			area_layer = uf.getLegendLayerByName(self.iface, "Service Area "+f_type)
			# create one if it doesn't exist
			if not area_layer:
				attribs = ['cost']
				types = [QtCore.QVariant.Double]
				area_layer = uf.createTempLayer('Service Area '+f_type,'POINT',self.network_layer.crs().postgisSrid(), attribs, types)
				uf.loadTempLayer(area_layer)
			# insert service area points
			geoms = []
			values = []
			for point in service_area.itervalues():
				# each point is a tuple with geometry and cost
				geoms.append(point[0])
				# in the case of values, it expects a list of multiple values in each item - list of lists
				values.append([cutoff])
			uf.insertTempFeatures(area_layer, geoms, values)
			self.refreshCanvas(area_layer)
			
		"""
		if show:
			# show layer
		else:
			# dont show layer

		"""
			
	def calc_servicearea_police(self):
		expression = """\"type\"=\'police\'"""
		layer_name = uf.getLegendLayerByName(self.iface, self.locations)
		police_locations = uf.selectFeaturesByExpression(layer_name, expression)
		# output is a polygon layer with service area of police
		self.calculateServiceArea(police_locations, 'Police',  15, False)
		
	def calc_serviceare_fire(self):
		expression = """\"type\"=\'fire_brigade\'"""
		layer_name = uf.getLegendLayerByName(self.iface, self.locations)
		fire_locations = uf.selectFeaturesByExpression(layer_name, expression)
		# output is a polygon layer with service area of fire brigade
		self.calculateServiceArea(fire_locations, 'Fire Brigade',20, False)
		
#######
#    SOLVE
#######
	def open_police_sa(self):
		if self.policeSAButton.isChecked():
			# checked = true: show layer in iface
			text = 'button checked'
			uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
		else:
			# checked = false: hide layer
			text = 'button unchecked'
			### uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)

	def open_fire_sa(self):
		if self.fireSAButton.isChecked():
			# checked = true: show layer in iface
			text = 'button checked'
			uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
		else:
			# checked = false: hide layer
			text = 'button unchecked'
			### uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)

	def dispatch(self):
		text = 'Dispatched'
		uf.showMessage(self.iface, text, type='Info', lev=3, dur=1)
		
	def resolve(self):
		text = 'Resolved'
		uf.showMessage(self.iface, text, type='Info', lev=3, dur=13)
		
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
	def updateReport(self,report):
		self.reportList.clear()
		self.reportList.addItems(report)

	def insertReport(self,item):				# NOT WORKING! insertItem not supported
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
		layer = uf.getLegendLayerByName(self.iface,layer_name)
