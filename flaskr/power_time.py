from run import create_app  
import flaskr.refactored_helper as hp
from flaskr.refactored_classes import String
from flaskr.models import PanelInfo
from datetime import datetime, timedelta
import copy
import pandas as pd
from zoneinfo import ZoneInfo
import os
'''
@func this is where the power over time happens, so needs to take the time tested, the shadow data,
    and the string information, and use the _model_power function to find the max power at each time
    given shading data
@params - x, y of the string (top left point)
    - the name of the panel
    - the number of panels in the string
    - the rotation (0 is string running west to east, 90, 180, 270)
    - the voltage offset if necessary
    - timestep unit (minutes, hours, days)
    - the timestep integer (how many of the above)
    - the start/end date
    - the latitude/longitude coordinates
    - the name of the pixel file (file needs to be saved in flaskr/static/tmp)
    - the root path of the app
    - added site_name to save csv information
@outputs - a csv file with the vmp, imp and pmax at each time
    - a log file with each active bypass diode
    - graphs of power over time
'''
def _model_power_time(root_path, coords=(0,0), panel_name='Jinko_Solar_Co___Ltd_JKM410M_72HL_V', num_panels=28,
        rotation=90, voltage_offset=None, timestep_unit='hours', timestep_integer=1, start_date=datetime.now(), 
        end_date=datetime.now()+timedelta(days=1), pixel_file="_shadow_events_average_power_blocked.csv", lat=0, lon=0,
        site_name='Windmill'):

    # Create the full path inside csv_outputs
    root_csv_dir = "csv_outputs"
    folder_name = f"{site_name}_output_csv"
    full_path = os.path.join(root_csv_dir, folder_name)

    # Create both csv_outputs and Windmill_output_csv inside it
    os.makedirs(full_path, exist_ok=True)

    #first need to construct the string
    _string_instance = String(panel_name=panel_name, num_panels=num_panels, left_top_point=coords, rotation=rotation)
    _string_instance.voltage_offset = voltage_offset

    #take a deepcopy to compare shaded and unshaded 
    _string_copy = copy.deepcopy(_string_instance)

    #get the noct of the panel
    record = PanelInfo.query.filter_by(
        panel_name=_string_instance.panel_name
    ).first()
    noct = record.noct

    #create an empty dataframe to hold the output (one for shaded one for unshaded)
    df_shade = pd.DataFrame(columns=["time_str", "pmax", "vmp", "imp"])
    df_unshade = pd.DataFrame(columns=["time_str", "pmax", "vmp", "imp"])

    #calculate the timezone/timestep to accurately get weather conditions
    time_dict = {
        'minutes': 'min',
        'hours': 'h',
        'days': 'd'
    }
    t_unit = time_dict.get(timestep_unit)
    timezone = ZoneInfo(hp._get_timezone(lat, lon))
    timestep = timedelta(**{timestep_unit: timestep_integer})

    #get weather conditons
    dni_df = hp._get_irr(start_date, end_date, lat, lon, timestep_integer, t_unit, timezone)

    #create the dictionaries needed (pixels from file and panel)
    pixel_file_path = os.path.join(root_path, 'static', 'tmp', pixel_file)
    with open(pixel_file_path, "r") as pixel_file:
        pixel_dict = hp._file_pixel_dict(pixel_file, start_date, end_date, timestep)
    panel_dict = hp._calculate_pixels(_string_instance)

    #convert times to the correct timezone
    time = start_date.replace(tzinfo=timezone)
    end = end_date.replace(tzinfo=timezone)

    #iterates through each time
    while time <= end:
        time_str = time.strftime("%d:%H:%M")

        #gets the weather conditions at that time
        row = dni_df.loc[time]
        irr = row['irr']
        temp = row['temp']

        #ensures the testing string is unshaded then set shade
        _string_instance.reset_shade()
        irr_drop = hp._set_shade_at_time(time, panel_dict, pixel_dict, _string_instance) 

       #calculate the irradiance of the shaded cell
        if irr_drop is not None:
            shaded_irr = irr-irr_drop
        else:
            shaded_irr = 100

        #get the temperature of the shaded/unshaded cells
        unshaded_cell_temp = hp._estimate_temp(temp, noct, irr)
        shaded_cell_temp = hp._estimate_temp(temp, noct, shaded_irr)

        #if the irradiance is 0, then skip this time
        if irr == 0:
            df_unshade.loc[len(df_unshade)] = [time_str, 0, 0, 0]
            df_shade.loc[len(df_shade)] = [time_str, 0, 0, 0]
            time += timestep
            continue

        #if not model the time of both shaded and unshaded
        Pmax, Vmp, Imp = _string_instance._model_power((shaded_irr, shaded_cell_temp), (irr, unshaded_cell_temp), time_str, site_name=site_name, output_csv=True)
        Pmax2, Vmp2, Imp2 = _string_copy._model_power((shaded_irr, shaded_cell_temp), (irr, unshaded_cell_temp), time_str)

        #then add to df
        df_unshade.loc[len(df_unshade)] = [time_str, Pmax2, Vmp2, Imp2]
        df_shade.loc[len(df_shade)] = [time_str, Pmax, Vmp, Imp]

        print(f'Calculated for time {time_str}')

        time += timestep
    
    #finally convert to csv and output
    df_shade.to_csv("shaded_output.csv", index=False)
    df_unshade.to_csv("unshaded_output.csv", index=False)

if __name__ == '__main__':
    app = create_app()
    dt1 = datetime(2025, 7, 17)
    dt2 = datetime(2025, 7, 18)
    with app.app_context():
        _model_power_time(root_path=app.root_path, coords=(781, 443), start_date=dt1, end_date=dt2, lat=24, lon=69)



