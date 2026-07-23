from dotenv import load_dotenv
import os
import sys
from pathlib import Path

def load_environment(verbose=True):
    """Load environment variables from .env files with proper fallbacks"""
    
    # Try multiple env file possibilities (in order of priority)
    env_files = [
        '.env.local',  # Local development overrides
        '.env',        # Default configuration
    ]
    
    # Track which file was loaded
    loaded_file = None
    
    # Try to load from any available env file
    for env_file in env_files:
        if Path(env_file).is_file():
            load_dotenv(env_file)
            loaded_file = env_file
            break
    
    # Check for required variables
    required_vars = [
        'MISTRAL_API_KEY',
        'CEREBRAS_API_KEY', 
        'COHERE_API_KEY',
        'REDIS_URL',
        'MONGODB_URL'
    ]
    
    # Log status if verbose
    if verbose:
        if loaded_file:
            print(f"Environment loaded from: {loaded_file}")
        else:
            print(f"Warning: No environment file found. Checking for variables in system environment.")
    
    # Check for missing variables
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing and verbose:
        print(f"Warning: Missing required environment variables: {', '.join(missing)}")
        
    return loaded_file, missing