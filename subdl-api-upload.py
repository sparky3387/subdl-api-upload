import argparse
import requests
import json
import os
import glob
import time
import random
import sys
from typing import List, Dict, Any, Optional

# Define the base URL for the SubDL API
SUBDL_SEARCH_URL = "https://api.subdl.com/api/v1/subtitles"
SUBDL_UPLOAD_API_URL = "https://api3.subdl.com/user"
# Define the prefix for subtitle download links
LINK_PREFIX = "https://dl.subdl.com"

# --- Configuration for Processed Items ---
PROCESSED_LOG_FILE = "processed_subtitles.log"

# --- Helper Function for API Delay ---
def subdl_api_delay():
    """Waits for a random duration between 5 to 10 seconds."""
    delay_seconds = random.uniform(5, 10)
    # This print statement can be commented out if you prefer a quieter script
    print(f"    (Waiting for {delay_seconds:.2f} seconds before next SubDL API call...)")
    time.sleep(delay_seconds)

# --- Subdl API Functions (with delay added) ---

def search_subtitles(api_key: str, imdb_id: str = None, tmdb_id: str = None, type: str = None, languages: str = None, season_number: int = None, episode_number: int = None) -> Dict[str, Any]:
    """
    Searches for subtitles on SubDL, requesting release info as well.
    Can now also search for specific TV episodes.
    """
    subdl_api_delay()
    params = {
        "api_key": api_key,
        "imdb_id": imdb_id,
        "tmdb_id": tmdb_id,
        "type": type,
        "languages": languages,
        "season_number": season_number,
        "episode_number": episode_number,
        "subs_per_page": 30,
        "releases": 1
    }
    try:
        filtered_params = {k: v for k, v in params.items() if v is not None}
        response = requests.get(SUBDL_SEARCH_URL, params=filtered_params)
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": False, "error": f"Request failed with status code {response.status_code}"}
    except requests.RequestException as e:
        return {"status": False, "error": f"An error occurred: {e}"}

def get_n_id(token: str) -> Optional[str]:
    """
    Step 1: Get a unique ID (n_id) for the upload session.
    """
    subdl_api_delay()
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{SUBDL_UPLOAD_API_URL}/getNId", headers=headers)
        
        if response.status_code == 200 and response.json().get("ok"):
            return response.json().get("n_id")
        else:
            print(f"Error getting n_id. Status Code: {response.status_code}. Response: {response.text}")
            return None
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"An error occurred while getting n_id: {e}")
        return None

def upload_subtitle_file(token: str, n_id: str, file_path: str) -> Optional[Dict[str, Any]]:
    """
    Step 2: Upload the actual subtitle file.
    """
    subdl_api_delay()
    try:
        with open(file_path, 'rb') as f:
            files = {'subtitle': (os.path.basename(file_path), f)}
            data = {'n_id': n_id}
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.post(f"{SUBDL_UPLOAD_API_URL}/uploadSingleSubtitle", headers=headers, files=files, data=data)
            
            if response.status_code == 200 and response.json().get("ok"):
                return response.json().get("file")
            else:
                print(f"Error uploading file {os.path.basename(file_path)}: {response.text}")
                return None
    except (requests.RequestException, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"An error occurred during file upload: {e}")
        return None

def complete_subtitle_upload(token: str, n_id: str, file_n_id: str, metadata: Dict[str, Any]) -> bool:
    """
    Step 3: Submit all metadata to finalize the upload.
    """
    subdl_api_delay()
    data = {
        "file_n_ids": json.dumps([file_n_id]),
        "n_id": n_id,
        **metadata
    }
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(f"{SUBDL_UPLOAD_API_URL}/uploadSubtitle", headers=headers, data=data)
        
        upload_result = response.json()
        print(f"     -> API Upload Response: {json.dumps(upload_result, indent=4)}")

        if response.status_code == 200 and upload_result.get("status"):
            print(f"     -> Successfully submitted for review: {metadata.get('name')}")
            return True
        else:
            print(f"     -> Error completing subtitle upload for {metadata.get('name')}")
            return False
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"An error occurred completing the upload or decoding the response: {e}")
        return False

# --- Sonarr/Radarr API Functions ---

