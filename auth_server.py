#!/usr/bin/env python3
import os
import requests
import dotenv
import datetime
import webbrowser
import threading
from flask import Flask, request
from werkzeug.serving import make_server

app = Flask(__name__)

def load_env():
    if __name__ == "__main__":
        # Running as main, load .env from the current directory of the script
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    else:
        # Running as imported module, load .env from the parent directory
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    
    dotenv.load_dotenv(env_path)

load_env()

token_acquired = threading.Event()
token_thread = None

@app.route('/')
def index():
    return "Authorization Server is running"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if code:
        exchange_code_for_token(code)
        token_acquired.set()
        return 'Token acquired, shutting down server...'
    else:
        return 'Error: Code not received'

def get_auth_url():
    auth_url = 'https://www.facebook.com/v20.0/dialog/oauth'
    params = {
        'client_id': os.getenv('APP_ID'),
        'redirect_uri': "https://"+os.getenv('CLIENT_IP_ADDRESS')+":5000/callback",
        'state': "{st=state123abc,ds=123456789}",
        'scope':os.getenv('GRAPH_SCOPE'),
        'response_type': 'code'
    }
    authorization_url = f"{auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return authorization_url

def exchange_code_for_token(code):
    endpoint_url = 'https://graph.facebook.com/v20.0/oauth/access_token'
    params = {
        'client_id': os.getenv('APP_ID'),
        'client_secret': os.getenv('APP_SECRET'),
        'grant_type': 'authorization_code',
        'redirect_uri': 'https://'+os.getenv('CLIENT_IP_ADDRESS')+':5000/callback',
        'code': code
    }
    response = requests.post(endpoint_url, params=params)
    if response.status_code == 200:
        instagram_access_token = response.json()['access_token']
        try:
            expiry_date = datetime.datetime.now() + datetime.timedelta(seconds=response.json()['expires_in'])
        except:
            debug_token_url = 'https://graph.facebook.com/debug_token'
            debug_token_params = {
                'input_token': instagram_access_token,
                'access_token': os.getenv('APP_ID') + '|' + os.getenv('APP_SECRET')
            }
            debug_token_response = requests.get(debug_token_url, params=debug_token_params)
            expiry_date = datetime.datetime.fromtimestamp(debug_token_response.json()['data']['data_access_expires_at'])
            expiry_date = expiry_date.strftime('%Y-%m-%d %H:%M:%S.%f')
        os.environ['ACCESS_TOKEN'] = instagram_access_token
        os.environ['ACCESS_TOKEN_EXPIRY'] = str(expiry_date)
        dotenv.set_key('.env',"ACCESS_TOKEN", instagram_access_token)
        dotenv.set_key('.env',"ACCESS_TOKEN_EXPIRY", str(expiry_date))
        return response.json()
    else:
        return 'Error: Failed to exchange authorization code for token'

def run_server():
    server = make_server(os.getenv('CLIENT_IP_ADDRESS'), 5000, app, ssl_context="adhoc")
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    return server, server_thread

def open_webbrowser(auth_url):
    webbrowser.open(auth_url, new=1, autoraise=True)

def wait_for_token():
    global token_thread

    token_acquired.clear()
    # Start server and server thread
    server, server_thread = run_server()
    token_acquired.wait()

    # Wait for token acquisition thread to complete
    token_thread.join() if token_thread else None
    server.shutdown()
    server_thread.join()

def native_capture(auth_url):
    global token_thread
    token_thread = threading.Thread(target=open_webbrowser, args=(auth_url,))
    token_thread.start()

def stop_server():
    if not token_acquired.is_set():
        token_acquired.set()

if __name__ == "__main__":
    auth_url = get_auth_url()
    native_capture(auth_url)
    wait_for_token()