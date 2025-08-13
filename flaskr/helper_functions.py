import pvlib
from pvlib.location import Location
from datetime import datetime, timedelta
import pytz
from pathlib import Path
import pandas as pd
import os
import matplotlib.pyplot as plt
import shelve
from .models import EnvironmentalData
from flask import current_app
from . import db
from timezonefinder import TimezoneFinder
import numpy as np
import requests
from zoneinfo import ZoneInfo
from scipy.optimize import least_squares
from pvlib.ivtools.sdm import fit_cec_sam
import math

#use pvlib to find irradiance and temperature of longitude and latitude for a day
def get_info(start, end, lat, long):
    start = start.replace(year=2021) 
    end = end.replace(year=2021)
    data, metadata = pvlib.iotools.get_pvgis_hourly(
        latitude=lat,
        longitude=long,
        start=start.year,
        end=end.year
    )

    #need to add a timezone to test between
    start = start.replace(tzinfo=pytz.UTC)
    end = end.replace(tzinfo=pytz.UTC)

    #filter dates with timezone
    data = data[(data.index >= start) & (data.index <= end)]

    return data

#adjust information to get only the total irradiance and temperature of the location given a date
def adjust_df(df):
    filtered = pd.DataFrame({
        'Total Irradiance (W/m2)': df['poa_direct'] + df['poa_sky_diffuse'] + df['poa_ground_diffuse'],
        'Temperature (°C)': df['temp_air'] + (df['poa_direct'] + df['poa_sky_diffuse'] + df['poa_ground_diffuse'])/800 * 22
    }, index=pd.to_datetime(df.index, utc=True))

    filtered.index = filtered.index.tz_convert('Asia/Kolkata')

    return filtered

#interpolate temperature and irradiance between points
def interpolate_df(df, timestep=10):
    # Ensure the index is sorted and datetime-aware
    df = df.sort_index()
    df.index = pd.to_datetime(df.index)

    # Store new interpolated rows
    new_rows = []

    # Get all index values
    idx = df.index
    num_points = int(60 / timestep)
    end = idx[-1]

    for i, hour in enumerate(idx[:-1]):
        try:
            current = df.loc[hour]
            next_hour = idx[i + 1]
            next_row = df.loc[next_hour]

            # Compute changes per timestep
            temp_change = (next_row['Temperature (°C)'] - current['Temperature (°C)']) / num_points
            irr_change = (next_row['Total Irradiance (W/m2)'] - current['Total Irradiance (W/m2)']) / num_points

            for j in range(1, num_points):
                new_time = hour + timedelta(minutes=j * timestep)
                new_temp = current['Temperature (°C)'] + j * temp_change
                new_irr = current['Total Irradiance (W/m2)'] + j * irr_change
                new_rows.append((new_time, new_irr, new_temp))

        except Exception as e:
            print(f'Error interpolating between {hour} and next: {e}')
            continue

    # Create DataFrame of new rows
    interp_df = pd.DataFrame(
        new_rows,
        columns=['index', 'Total Irradiance (W/m2)', 'Temperature (°C)']
    ).set_index('index')

    # Combine and sort
    full_df = pd.concat([df, interp_df])
    full_df = full_df.sort_index()
    full_df = full_df[~full_df.index.duplicated(keep='first')]

    return full_df

#store information into a csv file
def create_edatabase(start, end, lat, lon):
    if end is None:
        end = start + timedelta(hours=24)
        
    df = get_info(start, end, lat, lon)
    filtered = adjust_df(df)
    
    #store in the database
    with current_app.app_context():
        for i, (index, row) in enumerate(filtered.iterrows()):
            exists = EnvironmentalData.query.filter_by(
                date=index.replace(year=2025),
                latitude=lat,
                longitude=lon
            ).first()
            
            if not exists:
                record = EnvironmentalData(
                    date = index,
                    hour = i,
                    longitude=lon,
                    latitude=lat,
                    temperature=row['Temperature (°C)'],
                    irradiance=row['Total Irradiance (W/m2)']
                )
                db.session.add(record)
        
        db.session.commit()
    
    return filtered

