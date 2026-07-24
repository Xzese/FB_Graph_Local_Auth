#!/usr/bin/env python3

import datetime
import os
import secrets
import threading
import webbrowser
from urllib.parse import urlencode

import dotenv
import requests
from flask import Flask, Response, request
from werkzeug.serving import make_server


app = Flask(__name__)


def get_env_path():
    """
    Return the location of the .env file.

    When run directly, the .env file is expected beside this script.
    When imported as a submodule, the .env file is expected in the
    parent project directory.
    """
    if __name__ == "__main__":
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".env",
        )

    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".env",
    )


dotenv.load_dotenv(get_env_path())


token_acquired = threading.Event()
token_thread = None

# Details for the currently active OAuth attempt.
pending_oauth_state = None
pending_auth_url = None

# Protect the pending OAuth state in case functions are called from
# different application and Flask server threads.
oauth_state_lock = threading.RLock()


def _get_required_environment_variable(name):
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable {name} is not configured."
        )

    return value.strip()


def _clear_pending_oauth_attempt():
    global pending_oauth_state
    global pending_auth_url

    with oauth_state_lock:
        pending_oauth_state = None
        pending_auth_url = None


@app.route("/")
def index():
    return Response(
        "Authorization server is running",
        status=200,
        mimetype="text/plain",
    )


@app.route("/callback")
def callback():
    state = request.args.get("state")
    code = request.args.get("code")

    with oauth_state_lock:
        expected_state = pending_oauth_state

    if not state or not expected_state:
        return Response(
            "Error: Invalid or missing OAuth state",
            status=400,
            mimetype="text/plain",
        )

    if not secrets.compare_digest(state, expected_state):
        return Response(
            "Error: Invalid or missing OAuth state",
            status=400,
            mimetype="text/plain",
        )

    # Facebook may return an OAuth error instead of an authorization code.
    oauth_error = request.args.get("error")

    if oauth_error:
        error_description = request.args.get(
            "error_description",
            oauth_error,
        )

        _clear_pending_oauth_attempt()

        return Response(
            f"Error: Facebook authorization failed: {error_description}",
            status=400,
            mimetype="text/plain",
        )

    if not code:
        _clear_pending_oauth_attempt()

        return Response(
            "Error: Authorization code not received",
            status=400,
            mimetype="text/plain",
        )

    token_response = exchange_code_for_token(code)

    if token_response is None:
        # Keep the current state and URL available so the user can reopen
        # the same authorization URL and retry the flow.
        return Response(
            "Error: Failed to exchange authorization code for token",
            status=502,
            mimetype="text/plain",
        )

    _clear_pending_oauth_attempt()
    token_acquired.set()

    return Response(
        "Token acquired, shutting down server...",
        status=200,
        mimetype="text/plain",
    )


def get_auth_url(force_new=False):
    """
    Return the URL for the current OAuth attempt.

    Repeated calls return the same URL and state unless force_new=True.
    This ensures a displayed QR code and a subsequently opened browser
    use the same OAuth state.
    """
    global pending_oauth_state
    global pending_auth_url

    with oauth_state_lock:
        if (
            not force_new
            and pending_oauth_state is not None
            and pending_auth_url is not None
        ):
            return pending_auth_url

        app_id = _get_required_environment_variable("APP_ID")
        client_ip_address = _get_required_environment_variable(
            "CLIENT_IP_ADDRESS"
        )
        graph_scope = _get_required_environment_variable("GRAPH_SCOPE")

        redirect_uri = (
            f"https://{client_ip_address}:5000/callback"
        )

        pending_oauth_state = secrets.token_urlsafe(32)

        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "state": pending_oauth_state,
            "scope": graph_scope,
            "response_type": "code",
        }

        pending_auth_url = (
            "https://www.facebook.com/v20.0/dialog/oauth?"
            + urlencode(params)
        )

        return pending_auth_url


