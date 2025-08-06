from .get_data import library_conditions
import flaskr.helper_functions as hp
import matplotlib.pyplot as plt
import math
from functools import lru_cache
import numpy as np
from scipy.optimize import fsolve
from flaskr.models import CellData, PanelInfo, ModuleData
from flaskr import db


#models the individual solar cells
class Solar_Cell():
    #constructor matching material of a cell to its ideal conditions
    def __init__(self, initial_conditions, panel_name, shadow, temp):
        try:
            #an array containing conditions given 25 degrees and 950 irradiance
            self.panel_name = panel_name
            self.ACTUAL_CONDITIONS = [0,0,0,0,0,0,0]
            if initial_conditions is not None:
                Iph, Is, n, Rs, Rp = initial_conditions
                self.ACTUAL_CONDITIONS = [Iph, Is, n, Rs, Rp, 25, 950]
            else:
                self.ACTUAL_CONDITIONS[5] = temp
                self.ACTUAL_CONDITIONS[6] = shadow
                self.set_library_conditions()

        except Exception as e:
            print("Error constructing cell: ", e)

    #using caching to store sets of values based on heat/irradiance
    @lru_cache(maxsize=10000)
    def _lookup(self, *key):
        G, T = key

        #query the model
        record = CellData.query.filter_by(
            panel_name = self.panel_name,
            temperature = self.round_3sf(T),
            irradiance = self.round_3sf(G)
        ).first() 

        if record:
            #return the saved conditions
            return record.iph, record.isat, record.n, record.Rs, record.Rp

        #if no conditions
        raise ValueError("No cached record")

    #takes an input of a shade level and returns the correct irradiance
    def set_shade(self, irr):
        try:
            self.ACTUAL_CONDITIONS[6] = irr
            self.set_library_conditions()
        except Exception as e:
            print("Shading level incorrect: ", e)

    #checks temperature in an acceptable range (0-75)
    def set_temp(self, temp):
        try:
            if 10<=temp<=50:
                self.ACTUAL_CONDITIONS[5] = temp
            else:
                raise ValueError("Temp between 0 and 75 celcius")
        except ValueError as e:
            print(e)

    #with the input conditions and a voltage find current
    #this has to be solved via a numerical method
    def find_current(self, V):
        q = (1.6 * (10**-19))
        k = (1.38 * (10**-23))

        Iph, Is, n, Rs, Rp, T = self.get_params()
        #finds root where this = 0
        def func(I):    
            exponent = (q*(V+I*Rs))/(n*k*T)
            current = Iph - Is * (np.exp(exponent) - 1) - (V+I*Rs)/Rp - I
            return current
        
        return fsolve(func, x0 = Iph)[0]
    
    #same method for voltage
    def find_voltage(self, I):
        q = 1.6e-19
        k = 1.38e-23

        Iph, Is, n, Rs, Rp, T = self.get_params()
        def diode_eqn(V):
            return Iph - Is * (np.exp((q * (V + I * Rs)) / (n * k * T)) - 1) - ((V + I * Rs) / Rp) - I

        try:
            V_guess = 0.5  # Reasonable starting guess (in volts)
            V_solution = fsolve(diode_eqn, x0=V_guess)[0]
        except Exception as e:
            print("Voltage solve failed:", e)
            return np.nan

        return V_solution

    #finds params then outputs ISC
    def find_short_circuit(self):
        return self.find_current(0)
    
    #outputs Voc
    def find_open_voltage(self):
        return self.find_voltage(0)

    #finds both if not in db
    def find_isc_voc(self):
        T = self.ACTUAL_CONDITIONS[5]
        G = self.ACTUAL_CONDITIONS[6]
        record = CellData.query.filter_by(
            panel_name = self.panel_name,
            temperature = T,
            irradiance = G
        ).first() 

        #if the record is found 
        if record:
            if record.voc is None:
                voc = self.find_open_voltage()
                record.voc = voc
            else:
                voc = record.voc

            if record.isc is None:
                isc = self.find_short_circuit()
                record.isc = isc
            else:
                isc = record.isc

            db.session.commit()

            return voc, isc
        
        #if record not in the database need to calculate params and set
        self.set_library_conditions()
        return self.find_isc_voc()

    #uses the voltage to find the max power
    #can set to true to output a graph
    def model_power(self, draw_graph=False):
        voc = self.find_open_voltage()
        #creates a normal range of voltages to test
        voltages = np.linspace(0, voc, 25) 
        currents = [self.find_current(V) for V in voltages]
        powers = [V*I for V, I in zip(voltages, currents)]

        power_index = np.argmax(powers)
        Pmax = powers[power_index]
        Vmp = voltages[power_index]
        Imp = currents[power_index]

        if draw_graph:
            hp.draw_graph(powers, voltages, currents, 'Cell', self.panel_name)

        self.volts = Vmp
        self.current = Imp

        T = self.ACTUAL_CONDITIONS[5]
        G = self.ACTUAL_CONDITIONS[6]

        record = CellData.query.filter_by(
            panel_name = self.panel_name,
            temperature = T,
            irradiance = G
        ).first() 

        if record:
            if record.pmax is None:
                record.pmax = Pmax
                record.vmp = Vmp
                record.imp = Imp

            db.session.commit()

            return Pmax, Vmp, Imp

        else: 
            self.set_library_conditions()
            return self.model_power(draw_graph)

    def get_params(self):
        Iph = self.ACTUAL_CONDITIONS[0]
        Is = self.ACTUAL_CONDITIONS[1]
        n = self.ACTUAL_CONDITIONS[2]
        Rs = self.ACTUAL_CONDITIONS[3]
        Rp = self.ACTUAL_CONDITIONS[4]
        Kt = self.ACTUAL_CONDITIONS[5] + 273.15

        return Iph, Is, n, Rs, Rp, Kt
    
    def set_library_conditions(self):
        try:
            T = self.ACTUAL_CONDITIONS[5]
            G = self.ACTUAL_CONDITIONS[6]
            
            #test if instance of tuple to look for cache hit
            try:
                values = self.find_hash_c(G, T)
                #print("Found in db")
                Iph, Is, n, Rs, Rp = values
            except ValueError:
                print("Not found checking library")
                Iph, Is, n, Rs, Rp = library_conditions(self.panel_name, G, T)
                self.save_hash_c(G, T, Iph, Is, n, Rs, Rp)

            self.ACTUAL_CONDITIONS[0] = Iph
            self.ACTUAL_CONDITIONS[1] = Is
            self.ACTUAL_CONDITIONS[2] = n
            self.ACTUAL_CONDITIONS[3] = Rs
            self.ACTUAL_CONDITIONS[4] = Rp
        except Exception as e:
            raise
    
    #convert a key from temperature and irr
    def _key_from_floats(self, *numbers, prec=2):
        return "|".join(f"{x:.{prec}g}" for x in numbers)

    #saving cell conditions to hash table
    def save_hash_c(self, G, T, Iph, Is, n, Rs, Rp):

        new_record = CellData(
            panel_name=self.panel_name,
            irradiance=self.round_3sf(G),
            temperature=self.round_3sf(T),
            iph=self.round_3sf(Iph),
            isat=self.round_3sf(Is),
            n=self.round_3sf(n),
            Rs=self.round_3sf(Rs),
            Rp=self.round_3sf(Rp)
        )
        db.session.add(new_record)
        db.session.commit()
        self._lookup.cache_clear()

    #finding the hash conditions
    def find_hash_c(self, *key):
        return self._lookup(*key)

    def round_3sf(self, x):
        if x == 0:
            return 0
        else:
            from math import log10, floor
            return round(x, 2 - int(floor(log10(abs(x)))))