def get_from_arr(api_url: str, api_key: str, endpoint: str) -> List[Dict[str, Any]]:
    """
    Generic function to get all items from a Sonarr/Radarr endpoint.
    """
    try:
        response = requests.get(f"{api_url}/api/v3/{endpoint}", headers={"X-Api-Key": api_key})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error connecting to {api_url}: {e}")
        return []

# --- Helper Functions for Processed Items ---

def load_processed_list(filename: str = PROCESSED_LOG_FILE) -> set:
    """Loads the set of processed items from a file."""
    processed = set()
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                for line in f:
                    processed.add(line.strip())
        except IOError as e:
            print(f"Warning: Could not read processed list from {filename}: {e}")
    return processed

def save_processed_item(item_key: str, filename: str = PROCESSED_LOG_FILE) -> None:
    """Appends an item to the processed list file."""
    try:
        with open(filename, 'a') as f:
            f.write(item_key + '\n')
    except IOError as e:
        print(f"Warning: Could not write to processed list file {filename}: {e}")

def get_item_key(item_type: str, tmdb_id: str, season: int = 0, episode: int = 0, imdb_id: Optional[str] = None) -> str:
    """Generates a unique key for an item to store in the processed list."""
    if item_type == "movie":
        return f"movie:{tmdb_id}"
    elif item_type == "tv":
        return f"tv:{tmdb_id}:{season}:{episode}"
    return f"{item_type}:{tmdb_id}:{imdb_id}" # Fallback if season/episode are 0

# --- Helper Functions for File Operations ---

def find_local_path(media_path: str, base_paths: List[str]) -> Optional[str]:
    """
    Tries to find the correct local path for a media item given a list of base paths.
    """
    folder_name = os.path.basename(media_path)
    for base_path in base_paths:
        potential_path = os.path.join(base_path, folder_name)
        if os.path.isdir(potential_path):
            return potential_path
    return None

def find_matching_srt_file(video_filepath: str) -> Optional[str]:
    """
    Given a full video file path, finds a matching .srt file.
    Example: /path/to/video.mkv -> /path/to/video.srt or /path/to/video.en.srt
    """
    base, _ = os.path.splitext(video_filepath)
    srt_files = glob.glob(f"{base}*.srt")
    if srt_files:
        return srt_files[0] # Return the first match
    return None

def is_hearing_impaired(filename: str) -> bool:
    """
    Checks for common Hearing Impaired tags in a subtitle filename.
    """
    fn_lower = filename.lower()
    # Check for tags like .hi.srt, .sdh.srt, .cc.srt
    hi_tags = ['.hi.', '.sdh.', '.cc.']
    return any(tag in fn_lower for tag in hi_tags)

# --- Movie Processing ---

