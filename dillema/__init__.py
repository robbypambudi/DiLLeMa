import subprocess

def get_git_version():
    try:
        # Get the latest Git tag (version)
        version = subprocess.check_output(["git", "describe", "--tags", "--always"]).strip().decode("utf-8")
        return version
    except subprocess.CalledProcessError:
        # If Git is not available, return a default version
        return "v0.1.0+unknown"
    
__version__ = get_git_version()
