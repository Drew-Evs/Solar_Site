from flask import Blueprint, render_template, request, session, url_for, current_app, jsonify, Response
import os
import json
from PIL import Image
from .refactored_classes import String
from .models import PanelInfo, EnvironmentalData
import flaskr.refactored_helper as hp
from datetime import datetime, timedelta
import pytz
from zoneinfo import ZoneInfo
import threading
import matplotlib.pyplot as plt
import copy
import queue
import psutil
import shutil
from memory_profiler import memory_usage
import tracemalloc
import cProfile, pstats, io
import matplotlib.dates as mdates
import uuid

sm = Blueprint('string_modelling', __name__)

#tracemalloc.start()

process = psutil.Process(os.getpid())

#global variable for a string
_instance = None

@sm.route('/upload', methods=['POST'])
def upload_file():
    try:
        panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
        panel_names = [p.panel_name for p in panels]

        uploads_path = os.path.join(current_app.root_path, 'static/uploads')

        #clear previous file
        for filename in os.listdir(uploads_path):
            file_path = os.path.join(uploads_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

        #request/save new file
        file = request.files['file']
        if file: 
            filepath = os.path.join(uploads_path, file.filename)
            file.save(filepath)

            return jsonify({
                "status": "success",
                "image": f"/static/uploads/{file.filename}" 
            })

        raise Exception('Failed to save file')
    except Exception as e:
        print(f"Failed due to {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@sm.route('/place_pixels', methods=['POST'])
def place_pixels():
    #create a unique id so to avoid using browser caching
    unique_id = uuid.uuid4().hex
    try:
        output_dir = f'flaskr/static/outputs'

        # Delete the entire directory if it exists
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        # Recreate the (now empty) directory
        os.makedirs(output_dir)

        panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
        panel_names = [p.panel_name for p in panels]

        #create a test string and pixel coords
        global _instance
        t_dict = hp._calculate_pixels(_instance)

        #need to find the image first
        filepath = f"./flaskr/static/uploads"

        if os.path.exists(filepath):
            files = sorted(os.listdir(filepath))
            if files:
                first_file = os.path.join(filepath, files[0])
                output_path = os.path.join(output_dir, f"{unique_id}.png")

        #open and draw pixels 
        with Image.open(first_file) as img:
            #ensure in rgb
            img = img.convert("RGB")
            
            #gets the pixel location 
            for key in t_dict:
                x,y = hp._key_to_pixel(key)
                x = int(x)
                y = int(y)
                if 0 <= x < img.width and 0 <= y < img.height:
                    img.putpixel((x, y), (0, 0, 255))
                
            img.save(output_path)
            print(f'/static/outputs/{unique_id}.png')

        return jsonify({
            "status": "success",
            "image": f"/static/outputs/{unique_id}.png",  # relative path for web use
        })

    except Exception as e:
        print(f'Error placing pixels {e}')
        return jsonify({
            "status": "error",
            "message": str(e)
        })
        
@sm.route('/build_string', methods=['POST'])
def build_string():
    global _instance
    _instance = None
    panel_count = int(request.form.get("panel_count", 28))
    panel_name = request.form.get("panel_name", 'Jinko_Solar_Co___Ltd_JKM410M_72HL_V')
    x = int(request.form.get("X", 0))
    y = int(request.form.get("Y", 0))
    rotation = int(request.form.get("rotation", 0))

    try:
        _instance = String(panel_name=panel_name, num_panels=panel_count, left_top_point=(x,y), rotation=rotation)
        max_power, vmp, imp = _instance._model_power((100, 45), (1000, 45))
        print(f'Max power is {max_power} and panel count is {panel_count} so per panel {max_power/panel_count}')
        print(f'Vmp is {vmp} and Imp is {imp}')
        max_power = max_power/panel_count
        place_pixels()
        return jsonify({"status": "success", "power": hp._round_sf(max_power)}) 

    except Exception as e:
        print(f'Exception is {e}')
        return jsonify({"status": "error", "message": str(e)})

#does the modelling for time against power
@sm.route('/model_power', methods=['POST', 'GET'])
def time_power_model():
    try:
        global _instance

        #pull results from the page
        data = request.args if request.method == 'GET' else request.form

        unit = data.get("unit", "minutes")
        time_int = int(data.get("time_int", 1))
        start_date = datetime.fromisoformat(data.get("start", datetime.now().isoformat()))
        end_date = datetime.fromisoformat(data.get("end", (datetime.now() + timedelta(hours=24)).isoformat()))
        lon = float(data.get("lon", 0))
        lat = float(data.get("lat", 0))
        p_filename = data.get("pfile", "")

        #last id to resume connection
        last_event_id = data.get('Last-Event-ID', None)

        if last_event_id in (None, '', 'null'):
            open("output_text.log", "w").close()
            open("unshaded_output.log", "w").close()
            open("shade_log.txt", "w").close()

        try:
            last_id = int(last_event_id)
        except (ValueError, TypeError):
            last_id = None

        #get correct timestep unit
        time_dict = {
            'minutes': 'min',
            'hours': 'h',
            'days': 'd'
        }

        t_unit = time_dict.get(unit)
        timezone = ZoneInfo(hp._get_timezone(lat, lon))
        
        timestep = timedelta(**{unit: time_int})

        dni_df = hp._get_irr(start_date, end_date, lat, lon, time_int, t_unit, timezone)

        app = current_app._get_current_object()

        record = PanelInfo.query.filter_by(
            panel_name=_instance.panel_name
        ).first()


    except Exception as e:
        print(f"Error due to {e}")
        return Response(f"data: {json.dumps({'error': str(e)})}\n\n", mimetype='text/event-stream')

    # Return response with proper headers for SSE
    response = Response(
        generate(_instance, timestep, p_filename, start_date, end_date, app, dni_df, timezone, last_id, lat, lon, record.noct), 
        mimetype='text/event-stream',
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
    return response

def generate(_instance, timestep, p_filename, start_date, end_date,
        app, dni_df, timezone, last_id, lat, lon, noct):

    try:
        local_instance = copy.deepcopy(_instance)

        with app.app_context():
            try:
                if local_instance is None:
                    raise Exception("String instance missing")
                
                #create the dictionary needed
                pixel_file_path = os.path.join(current_app.root_path, 'static', 'tmp', p_filename)
                with open(pixel_file_path, "r") as pixel_file:
                    pixel_dict = hp._file_pixel_dict(pixel_file, start_date, end_date, timestep)

                panel_dict = hp._calculate_pixels(local_instance)
            
            except Exception as e:
                print(f'Cant simulate due to: {e}')
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                return

            time = start_date.replace(tzinfo=timezone)
            end = end_date.replace(tzinfo=timezone)

            iteration_count = 0

            while time <= end:
                time_str = time.strftime("%d:%H:%M")
                #skips events already done
                if last_id is not None and iteration_count <= last_id:
                    time += timestep
                    iteration_count += 1
                    continue

                try:
                    row = dni_df.loc[time]
                except KeyError:
                    print(f"Time {time} not found in DNI dataframe")
                    time += timestep
                    continue
                
                try:
                    irr = row['irr']
                    temp = row['temp']

                    _instance.reset_shade()
                    local_instance.reset_shade()
                    irr_drop = hp._set_shade_at_time(time, panel_dict, pixel_dict, local_instance)
                    if irr_drop is not None:
                        shaded_irr = irr-irr_drop
                    else:
                        shaded_irr = 100

                    #get the average cell temp given shaded/unshaded
                    unshaded_cell_temp = hp._estimate_temp(temp, noct, irr)
                    shaded_cell_temp = hp._estimate_temp(temp, noct, shaded_irr)

                except Exception as e:
                    print(f'Finally failed due to {e}')
                    #string writing to the output
                    time += timedelta(hours=1)
                    continue

                if irr == 0:
                    str_out = f'{time_str}|0|0.0|0.0'

                    #write to the output
                    with open("output_text.log", "a") as f:
                        f.write(f'{str_out}\n')

                    with open("unshaded_output.log", "a") as f:
                        f.write(f'{str_out}\n')

                    time += timestep
                    iteration_count += 1
                    continue
                
                try:    
                    Pmax, Vmp, Imp = local_instance._model_power((shaded_irr, shaded_cell_temp), (irr, unshaded_cell_temp))
                    
                    data = {
                        'pmax': hp._round_sf(float(Pmax)) if Pmax is not None else 0.0,
                        'e_info': hp._round_sf(float(irr)) if irr is not None else 0.0,
                        'time': time_str,
                        'temp': hp._round_sf(temp),
                        'id': iteration_count
                    }

                    json_data = json.dumps(data)
                    # print(f"DEBUG at {time}: Pmax={Pmax}, irr={irr}, temp={temp}")
                    # print(f"Serialized data: {json_data}")

                    #string writing to the output
                    #normalise
                    str_out = f'{time_str}|{Pmax/1000}|{Vmp}|{Imp}|irr is {irr}|temp is{temp}'

                    #write to the output
                    with open("output_text.log", "a") as f:
                        f.write(f'{str_out}\n')

                    Pmax, Vmp, Imp = _instance._model_power((100, shaded_cell_temp), (irr, unshaded_cell_temp))
                    str_out = f'{time_str}|{Pmax/1000}|{Vmp}|{Imp}|{irr}|{temp}'

                    with open("unshaded_output.log", "a") as f:
                        f.write(f'{str_out}\n')

                    yield f"data: {json_data}\n\n"
                    
                    # Send heartbeat every 10 iterations
                    if iteration_count % 10 == 0:
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                except Exception as e:
                    print(f"Excepted because of {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return


                time += timestep
                iteration_count += 1

                import time as time_module

                time_module.sleep(0.7)

        #queue to allow graph paths from thread
        graph_queue = queue.Queue()

        def _draw():
            try:
                graph_paths, shaded, unshaded = draw_graph(start_date, end_date, lat, 
                    lon, local_instance.panel_name, timestep)

                if graph_paths is None:
                    raise Exception("No graphs formed")
                
                graph_queue.put({'success': True, 'paths': graph_paths, 
                    'shadedPower': shaded, 'unshadedPower': unshaded})

            except Exception as e:
                print(f'Graph drawing failed: {e}')
                graph_queue.put({'success': False, 'error': str(e)})

        #assign the graph drawing to the background
        graph_thread = threading.Thread(target=_draw)
        graph_thread.start()

        #indicate graphs starting
        yield f"data: {json.dumps({'type': 'graph_generating', 'message': 'Generating graphs...'})}\n\n"

        #set a timeout to avoid infinite graph
        graph_thread.join(timeout=60)

        #get results from graph and send
        try:
            result = graph_queue.get_nowait()
            
            if result['success']:
                graph_data = {
                    'type': 'graphs_ready',
                    'graphs': result['paths'],
                    'shadedPower': result['shadedPower'],
                    'unshadedPower': result['unshadedPower']
                }
                yield f"data: {json.dumps(graph_data)}\n\n"
            else:
                # Send error message
                error_data = {
                    'type': 'graph_error',
                    'error': result['error']
                }
                yield f"data: {json.dumps(error_data)}\n\n"

        #if the thread times out
        except queue.Empty:
            error_data = {
                'type': 'graph_error',
                'error': 'Graph generation timed out'
            }
            yield f"data: {json.dumps(error_data)}\n\n"

        yield "event: close\ndata: {}\n\n"

        pass
        
    except Exception as e:
        print(f"Generator error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@sm.route("/save_shade_file", methods=['POST'])
def save_shade_file():
    file = request.files.get("pfile")
    if file:
        uploads_dir = os.path.join(current_app.root_path, 'static', 'tmp')
        os.makedirs(uploads_dir, exist_ok=True)

        file_path = os.path.join(uploads_dir, file.filename)
        file.save(file_path)

        return jsonify({"filename": file.filename})
    return jsonify({"error": "No file uploaded"}), 400

@sm.route("/update_power", methods=['POST'])
def update_power():
    global _instance

    original_power = float(request.form.get('original_power'))
    new_power = float(request.form.get('update_power'))

    voltage_offset = new_power/original_power

    _instance.voltage_offset = voltage_offset

    return jsonify({"status": "success", "new_power": new_power})

#draws graphs of over time
def draw_graph(start_date, end_date, lat, lon, panel_name, timestep):
    results = [[],[],[]]
    times = []
    
    u_results = [[],[],[]]

    #sets up the results
    with open("output_text.log", "r") as f:
        lines = f.readlines()
        for line in lines:
            result = line.strip()

            #splits the results
            divided_res = result.split('|')

            #place them in the correct part of the results
            times.append(divided_res[0])
            results[0].append(float(divided_res[1]))
            results[1].append(float(divided_res[2]))
            results[2].append(float(divided_res[3]))

    #sets up the results
    with open("unshaded_output.log", "r") as f:
        lines = f.readlines()
        for line in lines:
            result = line.strip()

            #splits the results
            divided_res = result.split('|')

            u_results[0].append(float(divided_res[1]))
            u_results[1].append(float(divided_res[2]))
            u_results[2].append(float(divided_res[3]))

    output_dir = f'flaskr/static/powertimes/{panel_name}/{lat}{lon}/{start_date}'
    web_dir = f'static/powertimes/{panel_name}/{lat}{lon}/{start_date}'
    # Delete the entire directory if it exists
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    # Recreate the (now empty) directory
    os.makedirs(output_dir)

    #create a unique id so to avoid using browser caching
    unique_id = uuid.uuid4().hex

    plot_paths = []

    #creates the graphs and saves them to the plot
    # --- Plot Power vs Voltage ---
    power_masked = break_zero_blocks(times, results[0])
    u_power_masked = break_zero_blocks(times, u_results[0])
    plt.figure()
    plt.plot(times, u_power_masked, label='Unshaded Power over Time', color='red')
    plt.plot(times, power_masked, label='Shaded Power over Time', color='blue')
    plt.xlabel('Time')
    plt.ylabel('Power (kW)')
    plt.title(f'Power over Time')
    plt.gcf().autofmt_xdate(rotation=45)
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=10, maxticks=18))
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    power_vs_time_path = os.path.join(output_dir, f'{start_date}_{end_date}_{unique_id}P.png')
    web_path = os.path.join(web_dir, f'{start_date}_{end_date}_{unique_id}P.png')
    plt.savefig(power_vs_time_path)
    plt.close()
    plot_paths.append(web_path)

    # --- Plot Power vs Current ---
    voltage_masked = break_zero_blocks(times, results[1])
    u_voltage_masked = break_zero_blocks(times, u_results[1])
    plt.figure()
    plt.plot(times, u_voltage_masked, label='Unshaded Voltage over Time', color='blue')
    plt.plot(times, voltage_masked, label='Shaded Voltage over Time', color='green')
    plt.xlabel('Time')
    plt.ylabel('Voltages (V)')
    plt.title(f'Voltage over Time') 
    plt.gcf().autofmt_xdate(rotation=45)
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=10, maxticks=18))
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    voltage_vs_time_path = os.path.join(output_dir, f'{start_date}_{end_date}_{unique_id}V.png')
    web_path = os.path.join(web_dir, f'{start_date}_{end_date}_{unique_id}V.png')
    plt.savefig(voltage_vs_time_path)
    plt.close()
    plot_paths.append(web_path)

    # --- Plot Voltage vs Current ---
    current_masked = break_zero_blocks(times, results[2])
    u_current_masked = break_zero_blocks(times, u_results[2])
    plt.figure()
    plt.plot(times, u_current_masked, label='Unshaded Current over Time', color='green')
    plt.plot(times, current_masked, label='Shaded Current over Time', color='red')
    plt.xlabel('Time')
    plt.ylabel('Current (A)')
    plt.title(f'Current over Time')
    plt.gcf().autofmt_xdate(rotation=45)
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=10, maxticks=18))
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    current_vs_time_path = os.path.join(output_dir, f'{start_date}_{end_date}_{unique_id}I.png')
    web_path = os.path.join(web_dir, f'{start_date}_{end_date}_{unique_id}I.png')
    plt.savefig(current_vs_time_path)
    plt.close()
    plot_paths.append(web_path)

    #calculate shaded/unshaded results
    shaded_output = hp._round_sf(hp._khw_output(timestep, results[0]))
    unshaded_output = hp._round_sf(hp._khw_output(timestep, u_results[0]))
    

    return plot_paths, shaded_output, unshaded_output

# Print memory and CPU usage
def print_resource_usage(tag=""):
    mem_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = process.cpu_percent(interval=0.1)
    with open("resource_usage.log", "a") as f:
        f.write(f"[{tag}] Memory: {mem_mb:.2f} MB | CPU: {cpu_percent:.1f}%\n")

import numpy as np

def break_zero_blocks(times, values):
    arr = np.array(values, dtype=float)
    mask = arr != 0

    if np.any(mask):
        first_idx = np.argmax(mask)  
        last_idx = len(arr) - np.argmax(mask[::-1]) - 1
        # replace start/end zeros with NaN
        arr[:first_idx] = np.nan
        arr[last_idx+1:] = np.nan
    return arr