def process_movies(radarr_url: str, radarr_api_key: str, radarr_base_paths: List[str], subdl_search_key: str, subdl_upload_token: str, language: str, processed_items: set, always_upload: bool):
    """
    Main processing loop for Radarr movies.
    """
    print("\n--- Processing Radarr Movies ---")
    movies = get_from_arr(radarr_url, radarr_api_key, "movie")
    for movie in movies:
        title = movie.get("title")
        year = movie.get("year")
        tmdb_id = movie.get("tmdbId")
        
        if not movie.get('hasFile'):
            print(f"\n-> Skipping '{title} ({year})' as it is not downloaded.")
            continue
        
        movie_key = get_item_key("movie", tmdb_id=str(tmdb_id))

        if movie_key in processed_items:
            print(f"\n-> Skipping '{title} ({year})' as it was already processed.")
            continue

        local_release_group = movie.get('movieFile', {}).get('releaseGroup')

        # --- FINAL: Check for unwanted generic release groups ---
        unwanted_groups = ["sickbeard", "radarr", "sonarr"]
        if local_release_group and local_release_group.lower() in unwanted_groups:
            print(f"\n-> Skipping '{title} ({year})' because it has a generic release group ('{local_release_group}').")
            continue
        # --- END FINAL CHECK ---

        path = movie.get("path")
        imdb_id = movie.get("imdbId")
        video_filename = movie.get('movieFile', {}).get('relativePath')
        
        if not path:
            continue
            
        print(f"\nProcessing Movie: {title} ({year})")
        if local_release_group:
             print(f"  -> Local Release Group: {local_release_group}")
        else:
            print(f"  -> WARNING: Could not determine release group for '{title}'. Will perform a general check.")

        local_path = find_local_path(path, radarr_base_paths)

        if not local_path:
            print(f"  -> Could not find local path for '{path}' in base paths: {radarr_base_paths}")
            continue

        if not video_filename:
            print("  -> Could not determine video filename from Radarr API. Skipping.")
            continue

        video_filepath = os.path.join(local_path, video_filename)
        srt_path = find_matching_srt_file(video_filepath)

        if not srt_path:
            print("  -> No matching local .srt file found for the video file.")
            continue

        print(f"  -> Found matching subtitle file: {os.path.basename(srt_path)}")
        
        is_hi = is_hearing_impaired(os.path.basename(srt_path))
        print(f"  -> Hearing Impaired detected: {is_hi}")

        print("  -> Checking for existing subtitles on SubDL...")
        existing_subs_data = search_subtitles(api_key=subdl_search_key, tmdb_id=str(tmdb_id), type="movie", languages=language)

        found_match = False
        if existing_subs_data.get("status") and existing_subs_data.get("subtitles"):
            if local_release_group:
                for subtitle in existing_subs_data["subtitles"]:
                    if any(local_release_group.lower() in r.lower() for r in subtitle.get('releases', [])):
                        print(f"  -> Found matching subtitle for release group '{local_release_group}'. Skipping.")
                        print("     --- Matching Subtitle Details ---")
                        print(json.dumps(subtitle, indent=4))
                        found_match = True
                        break
            else:
                print(f"  -> Found {len(existing_subs_data['subtitles'])} general subtitle(s). Skipping because release group is unknown.")
                found_match = True

        if found_match:
            save_processed_item(movie_key)
            processed_items.add(movie_key)
            continue

        print(f"  -> No matching subtitles found for language '{language}' and release '{local_release_group}'.")

        do_upload = False
        if always_upload:
            print(f"  -> --always-upload-movie is set. Automatically uploading subtitle for '{title}'... (Press Ctrl+C to cancel this upload)")
            try:
                pass
            except KeyboardInterrupt:
                print("\nUpload cancelled by user. Moving to next movie.")
                print("  -> Adding to processed list to avoid re-processing on next run.")
                save_processed_item(movie_key)
                processed_items.add(movie_key)
                continue
            do_upload = True
        else:
            user_input = input(f"  ?? Do you want to upload the found subtitle file for '{title}'? (Y/n): ")
            if user_input.lower() != 'n':
                do_upload = True

        if do_upload:
            if upload_single_subtitle(
                subdl_upload_token=subdl_upload_token,
                file_path=srt_path,
                media_info={
                    "type": "movie",
                    "tmdb_id": tmdb_id,
                    "imdb_id": imdb_id,
                    "name": f"{title} ({year})",
                    "lang": language.upper(),
                    "season": 0,
                    "episode": 0,
                    "is_hi": is_hi
                }
            ):
                save_processed_item(movie_key)
                processed_items.add(movie_key)


# --- TV Show Processing ---