#draws the graphs
def draw_graph(powers, voltages, currents, type, panel_name):
    output_dir = f'flaskr/static/plots/{panel_name}'
    os.makedirs(output_dir, exist_ok=True)

    plot_paths = []

    #creates the graphs and saves them to the plot
    # --- Plot Power vs Voltage ---
    plt.figure()
    plt.plot(voltages, powers, label='Power vs Voltage', color='blue')
    plt.xlabel('Voltage (V)')
    plt.ylabel('Power (W)')
    plt.title(f'{type} Power vs Voltage')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    power_vs_voltage_path = os.path.join(output_dir, f'{panel_name}_{type}_PV.png')
    plt.savefig(power_vs_voltage_path)
    plt.close()
    plot_paths.append(power_vs_voltage_path)

    # --- Plot Power vs Current ---
    plt.figure()
    plt.plot(currents, powers, label='Power vs Current', color='green')
    plt.xlabel('Current (A)')
    plt.ylabel('Power (W)')
    plt.title(f'{type} Power vs Current')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    power_vs_current_path = os.path.join(output_dir, f'{panel_name}_{type}_PI.png')
    plt.savefig(power_vs_current_path)
    plt.close()
    plot_paths.append(power_vs_current_path)

    # --- Plot Voltage vs Current ---
    plt.figure()
    plt.plot(currents, voltages, label='Voltage vs Current', color='red')
    plt.xlabel('Current (A)')
    plt.ylabel('Power (W)')
    plt.title(f'{type} Voltage vs Current')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    current_vs_voltage_path = os.path.join(output_dir, f'{panel_name}_{type}_IV.png')
    plt.savefig(current_vs_voltage_path)
    plt.close()
    plot_paths.append(current_vs_voltage_path)

    return plot_paths

#opens a similar hash table for 
def create_hash_c(panel_name):
    #creates folder if doesn't exist
    folder = Path("./flaskr/cell_hash_tables")
    folder.mkdir(exist_ok=True)

    #get path to folder 
    panel_lookup = f'{panel_name}_lookup'
    hash_filename = str(folder / panel_lookup)

    #initiate db
    c_hash_db = shelve.open(hash_filename, flag="c", protocol=None, writeback=False)
    return c_hash_db

#opens a similar hash table for short circuits
def create_hash_isc(panel_name):
    #creates folder if doesn't exist
    folder = Path("./flaskr/isc_hash_tables")
    folder.mkdir(exist_ok=True)

    #get path to folder 
    panel_lookup = f'{panel_name}_lookup'
    hash_filename = str(folder / panel_lookup)

    #initiate db
    isc_hash_db = shelve.open(hash_filename, flag="c", protocol=None, writeback=False)
    return isc_hash_db

#a helper function to round to 3sf
def round_sf(x, sig=3):
    if x == 0:
        return 0
    from math import log10, floor
    return round(x, sig - int(floor(log10(abs(x)))) - 1)

def calculate_pixels(string):
    location_dict = {}

    #original start of string
    x, y = string.left_top_point

    #iterate through each panel
    for i, panel in enumerate(string.panel_list):
        #print(f'Panel number {i}')
        col = i*6
        row = 0
        for module in panel.module_list:
            for j in range(module.rows):
                for cell in module.cell_array[j]:
                    key = get_cell_pixel_pos(string, row, col)
                    if key in location_dict:
                        location_dict[key].append(cell)
                    else:
                        location_dict[key] = [cell]
                    col += 1
                row += 1
                col = i*6

    return location_dict

def get_cell_pixel_pos(string, row, col):
    #key values
    base_x, base_y = string.left_top_point
    cell_w = string.cell_width/0.67
    cell_h = string.cell_height/0.67
    rotation = string.rotation

    #depending on the way its facing, will grow in different directions
    if rotation == 0:
        x = base_x + col * cell_w
        y = base_y - row * cell_h
    elif rotation == 90:
        x = base_x + row * cell_h
        y = base_y + col * cell_w
    elif rotation == 180:
        x = base_x - col * cell_w
        y = base_y + row * cell_h
    elif rotation == 270:
        x = base_x - row * cell_h
        y = base_y - col * cell_w
    else:
        raise ValueError("Not valid rotation value")
    return pixel_to_key(x,y)

def pixel_to_key(*pixel_loc):
    x,y = pixel_loc
    return f'{x:.0f},{y:.0f}'

