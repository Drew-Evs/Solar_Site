from flask import Blueprint, render_template, request, session, url_for

db = Blueprint('routes', __name__)

@db.route('/')
def dashboard():
    return render_template('dashboard.html')

@db.route('/cell')
def cell():
    return render_template('cell_page.html')

@db.route('/panel')
def panel():
    return render_template('panel_page.html')

@db.route('/string')
def string():
    return render_template('string_page.html')