def process_tv_shows(sonarr_url: str, sonarr_api_key: str, sonarr_base_paths: List[str], subdl_search_key: str, subdl_upload_token: str, language: str, processed_items: set, always_upload: bool):
    """
    Main processing loop for Sonarr TV shows, now episode by episode.
    """
    print("\n--- Processing Sonarr TV Shows ---")
    shows = get_from_arr(sonarr_url, sonarr_api_key, "series")

    for show in shows:
        series_title = show.get("title")
        series_id = show.get("id")

        if not show.get('statistics', {}).get('episodeFileCount', 0) > 0:
            continue
            
        series_path = show.get("path")
        imdb_id = show.get("imdbId")
        tmdb_id = show.get("tmdbId")

        local_series_path = find_local_path(series_path, sonarr_base_paths)
        if not local_series_path:
            print(f"\n>>> Could not find local path for '{series_title}' in base paths. Skipping show.")
            continue
        
        all_episode_files = get_from_arr(sonarr_url, sonarr_api_key, f"episodefile?seriesId={series_id}")
        all_episodes_metadata = get_from_arr(sonarr_url, sonarr_api_key, f"episode?seriesId={series_id}")

        if not all_episode_files:
            print(f"\n>>> Show '{series_title}' has downloaded files according to stats, but API returned no details. Skipping.")
            continue
        
        episode_map = {ep['episodeFileId']: ep for ep in all_episodes_metadata if 'episodeFileId' in ep}

        for episode_file in all_episode_files:
            episode_file_id = episode_file.get("id")
            
            release_group = episode_file.get('releaseGroup')

            unwanted_groups = ["sickbeard", "radarr", "sonarr"]
            if release_group and release_group.lower() in unwanted_groups:
                print(f"\n--- Skipping episode file with generic release group ('{release_group}'): {episode_file.get('relativePath')}")
                continue
              
            episode_info = episode_map.get(episode_file_id)

            if not episode_info:
                print(f"  -> Skipping file because it could not be mapped to an episode in Sonarr's database: {episode_file.get('relativePath')}")
                continue
            
            season_num = episode_info.get('seasonNumber')
            episode_num = episode_info.get('episodeNumber')
            episode_title = episode_info.get('title', 'Unknown Title')
            
            if season_num is None or episode_num is None:
                print(f"  -> Skipping file due to missing season/episode number in mapped data: {episode_file.get('relativePath')}")
                continue

            episode_key = get_item_key("tv", tmdb_id=str(tmdb_id), season=season_num, episode=episode_num)
            
            if episode_key in processed_items:
                continue

            print(f"\n--- Processing Episode: {series_title} - S{season_num:02d}E{episode_num:02d} - {episode_title} ---")

            relative_path = episode_file.get('relativePath')

            if not relative_path:
                print("  -> Could not determine video filename (relativePath) from the Sonarr API. Skipping episode.")
                continue

            video_filepath = os.path.join(local_series_path, relative_path)
            srt_path = find_matching_srt_file(video_filepath)

            if not srt_path:
                print("  -> No matching local .srt file found for this episode.")
                continue
            
            print(f"  -> Found matching subtitle file: {os.path.basename(srt_path)}")

            is_hi = is_hearing_impaired(os.path.basename(srt_path))
            print(f"  -> Hearing Impaired detected: {is_hi}")

            if release_group:
                print(f"  -> Local Release Group: {release_group}")
            else:
                print("  -> WARNING: Could not determine release group for this episode.")

            print("  -> Checking for existing subtitles on SubDL...")
            existing_subs_data = search_subtitles(
                api_key=subdl_search_key, 
                tmdb_id=str(tmdb_id), 
                type="tv", 
                languages=language,
                season_number=season_num,
                episode_number=episode_num
            )
            
            found_match = False
            if existing_subs_data.get("status") and existing_subs_data.get("subtitles"):
                if release_group:
                    for subtitle in existing_subs_data["subtitles"]:
                        if any(release_group.lower() in r.lower() for r in subtitle.get('releases', [])):
                            print(f"  -> Found matching subtitle for release group '{release_group}'. Skipping episode.")
                            print("     --- Matching Subtitle Details ---")
                            print(json.dumps(subtitle, indent=4))
                            found_match = True
                            break
                else:
                    print(f"  -> Found {len(existing_subs_data['subtitles'])} general subtitle(s) for this episode. Skipping because release group is unknown.")
                    found_match = True
            
            if found_match:
                save_processed_item(episode_key)
                processed_items.add(episode_key)
                continue

            print(f"  -> No matching subtitles found for language '{language}' and release '{release_group}'.")
            
            do_upload = False
            if always_upload:
                print("  -> --always-upload-tv is set. Automatically uploading.")
                do_upload = True
            else:
                user_input = input(f"  ?? Do you want to upload the found subtitle file for S{season_num:02d}E{episode_num:02d}? (Y/n): ")
                if user_input.lower() != 'n':
                    do_upload = True
            
            if do_upload:
                if upload_single_subtitle(
                    subdl_upload_token=subdl_upload_token,
                    file_path=srt_path,
                    media_info={
                        "type": "tv",
                        "tmdb_id": tmdb_id,
                        "imdb_id": imdb_id,
                        "name": f"{series_title} - S{season_num:02d}E{episode_num:02d}",
                        "lang": language.upper(),
                        "season": season_num,
                        "episode": episode_num,
                        "is_hi": is_hi
                    }
                ):
                    save_processed_item(episode_key)
                    processed_items.add(episode_key)

