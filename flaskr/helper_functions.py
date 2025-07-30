import pvlib
from datetime import datetime, timedelta
import pytz
from pathlib import Path
import pandas as pd
import os
import matplotlib.pyplot as plt
import shelve

#use pvlib to find irradiance and temperature of longitude and latitude for a day
def get_info(start, end, lat, long):
    print(f'Start year {start.year} ')
    data, metadata = pvlib.iotools.get_pvgis_hourly(
        latitude=lat,
        longitude=long,
        start=start.year,
        end=end.year+1,
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
        #adjust temperature for panel (cell temp = air temp + irradiance/800 * 22)
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
def create_csv(start, lat, long):
    end = start + timedelta(hours=24)
    df = get_info(start, end, lat, long)
    filtered = adjust_df(df)
    filtered = interpolate_df(filtered)

    create_folder()

    #create the path via filename
    start = start.strftime('%Y.%m.%d')
    filename = f'{start}_coord{lat}{long}'
    
    filtered.to_csv(f'Environment_Params/{filename}.csv', index=False)
    return filtered

#creates the folder to store it in
def create_folder():
    folder_name = 'Environment_Params'
    current_dir = os.getcwd()
    folder_path = os.path.join(current_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

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
