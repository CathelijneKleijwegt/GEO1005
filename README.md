# GEO1005 Oscar Willems & Cyntha Nijmeijer
Material for the MSc Geomatics GEO1005 course project

UX Workflow

In file 'UX workflow' the user experience workflow diagram is given. It includes the most important actors – the control center and the departments – and the actions they need to take when using the decision support system. The Control center will be using the Plugin, so the steps in their workflow will be explained in more detail, in combination with the conceptual GUI in file GUI concept.


Check priority and department 

On the map all police stations, fire brigade stations and medical centers are shown. Also, the  the locations of incidents are shown. Next to this map in the plugin a table with all the incidents sorted by urgency will be shown. The top white field in file GUI concept will in the beginning contain the incident table of the incidents with the highest urgency and the bottom white field will contain the incident table with the second highest urgency. When all the incidents with the highest urgency are resolved, the bottom field moves to the upper field and in the bottom field, the incident table with the third urgency will appear. 
In the incident table the department(s) needed (police and/or fire brigade) are indicated as well, by giving the incident a NULL value if it’s NOT relevant for the department. By default, in the table the department location which is the best option to solve an incident is given, but a drop-down menu gives the control center the opportunity to choose another department location if they want to. The buttons ‘<< Incident’ and ‘Incident >>’ can be used to move through the incident table.


Check asset availability

The availability of fire trucks, police cars et cetera will be shown when clicking on a certain police or fire brigade station. There will appear symbols for each unit, so three blue car-symbols indicate that there are three police cars and personnel available. This is not realised yet, so it can’t be shown yet.


Determining shortest route

To decide which department location will be send to the incident, it is important to know the shortest route from all the department locations to the incident. Other incidents that block a road need to be taken into account. The shortest route will automatically be shown on the map when an incident is selected in the incident table. It is possible to select multiple incidents and show the routes of the department location(s) to multiple incidents.


Decide which department location(s) to send

The control center is still the responsible actor for the decision which department location(s) to send to and incident, since exceptions can occur. That is the reason that a dropdown menu is implemented in the police and fire brigade location columns in the incident table.


Dispatch department location(s)

When the control center has decided which department location to send to an incident, the only thing they need to do to actually send it to the incident is select the incident and click on the ‘dispatch’ button. Then an automatic message with the location of the incident, shortest route to the incident, materials needed and whether to work together with another emergency service is send to the correct department location.


Remove incidents from priority list

When an incident is resolved by the police and/or fire department,  it needs to be hidden from the incident table and the map. This will be done by the control center by selecting the incident in the incident table and then on the ‘resolve’ button. 


Service areas

In file GUI concept, there are two buttons haven’t been explained yet; the ‘Police service area’ and the ‘Fire brigade service area’. These buttons are toggles; when they are clicked down, the areas which are accessible within a certain timespan from the police/fire department are shown. When the user clicks on them again, they disappear from the map. 


