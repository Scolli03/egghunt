import requests
import json
import csv
from datetime import datetime
from dotenv import load_dotenv
import os
import threading
import time
from queue import Queue
from api_key_manager import APIKeyManager  # Import the APIKeyManager

# Load environment variables from a .env file
load_dotenv()

# Base URL for Torn API
BASE_URL = "https://api.torn.com/v2"

# Output file name
output_file = f"user_profile_data.json"

# Initialize the APIKeyManager with the JSON file
key_manager = APIKeyManager("faction_keys.json")

# Thread-safe queue for member IDs
member_queue = Queue()
results_lock = threading.Lock()
all_personal_stats = {}

# Function to fetch faction members
def fetch_faction_members(faction_id):
    """
    Fetch members of a faction using the Torn API.
    :param faction_id: The ID of the faction to fetch members for.
    :return: A dictionary of member IDs and their names.
    """
    print(f"[INFO] Fetching faction members for faction {faction_id}...")
    api_key = key_manager.get_next_key(faction_id)
    url = f"{BASE_URL}/faction/{faction_id}/members"
    params = {"key": api_key}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if "members" in data:
            print(f"[INFO] Faction members fetched successfully for faction {faction_id}.")
            return {str(member["id"]): member.get("name", "Unknown") for member in data["members"]}
        else:
            print(f"[ERROR] Failed to retrieve faction members for faction {faction_id}.")
            return {}
    else:
        print(f"[ERROR] Failed to fetch faction members for faction {faction_id}: {response.status_code}")
        return {}

