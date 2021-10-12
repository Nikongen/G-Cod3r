#!/usr/bin/python3.8

import requests
import json

'''
Read the Docs: https://moonraker.readthedocs.io/en/latest/web_api/
'''


def get_result(r):
    """
    Takes string response of HTTP Request and returns it in JSON format.

    :param r: Response of HTTP Request
    :return: JSON Dictionary of input
    """
    response = json.loads(r.text)
    if 'error' in response:
        raise Exception(f"Printer reports error: {response['error']}")
    if 'result' in response:
        return response['result']
    else:
        print(f"\tMoonraker:\t Json decode error: {r.text}")
        return f"\tMoonraker:\t Json decode error..."


class Moonraker:
    _websocket = ''
    _printer = ''
    _axis = ''
    _feedrate = ''

    def __init__(self, url='localhost', port=7125):
        """
        Constructor of moonraker class. Defines URL with moonraker websocket (for HTTP Post/Get requests) and prints
        'state_message' for given printer, if connection is successful.

        :param url: URL/IP of printer. Default is localhost
        :param port: Port of moonraker API. Default is 7125
        """
        self._set_url(url, port)
        r = get_result(requests.get(f"{self._websocket}/printer/info"))
        # May catch error if connection not successful
        print(f"Moonraker:\t {r['state_message']!s}")

    def __del__(self):
        """
        Destructor: Sends M112 - Emergency Stop G-code to printer.
        """
        requests.post(f"{self._websocket}/printer/emergency_stop")

    def _set_url(self, url='localhost', port=7125):
        """
        Sets Websocket out of url and port for connection with moonraker API

        :param url: URL/IP of printer. Default is localhost
        :param port: Port of moonraker API. Default is 7125
        """
        self._websocket = f"{url}:{port}"

    def send_g_code(self, gcode):
        """
        Sends given Gcode via moonraker API

        :param gcode: GCode to be sent
        """
        base = "/printer/gcode/script?script="
        print(f"\tMoonraker:\t Sending G-Code {gcode}")
        return get_result(requests.post(f"{self._websocket}{base}{gcode}"))

    def check_state(self):
        """
        Checks printer state (Standby, Busy, Idle)
        """
        # Moonraker API Anfrage für Durcker Status (Printing,Ready,Idle)
        r = get_result(requests.get(f"{self._websocket}/printer/info"))
        state = r['state']
        stae_msg = r['state_message']
        print(f"\tMoonraker:\t {state}:{stae_msg}")

    def upload_code(self):
        pass
        # @Todo: https://moonraker.readthedocs.io/en/latest/web_api/#file-upload