def key_to_pixel(key):
    try:
        x_str, y_str = key.split(',')
        x = float(x_str)
        y = float(y_str)
        return x, y
    except Exception as e:
        print(f'Exception key is {key}\n')

def file_pixel_dict(filename, start_date, end_date, timestep):
    d_format = "%d/%m/%Y %H:%M:%S"
    pixel_dict = {}
    time = start_date

    duration_frame = get_times(filename)

    while time <= end_date:
        in_range = get_shade_at_time(time, duration_frame)
        pixel_x = in_range['Pixel X'].values
        pixel_y = in_range['Pixel Y'].values

        pixel_arr = [pixel_to_key(x, y) for x, y in zip(pixel_x, pixel_y)] if not in_range.empty else []

        pixel_dict[datetime.strftime(time, d_format)] = pixel_arr

        time += timestep

    return pixel_dict

def get_times(filename): 
    df = pd.read_csv(filename, parse_dates=["First Shadow Timestamp", "Last Shadow Timestamp"], dayfirst=True)

    return df

def get_timezone(lat, lon):
    tf = TimezoneFinder()
    timezone_str = tf.timezone_at(lat=lat, lng=lon)
    return timezone_str

#interpolate change in temp/irradiance
#if timestep between hours
def interpolate(timestep, temp_change, irr_change, start, end,
        start_temp, start_irr):
    #stores the result in a dict
    t_per_step = (temp_change) * (60/timestep)
    i_per_step = (irr_change) * (60/timestep)
    time = start

    results = {}
    i = 0

    #iterates through each time
    while time < end:
        results[time] = (start_temp + t_per_step*i, start_irr + i_per_step*i)
        i += 1

    return results


#using clearsky from pvlib to get more accurate conditions
def get_irr(start_date, end_date, lat, lon, timestep, 
        timestep_unit, timezone):
    #define the location
    site = Location(lat, lon, tz=timezone)

    #get the time range 
    times = pd.date_range(start=f'{start_date} 00:00', end=f'{end_date} 23:59',
        freq=f'{timestep}{timestep_unit}', tz=timezone)

    print(timezone)

    #get the irradiance of the clearsky
    clearsky = site.get_clearsky(times)

    #get the solar position
    solpos = site.get_solarposition(times)

    #direct normal irr/diffuse horizontal/global horizontal 
    #direct from sun
    #sunlight coming horizontal after being scattered
    #total irradiance on a horizontal surface (combine with angle)
    dni = clearsky["dni"]
    dhi = clearsky['dhi']
    ghi = clearsky['ghi']

    #this assumes that the panels track perfactly, where the tilt is the solar zenith
    surface_tilt = 90 - solpos['apparent_elevation'] #tilt perpendicular to the suns rays (suns elevation)
    surface_azimuth = solpos['azimuth'] #sets panel horizontal to the suns current direction

    #using pvlib to get total irradiance on a panel
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        solar_zenith=solpos['apparent_zenith'],
        solar_azimuth=solpos['azimuth'],
        albedo=0.2
    )

    #get the high and low temperature 
    month = start_date.strftime('%m')
    print(month)

    t_high, t_low = get_avg_temp(lat, lon, month)
    #get the mean and difference from mean (amplitude)
    t_avg = (t_high + t_low)/2
    amp = (t_high - t_low)/2

    #assume min temp at 3am and max at 3pm
    time_low = 3

    temps = []

    for time in times:
        #get the hour of the day
        hour = time.hour + time.minute/60

        #take the averaga and sin curve deviation to get a synethic time curve
        angle = ((hour-time_low)/24) * 2 * np.pi - (np.pi/2) #shift by -pi/2
        temp = t_avg + amp * np.sin(angle)
        temps.append(temp)

    ambient_temp = pd.Series(temps, index=times)

    
    df = pd.DataFrame({
        'irr': poa['poa_global'],
        'temp': ambient_temp
    }, index=times)

    return df
        
