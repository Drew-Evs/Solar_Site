import matplotlib.pyplot as plt
import pandas as pd
import pvlib
from pvlib.location import Location
from pvlib.ivtools.sdm import fit_cec_sam
from pvlib.pvsystem import calcparams_cec, singlediode
from datetime import datetime, timedelta
import requests
import numpy as np
from timezonefinder import TimezoneFinder

'''
@func draws and saves graphs for power against voltage/current and IV curve
    saves under the panel_name and type (panel/module/cell)
@params powers, voltages, currents, type, panel_name
@output the path to the plots
'''
def _draw_graph(powers, voltages, currents, type, panel_name):
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

'''
@func rounds the float to 3 significant figures
@params the float x, and the number of figs to round to
@output the rounded float
'''
def _round_sf(x, sig=3):
    if x == 0:
        return 0
    from math import log10, floor
    return round(x, sig - int(floor(log10(abs(x)))) - 1)

'''
@func calculate the locations of the pixels in the string given the top left coordinate of the string 
    assuming 6 cells per row
@params the string which holds the number of rows/cell dimensions
@output a dictionary, linking pixel to cells
''' 
def _calculate_pixels(string):
    location_dict = {}

    #the start pos of the string
    #iterate through each panel
    for p_idx, panel in enumerate(string.panel_list):
        col = p_idx*6
        row = 0

        row_offset = 0
        panel_col_offset = 0

        #iterate through each module
        for module in panel.module_list:
            panel_col_offset = p_idx * 6
            num_rows = len(module.cell_list) // 6
            #iterate throug each row in the module
            for idx, cell in enumerate(module.cell_list):
                row = row_offset + (idx // 6)
                col = panel_col_offset + (idx % 6)
                key = _get_cell_pixel_pos(string, row, col)
                if key not in location_dict:
                    location_dict[key] = []
                location_dict[key].append(cell)
            row_offset += num_rows

    return location_dict

'''
@func given the string cell dimensions and rotation, and the row/column number find the pixel pos
@params the string to test and the row/col integer
@output the pixel location as a key
'''
def _get_cell_pixel_pos(string, row, col):
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
    return _pixel_to_key(x,y)

'''
@func converts pixel coords to a key
@params the x/y of the cell
@output a string as x,y
'''
def _pixel_to_key(*pixel_loc):
    x,y = pixel_loc
    return f'{x:.0f},{y:.0f}'

'''
@func reverses the above sets key to pixel
@params the key 
@outputs returns the x and y
'''
def _key_to_pixel(key):
    try:
        x_str, y_str = key.split(',')
        x = float(x_str)
        y = float(y_str)
        return x, y
    except Exception as e:
        print(f'Exception key is {key}\n')

'''
@func takes the file, and converts it to a dictionary of times to a shaded pixel list
@param the filename, start/end date and the timestep
@output a dictionary that maps times to list of shaded pixels
'''
def _file_pixel_dict(filename, start_date, end_date, timestep):
    d_format = "%d/%m/%Y %H:%M:%S"
    pixel_dict = {}
    time = start_date

    duration_frame = pd.read_csv(filename, parse_dates=["First Shadow Timestamp", "Last Shadow Timestamp"], dayfirst=True)

    while time <= end_date:
        try:
            in_range = duration_frame[
                (duration_frame["First Shadow Timestamp"] <= time) &
                (duration_frame["Last Shadow Timestamp"] >= time)
            ]
            pixel_x = in_range['Pixel X'].values
            pixel_y = in_range['Pixel Y'].values

            pixel_arr = [_pixel_to_key(x, y) for x, y in zip(pixel_x, pixel_y)] if not in_range.empty else []

            pixel_dict[datetime.strftime(time, d_format)] = pixel_arr

            time += timestep
        except Exception as e:
            print(f'Shading failed due to exception {e}')

    return pixel_dict

'''
@func uses the nasa api to request the monthly high and low temperature of a month
@param the month to test, the longitude and the latitude
@output the high and low for that month at that location
'''   
def _get_avg_temp(lat, lon, month):
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
    response = requests.get(url)
    data = response.json()

    records = []
    for date_str, values in data['properties']['parameter']['T2M_MAX'].items():
        records.append({
            'YearMonth': date_str,
            'Tmax': values,
            'Tmin': data['properties']['parameter']['T2M_MIN'][date_str]
        })

    #filter the records to the correct month
    filtered_records = []
    for record in records:
        if record['YearMonth'] == f'2019{month}':
            filtered_records.append(record)

    #get the high and low 
    t_high = record['Tmax']
    t_low = record['Tmin']
    return t_high, t_low

'''
@func uses the pvlib, to find the irradiance for the given location
    matches this with a sin curve to estimate ambient temperatures
    assumes panel points directly at sun
@params the start/end date, long/lat coordinates the timstep and the timezone
@output dataframe object, holding the ambient temp and global irradiance
'''
def _get_irr(start_date, end_date, lat, lon, timestep, 
        timestep_unit, timezone):
    #define the location
    site = Location(lat, lon, tz=timezone)

    #get the time range 
    times = pd.date_range(start=f'{start_date} 00:00', end=f'{end_date} 23:59',
        freq=f'{timestep}{timestep_unit}', tz=timezone)

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

    shaded_poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        dni=0,       # no direct sunlight
        ghi=ghi,
        dhi=dhi,
        solar_zenith=solpos['apparent_zenith'],
        solar_azimuth=solpos['azimuth'],
        albedo=0.2
    )

    #get the high and low temperature 
    month = start_date.strftime('%m')
    t_high, t_low = _get_avg_temp(lat, lon, month)

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
        'temp': ambient_temp,
        'shaded_irr': shaded_poa['poa_global']
    }, index=times)

    return df

