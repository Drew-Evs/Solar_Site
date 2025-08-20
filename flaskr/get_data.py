import pvlib
import numpy as np
import pandas as pd
import os
import difflib
from flaskr.models import PanelInfo, CustomPanel
from . import db

def create_csv_entry(panel_name):
    cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
    #use a list of temperatures/irradiances to get results to place in the neural net
    temperatures = np.linspace(10, 50, 16)
    irrads = np.linspace(100, 1000, 36)

    records = []

    try:
        #test for close matches first
        if panel_name not in cec_modules.columns:
            print(f"Panel '{panel_name}' not found in library.")
            suggestions = difflib.get_close_matches(panel_name, cec_modules.columns, n=3)
            if suggestions:
                print("Did you mean:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")
            raise Exception
        else:
            print(f"{panel_name} found in library")

        module = cec_modules[panel_name]
        print(f'Creating entry for panel name {panel_name}')
        #testing if each module has the required items to calculate data
        required = ['alpha_sc', 'a_ref', 'I_L_ref', 'I_o_ref', 'R_sh_ref', 'R_s']
        if not all(param in module and not pd.isna(module[param]) for param in required):
            print(F'Skipping {panel_name} as its missing parameters')
            raise Exception

        #iterate through each one outputting a record
        for cell_t in temperatures:
            for G in irrads:
                Iph, Is, Rs, Rp, nNsVth = pvlib.pvsystem.calcparams_desoto(
                    effective_irradiance = G,
                    temp_cell = cell_t,
                    alpha_sc=module['alpha_sc'],
                    a_ref=module['a_ref'],
                    I_L_ref=module['I_L_ref'],
                    I_o_ref=module['I_o_ref'],
                    R_sh_ref=module['R_sh_ref'],
                    R_s=module['R_s'],
                    EgRef=1.121,
                    dEgdT=-0.0002677
                )

                #use nNsVth to estimate ideality
                k = 1.380649e-23
                q = 1.602e-19
                T_K = cell_t + 273.15
                Vth = k * T_K / q
                Ns = module['N_s']
                n = nNsVth / (Ns * Vth)

                # Try to get height and width if they exist
                length = module.get('Length', None)  # in mm
                width = module.get('Width', None)    # in mm

                Nd = max(1, Ns//20)

                records.append([panel_name, G, cell_t, Iph, Is, n, Rs, Rp, Ns, Nd, length, width])

        df = pd.DataFrame(records, columns=['name', 'G', 'T', 'Iph', 'Is', 'n', 'Rs', 'Rp', 'Ns', 'Nd', 'L(m)', 'W(m)'])

        # If file exists, append to existing and is non empty else new entry made 
        if os.path.exists('solar_data.csv') and os.path.getsize('solar_data.csv') > 0:
            df_existing = pd.read_csv('solar_data.csv')
            df_combined = pd.concat([df_existing, df], ignore_index=True)
        else:
            df_combined = df

        # Write once
        df_combined.to_csv('solar_data.csv', index=False)
        print(f"Successfully saved data for {panel_name}")

        return 1

    except Exception as e:
        print(f'Failed module {panel_name} because of {e}')
        return 0

def library_conditions(panel_name, G, T):
    cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
    try:
        try: 
            module = cec_modules[panel_name]
        
            Iph, Is, Rs, Rp, nNsVth = pvlib.pvsystem.calcparams_desoto(
                effective_irradiance = G,
                temp_cell = T,
                alpha_sc=module['alpha_sc'],
                a_ref=module['a_ref'],
                I_L_ref=module['I_L_ref'],
                I_o_ref=module['I_o_ref'],
                R_sh_ref=module['R_sh_ref'],
                R_s=module['R_s'],
                EgRef=1.121,
                dEgdT=-0.0002677
            )

            Ns = module['N_s']

        #if not in cecmod check database
        except:
            from flask import current_app
            with current_app.app_context():
                record = CustomPanel.query.filter_by(
                    panel_name=panel_name
                ).first()
            
            Ns = record.num_cells

            Iph, Is, Rs, Rp, nNsVth = pvlib.pvsystem.calcparams_desoto(
                effective_irradiance = G,
                temp_cell = T,
                alpha_sc=record.alpha_sc,
                a_ref=record.a_ref,
                I_L_ref=record.i_l_ref,
                I_o_ref=record.i_o_ref,
                R_sh_ref=record.r_sh_ref,
                R_s=record.r_s,
                EgRef=1.121,
                dEgdT=-0.0002677
            )

        #use nNsVth to estimate ideality
        k = 1.380649e-23
        q = 1.602e-19
        T_K = T + 273.15
        Vth = k * T_K / q 
        n = nNsVth / (Ns * Vth)

        return Iph, Is, nNsVth, Rs, Rp
        
    except Exception as e:
        print(f'{panel_name} not in library: {e}')
        raise

#gets the whole module lookup info
def lib_mod_lookup(panel_name, G, T):
    cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
    try:
        module = cec_modules[panel_name]
    
        Iph, Is, Rs, Rp, nNsVth = pvlib.pvsystem.calcparams_desoto(
            effective_irradiance = G,
            temp_cell = T,
            alpha_sc=module['alpha_sc'],
            a_ref=module['a_ref'],
            I_L_ref=module['I_L_ref'],
            I_o_ref=module['I_o_ref'],
            R_sh_ref=module['R_sh_ref'],
            R_s=module['R_s'],
            EgRef=1.121,
            dEgdT=-0.0002677
        )

        return Iph, Is, Rs, Rp, nNsVth
    except:
        print("Failed")
        return None

#builds a database of panels at standard conditions
def build_database_mod():
    from flaskr import create_app
    app = create_app()

    cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')

    records = []

    with app.app_context():
        try:         
            for name in cec_modules:
                module = cec_modules[name]

                Ns = module['N_s']

                # Try to get height and width if they exist
                length = module.get('Length', None)  # in mm
                width = module.get('Width', None)    # in mm

                Nd = max(1, Ns//20)

                new_record = PanelInfo(
                    panel_name=name,
                    length=length,
                    width=width,
                    num_cells=Ns,
                    num_diodes=Nd
                )
                db.session.add(new_record)
                print(f"Successfully saved data for {name}")

            db.session.commit()

        except Exception as e:
            print(f'Failed because of {e}')


#uses the input dc and the inverter name to test output power
def find_ac_power(inverter_name, in_p):
    try:
        #test for close matches first
        if inverter_name not in inverters.columns:
            print(f"Panel '{inverter_name}' not found in library.")
            suggestions = difflib.get_close_matches(inverter_name, inverters.columns, n=3)
            if suggestions:
                print("Did you mean:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")
            raise Exception
        else:
            print(f"{inverter_name} found in library")

        inverter = inverters[inverter_name]

        print(f"Rated power of inverter is {inverter['Pdco']} W")

        AC_P = pvlib.inverter.pvwatts(in_p, inverter['Pdco'])

        #also want the voltage
        AC_V = inverter['Vac']
        print(f'Power {AC_P} voltage {AC_V}')
        
        return AC_P, AC_V
    except Exception as e:
        print(f'{inverter_name} not found')

def build_database_inverter():
    inverters = pvlib.pvsystem.retrieve_sam('CECInverter')

    records = []

    for name in inverters.columns:
        inverter = inverters[name]
        AC_V = inverter['Vac']
        AC_P_rated = inverter['Paco']
        DC_V_rated = inverter['Pdco']
        V_max = inverter['Vdcmax']
        I_max = inverter['Idcmax']
        low_mpp = inverter['Mppt_low']
        high_mpp = inverter['Mppt_high']

        records.append([name, AC_V, AC_P_rated, DC_V_rated,
                       V_max, I_max, low_mpp, high_mpp])
        print(f'added {name}')
        
    df = pd.DataFrame(records, columns=['Name', 'AC V output', 'Rated AC power at STC', 'Rated DC V at STC', 'Max DC V',
                                        'Max DC I', 'Lower MPPT V', 'Upper MPPT V'])
    
    df.to_csv('Inverter_Database.csv')
    print("Saved data succesfully")
    
def build_database():
    build_database_inverter()
    build_database_mod()

def attempt():
    sand_modules = pvlib.pvsystem.retrieve_sam(path='/workspaces/Solar_Site/PV_Module_List_Full_Data_ADA.xlsx')
    print(sand_modules.keys())
    #print([model for model in sand_modules.keys() if 'KM550' in model])

def print_cec_module_params(panel_name):
    # Retrieve the CEC module database
    cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
    
    if panel_name not in cec_modules:
        print(f"Panel '{panel_name}' not found in CEC database.")
        return
    
    module = cec_modules[panel_name]
    
    print(f"=== {panel_name} ===")
    print(f"alpha_sc: {module['alpha_sc']}")
    print(f"a_ref: {module['a_ref']}")
    print(f"I_L_ref: {module['I_L_ref']}")
    print(f"I_o_ref: {module['I_o_ref']}")
    print(f"R_sh_ref: {module['R_sh_ref']}")
    print(f"R_s: {module['R_s']}")
    print(f"N_s: {module['N_s']}")

if __name__ == "__main__":
    print_cec_module_params('Jinko_Solar_Co___Ltd_JKM410M_72HL_V')