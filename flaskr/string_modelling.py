from flask import Blueprint, render_template, request, session, url_for, current_app
import os
from PIL import Image
from .classes import Solar_String
from .models import PanelInfo
import flaskr.helper_functions as hp
import datetime

sm = Blueprint('string_modelling', __name__)

#global variable for a string
_instance = None

@sm.route('/upload', methods=['POST'])
def upload_file():
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
        filepath = f"./flaskr/static/uploads/{file.filename}"
        file.save(filepath)

        return render_template('string_page.html', uploaded=True, image=filepath,
            panel_names=panel_names)


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
                print("First file:", first_file)

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

            return render_template('string_page.html', uploaded=True, image=output_path,
                panel_names=panel_names)

    except Exception as e:
        print(f'Error placing pixels {e}')
        return render_template('string_page.html', uploaded=False,
            panel_names=panel_names)
        
@sm.route('/build_string', methods=['POST'])
def build_string():
    global _instance
    panel_count = int(request.form.get("panel_count", 28))
    panel_name = request.form.get("panel_name", 'Jinko_Solar_Co___Ltd_JKM410M_72HL_V')
    x = int(request.form.get("X", 0))
    y = int(request.form.get("Y", 0))
    rotation = int(request.form.get("Rotation", 0))

    try:
        _instance = Solar_String(panel_name, length=4.69, width=2.278, rotation=rotation, num_panels=panel_count, left_top_point=(x,y))

    except Exception as e:
        print(f'Excpetion is {e}')
        panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
        panel_names = [p.panel_name for p in panels]
        return render_template('string_page.html',panel_names=panel_names)

    return place_pixels()

@sm.route('/get_environment_data', methods=['POST'])
def get_enviroment_data():
    hp.create_edatabase(datetime.datetime.now(), 24, 69)
    return place_pixels()


#does the modelling for time against power
@sm.route('/model_power', methods=['POST', 'GET'])
def time_power_model():
    global _instance

    shaded_results = [[],[],[]]
    unshaded_results = [[],[],[]]

    string_pixels = hp.calculate_pixels(_instance)

    pixel_file = request.get.form("pfile")
    file_pixels = hp.file_pixel_dict(pixel_file, start_date, end_date, time_step)