def set_shade_at_time(time, panel_dict, file_dict, _instance, irr, shaded_temp, log_path="shade_log.txt"):
    time_str = time.strftime('%d/%m/%Y %H:%M:%S')
    try:
        pixels = file_dict.get(time_str, [])
        shaded_cells = set()
        crossover_coords = []

        parent_list = set()

        for pixel in pixels:
            cells = panel_dict.get(pixel, [])
            if len(cells) > 1:
                crossover_coords.append(pixel)
            for cell in cells:
                cell.set_shade(irr=100, temp=shaded_temp)
                cell.parent.update_shaded(True)
                parent_list.add(cell.parent)
                #shaded_cells.add(str(cell))  

        output = f"Shade set successfully for {time_str}"

        '''
        used for logging and debugging not needed
        shaded_count = 0

        for module in parent_list:
            if module.shaded == True:
                shaded_count += 1

        ins_shaded_cells = 0
        ins_shaded_count = 0

        for panel in _instance.panel_list:
            for module in panel.module_list:
                if module.shaded == True:
                    ins_shaded_count += 1
                    for cell in module.cell_list:
                        if cell.ACTUAL_CONDITIONS[6] < irr:
                            ins_shaded_cells += 1


        # Prepare log content
        log_content = [
            f"Time: {time_str}",
            f"Number of shaded cells: {len(shaded_cells)}",
            f"Cells shaded: {', '.join(sorted(shaded_cells)) if shaded_cells else 'None'}",
            f"Number of shaded coordinates: {len(pixels)}",
            f"Shaded coordinates: {', '.join(pixels) if pixels else 'None'}",
            f"Crossover coordinates ({len(crossover_coords)}): {', '.join(crossover_coords) if crossover_coords else 'None'}",
            f"Number of shaded modules {shaded_count}",
            f"List of shaded modules: {[str(module) for module in sorted(parent_list, key=str)]}",
            "-" * 50,
            f"Using the _instance",
            f"Number of shaded modules {ins_shaded_count}",
            f"Number of shaded cells {ins_shaded_cells}",
            "-" * 50
        ]

        # Write log
        with open(log_path, "a") as log_file:
            log_file.write("\n".join(log_content) + "\n")
        '''

    except Exception as e:
        output = f"Failed due to {e}"

        # with open(log_path, "a") as log_file:
        #     log_file.write(f"{time_str} - ERROR: {e}\n{'-'*50}\n")

    return output

#given a certain time returns the pixels that are shaded at that time
def get_shade_at_time(time, df):
    d_format = "%d/%m/%Y %H:%M:%S"
    in_range = df[
        (df["First Shadow Timestamp"] <= time) &
        (df["Last Shadow Timestamp"] >= time)
    ]

    return in_range

def _key_from_floats(*numbers, prec=2):
    return "|".join(f"{x:.{prec}g}" for x in numbers)

def _floats_from_key(key: str):
    return tuple(float(x) for x in key.split("|"))

#using nasa api to request temperature infromation for a year 
def get_avg_temp(lat=24, lon=69, month='01'):

    start_year = 2019
    end_year = 2020

    #use nasa power parameters
    #t2m_max is max and t2m_min min
    params = ["T2M_MAX", "T2M_MIN"]

    #the api url to request data from
    url = (
        f"https://power.larc.nasa.gov/api/temporal/monthly/point"
        f"?parameters={','.join(params)}"
        f"&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_year}&end={end_year}"
        f"&format=JSON"
    )

    print("Fetching data")
    response = requests.get(url)
    data = response.json()

    records = []
    for date_str, values in data['properties']['parameter']['T2M_MAX'].items():
        records.append({
            'YearMonth': date_str,
            'Tmax': values,
            'Tmin': data['properties']['parameter']['T2M_MIN'][date_str]
        })


    #build a sin curve of temperatures between a low at 3am and a high at 3pm
    filtered_records = []
    for record in records:
        if record['YearMonth'] == f'2019{month}':
            filtered_records.append(record)

    #get the high and low 
    t_high = record['Tmax']
    t_low = record['Tmin']

    print(f'high is {t_high}, low is {t_low}')
    
    return t_high, t_low

#estimates the actual temperature of a cell based on noct, irradiance and ambient
#if no sunlight - cell would be ambient temp
#(noct-20)/800 this tells how much above the temp it will heat per irradiance
#noct measured at 20 degrees and 800 irradiance
def estimate_temp(ambient_temp, noct, irr):
    return ambient_temp + (((noct-20)/800) * irr)

