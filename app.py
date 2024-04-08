from flask import Flask, render_template, request, redirect, flash, url_for, make_response, session, jsonify, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
import json, requests, os, re, MySQLdb.cursors
from datetime import datetime
from code_gen import generate_room_code
from flask_socketio import SocketIO, join_room, leave_room, send



app = Flask(__name__)

with open("config.json", 'r') as c:
    params = json.load(c)["params"]

local_server = True
app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['UPLOAD_FOLDER'] = params['upload_location']
socketio = SocketIO(app)


if(local_server):
    app.config['SQLALCHEMY_DATABASE_URI'] = params['local_uri']
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = params['prod_uri']
# Init news api 



db = SQLAlchemy(app)

class Accounts(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), nullable=False) 
    password = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(20), nullable=False)
    date = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)

# Error handler for 404 page not found
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.route('/', methods=['GET', 'POST'])
def home():
    if "username" in session:
        nick = session['username']
    else:
        nick = "User"
    return render_template('index.html', nick=nick)

# Live Chatting
rooms = {}

@app.route('/chat', methods=["GET", "POST"])
def chat():
    if "username" in session:
        if request.method == "POST":
            # name = request.form.get('name')
            name = session['username']
            create = request.form.get('create', False)
            code = request.form.get('code')
            join = request.form.get('join', False)
    
            # if not name:
            #     return render_template('chat.html', error="Name is required", code=code)
    
            if create != False:
                room_code = generate_room_code(6, list(rooms.keys()))
                new_room = {
                    'members': 0,
                    'messages': []
                }
                rooms[room_code] = new_room
    
            if join != False:
                # no code
                if not code:
                    return render_template('chat.html', error="Please enter a room code to enter a chat room", name=name)
                # invalid code
                if code not in rooms:
                    return render_template('chat.html', error="Room code invalid", name=name)
    
                room_code = code
    
            session['room'] = room_code
            session['username'] = name
            return redirect(url_for('room'))
        else:
            return render_template('chat.html')
    else:
        return redirect('/login')


@app.route('/room')
def room():
    room = session.get('room')
    name = session['username']

    if name is None or room is None or room not in rooms:
        return redirect(url_for('chat'))

    messages = rooms[room]['messages']
    return render_template('room.html', room=room, user=name, messages=messages)


@socketio.on('connect')
def handle_connect():
    name = session['username']
    room = session.get('room')

    if name is None or room is None:
        return
    if room not in rooms:
        leave_room(room)
   
    join_room(room)
    send({
        "sender": "",
        "message": f"{name} has entered the chat"
    }, to=room)
    rooms[room]["members"] += 1


@socketio.on('message')
def handle_message(payload):
    room = session.get('room')
    name = session['username']

    if room not in rooms:
        return

    message = {
        "sender": name,
        "message": payload["message"]
    }
    send(message, to=room)
    rooms[room]["messages"].append(message)


@socketio.on('disconnect')
def handle_disconnect():
    room = session.get("room")
    name = session['username']
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]

    send({
        "message": f"{name} has left the chat",
        "sender": ""
    }, to=room)



# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if "username" in session:
        # Redirect the logged-in user to a separate route
        return redirect('/chat')
    else:
        msg = ''
        if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
            username = request.form['username']
            password = request.form['password']
            # Query the database for the user
            account = Accounts.query.filter_by(username=username, password=password).first()
            if account:
                # Set session variables
                session['loggedin'] = True
                session['id'] = account.id
                session['username'] = account.username
                msg = 'Logged in successfully!'
                return render_template('chat.html', msg=msg)
            else:
                msg = 'Incorrect username/password!'
        return render_template('login.html', msg=msg)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if "username" in session:
        # Redirect the logged-in user to a separate route
          return redirect('/#')
    else:
        msg = ''
        if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form:
            username = request.form['username']
            password = request.form['password']
            email = request.form['email']
            
            # Check if the username already exists
            existing_account = Accounts.query.filter_by(username=username).first()
            if existing_account:
                msg = 'Account already exists!'
            elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
                msg = 'Invalid email address!'
            elif not re.match(r'[A-Za-z0-9]+', username):
                msg = 'Username must contain only characters and numbers!'
            elif not username or not password or not email:
                msg = 'Please fill out the form!'
            else:
                # Create a new account
                new_account = Accounts(username=username, password=password, email=email)
                db.session.add(new_account)
                db.session.commit()
                msg = 'You have successfully registered!'
                return render_template('login.html', msg=msg)
        elif request.method == 'POST':
            msg = 'Please fill out the form!'
        return render_template('register.html', msg=msg)


# Logout
@app.route('/logout')
def logout():
    if "username" in session:
        session.pop('loggedin', None)
        session.pop('id', None)
        session.pop('username', None)
        return redirect("/#")
    else:
        return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True)

