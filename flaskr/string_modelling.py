from flask import Blueprint, render_template, request, session, url_for, current_app, jsonify, Response
import os
import json
from PIL import Image
from .classes import Solar_String
from .models import PanelInfo, EnvironmentalData
import flaskr.helper_functions as hp
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
    try:
        panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
        panel_names = [p.panel_name for p in panels]

        #create a test string and pixel coords
        global _instance
        t_dict = hp.calculate_pixels(_instance)

        #need to find the image first
        filepath = f"./flaskr/static/uploads"
        output_dir = f"./flaskr/static/outputs"
        os.makedirs(output_dir, exist_ok=True)
        if os.path.exists(filepath):
            files = sorted(os.listdir(filepath))
            if files:
                first_file = os.path.join(filepath, files[0])
                output_path = os.path.join(output_dir, files[0])

        #clear the path first
        for f in os.listdir(output_dir):
            file_path = os.path.join(output_dir, f)
            if os.path.isfile(file_path):
                os.remove(file_path)

        #open and draw pixels 
        with Image.open(first_file) as img:
            #ensure in rgb
            img = img.convert("RGB")
            
            #gets the pixel location 
            for key in t_dict:
                x,y = hp.key_to_pixel(key)
                x = int(x)
                y = int(y)
                if 0 <= x < img.width and 0 <= y < img.height:
                    img.putpixel((x, y), (0, 0, 255))
                
            img.save(output_path)
            print(f'/static/outputs/{files[0]}')

        return jsonify({
            "status": "success",
            "image": f"/static/outputs/{files[0]}"  # relative path for web use
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
        _instance = Solar_String(panel_name, length=4.69, width=2.278, rotation=rotation, num_panels=panel_count, left_top_point=(x,y))
        place_pixels()
        return jsonify({"status": "success"})

    except Exception as e:
        print(f'Exception is {e}')
        return jsonify({"status": "error", "message": str(e)})

@sm.route('/get_environment_data', methods=['POST'])
def get_enviroment_data():
    hp.create_edatabase(datetime.now(), 24, 69)
    return place_pixels()

#does the modelling for time against power
@sm.route('/model_power', methods=['POST', 'GET'])
def time_power_model():
    try:
        global _instance

        #pull results from the page
        data = request.args if request.method == 'GET' else request.form

        print(f'Request args: {request.args}')

        unit = data.get("unit", "minutes")
        time_int = int(data.get("time_int", 1))
        start_date = datetime.fromisoformat(data.get("start", datetime.now().isoformat()))
        end_date = datetime.fromisoformat(data.get("end", (datetime.now() + timedelta(hours=24)).isoformat()))
        lon = float(data.get("lon", 0))
        lat = float(data.get("lat", 0))
        p_filename = data.get("pfile", "")

        #last id to resume connection
        last_event_id = data.get('Last-Event-ID', None)

        try:
            last_id = int(last_event_id)
        except (ValueError, TypeError):
            last_id = None

        print(f"File name is {p_filename}")

        #get correct timestep unit
        time_dict = {
            'minutes': 'm',
            'hours': 'h',
            'days': 'd'
        }

        t_unit = time_dict.get(unit)
        timezone = ZoneInfo(hp.get_timezone(lat, lon))
        
        timestep = timedelta(**{'hours': time_int})
        print(timestep)

        dni_df = hp.get_irr(start_date, end_date, lat, lon, time_int, t_unit, timezone)

        app = current_app._get_current_object()

    except Exception as e:
        print(f"Error due to {e}")
        return Response(f"data: {json.dumps({'error': str(e)})}\n\n", mimetype='text/event-stream')

    # Return response with proper headers for SSE
    response = Response(
        generate(_instance, timestep, p_filename, start_date, end_date, app, dni_df, timezone, last_id, lat, lon), 
        mimetype='text/event-stream',
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
    return response

def generate(_instance, timestep, p_filename, start_date, end_date,
        app, dni_df, timezone, last_id, lat, lon):
    try:
        local_instance = copy.deepcopy(_instance)
        print(f'Local copy {local_instance.num_panels}')

        print(f'Last id is {last_id}')

        #stores data
        times = []
        results = [[],[],[]]

        with app.app_context():
            try:
                if local_instance is None:
                    raise Exception("String instance missing")
                
                #create the dictionary needed
                pixel_file_path = os.path.join(current_app.root_path, 'static', 'tmp', p_filename)
                print(f'Pixel file path: {pixel_file_path}')
                with open(pixel_file_path, "r") as pixel_file:
                    pixel_dict = hp.file_pixel_dict(pixel_file, start_date, end_date, timestep)

                print(f'pixel dict is {pixel_dict}')

                panel_dict = hp.calculate_pixels(local_instance)
            
            except Exception as e:
                print(f'Cant simulate due to: {e}')
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                return

            time = start_date.replace(tzinfo=timezone)
            end = end_date.replace(tzinfo=timezone)
            print(f'timezone is {timezone}')

            print(dni_df.index)
            print("Index type:", type(dni_df.index[0]))
            print("Index example:", dni_df.index[0])

            iteration_count = 0

            while time <= end:
                #skips events already done
                if last_id is not None and iteration_count <= last_id:
                    time += timedelta(hours=1)
                    iteration_count += 1
                    continue


                print("Time in loop:", time, type(time))
                try:
                    row = dni_df.loc[time]
                except KeyError:
                    print(f"Time {time} not found in DNI dataframe")
                    time += timestep
                    continue
                
                try:
                    irr = row['dni']
                    temp = row['temp']
                except Exception as e:
                    print(f'Finally failed due to {e}')
                    time += timedelta(hours=1)
                    continue

                if irr == 0:
                    time += timestep
                    iteration_count += 1
                    continue
                
                try:
                    #calculate the values like before
                    out1 = local_instance.reset(irr, temp)
                    print(f'Output from reset is {out1}')
                    
                    #out = hp.set_shade_at_time(time, panel_dict, pixel_dict)
                    #print(f'Output from shade is {out}')
                except Exception as e:
                    print(f'Setting shade failed due to {e}')
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return
                
                try:    
                    Pmax, Vmp, Imp = local_instance.model_power()
                    print(f'pmax found as {Pmax}')
                    
                    data = {
                        'pmax': float(Pmax) if Pmax is not None else 0.0,
                        'e_info': float(irr) if irr is not None else 0.0,
                        'time': time.isoformat(),
                        'id': iteration_count
                    }

                    times.append(time)
                    results[0].append(Pmax)
                    results[1].append(Vmp)
                    results[2].append(Imp)

                    json_data = json.dumps(data)
                    print(f"DEBUG at {time}: Pmax={Pmax}, irr={irr}, temp={temp}")
                    print(f"Serialized data: {json_data}")

                    yield f"data: {json_data}\n\n"
                    
                    # Send heartbeat every 10 iterations
                    if iteration_count % 10 == 0:
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                except Exception as e:
                    print(f"Excepted because of {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return


                time += timedelta(hours=1)
                iteration_count += 1

                import time as time_module

                time_module.sleep(0.7)

        #queue to allow graph paths from thread
        graph_queue = queue.Queue()

        def _draw():
            try:
                graph_paths = draw_graph(results, times, start_date, end_date, lat, 
                    lon, local_instance.panel_name)

                if graph_paths is None:
                    raise Exception("No graphs formed")
                
                graph_queue.put({'success': True, 'paths': graph_paths})

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
                    'graphs': result['paths']
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


#draws graphs of over time
def draw_graph(results, times, start_date, end_date, lat, lon, panel_name):
    output_dir = f'flaskr/static/powertimes/{panel_name}/{lat}{lon}/{start_date}'
    web_dir = f'static/powertimes/{panel_name}/{lat}{lon}/{start_date}'
    # Delete the entire directory if it exists
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    # Recreate the (now empty) directory
    os.makedirs(output_dir)

    plot_paths = []

    #creates the graphs and saves them to the plot
    # --- Plot Power vs Voltage ---
    plt.figure()
    plt.plot(times, results[0], label='Power over Time', color='blue')
    plt.xlabel('Time')
    plt.ylabel('Power (W)')
    plt.title(f'{start_date}-{end_date} Power over Time')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    power_vs_time_path = os.path.join(output_dir, f'{start_date}_{end_date}_P.png')
    web_path = os.path.join(web_dir, f'{start_date}_{end_date}_P.png')
    plt.savefig(power_vs_time_path)
    plt.close()
    plot_paths.append(web_path)

    # --- Plot Power vs Current ---
    plt.figure()
    plt.plot(times, results[1], label='Voltage over Time', color='green')
    plt.xlabel('Time')
    plt.ylabel('Voltages (V)')
    plt.title(f'{start_date}-{end_date} Voltage over Time')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    voltage_vs_time_path = os.path.join(output_dir, f'{start_date}_{end_date}_V.png')
    web_path = os.path.join(web_dir, f'{start_date}_{end_date}_V.png')
    plt.savefig(voltage_vs_time_path)
    plt.close()
    plot_paths.append(web_path)

    # --- Plot Voltage vs Current ---
    plt.figure()
    plt.plot(times, results[2], label='Current over Time', color='red')
    plt.xlabel('Time')
    plt.ylabel('Current (A)')
    plt.title(f'{start_date}-{end_date} Current over Time')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    current_vs_time_path = os.path.join(output_dir, f'{start_date}_{end_date}_I.png')
    web_path = os.path.join(web_dir, f'{start_date}_{end_date}_I.png')
    plt.savefig(current_vs_time_path)
    plt.close()
    plot_paths.append(web_path)

    return plot_paths

# Print memory and CPU usage
def print_resource_usage(tag=""):
    mem_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = process.cpu_percent(interval=0.1)
    with open("resource_usage.log", "a") as f:
        f.write(f"[{tag}] Memory: {mem_mb:.2f} MB | CPU: {cpu_percent:.1f}%\n")
