from .get_data import library_conditions, lib_mod_lookup
import flaskr.helper_functions as hp
import matplotlib.pyplot as plt
import math
from functools import lru_cache
import numpy as np
from scipy.optimize import fsolve
from flaskr.models import CellData, PanelInfo, ModuleData, CellLookup, ModuleLookup, WholeModuleLookup
from flaskr import db
from pvlib import pvsystem


#models the individual solar cells
class Solar_Cell():
    #shard cache for all solar cells
    _cell_cache = None

    #constructor matching material of a cell to its ideal conditions
    def __init__(self, initial_conditions, panel_name, shadow, temp):
        try:
            #an array containing conditions given 25 degrees and 950 irradiance
            self.panel_name = panel_name
            self.ACTUAL_CONDITIONS = [0,0,0,0,0,0,0]
            self.parent = None

            #loads cache for first instance 
            if Solar_Cell._cell_cache is None:
                Solar_Cell._load_cell_cache()

            if initial_conditions is not None:
                Iph, Is, n, Rs, Rp = initial_conditions
                self.ACTUAL_CONDITIONS = [Iph, Is, n, Rs, Rp, 25, 950]
            else:
                self.ACTUAL_CONDITIONS[5] = temp
                self.ACTUAL_CONDITIONS[6] = shadow
                self.set_library_conditions()

        except Exception as e:
            print("Error constructing cell: ", e)

    #loads the cache at the class level
    @classmethod
    def _load_cell_cache(cls):
        print("Loading shared module cache from DB...")
        cls._cell_cache = {
            (rec.panel_name, rec.key): rec.value
            for rec in CellLookup.query.all()
        }
        print(f"Loaded {len(cls._cell_cache)} entries into shared cache")

    #using caching to store sets of values based on heat/irradiance
    def _lookup(self, *key):
        key_str = hp._key_from_floats(*key)

        #query the cache
        try:
            result = Solar_Cell._cell_cache[(self.panel_name, key_str)]
            results = hp._floats_from_key(result) 
            return results[0], results[1], results[2], results[3], results[4]
        except:
            #if no conditions
            raise ValueError("No cached record")

    #takes an input of a shade level and returns the correct irradiance
    def set_shade(self, irr, temp):
        try:
            self.ACTUAL_CONDITIONS[5] = temp
            self.ACTUAL_CONDITIONS[6] = irr
            self.set_library_conditions()
        except Exception as e:
            print("Shading level incorrect: ", e)

    #checks temperature in an acceptable range (0-75)
    def set_temp(self, temp):
        try:
            if -15<=temp<=75:
                self.ACTUAL_CONDITIONS[5] = temp
            else:
                raise ValueError("Temp between -15 and 75 celcius")
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

    #saving cell conditions to hash table
    def save_hash_c(self, G, T, Iph, Is, n, Rs, Rp):
        key = hp._key_from_floats(G,T)
        values = hp._key_from_floats(Iph, Is, n, Rs, Rp)

        Solar_Cell._cell_cache[(self.panel_name, key)] = values

        existing = CellLookup.query.filter_by(panel_name=self.panel_name, key=key).first()

        if existing:
            existing.value = values
        else:
            new_record = CellLookup(
                panel_name=self.panel_name,
                key=key,
                value=values
            )
            db.session.add(new_record)
        db.session.commit()

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
    #shared cache between modules
    _module_cache = None

    def __init__(self, initial_conditions, panel_name, cell_count, rows):
        #initiates variables
        self.cell_count = cell_count
        self.rows = rows
        self.cell_list = []
        self.panel_name = panel_name

        self.temperature = 25
        self.irradiance = 1000

        #initiates cache if non existant
        if Simple_Module._module_cache is None:
            Simple_Module._load_module_cache()

        #test if any cells have been shaded
        self.shaded = False

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
                        #reference self in the child cell
                        cell.parent = self 
                        self.cell_list.append(cell)
                        temp.append(cell)
                    self.cell_array.append(temp)

                self.bypass_diode = Bypass_Diode(self.cell_list)
            else:
                raise ValueError

        except ValueError as e:
            print("Need the number of cells to be divisible by number of rows")

    #open caching for voltage
    @classmethod
    def _load_module_cache(cls):
        print("Loading shared module cache from DB...")
        cls._module_cache = {
            (rec.panel_name, rec.key): rec.voltage
            for rec in ModuleLookup.query.all()
        }
        print(f"Loaded {len(cls._module_cache)} entries into shared cache")

    # #open caching for voltage of the whole module
    # @classmethod
    # def _load_whole_module_cache(cls):
    #     print("Loading shared module cache from DB...")
    #     cls._module_cache = {
    #         (rec.panel_name, rec.key): rec.voltage
    #         for rec in WholeModuleLookup.query.all()
    #     }
    #     print(f"Loaded {len(cls._module_cache)} entries into shared cache")

    # def _module_lookup(self, I, Iph, Is, Rs, Rp, nNsVth):
    #     key_str = hp._key_from_floats(I, Iph, Is, Rs, Rp, nNsVth)

    #     try:
    #         return Simple_Module._module_cache[(self.panel_name, key_str)]
    #     except KeyError:
    #         return math.nan

    def _lookup(self, I, Iph, Is, nC, Rs, Rp, Kt):
        key_str = hp._key_from_floats(I, Iph, Is, nC, Rs, Rp, Kt)

        try:
            return Simple_Module._module_cache[(self.panel_name, key_str)]
        except KeyError:
            return math.nan

    #sets the module to either there is shaded cells or no shaded cells
    def update_shaded(self, s_bool):
        self.shaded = s_bool

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
        nNsVth = nC * nS * (k * Kt / q)

        voltage = self.find_hash_v(I, Iph, Is, nC, Rs, Rp, Kt)

        if math.isnan(voltage):
            # try using pvlib function if fails test using the linear solver
            try:
                voltage = pvsystem.v_from_i(
                    current=I,
                    photocurrent=Iph,
                    saturation_current=Is,
                    resistance_series=Rs,
                    resistance_shunt=Rp,
                    nNsVth=nNsVth
                )
            except Exception:
                # fallback to fsolve if v_from_i fails
                def func(V):
                    exponent = (q * (V + I*Rs)) / (nC * nS * k * Kt)
                    exponent = np.clip(exponent, -600, 600)
                    return Iph - Is * (np.exp(exponent) - 1) - (V + I*Rs)/Rp - I
                
                voltage = fsolve(func, x0=self.module_open_voltage())[0]

            self.save_hash_v(I, Iph, Is, nC, Rs, Rp, Kt, voltage)

        return voltage

    #gets the whole voltage if it can 
    # def whole_module_voltage(self, I, *values):
    #     Iph, Is, Rs, Rp, nNsVth = values

    #     if self.shaded:
    #         return self.bypass_diode.find_voltage(I)

    #     voltage = self._module_lookup(I, Iph, Is, Rs, Rp, nNsVth)

    #     # fallback
    #     if math.isnan(voltage):
    #         voltage = pvsystem.v_from_i(
    #             current=I,
    #             photocurrent=Iph,
    #             saturation_current=Is,
    #             resistance_series=Rs,
    #             resistance_shunt=Rp,
    #             nNsVth=nNsVth
    #         )

    #     # only save valid voltages
    #     if not math.isnan(voltage):
    #         self.save_hash_mod_v(I, Iph, Is, Rs, Rp, nNsVth, voltage)

    #     return voltage


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
        Iph = np.inf
        Is = nC = Rs = Rp = Kt = 0
        for i, cell in enumerate(self.cell_list):
            t_Iph, t_Is, t_nC, t_Rs, t_Rp, t_Kt = cell.get_params()
            if t_Iph < Iph:
                Iph = t_Iph
            Is += t_Is
            nC += t_nC
            Rs += t_Rs
            Rp += t_Rp
            Kt += t_Kt
        
        #want averages of certain parameter
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
    
    #opens dictionary based on panel name to save the information
    #cache handles any misses (_lookup)
    def save_hash_v(self, current, Iph, Is, nC, Rs, Rp, Kt, voltage):
        key = hp._key_from_floats(current, Iph, Is, nC, Rs, Rp, Kt)

        Simple_Module._module_cache[(self.panel_name, key)] = voltage

        existing = ModuleLookup.query.filter_by(panel_name=self.panel_name, key=key).first()

        if existing:
            existing.voltage = voltage
        else:
            new_record = ModuleLookup(
                panel_name=self.panel_name,
                key=key,
                voltage=voltage
            )
            db.session.add(new_record)
        db.session.commit()

    # def save_hash_mod_v(self, current, Iph, Is, Rs, Rp, nNsVth, voltage):
    #     key = hp._key_from_floats(current, Iph, Is, Rs, Rp, nNsVth)

    #     Simple_Module._module_cache[(self.panel_name, key)] = voltage

    #     existing = WholeModuleLookup.query.filter_by(panel_name=self.panel_name, key=key).first()

    #     if existing:
    #         existing.voltage = voltage
    #     else:
    #         new_record = WholeModuleLookup(
    #             panel_name=self.panel_name,
    #             key=key,
    #             voltage=voltage
    #         )
    #         db.session.add(new_record)
    #     db.session.commit()

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

    #rearranged to find the voltage
    def find_voltage(self, I):
        q = 1.6e-19
        k = 1.38e-23

        Isbd, nbd, Tbd = self.get_params()

        voltage = (nbd * k * Tbd / q) * np.log(I / Isbd + 1)
        return voltage

