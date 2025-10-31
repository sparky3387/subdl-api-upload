# subdl-api-upload
=======================================
Automatically upload your subtitle collection to SUBDL

## Overview

This script automates the process of finding local subtitle files (`.srt`) for your media library and uploading them to SubDL.com.

It connects to your Sonarr (for TV shows) and Radarr (for movies) instances to get a list of all downloaded media. For each item, it checks for a local subtitle file, searches SubDL to prevent duplicates, and then prompts you (or automatically uploads) the subtitle.

## Requirements

1.  **Python 3:** The script is written in Python 3.
2.  **Requests Library:** You must have the `requests` library installed. You can install it using pip:
    ```bash
    pip install requests
    ```

## Configuration & API Keys

The script requires several command-line arguments to function. Here is how to get each required part:

### 1. Radarr API Key (`--radarr-api-key`)
   - Open your Radarr web interface.
   - Go to **Settings -> General**.
   - Your API Key is listed in the "Security" section. Copy this long string.

### 2. Sonarr API Key (`--sonarr-api-key`)
   - Open your Sonarr web interface.
   - Go to **Settings -> General**.
   - Your API Key is listed in the "Security" section. Copy this long string.

### 3. SubDL Search API Key (`--subdl-search-key`)
   - Log in to your account on **SubDL.com**.
   - Navigate to your account settings or API section.
   - Find your generated API Key for searching.

### 4. SubDL Upload Token (`--subdl-upload-token`)
   This is the most complex part, as this token is temporary and must be retrieved from your browser. It expires after a while (e.g., a day or a week), and you will need to get a new one if the script reports an "Unauthorized Access" error.

   1.  Open Google Chrome or Firefox and log in to your account on **SubDL.com**.
   2.  Open the **Developer Tools** (usually by pressing **F12** or **Ctrl+Shift+I**).
   3.  Click on the **"Network"** tab within the Developer Tools.
   4.  On the SubDL website, perform an action that requires you to be logged in (e.g., click on your profile, go to the upload page). This will generate traffic in the Network tab.
   5.  In the Network tab's filter box, type `api3` to find the relevant API requests.
   6.  Click on one of these requests in the list (e.g., `getNId` or `profile`).
   7.  A new panel will open. Look for the **"Request Headers"** section.
   8.  Find the header named `Authorization`. It will look like this:
       `Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...`
   9.  Copy the **entire long string of characters *after* "Bearer "** (the part that starts with `eyJ...`). This is your Upload Token.

## Command-Line Arguments

*   `--radarr-url`: URL for your Radarr instance (e.g., `http://localhost:7878`).
*   `--radarr-api-key`: Your Radarr API key.
*   `--radarr-base-paths`: Comma-separated list of your Radarr media root folders (e.g., `/movies,/movies2`).
*   `--sonarr-url`: URL for your Sonarr instance (e.g., `http://localhost:8989`).
*   `--sonarr-api-key`: Your Sonarr API key.
*   `--sonarr-base-paths`: Comma-separated list of your Sonarr media root folders (e.g., `/tv`).
*   `--subdl-search-key`: Your SubDL API key for searching.
*   `--subdl-upload-token`: The temporary JWT token for uploading, retrieved from your browser.
*   `--language`: (Optional) The two-letter language code for the subtitles (default: `en`).
*   `--always-upload-tv`: (Optional) If present, automatically uploads TV subtitles without asking.
*   `--always-upload-movie`: (Optional) If present, automatically uploads movie subtitles without asking.

## Usage Example

Run the script from your terminal. Replace all placeholder values with your actual data.

```bash
python subdl_uploader.py \
    --radarr-url "http://192.168.1.10:7878" \
    --radarr-api-key "YOUR_RADARR_API_KEY" \
    --radarr-base-paths "/media/movies" \
    --sonarr-url "http://192.168.1.10:8989" \
    --sonarr-api-key "YOUR_SONARR_API_KEY" \
    --sonarr-base-paths "/media/tvshows" \
    --subdl-search-key "YOUR_SUBDL_SEARCH_KEY" \
    --subdl-upload-token "eyJ...[PASTE_THE_LONG_TOKEN_HERE]...2a4" \
    --language "en" \
    --always-upload-movie
```

## How it Works & Features

-   **Stateful Processing:** The script creates a `processed_subtitles.log` file to remember which movies and TV episodes it has already processed (either skipped or uploaded). On subsequent runs, it will skip these items to save time.
-   **Duplicate Prevention:** Before uploading, it searches SubDL for existing subtitles for the same movie/episode that match your local file's release group, preventing duplicate uploads.
-   **Hearing Impaired (HI) Detection:** It automatically detects if a subtitle is for the hearing impaired by checking the filename for `.hi.` or `.sdh.` tags and sets the flag correctly on upload.
-   **Release Group Handling:** It intelligently skips uploads for releases from the "Sickbeard" group, as these are often unreliable.
-   **Rate Limiting:** A random 5-10 second delay is added before every call to the SubDL API to avoid being rate-limited.
-   **Cancellation:** For automatic movie uploads, you can press **Ctrl+C** during the brief delay to cancel the upload for that specific movie and mark it as processed.
