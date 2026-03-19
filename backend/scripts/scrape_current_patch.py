import argparse
import os
import re
import sys
from pathlib import Path

# Add project root to sys path to import other scripts from backend/scripts
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from fetch_riot_patch import default_url_for_version
import requests

def get_latest_version(data_dir: Path) -> str:
    """Finds the highest patch version parsed in the given raw data directory."""
    highest_major = 0
    highest_minor = 0
    
    if not data_dir.exists():
        return "26.4" # default fallback
        
    for p in data_dir.glob("*.json"):
        match = re.search(r"(\d+)\.(\d+)\.json", p.name)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            
            if major > highest_major or (major == highest_major and minor > highest_minor):
                highest_major = major
                highest_minor = minor
                
    if highest_major == 0 and highest_minor == 0:
        return "26.4"
        
    return f"{highest_major}.{highest_minor}"

def get_next_version(current_version: str) -> str:
    """Calculates the next theoretical patch version.
    
    Assumes standard Riot patch numbering where a season usually has 24 patches.
    If it hits 24, increment the major and reset minor to 1.
    """
    parts = current_version.split(".")
    major = int(parts[0])
    minor = int(parts[1])
    
    if minor >= 24:
        major += 1
        minor = 1
    else:
        minor += 1
        
    return f"{major}.{minor}"

def check_patch_exists(version: str) -> str:
    """Attempts to fetch the possible URLs. Returns the successful URL if 200 OK, empty string otherwise."""
    slug = version.replace(".", "-")
    patterns = [
        f"https://www.leagueoflegends.com/en-us/news/game-updates/patch-{slug}-notes/",
        f"https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-{slug}-notes/"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for url in patterns:
        print(f"Checking if {url} exists...")
        try:
            # Try HEAD first
            response = requests.head(url, headers=headers, timeout=10)
            
            # Fall back to GET if HEAD is disallowed or blocked (e.g. 403, 405)
            if response.status_code != 200:
                response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                print(f"Success! Found notes at: {url}")
                return url
            else:
                print(f"URL returned status code {response.status_code}")
                
        except Exception as e:
            print(f"Error checking url {url}: {e}")
            
    return ""
        
def main():
    parser = argparse.ArgumentParser(description="Checks for the next patch and automatically parses it if available.")
    parser.add_argument("--use-llm-fallback", action="store_true", help="If passed, will use the LLM to process ambiguous lines.")
    args = parser.parse_args()
    
    raw_data_dir = Path("data/raw")
    latest_version = get_latest_version(raw_data_dir)
    next_version = get_next_version(latest_version)
    
    print(f"Latest local version detected: {latest_version}")
    print(f"Expected next patch version: {next_version}")
    
    found_url = check_patch_exists(next_version)
    if not found_url:
        print(f"Patch {next_version} notes do not appear to be live yet at known locations.")
        print("Exiting gracefully. The GitHub Action will simply finish with no changes.")
        sys.exit(0)
        
    print(f"Patch {next_version} is LIVE! Triggering auto-import...")
    
    # We use os.system since we want to share stdout and handle the script nicely
    cmd = f"python scripts/auto_import_patch.py --version {next_version} --url \"{found_url}\" --replace-entities --skip-ingest"
    
    if args.use_llm_fallback:
        cmd += " --use-llm-fallback"
        
    print(f"Running command: {cmd}")
    result = os.system(cmd)
    
    if result != 0:
        print(f"Error: auto_import_patch.py failed with exit code {result}")
        sys.exit(1)
        
    print(f"Successfully scraped patch {next_version}!")
    
if __name__ == "__main__":
    main()
