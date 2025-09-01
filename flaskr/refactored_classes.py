import numpy as np
from .models import PanelInfo
from flaskr.simple_calc import _get_bypass_current, _calculate_voltage, _get_current_from_voltage, _get_cell_conditions, _get_voltage_from_current
import os
import pandas as pd
import flaskr.refactored_helper as hp
'''
@class simplified version of the cell class
    want to hold whether the cell is shaded/not shaded
@methods - get_shade()
        - set_shade()
'''
class Cell():
    def __init__(self):
        self.shaded = False
        self.parent = None
    
    def _set_shade(self, shade_val=True):
        self.shaded = shade_val

    def _get_shade(self):
        return self.shaded

'''
@class simplified version of the module class
    holds a list of cell objects
@methods - get_voltage(I, shaded_voltage, unshaded_voltage)
'''
class Module():
    def __init__(self, num_cells):
        self.cell_list = [Cell() for _ in range(num_cells)]

    #need to get the voltage of the module
    def _get_voltage(self, *values):
        shaded = False
        shaded_voltage, unshaded_voltage = values

        voltage = _calculate_voltage(self.cell_list, shaded_voltage, unshaded_voltage)

        #if the bypass is active set voltage to 0.7
        if _get_bypass_current(voltage) > 0:
            voltage = 0.7

        return voltage

'''
@class simplified version of panel class
    holds a list of modules and the number of cells in each one
@methods - get_voltage(I, shaded_voltage, unshaded_voltage)
    - all_cells() - flattens cells
'''
class Panel():
    def __init__(self, cells_per_module, num_modules):
        self.module_list = [Module(cells_per_module) for _ in range(num_modules)]
        self.shaded = False

    #adds up the voltage of all modules
    def _get_voltage(self, *values):
        voltage = 0
        for module in self.module_list:
            voltage += module._get_voltage(*values)

        return voltage

    #flattens all the cells into a single list
    def _all_cells(self):
        return [cell for module in self.module_list for cell in module.cell_list]

