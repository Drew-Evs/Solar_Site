import pvlib
import numpy as np
import math
from pvlib import pvsystem
from flaskr.models import CustomPanel
from flaskr import db

'''
@func need to use the pvlib to get the features of a module needed for calculation 
    (Iph, Isat, Rs, Rp, nNsVth) - then convert to per cell (Ns = num cells)
    To do this rs = rs/Ns, nVth = nNsVth/Ns and rp = rp*Ns
@params panel name, irradiance, cell temperature
@output Iph, Isat, Rs, Rp, nNsVth
'''
def _get_cell_conditions(panel_name, G, T):
    #get the module from the library
    cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
    try:
        module = cec_modules[panel_name]
        Ns = module['N_s']

        #calculates the parameters
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

        #convert to cell conditions
        Rs_cell = Rs / Ns
        Rp_cell = Rp * Ns
        nVth_cell = nNsVth / Ns
        Iph_cell = Iph
        Is_cell = Is

        return Iph_cell, Is_cell, nVth_cell, Rs_cell, Rp_cell
    except:
        try:
            # if this fails attempt extraction from database
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

            Rs_cell = Rs / Ns
            Rp_cell = Rp * Ns
            nVth_cell = nNsVth / Ns
            Iph_cell = Iph
            Is_cell = Is

            return Iph_cell, Is_cell, nVth_cell, Rs_cell, Rp_cell
        except Exception as e:
            print(f'_get_cell_condtions failed: {e}')
            raise

'''
@func use the cell conditions and the pvlib single diode model to calculate voltage at certain currents
    need to output the voltage of a cell given the cell temperature, irradiance and current
@params panel_name, G, T and current
@output the voltage of the cell
'''
def _get_voltage_from_current(panel_name, G, T, I, values=None):
    try:
        if values is None:
            Iph_cell, Is_cell, nVth_cell, Rs_cell, Rp_cell = _get_cell_conditions(panel_name, G, T)
        else:
            #get the cell conditions
            Iph_cell, Is_cell, nVth_cell, Rs_cell, Rp_cell = values

        #use v_from_i to return the voltage
        voltage = pvsystem.v_from_i(
            current=I,
            photocurrent=Iph_cell,
            saturation_current=Is_cell,
            resistance_series=Rs_cell,
            resistance_shunt=Rp_cell,
            nNsVth=nVth_cell
        )

        if math.isnan(voltage):
            return -0.7

        return voltage
    except Exception as e:
        print(f'_get_voltage_from_current failed: {e}')
        raise

'''
@func use the cell conditions and the pvlib single diode model to calculate current at certain voltages
    need to output the voltage of a cell given the cell temperature, irradiance and current
@params panel_name, G, T and voltage
@output the current of the cell
'''
def _get_current_from_voltage(panel_name, G, T, V, values):
    try:
        #get the cell conditions
        Iph_cell, Is_cell, nVth_cell, Rs_cell, Rp_cell = values

        #use v_from_i to return the voltage
        current = pvsystem.i_from_v(
            voltage=V,
            photocurrent=Iph_cell,
            saturation_current=Is_cell,
            resistance_series=Rs_cell,
            resistance_shunt=Rp_cell,
            nNsVth=nVth_cell
        )

        if math.isnan(current):
            return 0

        return current
    except Exception as e:
        print(f'_get_voltage_from_current failed: {e}')
        raise

'''
@func take the input of the cell_list to count up the shaded/unshaded cells
    multiply by the value of the shaded cell voltage/unshaded cell voltage
@params cell_list, shaded_voltage, unshaded_voltage
@output voltage added up
'''
def _calculate_voltage(cell_list, *values):
    shaded_voltage, unshaded_voltage = values
    shaded_count = unshaded_count = 0

    #iterate through cell list
    for cell in cell_list:
        shade = cell._get_shade()
        if shade:
            shaded_count += 1
        else:
            unshaded_count += 1

    #multiply by the shaded value 
    voltage = 0
    voltage += shaded_voltage * shaded_count
    voltage += unshaded_voltage * unshaded_count

    return voltage

'''
@func calculate the current of the bypass diode - see if its activated
    if the current is positive, then need to activate 
    uses the negative of the module voltage
@params voltage
@output current
'''
def _get_bypass_current(voltage):
    #negative of the voltage = bypass voltage
    bd_v = -voltage

    #the costants used to calculate
    q = 1.6e-19
    k = 1.38e-23
    Isbd = 1.6 * (10 ** -9)
    nbd = 1
    Tbd = 308.15 #in kelvin

    #finds current with a clipped exponent
    exponent = np.clip((q * bd_v) / (nbd * k * Tbd), -600, 600)
    current = Isbd * (np.exp(exponent) - 1)

    return current