# Function to fetch personal stats for a user (thread worker)
def fetch_personal_stats_worker(faction_id, faction_name, members):
    """
    Worker function to fetch personal stats for a user.
    :param faction_id: The ID of the faction the user belongs to.
    :param faction_name: The name of the faction the user belongs to.
    :param members: A dictionary mapping member IDs to their names.
    """
    while not member_queue.empty():
        member_id = member_queue.get()
        api_key = key_manager.get_next_key(faction_id)
        base_url = f"{BASE_URL}/user/{member_id}/personalstats"
        try:
            # Get the timestamp for January 1st of the current year
            current_year = datetime.now().year
            jan_1_timestamp = int(datetime(current_year, 1, 1).timestamp())

            # Fetch stats with the timestamp (previous year's total)
            params_with_timestamp = {"key": api_key, "stat": "eastereggsfound", "timestamp": jan_1_timestamp}
            response_with_timestamp = requests.get(base_url, params=params_with_timestamp)
            if response_with_timestamp.status_code == 200:
                response_data = response_with_timestamp.json()
                if "error" in response_data and response_data["error"]["code"] == 5:
                    # Too many requests error
                    retry_after = 60  # Default retry time
                    print(f"[WARNING] Too many requests for user {member_id}. Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    member_queue.put(member_id)  # Requeue the member for retry
                    continue
                personalstats = response_data.get("personalstats", [])
                previous_total = next((stat["value"] for stat in personalstats if stat["name"] == "eastereggsfound"), 0)
            else:
                print(f"[ERROR] Failed to fetch previous total for user {member_id}: {response_with_timestamp.status_code}")
                previous_total = 0

            # Fetch stats without the timestamp (current total)
            params_without_timestamp = {"key": api_key, "stat": "eastereggsfound"}
            response_without_timestamp = requests.get(base_url, params=params_without_timestamp)
            if response_without_timestamp.status_code == 200:
                response_data = response_without_timestamp.json()
                if "error" in response_data and response_data["error"]["code"] == 5:
                    # Too many requests error
                    retry_after = 60  # Default retry time
                    print(f"[WARNING] Too many requests for user {member_id}. Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    member_queue.put(member_id)  # Requeue the member for retry
                    continue
                current_total = response_data.get("personalstats", {}).get("items", {}).get("found", {}).get("easter_eggs", 0)
            else:
                print(f"[ERROR] Failed to fetch current total for user {member_id}: {response_without_timestamp.status_code}")
                current_total = 0

            # Calculate the current year's value
            current_year_value = max(0, current_total - previous_total)  # Ensure no negative values

            # Store the result
            with results_lock:
                all_personal_stats[member_id] = {
                    "name": members.get(member_id, "Unknown"),  # Member name
                    "faction_name": faction_name,
                    "current_year_value": current_year_value,
                    "all_time_total": current_total,
                }
            print(f"[INFO] Fetched stats for member {member_id} from faction {faction_name}: Current Year: {current_year_value}, All Time: {current_total}")

        except Exception as e:
            print(f"[ERROR] Error fetching data for user {member_id}: {e}")
        finally:
            member_queue.task_done()
        time.sleep(1.5)  # Default sleep time to avoid hitting the rate limit

# Main function to fetch data for all factions
def fetch_all_factions(process_all=True, max_members=10):
    """
    Fetch data for all factions and their members.
    :param process_all: If True, process all factions and members. If False, process only the first faction and first `max_members` members.
    :param max_members: The maximum number of members to process per faction when `process_all` is False.
    """
    with open("faction_keys.json", "r") as f:
        factions = json.load(f)

    # Limit to the first faction if not processing all
    factions_to_process = factions.items() if process_all else [next(iter(factions.items()))]

    for faction_id, faction_data in factions_to_process:
        faction_name = faction_data["faction_name"]
        print(f"[INFO] Processing faction: {faction_name} (ID: {faction_id})")

        # Fetch faction members
        members = fetch_faction_members(faction_id)
        member_ids = list(members.keys())

        # Limit to the first `max_members` if not processing all
        if not process_all:
            member_ids = member_ids[:max_members]

        for member_id in member_ids:
            member_queue.put(member_id)

        # Create and start threads for fetching personal stats
        print(f"[INFO] Starting threads to fetch personal stats for faction {faction_name}...")
        num_threads = 14  # Adjust based on your system and API limits
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=fetch_personal_stats_worker, args=(faction_id, faction_name, members))
            thread.start()
            threads.append(thread)

        # Wait for all threads to finish
        for thread in threads:
            thread.join()

        print(f"[INFO] Finished processing faction: {faction_name} (ID: {faction_id})")

    # Save the new stats to a JSON file
    with open(output_file, "w") as f:
        json.dump(all_personal_stats, f, indent=4)

    print(f"[INFO] Data saved to {output_file}")

# New functionality: Extract Easter Egg Hunt scores and save to separate CSV files for each faction
def extract_easter_egg_hunt_scores(input_file, output_dir):
    """
    Extract Easter Egg Hunt scores and save to separate CSV files for each faction.
    :param input_file: The JSON file containing user data.
    :param output_dir: The directory where faction-specific CSV files will be saved.
    """
    print("[INFO] Extracting and sorting Easter Egg Hunt scores...")
    try:
        with open(input_file, "r") as f:
            data = json.load(f)

        # Prepare data grouped by faction
        faction_data = {}

        # Collect and group data by faction
        for user_id, user_data in data.items():
            name = user_data.get("name", "Unknown")
            faction_name = user_data.get("faction_name", "Unknown")
            current_year_value = user_data.get("current_year_value", 0)
            all_time_total = user_data.get("all_time_total", 0)

            if faction_name not in faction_data:
                faction_data[faction_name] = []

            faction_data[faction_name].append((user_id, name, faction_name, current_year_value, all_time_total))

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Process each faction's data
        for faction_name, users in faction_data.items():
            # Sort the data by current year value (index 3) in descending order
            users.sort(key=lambda x: x[3], reverse=True)

            # Prepare CSV data and Discord table
            csv_data = [["User ID", "Name", "Faction", "Current Year Value", "All Time Total"]]
            discord_table = "| User ID | Name            | Faction               | Current Year Value | All Time Total |\n"
            discord_table += "|---------|-----------------|-----------------------|--------------------|----------------|\n"

            for user_id, name, faction_name, current_year_value, all_time_total in users:
                csv_data.append([user_id, name, faction_name, current_year_value, all_time_total])
                discord_table += f"| {user_id:<7} | {name:<15} | {faction_name:<21} | {current_year_value:<18} | {all_time_total:<14} |\n"

            # Write to faction-specific CSV file
            faction_csv_file = os.path.join(output_dir, f"{faction_name.replace(' ', '_')}_scores.csv")
            with open(faction_csv_file, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerows(csv_data)

            print(f"[INFO] Scores for faction '{faction_name}' saved to {faction_csv_file}.")
            print(f"[INFO] Discord Table for faction '{faction_name}':\n")
            print(discord_table)

    except Exception as e:
        print(f"[ERROR] Failed to extract and sort Easter Egg Hunt scores: {e}")

# Fetch data for all factions
fetch_all_factions()

# Extract scores and save to separate CSV files for each faction
extract_easter_egg_hunt_scores(output_file, "faction_scores")