def upload_single_subtitle(subdl_upload_token: str, file_path: str, media_info: Dict[str, Any]) -> bool:
    """
    Handles the 3-step upload process for a single subtitle file.
    Returns True if upload was successful, False otherwise.
    """
    print(f"  -> Starting upload for: {os.path.basename(file_path)}")
    n_id = get_n_id(subdl_upload_token)
    if not n_id:
        print("     Failed to get upload session ID. Aborting upload for this file.")
        return False

    print(f"     Got session ID: {n_id}")
    file_info = upload_subtitle_file(subdl_upload_token, n_id, file_path)
    if not file_info or "file_n_id" not in file_info:
        print("     Failed to upload file. Aborting upload for this file.")
        return False
    
    file_n_id = file_info["file_n_id"]
    print(f"     File uploaded successfully. File ID: {file_n_id}")

    is_hi = media_info.get("is_hi", False)

    metadata = {
        "type": media_info["type"],
        "tmdb_id": media_info["tmdb_id"],
        "imdb_id": media_info.get("imdb_id"),
        "name": media_info["name"],
        "lang": media_info["lang"],
        "quality": "web", # Defaulting to web, can be improved
        "production_type": 0,
        "releases": json.dumps([os.path.basename(file_path).replace('.srt', '')]),
        "framerate": 0,
        "comment": "Uploaded via script",
        "season": media_info["season"],
        "ef": media_info["episode"], # ef = episode from
        "ee": media_info["episode"], # ee = episode end
        "hi": str(is_hi).lower(),
        "is_full_season": "false",
    }
    
    print("     Submitting metadata...")
    success = complete_subtitle_upload(subdl_upload_token, n_id, file_n_id, metadata)
    return success

def main():
    parser = argparse.ArgumentParser(description="Find local subtitles and upload them to SubDL.")
    # Radarr Args
    parser.add_argument("--radarr-url", required=True, help="URL for your Radarr instance.")
    parser.add_argument("--radarr-api-key", required=True, help="API key for your Radarr instance.")
    parser.add_argument("--radarr-base-paths", required=True, help="Comma-separated list of base paths where your Radarr media is stored.")
    # Sonarr Args
    parser.add_argument("--sonarr-url", required=True, help="URL for your Sonarr instance.")
    parser.add_argument("--sonarr-api-key", required=True, help="API key for your Sonarr instance.")
    parser.add_argument("--sonarr-base-paths", required=True, help="Comma-separated list of base paths where your Sonarr media is stored.")
    # SubDL Args
    parser.add_argument("--subdl-search-key", required=True, help="API key for SubDL search.")
    parser.add_argument("--subdl-upload-token", required=True, help="Authentication Token (JWT) from browser for SubDL upload.")
    parser.add_argument("--language", default="en", help="Language of the subtitles to search for and upload (e.g., 'en', 'es').")
    # New Control Args
    parser.add_argument("--always-upload-tv", action="store_true", help="Automatically answer 'yes' to all TV show upload prompts.")
    parser.add_argument("--always-upload-movie", action="store_true", help="Automatically upload subtitles for movies without prompting.")

    args = parser.parse_args()

    radarr_base_paths = [p.strip() for p in args.radarr_base_paths.split(',')]
    sonarr_base_paths = [p.strip() for p in args.sonarr_base_paths.split(',')]

    processed_items = load_processed_list()
    print(f"Loaded {len(processed_items)} previously processed items.")

    process_movies(args.radarr_url, args.radarr_api_key, radarr_base_paths, args.subdl_search_key, args.subdl_upload_token, args.language, processed_items, args.always_upload_movie)
    process_tv_shows(args.sonarr_url, args.sonarr_api_key, sonarr_base_paths, args.subdl_search_key, args.subdl_upload_token, args.language, processed_items, args.always_upload_tv)

if __name__ == "__main__":
    main()