#get power in kwh
def khw_output(timestep, powers):
    total = 0
    for power in powers:
        total += power*(timestep/timedelta(hours=1))

    return total

#used when creating new custom panels from outside the library
#used to find:
#i_l - light generated current around isc
#i-O - diode sat current
#r_s - series resistance
#r_sh - shunt resistance (aka parallel resistance)
#a_ref a reference ideality factor
from pvlib.pvsystem import calcparams_cec, singlediode

import math
import numpy as np

# Try to import pvlib, but provide fallback
try:
    from pvlib.pvsystem import fit_cec_sam
    PVLIB_AVAILABLE = True
except ImportError:
    PVLIB_AVAILABLE = False
    print("Warning: pvlib not available")

def custom_panel_variables(Voc, Isc, Vmp, Imp, N_cells, alpha_sc, cell_type, gamma_pmp, beta_voc):
    """
    Corrected parameter extraction with proper physics-based constraints
    """
    
    # Constants
    k = 1.380649e-23  # Boltzmann constant (J/K)
    q = 1.602176634e-19  # Elementary charge (C)
    T_ref = 25 + 273.15  # Reference temperature (K)
    
    # Expected power
    expected_power = Vmp * Imp
    print(f"Expected Pmp = {Vmp} * {Imp} = {expected_power:.1f} W")
    
    # Input validation
    if Vmp >= Voc:
        print(f"ERROR: Vmp ({Vmp}V) should be less than Voc ({Voc}V)")
        return None
    if Imp >= Isc:
        print(f"ERROR: Imp ({Imp}A) should be less than Isc ({Isc}A)")
        return None
    
    # Check alpha_sc units - should be small (A/°C)
    if alpha_sc > 1.0:
        print(f"WARNING: alpha_sc ({alpha_sc}) seems too large. Should be in A/°C")
        print("Expected range: 0.001 to 0.01 A/°C for typical panels")
    
    # Try pvlib first, but with better error handling
    if PVLIB_AVAILABLE:
        try:
            result = try_pvlib_extraction(Voc, Isc, Vmp, Imp, N_cells, alpha_sc, cell_type, gamma_pmp, beta_voc)
            if result is not None:
                return result
        except Exception as e:
            print(f"pvlib extraction failed: {e}")
    
    # Use physics-based extraction
    return physics_based_extraction(Voc, Isc, Vmp, Imp, N_cells, expected_power)

def try_pvlib_extraction(Voc, Isc, Vmp, Imp, N_cells, alpha_sc, cell_type, gamma_pmp, beta_voc):
    """
    Attempt pvlib parameter extraction with multiple approaches
    """
    
    # Normalize cell type
    cell_type_map = {
        'multi/poly': 'multiSi',
        'poly': 'multiSi', 
        'mono': 'monoSi'
    }
    normalized_cell_type = cell_type_map.get(cell_type.lower(), 'multiSi')
    
    # Try different parameter combinations
    attempts = [
        # Original values
        {'gamma_pmp': gamma_pmp, 'beta_voc': beta_voc, 'alpha_sc': alpha_sc},
        # Convert percentages to fractions if they seem to be in percent
        {'gamma_pmp': gamma_pmp/100 if abs(gamma_pmp) > 0.01 else gamma_pmp, 
         'beta_voc': beta_voc/100 if abs(beta_voc) > 0.01 else beta_voc, 
         'alpha_sc': alpha_sc},
        # Use typical values if extraction fails
        {'gamma_pmp': -0.004, 'beta_voc': -0.003, 'alpha_sc': alpha_sc}
    ]
    
    for i, params in enumerate(attempts):
        try:
            print(f"pvlib attempt {i+1}: gamma_pmp={params['gamma_pmp']:.6f}, beta_voc={params['beta_voc']:.6f}")
            
            cec_params = fit_cec_sam(
                v_oc=Voc,
                i_sc=Isc, 
                v_mp=Vmp,
                i_mp=Imp,
                cells_in_series=N_cells,
                celltype=normalized_cell_type,
                **params
            )
            
            I_L_ref, I_o_ref, R_s, R_sh_ref, nNsVth, _ = cec_params
            
            # Calculate ideality factor
            k = 1.380649e-23
            q = 1.602176634e-19
            T_ref = 25 + 273.15
            Vth_module = N_cells * k * T_ref / q
            a_ref = nNsVth / Vth_module
            
            # Sanity check the results
            if is_parameters_reasonable(I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref, Isc, expected_power):
                print(f"pvlib extraction successful on attempt {i+1}")
                print(f"  I_L_ref = {I_L_ref:.6f} A")
                print(f"  I_o_ref = {I_o_ref:.2e} A")
                print(f"  R_s = {R_s:.6f} Ω")
                print(f"  R_sh_ref = {R_sh_ref:.1f} Ω")
                print(f"  a_ref = {a_ref:.6f}")
                return I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref
            else:
                print(f"  Parameters failed sanity check")
                
        except Exception as e:
            print(f"  Attempt {i+1} failed: {e}")
    
    return None

