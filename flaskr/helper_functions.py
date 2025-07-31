import pvlib
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
def create_edatabase(start, lat, lon):
    end = start + timedelta(hours=24)
    df = get_info(start, end, lat, lon)
    filtered = adjust_df(df)
    
    #store in the database
    with current_app.app_context():
        for i, (index, row) in enumerate(filtered.iterrows()):
            exists = EnvironmentalData.query.filter_by(
                date=index,
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
        x = base_x - row * cell_h
        y = base_y + col * cell_w
    elif rotation == 180:
        x = base_x - col * cell_w
        y = base_y + row * cell_h
    elif rotation == 270:
        x = base_x + row * cell_h
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

def file_pixel_dict(filename, start_date, end_date):
    pixel_dict = {}
    time = start_date

    duration_frame = get_times(filename)

    while time <= end_date:
        in_range = get_shade_at_time(time, duration_frame)
        pixel_x = in_range['Pixel X'].values
        pixel_y = in_range['Pixel Y'].values

        pixel_arr = [pixel_to_key(x, y) for x, y in zip(pixel_x, pixel_y)] if not in_range.empty else []

        pixel_dict[datetime.strftime(time, d_format)] = pixel_arr

        time += timedelta(minutes=30)
    
    return pixel_dict