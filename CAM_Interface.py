from io import StringIO
from moonraker import Moonraker
import numpy as np
import pyperclip

class CAM_Interface:

    def __init__(self, **kwargs):
        """
        Initializes GCode Object with necessary keyword parameters

        nozzle_diameter: float - nozzle diameter in mm
        filament_diameter: float - filament diameter in mm
        layer_width:  float - Width of  layer in mm
        layer_height.  float - Height of layer in mm
        z_lift:  float - Z-lift for travel moves in mm
        t0_temp: float - Temperatur Tool 0
        tn_temp: float - Temperatur Tool n
        bed_temp:  float - Temperatur Druckbett
        """
        self._gcode_script = StringIO("")
        self._properties = kwargs
        # @Todo: Handling of more toolheads with different settings (nozzle, layer height etc.) -> add toolhead method
        self._inc_mode = False
        self._simulation = 'simulation' in self._properties and self._properties['simulation']
        self._properties['extrude_override'] = 100
        self._properties['speed_override'] = 100
        # Backlash compensation
        # Clockwise rotation -> downwards, -z direction
        # Start after homing or probe -> last movement ccw/upwards
        self._last_z_cw = False
        self._moonraker = None
        self._toolhead = None
        self._x = 0.0
        self._y = 0.0
        self._z = 0.0


        self._prepare_print()

    # Start und End-Codes
    def _prepare_print(self):
        """
        Start code for print. Preheating, set G90 and  Relativer Modus für Extruder
        """
        t0_temp = self._properties['t0_temp'] if 't0_temp' in self._properties else 0
        bed_temp = self._properties['bed_temp'] if 'bed_temp' in self._properties else 0
        start_tool = self._properties['start_tool'] if self._properties['start_tool'] else 0
        self._properties['absolute'] = True
        self._gcode_script.write("; start code\n"
                                 "G21 ; units mm\n"
                                 "G90 ; absolute mode\n"
                                 "M83 ; relative extrusion\n"
                                 f"T{start_tool:d}\n"
                                 "; Preheat\n"
                                 f"M104 T0 S{t0_temp:d}\n"
                                 f"M190 S{bed_temp:d}\n"
                                 "; wait for temp to be reached...\n"
                                 f"M109 T0 S{t0_temp:d}\n"
                                 )
        if not self._simulation:
            self._gcode_script.write(f"start_print ; klipper start code\n")

    def _add_end_code(self):
        """
        Adds klipper end code to gcode script
        """
        if not self._simulation:
            self._gcode_script.write("end_print ; klipper end code")

    # Bewegung und Position
    def _update_pos(self, **kwargs):
        """
        Store current position ot toolhead after every movement / G1

        :param kwargs: x,y,z
        """
        if self._inc_mode:
            if 'x' in kwargs:
                self._x += kwargs['x']
            if 'y' in kwargs:
                self._y += kwargs['y']
            if 'z' in kwargs:
                self._z += kwargs['z']
        else:
            if 'x' in kwargs:
                self._x = kwargs['x']
            if 'y' in kwargs:
                self._y = kwargs['y']
            if 'z' in kwargs:
                self._z = kwargs['z']

    def _move_to_pos(self, **kwargs):
        """
        Adds G1 for travel to requested position (no extrusion)

        :param  kwargs: x,y,z - Position in mm, f - feedrate in mm/min,
                inc - boolean incremental mode/G91 (default is G90)
       """
        code = ""
        z_lift = kwargs['z_lift'] if 'z_lift' in kwargs and not self._simulation else 0
        inc = 'inc' in kwargs and kwargs['inc']
        retract = 'retract' in kwargs and kwargs['retract']
        # most G-Code Visualizer do not work with G10/G11 (firmware retraction in klipper)
        if retract and not self._simulation:
            code += f"; Retract\nG10\n"
        if z_lift > 0:
            self._set_relative_mode()
            self._backlash_compensation(z_lift)
            code += f"; Z-Lift\nG1Z{z_lift:.3f}\n"
        self._set_mode(inc)
        code += "G1"
        if 'x' in kwargs:
            code += f"X{kwargs['x']:.3f}"
            self._update_pos(x=kwargs['x'])
        if 'y' in kwargs:
            code += f"Y{kwargs['y']:.3f}"
            self._update_pos(y=kwargs['y'])
        if 'z' in kwargs:
            self._backlash_compensation(kwargs['z'])
            code += f"Z{kwargs['z']:.3f}"
            self._update_pos(z=kwargs['z'])
        if 'f' in kwargs:
            code += f"F{kwargs.get('f'):.3f}"
            self._properties['feedrate'] = kwargs.get('f')
        code += "\n"
        if not ('z' in kwargs) and z_lift > 0:
            self._set_relative_mode()
            self._backlash_compensation(-z_lift)
            code += f"; Undo Z-Lift\nG1Z{-z_lift:.3f}\n"
        if retract and not self._simulation:
            code += f"; Unretract\nG11\n"
        self._set_mode(inc)
        self._gcode_script.write(code)

    def abs_move(self, **kwargs):
        """
        Shortcut fot move_to_pos with absolute coordinates

        :param kwargs: x,y,z,e - Position in mm, f - Feedrate in mm/min,
        """
        kwargs['inc'] = False
        self._move_to_pos(**kwargs)

    def rel_move(self, **kwargs):
        """
        Shortcut fot move_to_pos with incremental values

        :param kwargs: x,y,z,e - Position in mm, f - Feedrate in mm/min,
        """
        kwargs['inc'] = True
        self._move_to_pos(**kwargs)

    def _backlash_compensation(self, new_z):
        """
        Checks if backlash can appear. Compensates if necessary by adding FORCE movements for compensation
        FORCE_MOVE, will not change state of GCode parser.
        For using with kinematic methods. If backlash was measured correctly toolhead should not move while
        compensating.

        :param new_z: angefragte z koordinate
        """
        # @Todo Backlash compensation for all axis
        if self._properties['backlash'] > 0:
            # Check if requested move leads to cw or ccw rotation of motor/axis
            if self._inc_mode:
                # G91
                cw = new_z < 0
            else:
                # G90
                cw = new_z - self._z < 0
            if self._last_z_cw != cw:
                # Direction change, compensate backlash
                last = "cw" if self._last_z_cw else "ccw"
                new = "cw" if cw else "ccw"
                sign = 2*(not cw) - 1
                stepper = "stepper_z1" if self._toolhead else "stepper_z"
                self._gcode_script.write(f"; Backlash Compensation ({self._properties['backlash']:2.2f}mm)\n"
                                         f"; Last: {last:s} - Next: {new:s}\n"
                                         "FORCE_MOVE "
                                         f"STEPPER={stepper:s} "
                                         f"DISTANCE={sign*self._properties['backlash']:1.4f} "
                                         f"VELOCITY=.6 "
                                         f"ACCEL=0.5\n")
            self._last_z_cw = cw

    # Druck Befehle
    def _print_move(self, **kwargs):
        """
        Adds G1 code according to requested parameters

        layer width and height is only changed, if given in kwargs
        Extrusion distance is calculated with given parameters.

        :param kwargs: x,y,z,e - Position in mm, f - Feedrate in mm/min,
        """
        inc = 'inc' in kwargs and kwargs['inc']
        absolute = not inc
        self._set_mode(inc)
        distance = .0
        code = "G1"
        if 'x' in kwargs:
            distance += (absolute * self._x - kwargs['x']) ** 2
            code += f"X{kwargs['x']:.3f}"
            self._update_pos(x=kwargs['x'])
        if 'y' in kwargs:
            distance += (absolute * self._y - kwargs['y']) ** 2
            code += f"Y{kwargs['y']:.3f}"
            self._update_pos(y=kwargs['y'])
        if 'z' in kwargs:
            self._backlash_compensation(kwargs['z'])
            distance += (absolute * self._z - kwargs['z']) ** 2
            code += f"Z{kwargs['z']:.3f}"
            self._update_pos(z=kwargs['z'])
        code += f"E{self._get_extrusion_distance(np.sqrt(distance)):.6f}"
        if 'f' in kwargs:
            code += f"F{kwargs.get('f'):.3f}"
            self._properties['feedrate'] = kwargs.get('f')
        code += "\n"
        self._set_mode(inc)
        self._gcode_script.write(code)

    def abs_print(self, **kwargs):
        """
        Shortcut for print_move with  absolute coordinates.

        :param kwargs: x,y,z,e - Position in mm, f - Feedrate in mm/min,
        """
        kwargs['inc'] = False
        self._print_move(**kwargs)

    def rel_print(self, **kwargs):
        """
        Shortcut für print_move with incremental distances.
        :param kwargs: x,y,z,e - Position in mm, f - Feedrate in mm/min,
        """
        kwargs['inc'] = True
        self._print_move(**kwargs)

    # Direct G-Codes to printer
    def wait(self, time: float):
        """
        G4 (Dwell) such that printer waits given time period.

        :param time: Time in seconds.
        """
        self._gcode_script.write(f"G4P{time*1e3:.2f}\n")

    def extrude(self, dist=10):
        """
        Extrude given distance

        :param dist: distance in mm (default 10)
        """
        self._gcode_script.write(f"; Manual Extrude Filament\nG1E{dist:2.2f}\n")

    def retract(self):
        """
        Retraction filament using firmware retraction
        """
        if not self._simulation:
            self._gcode_script.write(";Retract\nG10\n")

    def unretract(self):
        """
        Unretract via firmware retrcation
        """
        if not self._simulation:
            self._gcode_script.write("; Unretract\nG11\n")

    def probe_tool(self):
        """
        Start probe sequence for active tool
        """
        if not self._simulation:
            self._gcode_script.write("probe ; klipper macro for probe\n")
        # @Todo: allow costum macro for probing

    def toolchange(self):
        """
        Method for toolchange. Initially for 2 toolheads. Not in use rn
        """
        if self._toolhead == 0:
            self._properties_t0 = self._properties
            self._properties = self._properties_t1
            self._gcode_script.write("T1\n")
            self._toolhead = 1
        elif self._toolhead == 1:
            self._properties_t1 = self._properties
            self._properties = self._properties_t0
            self._gcode_script.write("T0\n")
            self._toolhead = 0
        else:
            raise Exception("Something's wrong here... toolchange in CAM_Interface.py")

    # Getter #
    def get_pos(self):
        """
        Returns coordinates tupel (X,Y,Z).

        :return tupel(X,Y,Z)
        """
        return self._x, self._y, self._z

    def _get_extrusion_distance(self, length: float) -> float:
        """
        Calculates extrusion distance on given length of GCode move. E Value for G-code

        :param length: Length of strucutre to be extruded
        :return: extrusion distance in mm
        """
        if not (self._properties['layer_width'] and self._properties['layer_height'] and self._properties['layer_width']
                and self._properties['filament_diameter'] and self._properties['nozzle_diameter']):
            raise Exception("Print properties not set")
        if self._properties['layer_width'] < self._properties['layer_width']:
            raise Exception("Extruded width smaller than Nozzle, which is not possible")

        # from https://manual.slic3r.org/advanced/flow-math
        if self._properties['layer_width'] > 1.05 * self._properties['nozzle_diameter']:
            # E = (4/pi*(w - h) * h + h^2) * L / d_F^2
            return (4 / np.pi * (self._properties['layer_width'] - self._properties['layer_height']) *
                    self._properties['layer_height'] + self._properties['layer_height'] ** 2) * length / \
                   self._properties[
                       'filament_diameter'] ** 2
        else:
            # https://github.com/slic3r/Slic3r/issues/3118
            # E = (4*L*w*h)/(pi*D_F²)
            return (4 * length * self._properties['layer_width'] * self._properties['layer_height']) / (
                        np.pi * self._properties['filament_diameter'] ** 2)

    def get_print_property(self, keyword: str):
        """
        Returns requested property.

        :param keyword: str - keyword
        """
        if keyword in self._properties:
            return self._properties[keyword]
        raise ValueError(f"Keyword {keyword:s} does not exist!")

    # Setter #
    def set_print_properties(self, **kwargs):
        """
        Sets given print property

        :param kwargs: keyword(s) and value(s)
        """
        for key, value in kwargs.items():
            self._properties[key.lower()] = value

    def set_feedrate(self, feedrate: float):
        """
        Sets feedrate in mm/min via G1F

        :param feedrate: Feedrate in mm/min
        """
        self._gcode_script.write(f"G1F{feedrate:3.3f}\n")

    def set_tool(self, tool: int):
        """
        Sets active toolhead.
        """
        pass
        # @Todo: Support for multiple toolheads

    def set_speed_override(self, value: float, increment=False):
        """
        Set speed factor override percentage (M220 S<percent>)

        :param value: Value in percent.
        :param increment: If true, value will be incremented.
        """
        if abs(value) > 0:
            if increment:
                self._properties['speed_override'] += value
            else:
                self._properties['speed_override'] = value
            self._gcode_script.write(f"M220S{self._properties['speed_override']:.2f}\n")

    def set_extrude_override(self, value: float, increment=False):
        """
        Set extrude factor override percentage (M221 S<percent>)

        :param value: Value in percent.
        :param increment: If true, value will be incremented.
        """
        if abs(value) > 0:
            if increment:
                self._properties['extrude_override'] += value
            else:
                self._properties['extrude_override'] = value
            self._gcode_script.write(f"M221S{self._properties['extrude_override']:.2f}\n")

    def _set_mode(self, inc: bool):
        """
        Set incremental (G91) or absolute (G90=

        :param inc: True for incremental mode
        """
        if inc:
            self._set_relative_mode()
        else:
            self._set_absolute_mode()

    def _set_absolute_mode(self):
        """
        Sets to absolute mode (G90).
        """
        if self._inc_mode:
            self._gcode_script.write("G90\n")
            self._inc_mode = False

    def _set_relative_mode(self):
        """
        Sets to incremental mode (G91).
        """
        if not self._inc_mode:
            self._gcode_script.write("G91\n")
            self._inc_mode = True

    def set_firmware_retraction(self, **kwargs):
        """
        Change parameters for firmware retraction G10/G11 codes according to
        https://www.klipper3d.org/G-Codes.html#firmware-retraction

        :param kwargs: length, speed, un_length, un_speed
        """
        if not self._simulation:
            self._gcode_script.write("SET_RETRACTION ")
            if 'length' in kwargs:
                self._gcode_script.write(f"RETRACT_LENGTH={kwargs['length']} ")
            if 'speed' in kwargs:
                self._gcode_script.write(f"RETRACT_SPEED={kwargs['speed']} ")
            if 'un_length' in kwargs:
                self._gcode_script.write(f"UNRETRACT_EXTRA_LENGTH={kwargs['un_length']} ")
            if 'un_speed' in kwargs:
                self._gcode_script.write(f"UNRETRACT_SPEED={kwargs['un_speed']}")
            self._gcode_script.write("\n")

    # Methoden für Skript #
    def add_comment(self, comment: str):
        """
        Add comment to Gcode script

        :param comment: some text
        """
        self._gcode_script.write(f"; {comment}\n")

    def save_script(self, filename: str):
        """
        Save G-Code script under given (relative) path.

        :param filename: filename / relative path
        """
        with open(f"{filename}", mode='w') as f:
            print(self._gcode_script.getvalue(), file=f)
            print(f"File saved at {filename}")

    def upload_script(self, filename: str):
        """
        Upload script via moonraker API

        :param filename: filename
        """
        #@Todo: upload via moonraker api
        if 'simulation' in self._properties and self._properties['simulation']:
            self.save_script(f"/home/ptnano/webgcode/webapp/samples/show_me.gcode")
            self.copy_to_clipboard()
        else:
            self.save_script(f"/home/ptnano/gcode_files/{filename}.gcode")

    def copy_to_clipboard(self):
        """
        Copy Gcode script to clipboard. E.g. for verifying with ncviewer.com or repetier host.
        """
        print("Script copied to clipboard.")
        pyperclip.copy(self._gcode_script.getvalue())

    def show_script(self):
        """
        Show generated Gcode script in stdout.
        """
        print(self._gcode_script.getvalue())
