# FB_Graph_Local_Auth

This repository contains code to make an authentication server using the Facebook Graph API for local authentication on a device or local network. This functionality was originally part of the [Smart Display App](https://github.com/yourusername/Smart-Display-App), but has been moved into a standalone repository.

## Setting Up the Authentication Server

### Creating the Facebook Development App

1. Go to the [Facebook Developer Dashboard](https://developers.facebook.com/) and log in with your Facebook account.
2. Click on "My Apps" and then "Create App".
3. Choose the "Business" category and click "Next".
4. Fill in the required fields such as the app name, email address, and select a Business Manager account if applicable. Click "Create App".
5. Once the app is created, navigate to the app dashboard.
6. In the app dashboard, navigate to the "Products" section.
7. Click on "Add a Product" and select "Facebook Login".
8. Follow the prompts to configure Facebook Login for your app.
9. After configuring Facebook Login, repeat step 7 and select "Instagram Graph API".
10. Follow the prompts to configure Instagram Graph API for your app.
11. Navigate to the "Settings" tab in the app dashboard.
12. In the "Basic" settings, add the app domain (in the format `127.0.0.1`) in the "App Domains" field. This will whitelist the redirect URIs.
13. In the "Facebook Login" settings, add the client local IP address (in the format `https://127.0.0.1/callback`) to the "Valid OAuth Redirect URIs".
14. Save your changes.

### Setting Environment Variables

1. Create a `.env` file in the project directory.
2. Set the following environment variables in the `.env` file:
   - `APP_ID`: The App ID obtained from the Facebook Developer Dashboard.
   - `APP_SECRET`: The App Secret obtained from the Facebook Developer Dashboard.
   - `CLIENT_TOKEN`: The Client Token obtained from the Facebook Developer Dashboard.
   - `CLIENT_IP_ADDRESS`: The local IP address of the device where the application will run. This can be either `192.168.x.y`, `localhost`, or `127.0.0.1`.

Ensure that the `.env` file contains these variables with their respective values before running the application. These variables are necessary for the application to communicate with the Facebook Graph API services.

### Generating the Authentication URL

The authentication server includes a function `get_auth_url()` that uses the environment variables to get the authentication URL from the Facebook Graph API. By default, if you run the code as the main module, it will open up the local browser to start the authentication process.