#models a series of solar cells connected to a bypass diode
class Simple_Module():
    def __init__(self, initial_conditions, panel_name, cell_count, rows):
        #initiates variables
        self.cell_count = cell_count
        self.rows = rows
        self.cell_list = []
        self.panel_name = panel_name

        #open caching for voltage
        @lru_cache(maxsize=10_000)
        def _lookup(I, Iph, Is, nC, Rs, Rp, Kt):
            try:
                record = ModuleData.query.filter_by(
                    kt = Kt,
                    iph = Iph,
                    isat = Is,
                    n = nC,
                    Rs = Rs,
                    Rp = Rp,
                    current = I
                ).first()
                return record.voltage
            except Exception as e:
                return math.nan
        
        self._lookup = _lookup

        self.Isc = 0

        #each module has 1 bypass diode and a set number of rows of cells
        #every row should have the same ammount
        try: 
            self.cell_array = []
            if self.cell_count % self.rows == 0:
                for i in range(self.rows):
                    temp = []
                    for j in range(self.cell_count//rows):
                        cell = Solar_Cell(initial_conditions, panel_name, 950, 25)
                        self.cell_list.append(cell)
                        temp.append(cell)
                    self.cell_array.append(temp)

                self.bypass_diode = Bypass_Diode(self.cell_list)
            else:
                raise ValueError

        except ValueError as e:
            print("Need the number of cells to be divisible by number of rows")

    #gets the min isc of module
    def actual_short_circuit(self):
        self.Isc = self.get_current(0)
        return self.Isc

    #calculates total open voltage
    def module_open_voltage(self):
        open_v = 0
        for cell in self.cell_list:
            open_v += cell.find_open_voltage()
        return open_v
    
    #gets voltage given current and average parameters
    def get_voltage(self, I, values=None):
        if values is None:
            Iph, Is, nC, Rs, Rp, Kt = self.get_total_params()
        else:
            Iph, Is, nC, Rs, Rp, Kt = values

        q = (1.6 * (10**-19))
        k = (1.38 * (10**-23))

        nS = self.cell_count

        value = self.find_hash_v(I, Iph, Is, nC, Rs, Rp, Kt) 
        if not math.isnan(value): 
            return value
        
        #finds root where this = 0
        def func(V):    
            exponent = (q*(V+I*Rs))/(nC*nS*k*Kt)
            exponent = np.clip(exponent, -600, 600)
            current = Iph - Is * (np.exp(exponent) - 1) - (V+I*Rs)/Rp - I
            return current

        Voc = self.module_open_voltage()
        initial_guess = Voc
        voltage = fsolve(func, x0 = initial_guess)[0]
        
        self.save_hash_v(I, Iph, Is, nC, Rs, Rp, Kt, voltage) 

        return voltage

    #current calculations
    def get_current(self, V):
        Iph, Is, nC, Rs, Rp, Kt = self.get_total_params()

        q = (1.6 * (10**-19))
        k = (1.38 * (10**-23))

        nS = self.cell_count

        #finds root where this = 0
        def func(I):    
            exponent = (q*(V+I*Rs))/(nC*nS*k*Kt)
            current = Iph - Is * (np.exp(exponent) - 1) - (V+I*Rs)/Rp - I
            return current
        
        return fsolve(func, x0 = Iph)[0]

    #get average results for calculation
    def get_total_params(self):
        self.update_cell_conditions()
        Iph = Is = nC = Rs = Rp = Kt = 0
        for i, cell in enumerate(self.cell_list):
            t_Iph, t_Is, t_nC, t_Rs, t_Rp, t_Kt = cell.get_params()
            Iph += t_Iph
            Is += t_Is
            nC += t_nC
            Rs += t_Rs
            Rp += t_Rp
            Kt += t_Kt
        
        #want averages of certain parameters
        Iph = Iph/self.cell_count
        Is = Is/self.cell_count
        nC = nC/self.cell_count
        Kt = Kt/self.cell_count

        return Iph, Is, nC, Rs, Rp, Kt

    #models power of the module
    def find_max_power(self, draw_graph=False):
        #if the bypass diode active then want to stop it
        if self.bypass_diode.active == False:
            #sets the conditions of each cell based on sunlight
            self.update_cell_conditions()

            #get the maximum current that flows (short circuit current)
            max_v = self.module_open_voltage()

            max_v = self.module_open_voltage()
            voltages = np.linspace(0, max_v, 25) 
            currents = [self.get_current(V) for V in voltages]
            powers = [V*I for V, I in zip(voltages, currents)]

            power_index = np.argmax(powers)

            Pmax = powers[power_index]
            Vmp = voltages[power_index]
            Imp = currents[power_index]
            
            if draw_graph:
                hp.draw_graph(voltages, currents, powers)

            self.volts = Vmp
            self.current = Imp

            return Pmax, Vmp, Imp
        else:
            return 0, 0, 0

    #will return a stable key to use as a float
    def _key_from_floats(self, *numbers, prec=6):
        return "|".join(f"{x:.{prec}g}" for x in numbers)
    
    #opens dictionary based on panel name to save the information
    #cache handles any misses (_lookup)
    def save_hash_v(self, current, Iph, Is, nC, Rs, Rp, Kt, voltage):
        new_record = ModuleData(
            kt=Kt,
            iph=Iph,
            isat=Is,
            n=nC,
            Rs=Rs,
            Rp=Rp,
            voltage=voltage,
            current=current
        )
        db.session.add(new_record)
        db.session.commit()
        #syncs the RAM and cache
        self._lookup.cache_clear()

    #tests if hash in dictionary already 
    def find_hash_v(self, current, Iph, Is, nC, Rs, Rp, Kt):
        return self._lookup(current, Iph, Is, nC, Rs, Rp, Kt)
        
    #turn on the bypass diode
    def activate_bypass(self):
        self.bypass_diode.activate()
        
    def update_cell_conditions(self):
        for i, cell in enumerate(self.cell_list):
            cell.set_library_conditions()

    def print_module(self, num, I):
        V = self.get_current(I)
        rows = [f'-- Module {num} --']
        for r in range(self.rows):
            line = ("|".join(f"Cell {(r*6)+x} {cell.ACTUAL_CONDITIONS[6]}" for x, cell in enumerate(self.cell_array[r])))
            rows.append(line)

        status = "Bypass diode inactive" if self.bypass_diode.active == False else "Bypass diode active"
        status += f'| Current is {I:.2f} and Isc is {self.Isc:.2f} | Voltage is {V:.2f}'
        rows.append(status)
        return rows

    #output the module at the end
    def print_module(self, num, I):
        V = self.get_current(I)
        rows = [f'-- Module {num} --']
        for r in range(self.rows):
            line = ("|".join(f"Cell {(r*6)+x} {cell.ACTUAL_CONDITIONS[6]}" for x, cell in enumerate(self.cell_array[r])))
            rows.append(line)

        status = "Bypass diode inactive" if self.bypass_diode.active == False else "Bypass diode active"
        status += f'| Current is {I:.2f} and Isc is {self.Isc:.2f} | Voltage is {V:.2f}'
        rows.append(status)
        return rows

    def file_module(self, num, I):
        V = self.get_current(I)
        rows = [f'-- Module {num} --']
        for r in range(self.rows):
            line = ("|".join(f"Cell {(r*6)+x} {cell.ACTUAL_CONDITIONS[6]}" for x, cell in enumerate(self.cell_array[r])))
            rows.append(line)

        status = "Bypass diode inactive" if self.bypass_diode.active == False else "Bypass diode active"
        status += f'| Current is {I:.2f} and Isc is {self.Isc:.2f} | Voltage is {V:.2f}'
        rows.append(status)
        return rows

#models the bypass diodes
class Bypass_Diode():
    def __init__(self, connected_cells):
        self.connected_cells = connected_cells
        self.active = False
        self.Isbd = 1.6 * (10 ** -9)
        self.nbd = 1
        self.Tbd = 35 + 273.15

    def get_params(self):
        return self.Isbd, self.nbd, self.Tbd

    def activate(self):
        self.active = True
        for cell in self.connected_cells:
            cell.volts = -0.7/len(self.connected_cells)
            cell.current = 0

    def find_current(self, V):
        q = 1.6e-19
        k = 1.38e-23

        Isbd, nbd, Tbd = self.get_params()

        # finds current
        exponent = np.clip((q * V) / (nbd * k * Tbd), -600, 600)
        current = Isbd * (np.exp(exponent) - 1)
        
        return current

#models the panels as a collection of modules
class Panel():
    def __init__(self, initial_conditions, panel_name, module_count=3, cell_per_module=18, row_per_module=2,):
        
        self.module_count = module_count
        self.cell_per_module = cell_per_module
        self.row_per_module = row_per_module

        self.module_list = []
        for i in range(module_count):
            module = Simple_Module(initial_conditions, panel_name, cell_per_module, row_per_module)
            self.module_list.append(module)

        #need to initiate after module list created
        self.module_conditions = {} 

    #need the highest photocurrent of all modules to find the max current to test for
    def get_max_iph(self):
        #minimum value
        max_iph = float('-inf')
        for i, module in enumerate(self.module_list):
            Iph, Is, nC, Rs, Rp, Kt = module.get_total_params()
            self.store_dict(module, Iph, Is, nC, Rs, Rp, Kt)
            if Iph > max_iph:
                max_iph = Iph

        return max_iph

    def set_short_circuits(self):
        self.short_circuits = [module.actual_short_circuit() for module in self.module_list]
    
    #sum the voltage
    def voltage_summation(self, I):
        sum_v = 0

        for i, module in enumerate(self.module_list):
            values = self.load_dict(module)
            #also need to test if Iph is too low values[0] is iph
            if self.short_circuits[i] < I or I > values[0]:
                module.activate_bypass()
                sum_v += -0.7
            else:
                sum_v += module.get_voltage(I, values)

        return sum_v

        #store the total parameters per module in the dictionary
    def store_dict(self, module, *values):
        self.module_conditions[module] = values

    def load_dict(self, module):
        values = self.module_conditions[module]
        return values
    
    #models currents against voltage to get max power
    def model_power(self, draw_graph=False):
        #finds max current to test
        max_I = self.get_max_iph()

        currents = np.linspace(0, max_I, 20)
        voltages = [self.voltage_summation(I) for I in currents]
        powers = [V*I for V, I in zip(voltages, currents)]

        max_index = np.argmax(powers)
        Pmax, Vmp, Imp = powers[max_index], voltages[max_index], currents[max_index]  

        if draw_graph:
            hp.draw_graph(powers, voltages, currents)

    def set_db(self, hash_db):
        for module in self.module_list:
            module.hash_db = hash_db

    def close_cache(self):
        for module in self.module_list:
            module._lookup.cache_clear()
            for cell in module.cell_list:
                cell._lookup.cache_clear()

    def set_db_c(self, hash_db, isc_db):
        for module in self.module_list:
            for cell in module.cell_list:
                cell.hash_db = hash_db
                cell.isc_hash_db = isc_db

    def set_bypasses(self, I):
        for module in self.module_list:
            module.bypass_diode.active = I > module.Isc

    def print_panel(self, I, start_num: int = 0, col_sep: str = "   ||   "):
        # 1) Collect rows for every module
        module_blocks = [
            mod.print_module(idx, I)          
            for idx, mod in enumerate(self.module_list, start=start_num)
        ]

        # 2) Pad shorter blocks with "" so zip_longest works
        max_rows = max(len(block) for block in module_blocks)
        for block in module_blocks:
            block += [""] * (max_rows - len(block))

        # 3) Determine a single column width (max line length over all modules)
        col_width = max(len(line) for block in module_blocks for line in block)

        # 4) Pad every cell in every column to that width
        for block in module_blocks:
            for i, line in enumerate(block):
                block[i] = line.ljust(col_width)

        # 5) Print row by row
        for row_tuple in zip_longest(*module_blocks, fillvalue=" " * col_width):
            print(col_sep.join(row_tuple))
        print() 

    def file_panel(self, I, start_num: int = 0, col_sep: str = "   ||   "):
        # 1) Collect rows for every module
        module_blocks = [
            mod.file_module(idx, I)          
            for idx, mod in enumerate(self.module_list, start=start_num)
        ]

        # 2) Pad shorter blocks with "" so zip_longest works
        max_rows = max(len(block) for block in module_blocks)
        for block in module_blocks:
            block += [""] * (max_rows - len(block))

        # 3) Determine a single column width (max line length over all modules)
        col_width = max(len(line) for block in module_blocks for line in block)

        # 4) Pad every cell in every column to that width
        for block in module_blocks:
            for i, line in enumerate(block):
                block[i] = line.ljust(col_width)

        # 5) Print row by row
        output = []
        for row_tuple in zip_longest(*module_blocks, fillvalue=" " * col_width):
            output.append(col_sep.join(row_tuple))

        return "\n".join(output)

#models a string as a series of panels
class Solar_String():
    #constructs the solar string
    def __init__(self, panel_name, left_top_point, length=None, width=None, rotation=0, num_panels=25):
        try:
            self.left_top_point = left_top_point
            self.panel_name = panel_name

            #search db for info
            record = PanelInfo.query.filter_by(
                panel_name=panel_name
            ).first()

            if record:
                Ns = record.num_cells
                Nd = record.num_diodes
                l = record.length
                w = record.width

            if l is None or w is None:
                l = length
                w = width
                record.length = length
                record.width = width
                db.session.commit()

            self.length = float(l)
            self.width = float(w)

            self.rotation = rotation

            self.num_panels = num_panels

            #calculate the total num of rows (typically 6 in a row)
            num_rows = Ns//6
            row_module = num_rows//Nd
            
            #want to calculate width/height of each cell
            cell_height = self.length/num_rows
            #calc panel width/6
            cell_width = self.width/6

            self.cell_height = cell_height
            self.cell_width = cell_width

            #calculate overall initial conditions once for speed
            initial_conditions = library_conditions(panel_name, 950, 25)

            #find max of cells per module
            cells_per_module = row_module * 6

            #initiate the number of panels
            self.panel_list = []
            for i in range(num_panels):
                panel = Panel(initial_conditions, panel_name, Nd, cells_per_module, row_module)
                self.panel_list.append(panel)

                print(f"Panel {i} initiated")

            # #opens the hash table for updating cells
            # self.create_hash_c()
            # self.create_hash_isc()
            # for panel in self.panel_list:
            #     panel.set_db_c(self.c_hash_db, self.isc_hash_db)

            # #and for voltage
            # self.create_hash_v()
            # for panel in self.panel_list:
            #     panel.set_db(self.v_hash_db)
            #     panel.set_short_circuits()

        except Exception as e:
            print(f'Cant build that solar panel missing data - {e}')

    #get max iph from each panel to calculate own max iph
    def get_max_iph(self):
        max_iph = float('-inf')
        for panel in self.panel_list:
            panel.set_short_circuits()
            iph = panel.get_max_iph()
            if iph > max_iph:
                max_iph = iph

        return max_iph
    
    #calculate total voltage for the string given a current
    def get_voltage(self, I):
        print(f'Testing current {I}')
        sum_v = 0
        for panel in self.panel_list:
            sum_v += panel.voltage_summation(I)

        return sum_v

    #models power of the string
    def model_power(self, draw_graph=False):
        try:
            max_I = self.get_max_iph()
            currents = list(np.linspace(0, max_I, 15))
            voltages = [self.get_voltage(I) for I in currents]
            
            results = [(i, v) for i, v in zip(currents, voltages)]
            #need to unpack from results
            powers = [v * i for i, v in results]    

            max_index = np.argmax(powers)

            if draw_graph:
                hp.draw_graph(powers, voltages, currents)

            Pmax = powers[max_index]
            Vmp = voltages[max_index]
            Imp = currents[max_index]
            return Pmax, Vmp, Imp
        except Exception as e:
            print(f'error in modelling power: {e}')
            return 0, 0, 0

        #returns the four points of the solar string
    
    #gets the 4 points of the solar string
    def get_points(self):
        overall_width = (self.width * self.num_panels)/0.67
        length = self.length/0.67

        #convert to radians for calculating rotation vectors
        rd_rotation = np.radians(self.rotation)
        cos_t = np.cos(rd_rotation)
        sin_t = np.sin(rd_rotation)

        x, y = self.left_top_point

        #map the new points
        tl = (x, y)
        tr = (x + overall_width * cos_t, y + overall_width *sin_t )
        bl = (x - length * sin_t, y + length * cos_t)
        br = (tr[0] - length * sin_t, tr[1] + length * cos_t)

        #convert array into standard python float 
        base_array = [tl, tr, br, bl]
        converted = [(float(x), float(y)) for x, y in base_array]
        return converted

    #opens hash table for voltages
    def create_hash_v(self):
        #creates folder if doesn't exist
        folder = Path("./voltage_hash_tables")
        folder.mkdir(exist_ok=True)

        #get path to folder 
        panel_lookup = f'{self.panel_name}_lookup'
        self.hash_filename = str(folder / panel_lookup)

        #initiate db
        self.v_hash_db = shelve.open(self.hash_filename, flag="c", protocol=None, writeback=False)
    
    #opens a similar hash table for 
    def create_hash_c(self):
        #creates folder if doesn't exist
        folder = Path("./cell_hash_tables")
        folder.mkdir(exist_ok=True)

        #get path to folder 
        panel_lookup = f'{self.panel_name}_lookup'
        self.hash_filename = str(folder / panel_lookup)

        #initiate db
        self.c_hash_db = shelve.open(self.hash_filename, flag="c", protocol=None, writeback=False)

    #opens a similar hash table for short circuits
    def create_hash_isc(self):
        #creates folder if doesn't exist
        folder = Path("./isc_hash_tables")
        folder.mkdir(exist_ok=True)

        #get path to folder 
        panel_lookup = f'{self.panel_name}_lookup'
        self.hash_filename = str(folder / panel_lookup)

        #initiate db
        self.isc_hash_db = shelve.open(self.hash_filename, flag="c", protocol=None, writeback=False)

    def close(self):
        #close the hash db and the lru cache
        for panel in self.panel_list:
            panel.close_cache()
        self.v_hash_db.close()
        self.c_hash_db.close()

    #needs a way to test if bypasses should be activated
    def set_bypasses(self, I):
        for panel in self.panel_list:
            panel.set_bypasses(I)

    def print_string(self, I):
        num = 0
        for panel in self.panel_list:
            panel.print_panel(I, num)
            num += panel.module_count

    def file_string(self, I):
        output = ''
        num = 0
        for panel in self.panel_list:
            output += panel.file_panel(I, num)
            num += panel.module_count
        return output

    def reset(self, irr=100, temp=25):
        try:
            for panel in self.panel_list:
                for module in panel.module_list:
                    for cell in module.cell_list:
                        cell.set_temp(temp)
                        cell.set_shade(irr)
                panel.set_short_circuits()

                output = 'reset succesfully'
        except Exception as e:
            output = 'reset failed'
            raise e
            
        return output

    def find_bypasses(self, I):
        output = []
        for i, panel in enumerate(self.panel_list):
            for j, module in enumerate(panel.module_list):
                if module.bypass_diode.active == True:
                    output.append(f'Panel {i} module {j} bypass active')
                    output.append(f'Panel {i} module {j} I = {I}, Isc = {module.Isc}')

        return output