def exchange_code_for_token(code):
    app_id = _get_required_environment_variable("APP_ID")
    app_secret = _get_required_environment_variable("APP_SECRET")
    client_ip_address = _get_required_environment_variable(
        "CLIENT_IP_ADDRESS"
    )

    endpoint_url = (
        "https://graph.facebook.com/v20.0/oauth/access_token"
    )

    params = {
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": (
            f"https://{client_ip_address}:5000/callback"
        ),
        "code": code,
    }

    try:
        response = requests.post(
            endpoint_url,
            data=params,
            timeout=30,
        )
    except requests.RequestException as error:
        print(f"Token exchange request failed: {error}")
        return None

    if response.status_code != 200:
        print(
            "Token exchange failed with status "
            f"{response.status_code}: {response.text}"
        )
        return None

    try:
        response_payload = response.json()
    except ValueError:
        print("Token exchange returned an invalid JSON response.")
        return None

    instagram_access_token = response_payload.get("access_token")

    if not instagram_access_token:
        print("Token exchange response did not include an access token.")
        return None

    expiry_date = _get_access_token_expiry(
        response_payload=response_payload,
        instagram_access_token=instagram_access_token,
        app_id=app_id,
        app_secret=app_secret,
    )

    if expiry_date is None:
        print("Unable to determine the access-token expiry date.")
        return None

    expiry_date_string = str(expiry_date)

    os.environ["ACCESS_TOKEN"] = instagram_access_token
    os.environ["ACCESS_TOKEN_EXPIRY"] = expiry_date_string

    dotenv.set_key(
        get_env_path(),
        "ACCESS_TOKEN",
        instagram_access_token,
    )
    dotenv.set_key(
        get_env_path(),
        "ACCESS_TOKEN_EXPIRY",
        expiry_date_string,
    )

    return response_payload


def _get_access_token_expiry(
    response_payload,
    instagram_access_token,
    app_id,
    app_secret,
):
    expires_in = response_payload.get("expires_in")

    if expires_in is not None:
        try:
            return datetime.datetime.now() + datetime.timedelta(
                seconds=int(expires_in)
            )
        except (TypeError, ValueError):
            print(
                "Token response contained an invalid expires_in value."
            )

    debug_token_url = "https://graph.facebook.com/debug_token"

    debug_token_params = {
        "input_token": instagram_access_token,
        "access_token": f"{app_id}|{app_secret}",
    }

    try:
        debug_token_response = requests.get(
            debug_token_url,
            params=debug_token_params,
            timeout=30,
        )
    except requests.RequestException as error:
        print(f"Debug-token request failed: {error}")
        return None

    if debug_token_response.status_code != 200:
        print(
            "Debug-token request failed with status "
            f"{debug_token_response.status_code}: "
            f"{debug_token_response.text}"
        )
        return None

    try:
        debug_payload = debug_token_response.json()
        expiry_timestamp = debug_payload["data"][
            "data_access_expires_at"
        ]
        return datetime.datetime.fromtimestamp(
            int(expiry_timestamp)
        )
    except (KeyError, TypeError, ValueError):
        print(
            "Debug-token response did not contain a valid "
            "data_access_expires_at value."
        )
        return None


def run_server():
    client_ip_address = _get_required_environment_variable(
        "CLIENT_IP_ADDRESS"
    )

    print(client_ip_address)

    server = make_server(
        client_ip_address,
        5000,
        app,
        ssl_context="adhoc",
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
    )
    server_thread.start()

    return server, server_thread


def open_webbrowser(auth_url):
    webbrowser.open(
        auth_url,
        new=1,
        autoraise=True,
    )


def wait_for_token():
    global token_thread

    token_acquired.clear()

    server, server_thread = run_server()

    try:
        token_acquired.wait()
    finally:
        if (
            token_thread is not None
            and token_thread is not threading.current_thread()
        ):
            token_thread.join(timeout=5)

        server.shutdown()
        server_thread.join()


def local_browser_capture(auth_url=None):
    """
    Open the current OAuth URL in the local browser.

    auth_url remains optional for compatibility with existing callers.
    When omitted, get_auth_url() returns the existing pending URL rather
    than generating a different state.
    """
    global token_thread

    if auth_url is None:
        auth_url = get_auth_url()

    token_thread = threading.Thread(
        target=open_webbrowser,
        args=(auth_url,),
    )
    token_thread.start()


def stop_server():
    _clear_pending_oauth_attempt()
    token_acquired.set()


if __name__ == "__main__":
    authorization_url = get_auth_url()
    local_browser_capture(authorization_url)
    wait_for_token()