from flask import Blueprint, render_template, request, session, url_for, current_app, jsonify, Response
import os
import json
from PIL import Image
from .classes import Solar_String
from .models import PanelInfo
import flaskr.helper_functions as hp
from datetime import datetime, timedelta
import pytz

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
    hp.create_edatabase(datetime.datetime.now(), 24, 69)
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
        pixel_file = data.get("pfile", "")

        shaded_results = [[],[],[]]
        unshaded_results = [[],[],[]]

        pixel_file = request.form.get("pfile")
        #convert to string to slice the date
        string_file = f'{pixel_file}'
        result = string_file.split('_')[0]

        hp.create_edatabase(start_date, end_date, lat, lon)

        timestep = timedelta(**{unit: time_int})

    except Exception as e:
        print(f"Error due to {e}")
        return Response(f"data: {json.dumps({'error': str(e)})}\n\n", mimetype='text/event-stream')

    def generate():
        time = start_date
        while time <= end_date:
            data = {"time": time.isoformat()}
            yield f"data: {json.dumps(data)}\n\n"
            time += timestep

    return Response(generate(), mimetype='text/event-stream')


    