def is_parameters_reasonable(I_L, I_o, R_s, R_sh, a, I_sc, expected_power):
    """
    Check if extracted parameters are physically reasonable
    """
    checks = [
        (I_L > I_sc * 0.95, f"I_L ({I_L:.3f}) should be close to I_sc ({I_sc:.3f})"),
        (I_L < I_sc * 1.2, f"I_L ({I_L:.3f}) shouldn't be much larger than I_sc ({I_sc:.3f})"),
        (1e-15 < I_o < 1e-6, f"I_o ({I_o:.2e}) should be between 1e-15 and 1e-6 A"),
        (0.01 < R_s < 5.0, f"R_s ({R_s:.3f}) should be between 0.01 and 5.0 Ω"),
        (R_sh > 10, f"R_sh ({R_sh:.1f}) should be > 10 Ω"),
        (0.5 < a < 3.0, f"a ({a:.3f}) should be between 0.5 and 3.0")
    ]
    
    all_good = True
    for check, message in checks:
        if not check:
            print(f"    FAIL: {message}")
            all_good = False
    
    return all_good

def physics_based_extraction(Voc, Isc, Vmp, Imp, N_cells, expected_power):
    """
    Physics-based parameter extraction using fundamental PV equations
    """
    print("Using physics-based parameter extraction...")
    
    # Physical constants
    k = 1.380649e-23  # Boltzmann constant
    q = 1.602176634e-19  # Elementary charge  
    T = 25 + 273.15  # Temperature in Kelvin
    
    # Start with reasonable initial estimates
    n = 1.3  # Ideality factor for multicrystalline silicon
    Vt_cell = k * T / q  # Thermal voltage per cell (~0.0258 V at 25°C)
    Vt_module = n * N_cells * Vt_cell  # Module thermal voltage
    
    print(f"Thermal voltage per cell: {Vt_cell*1000:.1f} mV")
    print(f"Module thermal voltage: {Vt_module:.2f} V")
    
    # Method: Use the relationship between MPP and key parameters
    # At MPP: I = IL - Io*exp((V+I*Rs)/Vt) - (V+I*Rs)/Rsh
    
    # Estimate series resistance from the "knee" sharpness
    # Sharp knee (low Rs) vs. rounded knee (high Rs)
    fill_factor = (Vmp * Imp) / (Voc * Isc)
    print(f"Fill factor: {fill_factor:.3f}")
    
    # Typical Rs estimation based on fill factor and panel characteristics
    # For good panels: FF > 0.75, Rs < 0.5 Ω
    Rs_estimate = max(0.05, (0.82 - fill_factor) * 2.0)  # Empirical relationship
    Rs_estimate = min(Rs_estimate, 1.0)  # Cap at reasonable value
    
    # Better shunt resistance estimation
    # At low voltages, slope ≈ -1/Rsh
    # Use the fact that at V=0: I ≈ IL - V/Rsh ≈ Isc
    # And at MPP we have significant voltage
    dV_dI_mpp = (Voc - Vmp) / (Isc - Imp)  # Approximate slope
    Rsh_estimate = max(50, min(5000, dV_dI_mpp * 10))  # Scale appropriately
    
    # Light current - should be slightly larger than Isc
    # IL ≈ Isc + Voc/Rsh (accounting for shunt losses at Voc)
    IL_estimate = Isc + Voc / Rsh_estimate
    IL_estimate = min(IL_estimate, Isc * 1.1)  # Don't let it get too large
    
    # Dark saturation current from open circuit condition
    # At Voc: 0 = IL - Io*exp(Voc/Vt) - Voc/Rsh
    # So: Io = (IL - Voc/Rsh) / exp(Voc/Vt)
    try:
        exp_factor = math.exp(Voc / Vt_module)
        Io_estimate = (IL_estimate - Voc / Rsh_estimate) / exp_factor
        Io_estimate = max(1e-15, min(1e-8, Io_estimate))  # Reasonable bounds
    except OverflowError:
        Io_estimate = 1e-12  # Fallback
    
    print(f"Physics-based parameter estimates:")
    print(f"  I_L_ref = {IL_estimate:.6f} A")
    print(f"  I_o_ref = {Io_estimate:.2e} A")
    print(f"  R_s = {Rs_estimate:.6f} Ω")
    print(f"  R_sh_ref = {Rsh_estimate:.1f} Ω")
    print(f"  a_ref = {n:.6f}")
    
    # Validation: Check if these parameters can produce reasonable power
    validate_physics_parameters(IL_estimate, Io_estimate, Rs_estimate, Rsh_estimate, 
                               n, Vt_module, Vmp, Imp, expected_power)
    
    return IL_estimate, Io_estimate, Rs_estimate, Rsh_estimate, n