'''
@func takes the time and checks the dictionary, to find which pixels are shaded
    then sets them to shaded
@params the time, the pixel dictionary from the file and the string and the string instance
@output none
'''
def _set_shade_at_time(time, panel_dict, file_dict, string):
    time_str = time.strftime('%d/%m/%Y %H:%M:%S')
    try:
        pixels = file_dict.get(time_str, ([],[]))
        for pixel in pixels:
            cells = panel_dict.get(pixel, [])
        
            for cell in cells:
                cell._set_shade(True)

    except Exception as e:
        print(f"Failed to set shaded due to {e}")
        raise

'''
@func estimate the temperature of the cell above ambient temp
    based on noct ((noct-20)/800) tells how many degrees goes up per irr
@params ambient temp, noct, irr
@output cell temp estimation
'''
def _estimate_temp(ambient_temp, noct, irr):
    return ambient_temp + (((noct-20)/800) * irr)


'''
@func calculate the power output for the timestep
@params the timestep and list of powers
@output power output in the time in kWh
'''
def _khw_output(timestep, powers):
    total = 0
    for power in powers:
        total += power*(timestep/timedelta(hours=1))

    return total

'''
@func uses the coordinates of the spot to find the correct time
@params lat/lon coordinates
@output the timezone as a string
'''
def _get_timezone(lat, lon):
    tf = TimezoneFinder()
    timezone_str = tf.timezone_at(lat=lat, lng=lon)
    return timezone_str

'''
@func stores the series of variables needed for the single diode model in the custom panel table
    means that the user can build a custom panel 
@params need voc, isc, vmp, number of cells, alpha_sc, the type of cell, the gamma_pmp, beta_voc
@returns I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref, alpha_sc
'''
def _custom_panel_extraction(Voc, Isc, Vmp, Imp, N_cells, alpha_sc, gamma_pmp, beta_voc, cell_type,):
    #constants
    k = 1.380649e-23  # Boltzmann constant (J/K)
    q = 1.602176634e-19  # Elementary charge (C)
    T_ref = 25 + 273.15  # Reference temperature (K)

    #convert alpha/beta to I/degrees C and V/C
    alpha_sc_A_per_C = (alpha_sc * Isc) / 100.0
    beta_voc_V_per_C = (beta_voc * Voc) / 100.0 

    #attempt extraction from pvlib
    try:
        cec_params = fit_cec_sam(
            v_oc=Voc,
            i_sc=Isc, 
            v_mp=Vmp,
            i_mp=Imp,
            cells_in_series=N_cells,
            celltype=cell_type,
            temp_ref=25,
            gamma_pmp = gamma_pmp,
            beta_voc = beta_voc_V_per_C,
            alpha_sc = alpha_sc_A_per_C
        )
        
        I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref, adjust = cec_params

        return I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref, alpha_sc_A_per_C
    except Exception as e:
        print(f"Failed parameter extraction: {e}")
        return (0,) * 5

'''
@func a simple way using the single diode model to calculate the max power of a panel
@params takes in the outputs from above
@output the pmax, vmp and imp of the panel
'''
def _calculate_pmp_simple(I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref,
                        temp_cell=25, irradiance=1000, alpha_sc=0.006445):
    # Calculate parameters at operating conditions
    photocurrent, saturation_current, resistance_series, resistance_shunt, nNsVth = calcparams_cec(
        effective_irradiance=irradiance,
        temp_cell=temp_cell,
        alpha_sc=alpha_sc,
        a_ref=a_ref,
        I_L_ref=I_L_ref,
        I_o_ref=I_o_ref,
        R_sh_ref=R_sh_ref,
        R_s=R_s,
        Adjust=1
    )
    
    # Solve for operating point
    result = singlediode(
        photocurrent=photocurrent,
        saturation_current=saturation_current,
        resistance_series=resistance_series,
        resistance_shunt=resistance_shunt,
        nNsVth=nNsVth
    )
    
    return result['p_mp'], result['v_mp'], result['i_mp']
