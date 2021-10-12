import numpy as np
import sys
import os
import queue
import threading
from tkinter import Tk
from datetime import datetime
from time import sleep
import moonraker
import Marcator_1086R_HR
import userinterface
import constant


class Backend:
    _current_pos = 0
    _result_pos_list = []
    _target_pos_list = []
    _result_dist_list = []
    _target_dist_list = []
    _error_list = []
    _suspicious_error = .5
    _max_pos = 0
    _min_pos = 0
    _measurement_dict = {}
    _master_dict = {}
    _start_time = None
    _hist = None
    _plot = None
    _count = 0

    def __init__(self, master):
        print("Messuhr richtig positionieren!")
        print(f"Verfahren der {constant.AXIS}-Achse in {constant.DIRECTION} Richtung soll Messuhr eindrücken\nbzw. "
              f"Messwert erhöhen.\n")
        self._measurement_queue = queue.Queue()
        self._master_queue = queue.Queue()
        
        self._gui_master = master
        # GUI Initialisieren
        self._gui = userinterface.GuiWindow(master, self._measurement_queue, self._master_queue,
                                            self.start_measurement, self.stop_measurement, self.save_data)
        # Objekte und Parameter für Messung und Steuerung initialisieren
        self._min_pos = constant.MIN_POS + constant.SAFETY_DISTANCE
        self._max_pos = constant.MAX_POS - constant.SAFETY_DISTANCE
        self._moonraker = moonraker.Moonraker(constant.PRINTER, local=constant.LOCAL)
        self._moonraker.set_axis(constant.AXIS)
        self._moonraker.set_feedrate(constant.FEEDRATE)
        self._dial_gauge = Marcator_1086R_HR.DialGauge(constant.SERIAL_PORT)
        # Messuhr wird manchmal nicht sofort korrekt ausgelesen.
        # Bei zu großem Fehler soll erneut ausgelesen werden
        self._suspicious_error = constant.SUSPICIOUS_ERROR
        print(f"Fehler verdächtig, wenn größer {self._suspicious_error:+2.4f}.")
        # Variablen für Messungs-Thread
        self._running = False
        self._measurement_thread = None
        self._periodic_call()

    def _periodic_call(self):
        """
        Check every 200 ms if there is something new in the queue.
        """
        self._gui.process_incoming()
        self._gui_master.after(200, self._periodic_call)
        if self._running:
            # Letzte X Zeichen sind Mikrosekunden. Nicht Notwendig
            self._master_dict['runtime'] = str(datetime.now() - self._start_time)[:-7]
            self._master_queue.put(self._master_dict)

    def start_measurement(self):
        if not self._running:
            self._master_dict['btn_txt'] = "Messung stoppen"
            self._running = True
            self._start_time = datetime.now()
            self._measurement_thread = threading.Thread(target=self._measurement, name='Measurement-Thread')
            self._measurement_thread.start()
        else:
            self._running = False
            self._master_dict['btn_txt'] = "Messung starten"

    def _measurement(self):
        """
        Startet Messroutine
        """
        i = 0
        while self._running:
            # Iteration und start/beenden der Messung mit einer Variable
            self._running = False if i >= constant.ITERATIONS else True
            # Startposition messen und merken
            current_pos = self._dial_gauge.read_data()
            print(f"Start-Position:\t{current_pos:+2.4f}")
            old_pos = current_pos
            # Neue Position bestimmen und anfahren
            self._request_next_position(current_pos)
            # Messen der neuen Position und bestimmen der gefahrenen Distanz
            # Mehrmaliges auslesen mit Delay notwendig, da beim ersten mal der alte Wert gelesen wird....
            successful_read = False
            error, result_dist, retries = 9, 0, 0
            while not successful_read and retries < 5:
                current_pos = self._dial_gauge.read_data()
                # Abs Werte, da VZ dann angibt ob zu weit oder zu kurz gefahren
                error = abs(result_dist) - abs(self._target_dist_list[-1])
                if constant.DIRECTION == '-':
                    result_dist = old_pos - current_pos
                elif constant.DIRECTION == '+':
                    result_dist = current_pos - old_pos
                if abs(error) > self._suspicious_error:
                    print(f"Fehler sehr groß ({result_dist:+2.4f} -> {error:+2.4f}). Lese Messuhr erneut aus..({retries})")
                    retries = retries + 1
                    sleep(1)
                else:
                    successful_read = True
            
            # Speichern der Messwerte in Liste und Ausgabe ind stdout für Debugging/Überwachung
            self._result_pos_list.append(current_pos)
            self._result_dist_list.append(result_dist)
            self._error_list.append(error)
            print(f"Ist-Position:\t{current_pos:+2.4f}\nIst-Distanz:\t{result_dist:+2.4f}\nFehler:\t\t{error:+2.4f}\n")
            # dictionary für Übergabe an GUI vorbereiten und übergeben
            self._measurement_dict['x_data'] = self._target_dist_list
            self._measurement_dict['y_data'] = self._error_list
            self._measurement_dict['target'] = self._target_dist_list[-1]
            self._measurement_dict['result'] = self._result_dist_list[-1]
            self._measurement_dict['error'] = self._error_list[-1]
            self._measurement_dict['max_error'] = (np.max(self._error_list), np.min(self._error_list))
            self._measurement_dict['abs_max_error'] = np.max(np.abs(self._error_list))
            self._measurement_dict['mean_error'] = np.mean(np.abs(self._error_list))
            self._measurement_dict['count'] = i + 1
            self._measurement_dict['progress'] = (i + 1) / constant.ITERATIONS
            self._measurement_dict['max_pos'] = self._max_pos + 2
            self._measurement_queue.put(self._measurement_dict)
            i = i + 1

        print("Messung beendet.")
        return None

    def _request_next_position(self, current_pos):
        """
        Legt nächste anzufahrende Position fest und fährt diese an.
        """
        # Angeforderte Positionen nur so genau, wie Messuhr auslesen kann
        new_pos = np.round(np.random.uniform(self._min_pos, self._max_pos), decimals=4)
        if constant.DIRECTION == '-':
            distance = current_pos - new_pos
        elif constant.DIRECTION == '+':
            distance = new_pos - current_pos
        self._target_dist_list.append(distance)
        self._target_pos_list.append(new_pos)
        # Ausgabe der Soll-Position und Distanz
        print(f"Soll-Position:\t{new_pos:+2.4f}\nSoll-Distanz:\t{distance:+2.4f}")
        self._moonraker.move(distance)

    def save_data(self):
        """
        Methode zum Sichern der in GUI angezeigter Plots mit Zeitstempel
        """
        # Prüfen und Ordner existiert. Ggf erstellen
        if not os.path.exists(constant.DATA_DIR):
            os.mkdir(constant.DATA_DIR)
        # Zeitstempel und Basisname für Daten und Plots
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        fname_base = f"{constant.DATA_DIR}/{timestamp}_Messung_{constant.PRINTER}_{constant.AXIS}"
        # Plots speichern - .svg zum bearbeiten, .jpg für schnelle Ansicht
        self._gui.fig.savefig(fname_base + '.svg')
        self._gui.fig.savefig(fname_base + '.jpg')
        # Vorbereiten des Ausgabe Arrays
        out = np.zeros((len(self._target_dist_list), 5))
        out[:, 0] = np.asarray(self._target_pos_list)
        out[:, 1] = np.asarray(self._result_pos_list)
        out[:, 2] = np.asarray(self._target_dist_list)
        out[:, 3] = np.asarray(self._result_dist_list)
        out[:, 4] = np.asarray(self._error_list)
        # Alle Parameter in Headerzeilen der Datei schreiben
        header_text = (f"PRINTER: {constant.PRINTER}\n"
                       f"AXIS: {constant.AXIS}\n"
                       f"FEEDRATE: {constant.FEEDRATE}\n"
                       f"DIRECTION: {constant.DIRECTION}\n"
                       f"ITERATIONS: {constant.ITERATIONS}\n"
                       f"SERIAL_PORT: {constant.SERIAL_PORT}\n"
                       f"LOCAL: {constant.LOCAL}\n"
                       f"DATA DIR: {constant.DATA_DIR}\n"
                       f"MAX POS: {constant.MAX_POS}\n"
                       f"MIN POS: {constant.MIN_POS}\n"
                       f"SAFETY DISTANCE: {constant.SAFETY_DISTANCE}\n"
                       f"SUSPICIOUS ERROR: {constant.SUSPICIOUS_ERROR}\n"
                       f"COMMENT: {constant.COMMENT}\n"
                       f"Soll Position; Gemessene Position; Soll Distanz; Gemessene Distanz; Abweichung von Soll")
        np.savetxt(fname_base + '.txt', out, fmt='%+2.4f', delimiter=';', header=header_text)
        print(f"Daten unter {fname_base} gespeichert.")

    def stop_measurement(self):
        if self._running:
            print("Stoppe Messung.")
            self._running = False
            # Warte auf terminieren von MessungsThread
            self._measurement_thread.join()
            # GUI beenden und warten bis Thread terminiert
            self._gui_master.destroy()
            # self._gui_thread.join()
        #Nur manuelles Speichern um versehentliches spammen zu vermeiden
        #self.save_data()
        sys.exit(1)


root = Tk()
client = Backend(root)
root.mainloop()
