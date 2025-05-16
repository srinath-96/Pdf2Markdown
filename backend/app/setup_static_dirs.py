import os
import stat

def setup_static_directories():
    # Get the absolute path to the app directory
    app_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define paths
    static_dir = os.path.join(app_dir, "static")
    images_dir = os.path.join(static_dir, "images")
    markdown_dir = os.path.join(static_dir, "markdown_outputs")
    
    # Create directories if they don't exist
    for directory in [static_dir, images_dir, markdown_dir]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
        
        # Set permissions (rwxrwxr-x)
        os.chmod(directory, stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)
        print(f"Set permissions for: {directory}")
    
    # Verify directories exist and are writable
    for directory in [static_dir, images_dir, markdown_dir]:
        if not os.path.exists(directory):
            print(f"Error: Directory does not exist: {directory}")
            continue
            
        if not os.access(directory, os.W_OK):
            print(f"Error: Directory is not writable: {directory}")
            continue
            
        print(f"Verified directory: {directory} (exists and writable)")

if __name__ == "__main__":
    setup_static_directories() 