def validate_physics_parameters(IL, Io, Rs, Rsh, n, Vt, Vmp, Imp, expected_power):
    """
    Validate parameters by calculating current at MPP voltage
    """
    try:
        # Calculate current at Vmp using single diode equation
        # I = IL - Io*(exp((V+I*Rs)/Vt) - 1) - (V+I*Rs)/Rsh
        # This requires iterative solution, so we'll use Newton-Raphson
        
        def diode_equation(I, V=Vmp):
            return IL - Io * (math.exp((V + I*Rs)/Vt) - 1) - (V + I*Rs)/Rsh - I
        
        def diode_derivative(I, V=Vmp):
            exp_term = math.exp((V + I*Rs)/Vt)
            return -Io * Rs/Vt * exp_term - Rs/Rsh - 1
        
        # Newton-Raphson iteration
        I_calc = Imp  # Starting guess
        for _ in range(10):  # Max 10 iterations
            f = diode_equation(I_calc)
            df = diode_derivative(I_calc)
            if abs(df) < 1e-10:
                break
            I_new = I_calc - f/df
            if abs(I_new - I_calc) < 1e-6:
                break
            I_calc = I_new
        
        P_calc = Vmp * I_calc
        error_percent = abs(P_calc - expected_power) / expected_power * 100
        
        print(f"Parameter validation:")
        print(f"  Calculated current at Vmp: {I_calc:.3f} A (expected: {Imp:.3f} A)")
        print(f"  Calculated power: {P_calc:.1f} W (expected: {expected_power:.1f} W)")
        print(f"  Power error: {error_percent:.1f}%")
        
    except Exception as e:
        print(f"Validation calculation failed: {e}")

# Test function
def test_corrected_extraction():
    # Your problematic panel data
    Voc = 50.27  # V
    Isc = 14.01  # A  
    Vmp = 41.58  # V
    Imp = 13.23  # A
    num_cells = 144
    
    # Fix the alpha_sc - this should be much smaller!
    alpha_sc_percent = 0.046  # This is likely 0.046%/°C, not 0.046 A/°C
    alpha_sc_A_per_C = alpha_sc_percent * Isc / 100.0  # Convert properly
    print(f"Alpha_sc conversion: {alpha_sc_percent}%/°C * {Isc}A / 100 = {alpha_sc_A_per_C:.6f} A/°C")
    
    gamma_pmp_percent = -0.3  # %/°C
    beta_voc_percent = -0.25  # %/°C  
    panel_type = "multi/poly"
    
    result = custom_panel_variables_corrected(
        Voc, Isc, Vmp, Imp, num_cells,
        alpha_sc_A_per_C, panel_type,
        gamma_pmp_percent, beta_voc_percent
    )
    
    return result

if __name__ == "__main__":
    test_corrected_extraction()