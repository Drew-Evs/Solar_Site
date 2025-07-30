import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

#creates the app
def create_app(test_config=None):
    #creates then configures
    app = Flask(__name__, instance_relative_config=True)

    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        #load the test configuration if its passed in
        app.config.from_mapping(test_config)

    #makes sure the folder holding instance exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import routes, models
    app.register_blueprint(routes.bp)

    with app.app_context():
        db.create_all()

    from . import cell_info
    app.register_blueprint(cell_info.ci)

    return app