'''
@class simplified version of the string class
    holds a list of panels
    used to calculate the values of shaded/unshaded cell parameters
    then uses them to get the shaded/unshaded voltages of each current
    uses this to calculate power
@methods - get_voltage()
    - model_power() - finds pmp
    - set_shade_conditions() - sets irr/temp of shaded and unshaded 
    - all_cells() - flattens cells
    - short_circuit() - finds the short circuit value to test between 
    - get_params() - returns shaded and unshaded parameters
    - calc_voltages() - returns shaded and unshaded voltages
'''
class String():
    def __init__(self, num_panels, panel_name, left_top_point, rotation):
        try:
            #test database
            record = PanelInfo.query.filter_by(
                panel_name=panel_name
            ).first()

            if record:
                Ns = record.num_cells
                Nd = record.num_diodes
                l = record.length
                w = record.width

            #calculate the total num of rows (typically 6 in a row)
            self.num_rows = Ns//6

            #finds the dimensions of the cell
            self.cell_height = float(l)/self.num_rows
            self.cell_width = float(w)/6

            #sets the rotation of the string
            self.rotation = rotation

            #need to input the number of diodes per module, and number of cells per module
            self.panel_list = [Panel(Ns//Nd, Nd) for _ in range(num_panels)]
            self.panel_name = panel_name
            self.num_panels = num_panels

            #sets the irradiance/temperature values of the un/shaded cells
            self._set_shade_conditions((1000, 25), (100, 25))

            #the top left point of the string 
            self.left_top_point = left_top_point

            #a voltage offset to match up to the reality of the panel
            self.voltage_offset = None

        except Exception as e:
            print(f'Cant build solar string - missing database information: {e}')
            raise

    #sets the irr/temp
    def _set_shade_conditions(self, shaded, unshaded):
        self.shaded_conditions = shaded
        self.unshaded_conditions = unshaded
        
        #set the shaded/unshaded params
        self._get_params()

    #sets the iph, is etc. values
    def _get_params(self):
        self.shaded_params = _get_cell_conditions(self.panel_name, self.shaded_conditions[0], self.shaded_conditions[1])
        self.unshaded_params = _get_cell_conditions(self.panel_name, self.unshaded_conditions[0], self.unshaded_conditions[1])

    #find the short circuit when voltage is 0
    def _short_circuit(self):
        return _get_current_from_voltage(self.panel_name, self.unshaded_conditions[0], self.unshaded_conditions[1],
            0, self.unshaded_params)

    #given a current calculate the shade/unshaded voltages
    def _calc_voltages(self, I):
        shaded_voltage = _get_voltage_from_current(self.panel_name, self.shaded_conditions[0], self.shaded_conditions[1],
            I, self.shaded_params)
        unshaded_voltage = _get_voltage_from_current(self.panel_name, self.unshaded_conditions[0], self.unshaded_conditions[1],
            I, self.unshaded_params)
        return shaded_voltage, unshaded_voltage

    #get the sum voltage of all panels
    def _get_voltage(self, I):
        #gets the shaded/unshaded voltages
        shaded_voltage, unshaded_voltage = self._calc_voltages(I)
        voltage = 0
        for panel in self.panel_list:
            voltage += panel._get_voltage(shaded_voltage, unshaded_voltage)

        return voltage

    #model power to find the max
    def _model_power(self, shaded, unshaded, time, site_name='Windmill', output_csv=False):
        #takes in the shaded/unshaded conditions
        self._set_shade_conditions(shaded, unshaded)

        voltages = []

        #finds the short circuit to test between
        short_circuit = self._short_circuit()
        #creates a series of currents to test between
        currents = list(np.linspace(0, short_circuit, 20))

        #tests each current to find the voltages then sums each module voltage
        voltages = [
            self._get_voltage(I)*self.voltage_offset if self.voltage_offset is not None
            else self._get_voltage(I) for I in currents
        ]

        #zip results and calculates the power then max power
        results = [(i, v) for i, v in zip(currents, voltages)]
        powers = [i * v for i, v in results]

        max_index = np.argmax(powers)
        
        Pmax = powers[max_index]
        Vmp = voltages[max_index]
        Imp = currents[max_index]

        if output_csv == True:
            self._create_csv(Imp, time, site_name)

        return Pmax, Vmp, Imp

    #create a csv of the information
    def _create_csv(self, Imp, time, site_name):
        shaded_voltage, unshaded_voltage = self._calc_voltages(Imp)

        #list of results
        panel_num = []
        voltages = []
        shade = []
        
        for i, panel in enumerate(self.panel_list):
            shaded = False
            temp_voltage = panel._get_voltage(shaded_voltage, unshaded_voltage)

            voltages.append(
                temp_voltage*self.voltage_offset if self.voltage_offset is not None
                else temp_voltage
            )

            all_cells = panel._all_cells()
            for cell in all_cells:
                if cell.shaded == True:
                    shaded = True
                    break

            panel_num.append(i+1)
            shade.append(shaded)
        
        powers = [Imp * v for v in voltages]

        data = {
            'Panel Number': panel_num,
            'Current': [hp._round_sf(float(Imp))] * self.num_panels,
            'Voltage': [hp._round_sf(float(v)) for v in voltages],
            'Power': [hp._round_sf(float(p)) for p in powers],
            'Shaded': shade
        }

        df = pd.DataFrame(data)

        #save to folder
        folder_name = f"{site_name}_output_csv"
        file_name = f"{site_name}_{time.strftime('%Y:%m:%d_%H:%M')}.csv"
        full_path = os.path.join("csv_outputs", folder_name, file_name)
        df.to_csv(full_path, index=False)

    #returns a list of all cells
    def all_cells(self):
        return [cell for panel in self.panel_list for cell in panel._all_cells()]

    #resets all shade to unshaded
    def reset_shade(self):
        for cell in self.all_cells():
            cell._set_shade(False)
