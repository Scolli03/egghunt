import requests
import json
import csv
from datetime import datetime
from dotenv import load_dotenv
import os
import threading
import time
from queue import Queue

# Load environment variables from a .env file
load_dotenv()

# Get the Torn API key from the .env file
API_KEY = os.getenv("APIKEY")
BASE_URL = "https://api.torn.com/v2"

# Generate a unique filename with a timestamp for the final stats
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = f"faction_personalstats_{timestamp}.json"

# Function to fetch faction members
def fetch_faction_members():
    print("[INFO] Fetching faction members...")
    url = f"{BASE_URL}/faction/members"
    params = {"key": API_KEY}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if "members" in data:
            print("[INFO] Faction members fetched successfully.")
            # Save to JSON file
            with open("members.json", "w") as f:
                json.dump(data, f, indent=4)
            return {str(member["id"]): member.get("name", "Unknown") for member in data["members"]}
        else:
            print("[ERROR] Failed to retrieve faction members.")
            return {}
    else:
        print(f"[ERROR] Failed to fetch faction members: {response.status_code}")
        return {}

# Thread-safe queue for member IDs
member_queue = Queue()
results_lock = threading.Lock()
all_personal_stats = {}

# Function to fetch personal stats for a user (thread worker)
def fetch_personal_stats_worker():
    while not member_queue.empty():
        member_id = member_queue.get()
        url = f"{BASE_URL}/user/{member_id}/personalstats"
        params = {"key": API_KEY, "cat": "all"}
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                stats = response.json()
                with results_lock:
                    all_personal_stats[member_id] = stats
                print(f"[INFO] Fetched stats for member {member_id}.")
            else:
                print(f"[ERROR] Failed to fetch data for user {member_id}: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Error fetching data for user {member_id}: {e}")
        finally:
            member_queue.task_done()
        time.sleep(0.6)  # Respect API rate limit (100 calls per minute)

# Fetch faction members only if members.json doesn't already exist
if not os.path.exists("members.json"):
    member_names = fetch_faction_members()
else:
    print("[INFO] members.json already exists. Loading faction members from file...")
    with open("members.json", "r") as f:
        data = json.load(f)
        member_names = {str(member["id"]): member.get("name", "Unknown") for member in data.get("members", [])}

# Add member IDs to the queue
print("[INFO] Adding member IDs to the queue...")
for member_id in member_names.keys():
    member_queue.put(member_id)

# Create and start threads
print("[INFO] Starting threads to fetch personal stats...")
num_threads = 14  # Adjust based on your system and API limits
threads = []
for _ in range(num_threads):
    thread = threading.Thread(target=fetch_personal_stats_worker)
    thread.start()
    threads.append(thread)

# Wait for all threads to finish
for thread in threads:
    thread.join()

print("[INFO] All threads have finished fetching personal stats.")

# Save the new stats to a JSON file
with open(output_file, "w") as f:
    json.dump(all_personal_stats, f, indent=4)

print(f"[INFO] Data saved to {output_file}")

# Load the original and new data
print("[INFO] Loading original and new data...")
with open("faction_personalstats_OG.json", "r") as file:
    original_data = json.load(file)

with open(output_file, "r") as file:
    new_data = json.load(file)

# Calculate the difference in easter eggs found for each member
print("[INFO] Calculating differences in easter eggs found...")
egg_differences = []

for member_id, original_stats in original_data.items():
    original_eggs = original_stats.get("personalstats", {}).get("items", {}).get("found", {}).get("easter_eggs", 0)
    new_eggs = new_data.get(member_id, {}).get("personalstats", {}).get("items", {}).get("found", {}).get("easter_eggs", 0)
    difference = new_eggs - original_eggs
    member_name = member_names.get(member_id, "Unknown")
    egg_differences.append((member_name, difference))

# Sort the results from most found to least found
sorted_egg_differences = sorted(egg_differences, key=lambda x: x[1], reverse=True)

# Save the results to a CSV file
print("[INFO] Saving results to CSV file...")
with open("egg_hunt_results.csv", "w", newline="") as csvfile:
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(["Member Name", "Eggs Found This Year"])  # Header row
    csvwriter.writerows(sorted_egg_differences)  # Data rows

print("[INFO] Results saved to egg_hunt_results.csv")

# Print the results formatted for Discord
print("[INFO] Printing results formatted for Discord...")
print("```")
print("Egg Hunt Results:")
print("Member Name                | Eggs Found This Year")
print("-----------------------------------------------")
for member_name, difference in sorted_egg_differences:
    print(f"{member_name:<25} | {difference}")
print("```")
print("[INFO] Script execution completed.")