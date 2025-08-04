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

sm = Blueprint('string_modelling', __name__)

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

        unit = data.get("unit", "minutes")
        time_int = int(data.get("time_int", 1))
        start_date = datetime.fromisoformat(data.get("start", datetime.now().isoformat()))
        end_date = datetime.fromisoformat(data.get("end", (datetime.now() + timedelta(hours=24)).isoformat()))
        lon = float(data.get("lon", 0))
        lat = float(data.get("lat", 0))
        p_filename = data.get("pfile", "")

        print(f"File name is {p_filename}")

        shaded_results = [[],[],[]]
        unshaded_results = [[],[],[]]

        #get correct timestep unit
        time_dict = {
            'minutes': 'm',
            'hours': 'h',
            'days': 'd'
        }

        t_unit = time_dict.get(unit)
        timezone = ZoneInfo(hp.get_timezone(lat, lon))
        
        timestep = timedelta(**{unit: time_int})

        dni_df = hp.get_irr(start_date, end_date, lat, lon, time_int, t_unit, timezone)

        app = current_app._get_current_object()

    except Exception as e:
        print(f"Error due to {e}")
        return Response(f"data: {json.dumps({'error': str(e)})}\n\n", mimetype='text/event-stream')

    def generate():
        #stores data
        times = []
        results = [[],[],[]]

        try:
            if _instance is None:
                raise Exception("String instance missing")
            
            #create the dictionary needed
            pixel_file_path = os.path.join('/tmp/', p_filename)
            with open(pixel_file_path, "r") as pixel_file:
                pixel_dict = hp.file_pixel_dict(pixel_file, start_date, end_date, timestep)

            panel_dict = hp.calculate_pixels(_instance)
        
        except Exception as e:
            print(f'Cant simulate due to: {e}')
            yield f"event: error\ndata: {str(e)}\n\n"
            return

        with app.app_context():
            time = start_date.replace(tzinfo=timezone)
            end = end_date.replace(tzinfo=timezone)
            print(f'timezone is {timezone}')

            print(dni_df.index)
            print("Index type:", type(dni_df.index[0]))
            print("Index example:", dni_df.index[0])

            while time <= end:
                print("Time in loop:", time, type(time))
                row = dni_df.loc[time]
                irr = row['dni']
                temp = row['temp']

                if irr == 0:
                    time += timestep
                    continue
                
                #calculate the values like before
                _instance.reset(irr, temp)
                
                hp.set_shade_at_time(time, panel_dict, pixel_dict)
                
                try:    
                    Pmax, Vmp, Imp = _instance.model_power()
                    print(f'pmax found as {Pmax}')
                    data = {
                        'pmax': Pmax,
                        'e_info': irr,
                        'time': time.isoformat()
                    }

                    times.append(time)
                    results[0].append(Pmax)
                    results[1].append(Vmp)
                    results[2].append(Imp)

                    yield f"data: {json.dumps(data)}\n\n"

                except Exception as e:
                    print(f"Excepted because of {e}")
                    yield "event: close\ndata: done\n\n"
                
                time += timestep

            yield "event: close\ndata: done\n\n"

        draw_graph(results, times, start_date, end_date, lat, lon)

    return Response(generate(), mimetype='text/event-stream')


@sm.route("/save_shade_file", methods=['POST'])
def save_shade_file():
    file = request.files.get("pfile")
    if file:
        file_path = os.path.join("/tmp/", file.filename)
        file.save(file_path)
        return jsonify({"filename": file.filename})
    return jsonify({"error": "No file uploaded"}), 400


#draws graphs of over time
def draw_graph(results, times, start_date, end_date, lat, lon):
    output_dir = f'flaskr/static/powertimes/{panel_name}/{lat}{lon}/{start_date}'
    os.makedirs(output_dir, exist_ok=True)

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
    plt.savefig(power_vs_time_path)
    plt.close()
    plot_paths.append(power_vs_time_path)

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
    plt.savefig(voltage_vs_time_path)
    plt.close()
    plot_paths.append(voltage_vs_time_path)

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
    plt.savefig(current_vs_time_path)
    plt.close()
    plot_paths.append(current_vs_time_path)

    return plot_paths