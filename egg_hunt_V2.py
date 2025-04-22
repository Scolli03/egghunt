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
def fetch_personal_stats_worker(faction_id, faction_name):
    """
    Worker function to fetch personal stats for a user.
    :param faction_id: The ID of the faction the user belongs to.
    :param faction_name: The name of the faction the user belongs to.
    """
    while not member_queue.empty():
        member_id = member_queue.get()
        api_key = key_manager.get_next_key(faction_id)
        url = f"{BASE_URL}/user/{member_id}/profile"
        params = {"key": api_key}
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                stats = response.json()
                stats["faction_name"] = faction_name  # Add faction name to the stats
                with results_lock:
                    all_personal_stats[member_id] = stats
                print(f"[INFO] Fetched stats for member {member_id} from faction {faction_name}.")
            else:
                print(f"[ERROR] Failed to fetch data for user {member_id}: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Error fetching data for user {member_id}: {e}")
        finally:
            member_queue.task_done()
        time.sleep(0.6)  # Respect API rate limit (100 calls per minute)

# Main function to fetch data for all factions
def fetch_all_factions():
    """
    Fetch data for all factions and their members.
    """
    with open("faction_keys.json", "r") as f:
        factions = json.load(f)

    for faction_id, faction_data in factions.items():
        faction_name = faction_data["faction_name"]
        print(f"[INFO] Processing faction: {faction_name} (ID: {faction_id})")

        # Fetch faction members
        members = fetch_faction_members(faction_id)
        for member_id in members.keys():
            member_queue.put(member_id)

        # Create and start threads for fetching personal stats
        print(f"[INFO] Starting threads to fetch personal stats for faction {faction_name}...")
        num_threads = 14  # Adjust based on your system and API limits
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=fetch_personal_stats_worker, args=(faction_id, faction_name))
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

# New functionality: Extract Easter Egg Hunt scores and save to CSV
def extract_easter_egg_hunt_scores(input_file, output_csv):
    print("[INFO] Extracting and sorting Easter Egg Hunt scores...")
    try:
        with open(input_file, "r") as f:
            data = json.load(f)
        
        # Prepare data for CSV and Discord table
        csv_data = [["User ID", "Name", "Faction", "Easter Egg Hunt Score", "Total"]]
        discord_table = "| User ID | Name            | Faction               | Easter Egg Hunt Score | Total |\n"
        discord_table += "|---------|-----------------|-----------------------|-----------------------|-------|\n"

        # Collect and sort data by score in descending order
        sorted_data = []
        for user_id, user_data in data.items():
            name = user_data.get("name", "Unknown")
            faction_name = user_data.get("faction_name", "Unknown")
            competition = user_data.get("competition", {})
            
            if competition.get("name") == "Easter Egg Hunt":
                score = competition.get("score", 0)
                total = competition.get("total", 0)
                sorted_data.append((user_id, name, faction_name, score, total))
        
        # Sort the data by score (index 3) in descending order
        sorted_data.sort(key=lambda x: x[3], reverse=True)

        # Add sorted data to CSV and Discord table
        for user_id, name, faction_name, score, total in sorted_data:
            csv_data.append([user_id, name, faction_name, score, total])
            discord_table += f"| {user_id:<7} | {name:<15} | {faction_name:<21} | {score:<21} | {total:<5} |\n"

        # Write to CSV file
        with open(output_csv, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_data)

        print("[INFO] Easter Egg Hunt scores extracted and sorted successfully.")
        print("[INFO] Discord Table:\n")
        print(discord_table)

    except Exception as e:
        print(f"[ERROR] Failed to extract and sort Easter Egg Hunt scores: {e}")

# Fetch data for all factions
fetch_all_factions()

# Extract scores and save to CSV
extract_easter_egg_hunt_scores(output_file, "easter_egg_hunt_scores.csv")

