# G-Cod3r
Python framework for creating 3D printer G-Code from basic geometric shapes (line, rectangle, circle), mathematical functions and patterns out of those.

# Edit May 2025
This was build in paralell to [FullControl GCODE Designer](https://fullcontrolgcode.com/) and used for a thesis project. 
The project worked quite fine but gut abandoned after the thesis work. I decided to make this repo public as resource for others. Maybe someone finds this stuff useful. 

# Build in progress...
## TODOs
* Do some project planning
  * Do some UML stuff for functional Overview
* Upload G-Code Script via Moonraker API
* Support for G-Code Arcs (G2/G3)
* Support for multiple Toolheads
  * Dictionary for every Toolhead
* Backlash Compensation for all axis
  * May reuse backend.py for automatic backlash measurement
* Support for non Klipper Firmwares (Marlin, Repetier) -> ig different (G)codes for some specific configuration stuff
