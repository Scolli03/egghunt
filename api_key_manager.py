import json
from itertools import cycle

class APIKeyManager:
    def __init__(self, keys_file):
        """
        Initialize the APIKeyManager with a JSON file containing faction IDs and their API keys.
        :param keys_file: Path to the JSON file with faction IDs and keys.
        """
        self.keys_file = keys_file
        self.faction_keys = {}
        self.key_cycles = {}

        # Load the keys from the file
        self._load_keys()

    def _load_keys(self):
        """
        Load faction IDs and API keys from the JSON file.
        """
        try:
            with open(self.keys_file, "r") as f:
                self.faction_keys = json.load(f)
            
            # Create a cycle iterator for each faction's keys
            for faction_id, data in self.faction_keys.items():
                self.key_cycles[faction_id] = cycle(data["keys"])
        except Exception as e:
            print(f"[ERROR] Failed to load API keys: {e}")

    def get_next_key(self, faction_id):
        """
        Get the next API key for a given faction ID.
        :param faction_id: The faction ID for which to retrieve the next API key.
        :return: The next API key as a string.
        """
        if faction_id not in self.key_cycles:
            raise ValueError(f"Faction ID {faction_id} not found in the keys file.")
        return next(self.key_cycles[faction_id])