#models the panels as a collection of modules
class Panel():
    def __init__(self, initial_conditions, panel_name, module_count=3, cell_per_module=18, row_per_module=2):
        
        self.module_count = module_count
        self.cell_per_module = cell_per_module
        self.row_per_module = row_per_module
        self.panel_name = panel_name

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
    def voltage_summation(self, I, unshaded_count, unshaded_val):
        sum_v = 0

        for i, module in enumerate(self.module_list):
            values = self.load_dict(module)

            #increase count if shaded
            if module.shaded == False:
                unshaded_count += 1
                #test if value already calculated
                if unshaded_val == None:
                    unshaded_val = module.get_voltage(I, values)
                continue

            #also need to test if Iph is too low values[0] is iph
            if self.short_circuits[i] < I or I > values[0]: 
                module.activate_bypass() 
                sum_v += module.bypass_diode.find_voltage(I)
                
            else:
                sum_v += module.get_voltage(I, values)

        return sum_v, unshaded_count, unshaded_val

    def voltage_modelling(self, I):
        sum_v = 0
        for i, module in enumerate(self.module_list):
            if module.shaded == True:
                sum_v += -0.7
            else:
                values = self.load_dict(module)

                if self.short_circuits[i] < I or I > values[0]:
                    module.activate_bypass()
                    sum_v += -0.7
                else:
                    sum_v += module.get_voltage(I, values)
        
        return sum_v

    # def module_modelling(self, I):
    #     sum_v = 0
    #     for module in self.module_list:
    #         G = module.irradiance
    #         T = module.temperature
    #         Iph, Is, Rs, Rp, nNsVth = lib_mod_lookup(self.panel_name, G, T)
    #         sum_v += module.whole_module_voltage(I, Iph, Is, Rs, Rp, nNsVth)

    #     return sum_v

        #store the total parameters per module in the dictionary
    def store_dict(self, module, *values):
        self.module_conditions[module] = values

    def load_dict(self, module):
        values = self.module_conditions[module]
        return values
    
    #models currents against voltage to get max power
    def model_power(self, draw_graph=False):
        self.set_short_circuits()
        #finds max current to test
        max_I = self.get_max_iph()

        currents = np.linspace(0, self.short_circuits[0], 30)
        voltages = [self.voltage_modelling(I) for I in currents]
        powers = [V*I for V, I in zip(voltages, currents)]

        max_index = np.argmax(powers)
        Pmax, Vmp, Imp = powers[max_index], voltages[max_index], currents[max_index]  

        if draw_graph:
            hp.draw_graph(powers, voltages, currents)

        return Pmax, Vmp, Imp

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

            self.voltage_offset = None

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
        unshaded_count = 0
        unshaded_val = None
        sum_v = 0

        #adds up number of unshaded panels
        for panel in self.panel_list:
            voltage, unshaded_count, unshaded_val = panel.voltage_summation(I, unshaded_count, unshaded_val)
            sum_v += voltage

        #multiplies by the unshaded value
        if unshaded_val is not None:
            sum_v += (unshaded_val*unshaded_count)

        return sum_v

    # #models the voltage with a module as a whole
    # def get_voltage_module(self, I):
    #     print(f'Testing current {I}')
    #     # Step 1: cache module parameters once per unique module condition
    #     con_dict = {}
    #     for panel in self.panel_list:
    #         for module in panel.module_list:
    #             key = (module.panel_name, module.irradiance, module.temperature)
    #             if key not in con_dict:
    #                 con_dict[key] = lib_mod_lookup(module.panel_name, module.irradiance, module.temperature)

    #     # Step 2: sum module voltages
    #     sum_v = 0
    #     for panel in self.panel_list:
    #         for module in panel.module_list:
    #             values = con_dict.get((module.panel_name, module.irradiance, module.temperature))
    #             if values is not None:
    #                 sum_v += module.whole_module_voltage(I, *values)
    #     return sum_v


    #models power of the string
    def model_power(self, draw_graph=False):
        try:
            max_I = self.get_max_iph()
            currents = list(np.linspace(0, max_I, 30))
            voltages = [
                self.get_voltage(I)*self.voltage_offset if self.voltage_offset is not None
                else self.get_voltage(I) for I in currents
            ]
            
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

    def reset(self, irr, temp):
        try:
            for panel in self.panel_list:
                for module in panel.module_list:
                    module.update_shaded(False)
                    for cell in module.cell_list:
                        cell.set_shade(irr, temp)
                panel.set_short_circuits()

                output = 'reset succesfully'
        except Exception as e:
            output = 'reset failed'
            raise e
            
        return output

    # def module_reset(self, irr, temp):
    #     for panel in self.panel_list:
    #         for module in panel.module_list:
    #             module.temperature = temp
    #             module.irradiance = irr

    def find_bypasses(self, I):
        output = []
        for i, panel in enumerate(self.panel_list):
            for j, module in enumerate(panel.module_list):
                if module.bypass_diode.active == True:
                    output.append(f'Panel {i} module {j} bypass active')
                    output.append(f'Panel {i} module {j} I = {I}, Isc = {module.Isc}')

        return output
