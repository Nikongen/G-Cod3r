import numpy as np

from CAM_Interface import CAM_Interface

"""
Bibliothek mit grundlegenden Strukturen
"""
class CAM_structures():

    def __init__(self, interface: CAM_Interface):
        """
        Constructor for CAM methods. Needs object with CAM_Interface

        :param interface: CAM_Interface object
        """
        self._interface = interface

    def square_aperture(self, outer: float, inner: float, overlap=.25):
        """
        Hollow square aperture.

        :param outer: Outer length in mm
        :param inner: Inner length in mm
        :param overlap: layer overlap in percent
        """
        a = outer
        b = self._interface.get_print_property('layer_width') * (1-overlap)
        while a > inner:
            self._interface.rel_print(x=a)
            self._interface.rel_print(y=a)
            a -= b
            self._interface.rel_print(x=-a)
            self._interface.rel_print(y=-a)
            a -= b

    def rect_aperture(self, outer_x: float, outer_y: float, inner_x: float, inner_y: float, overlap=.25):
        """
        Hollow rectangle aperture.

        outer_x/inner_x > outer_y/inner_y

        Start at edge with smallest x,y coordinates
        :param outer_x: Seitenlänge außen in mm
        :param outer_y: Seitenlänge außen in mm
        :param inner_x: Seitenlänge Aussparung/Loch in mm
        :param inner_y: Seitenlänge Aussparung/Loch in mm
        :param overlap: Prozentualer überlapp der Schichten
        """
        start_pos = self._interface.get_pos()
        x = (outer_x - inner_x) / 2
        y = (outer_y - inner_y) / 2
        # Rechteck Rahmen um Gitter drucken. Sobald kleinere Breite erreicht, die größeren Blöcke einzeln drucken
        curr_x = inner_x
        curr_y = inner_y
        stride = self._interface.get_print_property('layer_width') * (1 - overlap)
        # Innen anfangen und nach außen schnecken
        while curr_y < outer_y:
            self._interface.rel_print(x=curr_x)
            self._interface.rel_print(y=curr_y)
            curr_x += stride
            curr_y += stride
            self._interface.rel_print(x=-curr_x)
            if curr_y >= outer_y:
                break
            self._interface.rel_print(y=-curr_y)
            curr_x += stride
            curr_y += stride
        # Ende "inneres Rechteck" an Startecke nur weiter außen
        # Position anfahren
        block1_x = start_pos[0] - (outer_y - inner_y) / 2
        block1_y = start_pos[1] - (outer_y - inner_y) / 2
        self._interface.abs_move(x=block1_x, absolute=True)
        self._interface.abs_move(y=block1_y, absolute=True)
        w = (outer_x - (inner_x + (outer_y - inner_y))) / 2
        curr_w = 0
        while curr_w < w:
            self._interface.rel_print(y=outer_y)
            curr_w += stride
            if curr_w >= w:
                break
            self._interface.rel_print(x=-stride)
            self._interface.rel_print(y=-outer_y)
            curr_w += stride
            if curr_w >= w:
                break
            self._interface.rel_print(x=-stride)
        # Anderen Randblock zeichnen
        # Position anfahren
        block2_x = start_pos[0] + inner_x + (outer_y-inner_y)/2 + stride/2
        block2_y = start_pos[1] - (outer_y-inner_y)/2
        self._interface.abs_move(x=block2_x, absolute=True)
        self._interface.abs_move(y=block2_y, absolute=True)
        curr_w = 0
        while curr_w < w:
            self._interface.rel_print(y=curr_y)
            curr_w += stride
            if curr_w >= w:
                break
            self._interface.rel_print(x=stride)
            self._interface.rel_print(y=-curr_y)
            curr_w += stride
            if curr_w >= w:
                break
            self._interface.rel_print(x=stride)


    def lattice(self, n: float, d: float, length: float):
        """
        Print lattice according to parameters.

        :param n: number of bars
        :param d: distance btwn bars
        :param length: length of bars
        :return:
        """
        a = n
        while a > 0:
            self._interface.rel_print(x=length)
            self._interface.rel_print(y=d)
            self._interface.rel_print(x=-length)
            self._interface.rel_print(y=d)
            a -= 2 * d
